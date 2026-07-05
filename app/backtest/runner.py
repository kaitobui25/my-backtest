from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.backtest.batch_engine import simulate_many_configs_with_entries_summary
from app.backtest.config import (
    DENSE_MIN_TEST_WIN_RATE,
    DENSE_MIN_TEST_TRADES_PER_DAY,
    DENSE_MIN_TRADES_PER_DAY,
    DENSE_MIN_WIN_RATE,
    DENSE_TIMEFRAMES,
    FEE_PER_SIDE,
    NORMAL_TIMEFRAMES,
    REQUIRED_COLUMNS,
    TEST_START,
    dense_grid_for_timeframe,
    normal_grid_for_timeframe,
)
from app.backtest.data_loader import load_ohlc
from app.backtest.engine import calendar_days_ns
from app.backtest.grid import build_config_grid

from app.backtest.result_builder import batch_to_dense_rows, batch_to_normal_rows
from app.backtest.signals import build_signal_variants, side_mode_arrays


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


def _result_frame(rows: list[dict[str, Any]], sort_cols: list[str] | None = None) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    df = pd.DataFrame(rows)
    for column in REQUIRED_COLUMNS:
        if column not in df.columns:
            df[column] = np.nan
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return df


def evaluate_timeframe(
    timeframe: str,
    mode: str = "normal",
    strategies: list[str] | set[str] | None = None,
    search_params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    if mode == "normal":
        return evaluate_normal_timeframe(timeframe, strategies, search_params)
    if mode == "dense_high_winrate":
        return evaluate_dense_timeframe(timeframe, strategies, search_params)
    raise ValueError(f"Unsupported mode: {mode}")


def evaluate_normal_timeframe(
    timeframe: str,
    strategies: list[str] | set[str] | None = None,
    search_params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    search_params = search_params or {}
    df = load_ohlc(timeframe)

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
    signals = build_signal_variants(df=df, timeframe=timeframe, mode="normal", strategies=strategies, strategy_params=strategy_params)
    max_signal_variants = search_params.get("max_signal_variants")
    if max_signal_variants is not None:
        signals = signals[: int(max_signal_variants)]

    grid_profile = search_params.get("grid_profile", "dense")
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
    min_test_win_rate = search_params.get("min_test_win_rate", 48)
    min_profit_factor = search_params.get("min_profit_factor", 1.05)
    min_test_profit_factor = search_params.get("min_test_profit_factor", 1.0)
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

    rows: list[dict[str, Any]] = []
    for signal in signals:
        if signal.long_entries.sum() + signal.short_entries.sum() < min_full_trades:
            continue
        for side_mode in signal.side_modes:
            longs, shorts = side_mode_arrays(signal.long_entries, signal.short_entries, side_mode)
            if longs.sum() + shorts.sum() < min_full_trades:
                continue
            sl_arr, tp_arr, mh_arr = build_config_grid(sl_values, tp_values, max_holds)
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
            )
            rows.extend(
                batch_to_normal_rows(
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
                )
            )

    return _result_frame(rows, ["score", "test_profit_factor", "test_total_return"])


def evaluate_dense_timeframe(
    timeframe: str,
    strategies: list[str] | set[str] | None = None,
    search_params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    search_params = search_params or {}
    df = load_ohlc(timeframe)

    open_ = df["open"].to_numpy(np.float64)
    high = df["high"].to_numpy(np.float64)
    low = df["low"].to_numpy(np.float64)
    close = df["close"].to_numpy(np.float64)
    index_ns = df.index.astype("datetime64[ns]").asi8.astype(np.int64, copy=False)
    test_start_idx = int(np.searchsorted(df.index.to_numpy(), np.datetime64(TEST_START), side="left"))
    is_test_exit = index_ns >= np.datetime64(TEST_START).astype("datetime64[ns]").astype(np.int64)
    days = calendar_days_ns(index_ns)
    test_days = calendar_days_ns(index_ns, is_test_exit)
    min_trades = int(np.ceil(days * search_params.get("min_trades_per_day", DENSE_MIN_TRADES_PER_DAY)))
    min_test_trades = int(np.ceil(test_days * search_params.get("min_test_trades_per_day", DENSE_MIN_TEST_TRADES_PER_DAY)))
    min_win_rate = search_params.get("min_win_rate", DENSE_MIN_WIN_RATE)
    min_test_win_rate = search_params.get("min_test_win_rate", DENSE_MIN_TEST_WIN_RATE)

    strategy_params = search_params.get("strategy_params", {})
    signals = build_signal_variants(df=df, timeframe=timeframe, mode="dense_high_winrate", strategies=strategies, strategy_params=strategy_params)
    max_signal_variants = search_params.get("max_signal_variants")
    if max_signal_variants is not None:
        signals = signals[: int(max_signal_variants)]

    sl_values, tp_values, max_holds = _grid(dense_grid_for_timeframe(timeframe), search_params)
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

    rows: list[dict[str, Any]] = []
    for signal in signals:
        if signal.long_entries.sum() + signal.short_entries.sum() < min_trades:
            continue
        for side_mode in signal.side_modes:
            longs, shorts = side_mode_arrays(signal.long_entries, signal.short_entries, side_mode)
            if longs.sum() + shorts.sum() < min_trades:
                continue
            sl_arr, tp_arr, mh_arr = build_config_grid(sl_values, tp_values, max_holds)
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
            )
            rows.extend(
                batch_to_dense_rows(
                    sl_arr, tp_arr, mh_arr,
                    tr_arr, wr_arr, tre_arr, pf_arr, exp_arr, mdd_arr, aw_arr, al_arr,
                    tpd_arr, mgd_arr, abh_arr,
                    ttr_arr, twr_arr, tre2_arr, tpf2_arr, texp_arr,
                    ttpd_arr, tmgd_arr, tabh_arr,
                    amb_arr,
                    timeframe, signal.strategy, signal.params, side_mode,
                    min_trades, min_win_rate, min_test_trades, min_test_win_rate,
                    equity_total_return_arr=eq_tr_arr,
                    equity_max_drawdown_arr=eq_mdd_arr,
                    final_equity_arr=fin_eq_arr,
                    liquidated_trades_arr=liq_arr,
                )
            )

    return _result_frame(rows, ["score", "test_total_return", "test_profit_factor"])


def run_search(
    timeframes: list[str] | tuple[str, ...] | None = None,
    mode: str = "normal",
    strategies: list[str] | set[str] | None = None,
    search_params: dict[str, Any] | None = None,
) -> pd.DataFrame:
    if timeframes is None:
        timeframes = DENSE_TIMEFRAMES if mode == "dense_high_winrate" else NORMAL_TIMEFRAMES

    frames = [evaluate_timeframe(timeframe, mode=mode, strategies=strategies, search_params=search_params) for timeframe in timeframes]
    rows = [frame for frame in frames if not frame.empty]
    if not rows:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

    df = pd.concat(rows, ignore_index=True)
    if mode == "dense_high_winrate":
        return df.sort_values(["score", "test_total_return", "test_profit_factor"], ascending=[False, False, False])
    return df.sort_values(["score", "test_profit_factor", "test_total_return"], ascending=[False, False, False])


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
