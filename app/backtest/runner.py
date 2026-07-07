from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.backtest.batch_engine import simulate_many_configs_normal_core_summary, simulate_many_configs_with_entries_summary
from app.backtest.config import (
    DENSE_MIN_TEST_WIN_RATE,
    DENSE_MIN_TEST_TRADES_PER_DAY,
    DENSE_MIN_TRADES_PER_DAY,
    DENSE_MIN_WIN_RATE,
    DENSE_TIMEFRAMES,
    FEE_PER_SIDE,
    NORMAL_TIMEFRAMES,
    TEST_START,
    dense_grid_for_timeframe,
    normal_grid_for_timeframe,
    result_columns_for_params,
)
from app.backtest.data_loader import load_ohlc
from app.backtest.engine import calendar_days_ns
from app.backtest.grid import build_config_grid
from app.backtest.result_builder import batch_to_dense_rows, batch_to_normal_rows
from app.backtest.signals import build_indicator_context, iter_signal_variants, side_mode_arrays


@dataclass
class SearchDiagnostics:
    load_data_sec: float = 0.0
    indicator_sec: float = 0.0
    signal_build_sec: float = 0.0
    simulate_sec: float = 0.0
    row_build_sec: float = 0.0
    total_runtime_sec: float = 0.0
    variants_generated: int = 0
    variants_skipped_low_signal: int = 0
    side_modes_scanned: int = 0
    kernel_calls: int = 0
    configs_tested: int = 0
    rows_kept: int = 0
    kernel_used: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "load_data_sec": round(self.load_data_sec, 4),
            "indicator_sec": round(self.indicator_sec, 4),
            "signal_build_sec": round(self.signal_build_sec, 4),
            "simulate_sec": round(self.simulate_sec, 4),
            "row_build_sec": round(self.row_build_sec, 4),
            "total_runtime_sec": round(self.total_runtime_sec, 4),
            "variants_generated": self.variants_generated,
            "variants_skipped_low_signal": self.variants_skipped_low_signal,
            "side_modes_scanned": self.side_modes_scanned,
            "kernel_calls": self.kernel_calls,
            "configs_tested": self.configs_tested,
            "rows_kept": self.rows_kept,
            "kernel_used": self.kernel_used,
        }


def _filter_value(filters: dict[str, Any], key: str, default: Any, timeframe: str | None = None) -> Any:
    value = filters.get(key, default)
    if timeframe is not None and isinstance(value, dict):
        return value.get(timeframe, default.get(timeframe) if isinstance(default, dict) else default)
    return value


def _grid(default_grid: tuple[list[float], list[float], list[int]], filters: dict[str, Any]) -> tuple[list[float], list[float], list[int]]:
    sl_values, tp_values, max_holds = default_grid
    return (
        list(filters.get("sl_values", sl_values)),
        list(filters.get("tp_values", tp_values)),
        list(filters.get("max_holds", max_holds)),
    )


def _normal_core_kernel_enabled(mode: str, search_params: dict[str, Any]) -> bool:
    entry_mode = search_params.get("entry_mode", "same_open")
    return (
        mode == "normal"
        and entry_mode in {"same_open", "default", None, ""}
        and not bool(search_params.get("use_spread_slippage", False))
        and not bool(search_params.get("use_position_sizing", False))
        and not bool(search_params.get("use_leverage", False))
        and not bool(search_params.get("use_liquidation", False))
        and not bool(search_params.get("compute_ambiguity_metrics", False))
    )


def _sort_cols_for_mode(mode: str) -> list[str]:
    if mode == "dense_high_winrate":
        return ["score", "test_total_return", "test_profit_factor"]
    return ["score", "test_profit_factor", "test_total_return"]


def _feature_flags(search_params: dict[str, Any]) -> dict[str, bool]:
    use_position_sizing = bool(search_params.get("use_position_sizing", False))
    use_leverage = bool(search_params.get("use_leverage", False))
    use_liquidation = bool(search_params.get("use_liquidation", False))
    return {
        "include_rr_metrics": bool(search_params.get("use_rr_metrics", False)),
        "include_ambiguity_metrics": bool(search_params.get("compute_ambiguity_metrics", False)),
        "include_equity_metrics": use_position_sizing or use_leverage or use_liquidation,
        "include_liquidation_metrics": use_liquidation,
    }


