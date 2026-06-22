from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any

import numpy as np
import pandas as pd

try:
    from numba import njit
except Exception:
    njit = None


EXIT_REASON = {1: "sl", 2: "tp", 3: "time", 4: "end"}


@dataclass
class SimResult:
    returns: np.ndarray
    entry_idx: np.ndarray
    exit_idx: np.ndarray
    direction: np.ndarray
    entry_price: np.ndarray
    exit_price: np.ndarray
    reason: np.ndarray


def shift_entries(long_signal: pd.Series, short_signal: pd.Series, lag_bars: int, conflict: str) -> tuple[np.ndarray, np.ndarray]:
    longs = long_signal.shift(lag_bars).fillna(False).to_numpy(dtype=np.bool_)
    shorts = short_signal.shift(lag_bars).fillna(False).to_numpy(dtype=np.bool_)
    both = longs & shorts
    if both.any():
        if conflict == "skip":
            longs[both] = False
            shorts[both] = False
        elif conflict == "long":
            shorts[both] = False
        elif conflict == "short":
            longs[both] = False
        else:
            raise ValueError(f"Unknown signal_conflict: {conflict}")
    return longs, shorts


def side_mode_arrays(long_entries: np.ndarray, short_entries: np.ndarray, side_mode: str) -> tuple[np.ndarray, np.ndarray]:
    if side_mode == "both":
        return long_entries, short_entries
    if side_mode == "long_only":
        return long_entries, np.zeros_like(short_entries)
    if side_mode == "short_only":
        return np.zeros_like(long_entries), short_entries
    raise ValueError(f"Unknown side_mode: {side_mode}")


