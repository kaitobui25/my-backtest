from __future__ import annotations

from itertools import product
from typing import Any

import numpy as np
import pandas as pd

from app.backtest.config import (
    DENSE_MIN_TEST_TRADES_PER_DAY,
    DENSE_MIN_TEST_WIN_RATE,
    DENSE_MIN_TRADES_PER_DAY,
    DENSE_MIN_WIN_RATE,
    DENSE_TIMEFRAMES,
    FEE_PER_SIDE,
    MIN_FULL_TRADES,
    MIN_TEST_TRADES,
    NORMAL_TIMEFRAMES,
    REQUIRED_COLUMNS,
    TEST_START,
    dense_grid_for_timeframe,
    normal_grid_for_timeframe,
)
from app.backtest.data_loader import load_ohlc
from app.backtest.engine import calendar_days_ns, max_gap_days_ns, simulate_trades, simulate_trades_with_entries
from app.backtest.metrics import metrics, score_candidate, score_dense_candidate
from app.backtest.signals import SignalVariant, build_signal_variants, side_mode_arrays


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
    is_test_exit = df.index.to_numpy() >= np.datetime64(TEST_START)

    signals = build_signal_variants(df=df, timeframe=timeframe, mode="normal", strategies=strategies)
    max_signal_variants = search_params.get("max_signal_variants")
    if max_signal_variants is not None:
        signals = signals[: int(max_signal_variants)]

    sl_values, tp_values, max_holds = _grid(normal_grid_for_timeframe(timeframe), search_params)
    min_full_trades = _filter_value(search_params, "min_full_trades", MIN_FULL_TRADES, timeframe)
    min_test_trades = _filter_value(search_params, "min_test_trades", MIN_TEST_TRADES, timeframe)
    min_test_win_rate = search_params.get("min_test_win_rate", 48)
    min_profit_factor = search_params.get("min_profit_factor", 1.05)
    min_test_profit_factor = search_params.get("min_test_profit_factor", 1.0)

    rows: list[dict[str, Any]] = []
    for signal in signals:
        if signal.long_entries.sum() + signal.short_entries.sum() < 8:
            continue
        for side_mode in signal.side_modes:
            longs, shorts = side_mode_arrays(signal.long_entries, signal.short_entries, side_mode)
            if longs.sum() + shorts.sum() < 8:
                continue
            for sl, tp, max_hold in product(sl_values, tp_values, max_holds):
                if tp <= 2.5 * FEE_PER_SIDE:
                    continue
                returns, exits = simulate_trades(open_, high, low, close, longs, shorts, sl, tp, FEE_PER_SIDE, max_hold)
                trades, wr, total_ret, pf, exp, max_dd, avg_win, avg_loss = metrics(returns)
                if trades < min_full_trades or total_ret <= 0 or pf < min_profit_factor or exp <= 0:
                    continue
                test_returns = returns[is_test_exit[exits]]
                test_trades, test_wr, test_ret, test_pf, test_exp, _, _, _ = metrics(test_returns)
                if (
                    test_trades < min_test_trades
                    or test_ret <= 0
                    or test_pf < min_test_profit_factor
                    or test_exp <= 0
                    or test_wr < min_test_win_rate
                ):
                    continue
                score = score_candidate(wr, total_ret, pf, exp, max_dd, trades, test_wr, test_ret, test_pf, test_exp)
                rows.append(
                    {
                        "timeframe": timeframe,
                        "strategy": signal.strategy,
                        "params": signal.params,
                        "side_mode": side_mode,
                        "sl": sl,
                        "tp": tp,
                        "max_hold": max_hold,
                        "trades": trades,
                        "win_rate": wr,
                        "total_return": total_ret,
                        "profit_factor": pf,
                        "expectancy": exp,
                        "max_drawdown": max_dd,
                        "avg_win": avg_win,
                        "avg_loss": avg_loss,
                        "test_trades": test_trades,
                        "test_win_rate": test_wr,
                        "test_total_return": test_ret,
                        "test_profit_factor": test_pf,
                        "test_expectancy": test_exp,
                        "score": score,
                    }
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
    is_test_exit = index_ns >= np.datetime64(TEST_START).astype("datetime64[ns]").astype(np.int64)
    days = calendar_days_ns(index_ns)
    test_days = calendar_days_ns(index_ns, is_test_exit)
    min_trades = int(np.ceil(days * search_params.get("min_trades_per_day", DENSE_MIN_TRADES_PER_DAY)))
    min_test_trades = int(np.ceil(test_days * search_params.get("min_test_trades_per_day", DENSE_MIN_TEST_TRADES_PER_DAY)))
    min_win_rate = search_params.get("min_win_rate", DENSE_MIN_WIN_RATE)
    min_test_win_rate = search_params.get("min_test_win_rate", DENSE_MIN_TEST_WIN_RATE)

    signals = build_signal_variants(df=df, timeframe=timeframe, mode="dense_high_winrate", strategies=strategies)
    max_signal_variants = search_params.get("max_signal_variants")
    if max_signal_variants is not None:
        signals = signals[: int(max_signal_variants)]

    sl_values, tp_values, max_holds = _grid(dense_grid_for_timeframe(timeframe), search_params)

    rows: list[dict[str, Any]] = []
    for signal in signals:
        if signal.long_entries.sum() + signal.short_entries.sum() < min_trades:
            continue
        for side_mode in signal.side_modes:
            longs, shorts = side_mode_arrays(signal.long_entries, signal.short_entries, side_mode)
            if longs.sum() + shorts.sum() < min_trades:
                continue
            for sl, tp, max_hold in product(sl_values, tp_values, max_holds):
                if tp <= 2.5 * FEE_PER_SIDE:
                    continue
                returns, entries, exits, bars_held = simulate_trades_with_entries(
                    open_, high, low, close, longs, shorts, sl, tp, FEE_PER_SIDE, max_hold
                )
                trades, wr, total_ret, pf, exp, max_dd, avg_win, avg_loss = metrics(returns)
                if (
                    trades < min_trades
                    or wr < min_win_rate
                    or total_ret <= 0
                    or pf < 1.0
                    or exp <= 0
                ):
                    continue

                test_mask = is_test_exit[exits]
                test_returns = returns[test_mask]
                test_entries = entries[test_mask]
                test_bars_held = bars_held[test_mask]
                test_trades, test_wr, test_ret, test_pf, test_exp, _, _, _ = metrics(test_returns)
                if (
                    test_trades < min_test_trades
                    or test_wr < min_test_win_rate
                    or test_ret <= 0
                    or test_pf < 1.0
                    or test_exp <= 0
                ):
                    continue

                safe_test_days = test_days if test_days > 0 else 1
                row = {
                    "win_rate": wr,
                    "profit_factor": pf,
                    "expectancy": exp,
                    "test_win_rate": test_wr,
                    "test_total_return": test_ret,
                    "test_profit_factor": test_pf,
                    "test_expectancy": test_exp,
                    "max_drawdown": max_dd,
                    "test_trades_per_day": test_trades / safe_test_days,
                }
                safe_days = days if days > 0 else 1
                safe_test_days = test_days if test_days > 0 else 1
                rows.append(
                    {
                        "timeframe": timeframe,
                        "strategy": signal.strategy,
                        "params": signal.params,
                        "side_mode": side_mode,
                        "sl": sl,
                        "tp": tp,
                        "max_hold": max_hold,
                        "trades": trades,
                        "win_rate": wr,
                        "total_return": total_ret,
                        "profit_factor": pf,
                        "expectancy": exp,
                        "max_drawdown": max_dd,
                        "avg_win": avg_win,
                        "avg_loss": avg_loss,
                        "trades_per_day": trades / safe_days,
                        "max_gap_days": max_gap_days_ns(index_ns, entries),
                        "avg_bars_held": float(np.mean(bars_held)) if bars_held.size else np.nan,
                        "test_trades": test_trades,
                        "test_win_rate": test_wr,
                        "test_total_return": test_ret,
                        "test_profit_factor": test_pf,
                        "test_expectancy": test_exp,
                        "test_trades_per_day": test_trades / safe_test_days,
                        "test_max_gap_days": max_gap_days_ns(index_ns, test_entries),
                        "test_avg_bars_held": float(np.mean(test_bars_held)) if test_bars_held.size else np.nan,
                        "score": score_dense_candidate(row),
                    }
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