def _result_frame(
    rows: list[dict[str, Any]],
    sort_cols: list[str] | None = None,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    columns = columns or result_columns_for_params({})
    if not rows:
        return pd.DataFrame(columns=columns)
    df = pd.DataFrame(rows)
    for column in columns:
        if column not in df.columns:
            df[column] = np.nan
    df = df[[column for column in columns if column in df.columns]]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return df


def _item_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item[key]
    return getattr(item, key)


def _row_matches_filter(row: dict[str, Any], item: Any) -> bool:
    field = _item_value(item, "field")
    op = _item_value(item, "op")
    value = _item_value(item, "value")
    if field not in row:
        return False
    raw = row[field]
    if op == "~":
        return str(value).lower() in str(raw).lower()
    if op == "=" and isinstance(raw, str):
        return raw == str(value)
    try:
        lhs = float(raw)
        rhs = float(value)
    except (TypeError, ValueError):
        if op == "=":
            return str(raw) == str(value)
        return False
    if np.isnan(lhs):
        return False
    if op == ">":
        return lhs > rhs
    if op == ">=":
        return lhs >= rhs
    if op == "<":
        return lhs < rhs
    if op == "<=":
        return lhs <= rhs
    if op == "=":
        return lhs == rhs
    return False


def _row_matches_filters(row: dict[str, Any], filters: list[Any] | tuple[Any, ...] | None) -> bool:
    return all(_row_matches_filter(row, item) for item in (filters or []))


def _exact_filter_values(filters: list[Any] | tuple[Any, ...] | None, field: str) -> set[str] | None:
    values = {
        str(_item_value(item, "value"))
        for item in (filters or [])
        if _item_value(item, "field") == field and _item_value(item, "op") == "="
    }
    return values or None


def _trim_rows(rows: list[dict[str, Any]], mode: str, limit: int, columns: list[str]) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return rows
    df = _result_frame(rows, _sort_cols_for_mode(mode), columns)
    return df.head(limit).to_dict(orient="records")


def _iter_timeframe_rows(
    timeframe: str,
    mode: str,
    strategies: list[str] | set[str] | None = None,
    search_params: dict[str, Any] | None = None,
    result_filters: list[Any] | tuple[Any, ...] | None = None,
    diagnostics: SearchDiagnostics | None = None,
):
    search_params = search_params or {}
    load_t0 = time.perf_counter()
    df = load_ohlc(timeframe)
    if diagnostics is not None:
        diagnostics.load_data_sec += time.perf_counter() - load_t0

    open_ = df["open"].to_numpy(np.float64)
    high = df["high"].to_numpy(np.float64)
    low = df["low"].to_numpy(np.float64)
    close = df["close"].to_numpy(np.float64)
    index_ns = df.index.astype("datetime64[ns]").asi8.astype(np.int64, copy=False)
    test_start_idx = int(np.searchsorted(df.index.to_numpy(), np.datetime64(TEST_START), side="left"))
    is_test_exit = index_ns >= np.datetime64(TEST_START).astype("datetime64[ns]").astype(np.int64)
    days = calendar_days_ns(index_ns)
    test_days = calendar_days_ns(index_ns, is_test_exit)

    strategy_params = search_params.get("strategy_params", {})
    max_signal_variants = search_params.get("max_signal_variants")
    max_signal_variants = int(max_signal_variants) if max_signal_variants is not None else None

    if mode == "normal":
        grid_profile = search_params.get("grid_profile", "normal")
        default_grid = dense_grid_for_timeframe(timeframe) if grid_profile == "dense" else normal_grid_for_timeframe(timeframe)
        sl_values, tp_values, max_holds = _grid(default_grid, search_params)
        min_full_trades = int(np.ceil(days * search_params.get("min_trades_per_day", 0.33)))
        min_test_trades = int(np.ceil(test_days * search_params.get("min_test_trades_per_day", 0.33)))
        explicit_min_full = _filter_value(search_params, "min_full_trades", None, timeframe)
        explicit_min_test = _filter_value(search_params, "min_test_trades", None, timeframe)
        if explicit_min_full is not None:
            min_full_trades = int(explicit_min_full)
        if explicit_min_test is not None:
            min_test_trades = int(explicit_min_test)
        row_builder = "normal"
        min_test_win_rate = search_params.get("min_test_win_rate", 48)
        min_profit_factor = search_params.get("min_profit_factor", 1.05)
        min_test_profit_factor = search_params.get("min_test_profit_factor", 1.0)
    elif mode == "dense_high_winrate":
        sl_values, tp_values, max_holds = _grid(dense_grid_for_timeframe(timeframe), search_params)
        min_full_trades = int(np.ceil(days * search_params.get("min_trades_per_day", DENSE_MIN_TRADES_PER_DAY)))
        min_test_trades = int(np.ceil(test_days * search_params.get("min_test_trades_per_day", DENSE_MIN_TEST_TRADES_PER_DAY)))
        row_builder = "dense"
        min_win_rate = search_params.get("min_win_rate", DENSE_MIN_WIN_RATE)
        min_test_win_rate = search_params.get("min_test_win_rate", DENSE_MIN_TEST_WIN_RATE)
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    use_normal_core = _normal_core_kernel_enabled(mode, search_params)
    if diagnostics is not None:
        kernel_name = "normal_core" if use_normal_core else "realistic"
        if diagnostics.kernel_used:
            if diagnostics.kernel_used != kernel_name:
                diagnostics.kernel_used = "mixed"
        else:
            diagnostics.kernel_used = kernel_name

    sl_arr, tp_arr, mh_arr = build_config_grid(sl_values, tp_values, max_holds)
    if mode == "normal":
        valid_cost_mask = tp_arr > 2.5 * FEE_PER_SIDE
        sl_arr = sl_arr[valid_cost_mask]
        tp_arr = tp_arr[valid_cost_mask]
        mh_arr = mh_arr[valid_cost_mask]
    if len(sl_arr) == 0:
        return

    entry_next_open = search_params.get("entry_mode", "same_open") == "next_open"
    use_spread_slippage = search_params.get("use_spread_slippage", False)
    spread_pct_val = search_params.get("spread_pct", 0.0) if use_spread_slippage else 0.0
    slippage_pct_val = search_params.get("slippage_pct", 0.0) if use_spread_slippage else 0.0
    use_position_sizing = search_params.get("use_position_sizing", False)
    risk_per_trade_pct = search_params.get("risk_per_trade_pct", 1.0)
    use_leverage = search_params.get("use_leverage", False)
    leverage_val = search_params.get("leverage", 1.0)
    use_liquidation = search_params.get("use_liquidation", False)
    maintenance_margin_pct = search_params.get("maintenance_margin_pct", 0.5)
    compute_ambiguity_metrics = search_params.get("compute_ambiguity_metrics", False)
    feature_flags = _feature_flags(search_params)

    indicator_context = None
    if mode == "normal":
        indicator_t0 = time.perf_counter()
        indicator_context = build_indicator_context(df)
        if diagnostics is not None:
            diagnostics.indicator_sec += time.perf_counter() - indicator_t0

    exact_side_modes = _exact_filter_values(result_filters, "side_mode") if mode == "normal" else None

    signal_iter = iter_signal_variants(
        df=df,
        timeframe=timeframe,
        mode=mode,
        strategies=strategies,
        strategy_params=strategy_params,
        max_signal_variants=max_signal_variants,
        indicator_context=indicator_context,
    )
    while True:
        signal_t0 = time.perf_counter()
        try:
            signal = next(signal_iter)
        except StopIteration:
            if diagnostics is not None:
                diagnostics.signal_build_sec += time.perf_counter() - signal_t0
            break
        if diagnostics is not None:
            diagnostics.signal_build_sec += time.perf_counter() - signal_t0
            diagnostics.variants_generated += 1
        if signal.long_entries.sum() + signal.short_entries.sum() < min_full_trades:
            if diagnostics is not None:
                diagnostics.variants_skipped_low_signal += 1
            continue
        for side_mode in signal.side_modes:
            if exact_side_modes is not None and side_mode not in exact_side_modes:
                continue
            longs, shorts = side_mode_arrays(signal.long_entries, signal.short_entries, side_mode)
            if longs.sum() + shorts.sum() < min_full_trades:
                if diagnostics is not None:
                    diagnostics.variants_skipped_low_signal += 1
                continue
            if diagnostics is not None:
                diagnostics.side_modes_scanned += 1
                diagnostics.kernel_calls += 1
                diagnostics.configs_tested += len(sl_arr)
            simulate_t0 = time.perf_counter()
            if use_normal_core:
                (
                    tr_arr, wr_arr, tre_arr, pf_arr, exp_arr, mdd_arr, aw_arr, al_arr,
                    tpd_arr, mgd_arr, abh_arr,
                    ttr_arr, twr_arr, tre2_arr, tpf2_arr, texp_arr,
                    ttpd_arr, tmgd_arr, tabh_arr,
                ) = simulate_many_configs_normal_core_summary(
                    open_, high, low, close, longs, shorts,
                    sl_arr, tp_arr, mh_arr, FEE_PER_SIDE,
                    test_start_idx, index_ns, days, test_days,
                )
                amb_arr = np.zeros(len(sl_arr), dtype=np.int64)
                eq_tr_arr = None
                eq_mdd_arr = None
                fin_eq_arr = None
                liq_arr = None
            else:
                (
                    tr_arr, wr_arr, tre_arr, pf_arr, exp_arr, mdd_arr, aw_arr, al_arr,
                    tpd_arr, mgd_arr, abh_arr,
                    ttr_arr, twr_arr, tre2_arr, tpf2_arr, texp_arr,
                    ttpd_arr, tmgd_arr, tabh_arr,
                    amb_arr,
                    eq_tr_arr, eq_mdd_arr, fin_eq_arr, liq_arr,
                ) = simulate_many_configs_with_entries_summary(
                    open_, high, low, close, longs, shorts,
                    sl_arr, tp_arr, mh_arr, FEE_PER_SIDE,
                    test_start_idx, index_ns, days, test_days,
                    entry_next_open, spread_pct_val, slippage_pct_val,
                    use_position_sizing, risk_per_trade_pct,
                    use_leverage, leverage_val,
                    use_liquidation, maintenance_margin_pct,
                    compute_ambiguity_metrics,
                )
            if diagnostics is not None:
                diagnostics.simulate_sec += time.perf_counter() - simulate_t0
            row_t0 = time.perf_counter()
            if row_builder == "normal":
                rows = batch_to_normal_rows(
                    sl_arr, tp_arr, mh_arr,
                    tr_arr, wr_arr, tre_arr, pf_arr, exp_arr, mdd_arr, aw_arr, al_arr,
                    tpd_arr, mgd_arr, abh_arr,
                    ttr_arr, twr_arr, tre2_arr, tpf2_arr, texp_arr,
                    ttpd_arr, tmgd_arr, tabh_arr,
                    amb_arr,
                    timeframe, signal.strategy, signal.params, side_mode,
                    min_full_trades, min_test_trades, min_test_win_rate,
                    min_profit_factor, min_test_profit_factor,
                    equity_total_return_arr=eq_tr_arr,
                    equity_max_drawdown_arr=eq_mdd_arr,
                    final_equity_arr=fin_eq_arr,
                    liquidated_trades_arr=liq_arr,
                    **feature_flags,
                )
            else:
                rows = batch_to_dense_rows(
                    sl_arr, tp_arr, mh_arr,
                    tr_arr, wr_arr, tre_arr, pf_arr, exp_arr, mdd_arr, aw_arr, al_arr,
                    tpd_arr, mgd_arr, abh_arr,
                    ttr_arr, twr_arr, tre2_arr, tpf2_arr, texp_arr,
                    ttpd_arr, tmgd_arr, tabh_arr,
                    amb_arr,
                    timeframe, signal.strategy, signal.params, side_mode,
                    min_full_trades, min_win_rate, min_test_trades, min_test_win_rate,
                    equity_total_return_arr=eq_tr_arr,
                    equity_max_drawdown_arr=eq_mdd_arr,
                    final_equity_arr=fin_eq_arr,
                    liquidated_trades_arr=liq_arr,
                    **feature_flags,
                )
            if diagnostics is not None:
                diagnostics.row_build_sec += time.perf_counter() - row_t0
            for row in rows:
                yield row


def evaluate_timeframe(
    timeframe: str,
    mode: str = "normal",
    strategies: list[str] | set[str] | None = None,
    search_params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    if mode not in {"normal", "dense_high_winrate"}:
        raise ValueError(f"Unsupported mode: {mode}")
    search_params = search_params or {}
    rows = list(_iter_timeframe_rows(timeframe, mode, strategies, search_params))
    return _result_frame(rows, _sort_cols_for_mode(mode), result_columns_for_params(search_params))


def evaluate_normal_timeframe(
    timeframe: str,
    strategies: list[str] | set[str] | None = None,
    search_params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    return evaluate_timeframe(timeframe, "normal", strategies, search_params)


def evaluate_dense_timeframe(
    timeframe: str,
    strategies: list[str] | set[str] | None = None,
    search_params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    return evaluate_timeframe(timeframe, "dense_high_winrate", strategies, search_params)


def run_search(
    timeframes: list[str] | tuple[str, ...] | None = None,
    mode: str = "normal",
    strategies: list[str] | set[str] | None = None,
    search_params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    search_params = search_params or {}
    if timeframes is None:
        timeframes = DENSE_TIMEFRAMES if mode == "dense_high_winrate" else NORMAL_TIMEFRAMES

    frames = [evaluate_timeframe(timeframe, mode=mode, strategies=strategies, search_params=search_params) for timeframe in timeframes]
    rows = [frame for frame in frames if not frame.empty]
    columns = result_columns_for_params(search_params)
    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.concat(rows, ignore_index=True)
    return df.sort_values(_sort_cols_for_mode(mode), ascending=[False] * len(_sort_cols_for_mode(mode)))


def run_search_limited(
    timeframes: list[str] | tuple[str, ...] | None = None,
    mode: str = "normal",
    strategies: list[str] | set[str] | None = None,
    search_params: dict[str, Any] | None = None,
    result_filters: list[Any] | tuple[Any, ...] | None = None,
    limit: int = 500,
    diagnostics: SearchDiagnostics | None = None,
) -> pd.DataFrame:
    search_params = search_params or {}
    total_t0 = time.perf_counter()
    if timeframes is None:
        timeframes = DENSE_TIMEFRAMES if mode == "dense_high_winrate" else NORMAL_TIMEFRAMES

    columns = result_columns_for_params(search_params)
    rows: list[dict[str, Any]] = []
    trim_threshold = max(limit * 2, limit + 100)
    for timeframe in timeframes:
        for row in _iter_timeframe_rows(timeframe, mode, strategies, search_params, result_filters, diagnostics):
            if not _row_matches_filters(row, result_filters):
                continue
            rows.append(row)
            if len(rows) > trim_threshold:
                rows = _trim_rows(rows, mode, limit, columns)

    row_t0 = time.perf_counter()
    df = _result_frame(rows, _sort_cols_for_mode(mode), columns)
    df = df.head(limit)
    if diagnostics is not None:
        diagnostics.row_build_sec += time.perf_counter() - row_t0
        diagnostics.rows_kept = len(df)
        diagnostics.total_runtime_sec += time.perf_counter() - total_t0
    return df


def run_search_limited_with_diagnostics(
    timeframes: list[str] | tuple[str, ...] | None = None,
    mode: str = "normal",
    strategies: list[str] | set[str] | None = None,
    search_params: dict[str, Any] | None = None,
    result_filters: list[Any] | tuple[Any, ...] | None = None,
    limit: int = 500,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    diagnostics = SearchDiagnostics()
    df = run_search_limited(
        timeframes=timeframes,
        mode=mode,
        strategies=strategies,
        search_params=search_params,
        result_filters=result_filters,
        limit=limit,
        diagnostics=diagnostics,
    )
    return df, diagnostics.to_dict()


def summarize_buy_hold(timeframes: list[str] | tuple[str, ...] = tuple(NORMAL_TIMEFRAMES)) -> pd.DataFrame:
    rows = []
    for timeframe in timeframes:
        df = load_ohlc(timeframe)
        full_return = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
        test = df[df.index >= TEST_START]
        test_return = (test["close"].iloc[-1] / test["close"].iloc[0] - 1) * 100 if len(test) else np.nan
        rows.append(
            {
                "timeframe": timeframe,
                "first": df.index.min(),
                "last": df.index.max(),
                "bars": len(df),
                "buy_hold_return_pct": full_return,
                "test_buy_hold_return_pct": test_return,
            }
        )
    return pd.DataFrame(rows)