def iter_execution_grid(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sl, tp, max_hold, side_mode in product(
        grid["stop_loss_pct"],
        grid["take_profit_pct"],
        grid["max_hold_bars"],
        grid["side_modes"],
    ):
        rows.append(
            {
                "stop_loss_pct": float(sl),
                "take_profit_pct": float(tp),
                "max_hold_bars": int(max_hold),
                "side_mode": str(side_mode),
            }
        )
    return rows


def simulate_trades(
    df: pd.DataFrame,
    long_entries: np.ndarray,
    short_entries: np.ndarray,
    stop_loss_pct: float,
    take_profit_pct: float,
    fee_per_side: float,
    slippage_per_side: float,
    max_hold_bars: int,
    same_bar_exit_priority: str,
) -> SimResult:
    out = _simulate_trades(
        df["open"].to_numpy(np.float64),
        df["high"].to_numpy(np.float64),
        df["low"].to_numpy(np.float64),
        df["close"].to_numpy(np.float64),
        long_entries,
        short_entries,
        float(stop_loss_pct),
        float(take_profit_pct),
        float(fee_per_side),
        float(slippage_per_side),
        int(max_hold_bars),
        same_bar_exit_priority == "sl",
    )
    return SimResult(*out)


def _simulate_trades_python(open_, high, low, close, long_entries, short_entries, sl, tp, fee_per_side, slippage_per_side, max_hold, priority_sl):
    returns: list[float] = []
    entry_idx: list[int] = []
    exit_idx: list[int] = []
    direction_arr: list[int] = []
    entry_price_arr: list[float] = []
    exit_price_arr: list[float] = []
    reason_arr: list[int] = []
    in_pos = False
    direction = 0
    entry_fill = 0.0
    entry_i = 0
    for i in range(len(open_)):
        exited_this_bar = False
        if in_pos:
            held = i - entry_i
            should_time_exit = max_hold > 0 and held >= max_hold
            do_exit = False
            reason = 0
            raw_exit = close[i]
            if direction == 1:
                sl_price = entry_fill * (1.0 - sl)
                tp_price = entry_fill * (1.0 + tp)
                hit_sl = low[i] <= sl_price
                hit_tp = high[i] >= tp_price
                if hit_sl and hit_tp:
                    raw_exit, reason = (sl_price, 1) if priority_sl else (tp_price, 2)
                    do_exit = True
                elif hit_sl:
                    raw_exit, reason, do_exit = sl_price, 1, True
                elif hit_tp:
                    raw_exit, reason, do_exit = tp_price, 2, True
                elif should_time_exit:
                    raw_exit, reason, do_exit = close[i], 3, True
                if do_exit:
                    exit_fill = raw_exit * (1.0 - slippage_per_side)
                    returns.append((exit_fill / entry_fill - 1.0) - 2.0 * fee_per_side)
            else:
                sl_price = entry_fill * (1.0 + sl)
                tp_price = entry_fill * (1.0 - tp)
                hit_sl = high[i] >= sl_price
                hit_tp = low[i] <= tp_price
                if hit_sl and hit_tp:
                    raw_exit, reason = (sl_price, 1) if priority_sl else (tp_price, 2)
                    do_exit = True
                elif hit_sl:
                    raw_exit, reason, do_exit = sl_price, 1, True
                elif hit_tp:
                    raw_exit, reason, do_exit = tp_price, 2, True
                elif should_time_exit:
                    raw_exit, reason, do_exit = close[i], 3, True
                if do_exit:
                    exit_fill = raw_exit * (1.0 + slippage_per_side)
                    returns.append((entry_fill / exit_fill - 1.0) - 2.0 * fee_per_side)
            if do_exit:
                entry_idx.append(entry_i)
                exit_idx.append(i)
                direction_arr.append(direction)
                entry_price_arr.append(entry_fill)
                exit_price_arr.append(exit_fill)
                reason_arr.append(reason)
                in_pos = False
                exited_this_bar = True
        if not in_pos and not exited_this_bar:
            if long_entries[i]:
                in_pos = True
                direction = 1
                entry_fill = open_[i] * (1.0 + slippage_per_side)
                entry_i = i
            elif short_entries[i]:
                in_pos = True
                direction = -1
                entry_fill = open_[i] * (1.0 - slippage_per_side)
                entry_i = i
    if in_pos:
        if direction == 1:
            exit_fill = close[-1] * (1.0 - slippage_per_side)
            returns.append((exit_fill / entry_fill - 1.0) - 2.0 * fee_per_side)
        else:
            exit_fill = close[-1] * (1.0 + slippage_per_side)
            returns.append((entry_fill / exit_fill - 1.0) - 2.0 * fee_per_side)
        entry_idx.append(entry_i)
        exit_idx.append(len(open_) - 1)
        direction_arr.append(direction)
        entry_price_arr.append(entry_fill)
        exit_price_arr.append(exit_fill)
        reason_arr.append(4)
    return (
        np.asarray(returns, dtype=np.float64),
        np.asarray(entry_idx, dtype=np.int64),
        np.asarray(exit_idx, dtype=np.int64),
        np.asarray(direction_arr, dtype=np.int64),
        np.asarray(entry_price_arr, dtype=np.float64),
        np.asarray(exit_price_arr, dtype=np.float64),
        np.asarray(reason_arr, dtype=np.int64),
    )


if njit is not None:
    _simulate_trades = njit(cache=True)(_simulate_trades_python)
else:
    _simulate_trades = _simulate_trades_python


def build_trade_log(df: pd.DataFrame, sim: SimResult, position_size_pct: float, initial_equity: float) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    equity = initial_equity
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    for idx in range(sim.returns.size):
        entry_i = int(sim.entry_idx[idx])
        exit_i = int(sim.exit_idx[idx])
        direction = int(sim.direction[idx])
        entry = float(sim.entry_price[idx])
        if direction == 1:
            mae = (low[entry_i : exit_i + 1].min() / entry - 1.0)
            mfe = (high[entry_i : exit_i + 1].max() / entry - 1.0)
            side = "long"
        else:
            mae = (entry / high[entry_i : exit_i + 1].max() - 1.0)
            mfe = (entry / low[entry_i : exit_i + 1].min() - 1.0)
            side = "short"
        notional_return = float(sim.returns[idx])
        equity_return = position_size_pct * notional_return
        equity *= 1.0 + equity_return
        rows.append(
            {
                "trade_no": idx + 1,
                "entry_time": df.index[entry_i],
                "exit_time": df.index[exit_i],
                "side": side,
                "entry_price": entry,
                "exit_price": float(sim.exit_price[idx]),
                "bars_held": exit_i - entry_i,
                "exit_reason": EXIT_REASON.get(int(sim.reason[idx]), "unknown"),
                "notional_return": notional_return,
                "notional_return_pct": notional_return * 100.0,
                "position_size_pct": position_size_pct,
                "equity_return": equity_return,
                "equity_return_pct": equity_return * 100.0,
                "equity_after": equity,
                "mae_pct": mae * 100.0,
                "mfe_pct": mfe * 100.0,
                "win": notional_return > 0,
            }
        )
    return pd.DataFrame(rows)
