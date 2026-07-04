from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def simulate_trades(open_, high, low, close, long_entries, short_entries, sl, tp, fee_per_side, max_hold):
    n = open_.shape[0]
    trade_returns = np.empty(n, dtype=np.float64)
    exit_idx = np.empty(n, dtype=np.int64)
    count = 0
    in_pos = False
    direction = 0
    entry = 0.0
    entry_i = 0

    for i in range(n):
        if in_pos:
            held = i - entry_i
            should_time_exit = max_hold > 0 and held >= max_hold
            if direction == 1:
                sl_price = entry * (1.0 - sl)
                tp_price = entry * (1.0 + tp)
                hit_sl = low[i] <= sl_price
                hit_tp = high[i] >= tp_price
                if hit_sl or hit_tp or should_time_exit:
                    if hit_sl:
                        exit_price = sl_price
                    elif hit_tp:
                        exit_price = tp_price
                    else:
                        exit_price = close[i]
                    trade_returns[count] = (exit_price / entry - 1.0) - 2.0 * fee_per_side
                    exit_idx[count] = i
                    count += 1
                    in_pos = False
            else:
                sl_price = entry * (1.0 + sl)
                tp_price = entry * (1.0 - tp)
                hit_sl = high[i] >= sl_price
                hit_tp = low[i] <= tp_price
                if hit_sl or hit_tp or should_time_exit:
                    if hit_sl:
                        exit_price = sl_price
                    elif hit_tp:
                        exit_price = tp_price
                    else:
                        exit_price = close[i]
                    trade_returns[count] = (entry / exit_price - 1.0) - 2.0 * fee_per_side
                    exit_idx[count] = i
                    count += 1
                    in_pos = False

        if not in_pos:
            if long_entries[i]:
                in_pos = True
                direction = 1
                entry = open_[i]
                entry_i = i
            elif short_entries[i]:
                in_pos = True
                direction = -1
                entry = open_[i]
                entry_i = i

    if in_pos:
        if direction == 1:
            trade_returns[count] = (close[n - 1] / entry - 1.0) - 2.0 * fee_per_side
        else:
            trade_returns[count] = (entry / close[n - 1] - 1.0) - 2.0 * fee_per_side
        exit_idx[count] = n - 1
        count += 1

    return trade_returns[:count], exit_idx[:count]


@njit(cache=True)
def simulate_trades_with_entries(open_, high, low, close, long_entries, short_entries, sl, tp, fee_per_side, max_hold):
    n = open_.shape[0]
    trade_returns = np.empty(n, dtype=np.float64)
    entry_idx = np.empty(n, dtype=np.int64)
    exit_idx = np.empty(n, dtype=np.int64)
    bars_held = np.empty(n, dtype=np.int64)
    count = 0
    in_pos = False
    direction = 0
    entry = 0.0
    entry_i = 0

    for i in range(n):
        if in_pos:
            held = i - entry_i
            should_time_exit = max_hold > 0 and held >= max_hold
            if direction == 1:
                sl_price = entry * (1.0 - sl)
                tp_price = entry * (1.0 + tp)
                hit_sl = low[i] <= sl_price
                hit_tp = high[i] >= tp_price
                if hit_sl or hit_tp or should_time_exit:
                    if hit_sl:
                        exit_price = sl_price
                    elif hit_tp:
                        exit_price = tp_price
                    else:
                        exit_price = close[i]
                    trade_returns[count] = (exit_price / entry - 1.0) - 2.0 * fee_per_side
                    entry_idx[count] = entry_i
                    exit_idx[count] = i
                    bars_held[count] = held
                    count += 1
                    in_pos = False
            else:
                sl_price = entry * (1.0 + sl)
                tp_price = entry * (1.0 - tp)
                hit_sl = high[i] >= sl_price
                hit_tp = low[i] <= tp_price
                if hit_sl or hit_tp or should_time_exit:
                    if hit_sl:
                        exit_price = sl_price
                    elif hit_tp:
                        exit_price = tp_price
                    else:
                        exit_price = close[i]
                    trade_returns[count] = (entry / exit_price - 1.0) - 2.0 * fee_per_side
                    entry_idx[count] = entry_i
                    exit_idx[count] = i
                    bars_held[count] = held
                    count += 1
                    in_pos = False

        if not in_pos:
            if long_entries[i]:
                in_pos = True
                direction = 1
                entry = open_[i]
                entry_i = i
                sl_price = entry * (1.0 - sl)
                tp_price = entry * (1.0 + tp)
                hit_sl = low[i] <= sl_price
                hit_tp = high[i] >= tp_price
                if hit_sl or hit_tp:
                    if hit_sl:
                        exit_price = sl_price
                    else:
                        exit_price = tp_price
                    trade_returns[count] = (exit_price / entry - 1.0) - 2.0 * fee_per_side
                    entry_idx[count] = entry_i
                    exit_idx[count] = i
                    bars_held[count] = 0
                    count += 1
                    in_pos = False
            elif short_entries[i]:
                in_pos = True
                direction = -1
                entry = open_[i]
                entry_i = i
                sl_price = entry * (1.0 + sl)
                tp_price = entry * (1.0 - tp)
                hit_sl = high[i] >= sl_price
                hit_tp = low[i] <= tp_price
                if hit_sl or hit_tp:
                    if hit_sl:
                        exit_price = sl_price
                    else:
                        exit_price = tp_price
                    trade_returns[count] = (entry / exit_price - 1.0) - 2.0 * fee_per_side
                    entry_idx[count] = entry_i
                    exit_idx[count] = i
                    bars_held[count] = 0
                    count += 1
                    in_pos = False

    if in_pos:
        if direction == 1:
            trade_returns[count] = (close[n - 1] / entry - 1.0) - 2.0 * fee_per_side
        else:
            trade_returns[count] = (entry / close[n - 1] - 1.0) - 2.0 * fee_per_side
        entry_idx[count] = entry_i
        exit_idx[count] = n - 1
        bars_held[count] = n - 1 - entry_i
        count += 1

    return trade_returns[:count], entry_idx[:count], exit_idx[:count], bars_held[:count]


def calendar_days_ns(index_ns: np.ndarray, mask: np.ndarray | None = None) -> int:
    values = index_ns if mask is None else index_ns[mask]
    if values.size == 0:
        return 0
    return int((values[-1] - values[0]) // 86_400_000_000_000 + 1)


def max_gap_days_ns(index_ns: np.ndarray, entry_idx: np.ndarray) -> float:
    if entry_idx.size < 2:
        return np.inf
    entry_times = index_ns[entry_idx]
    gaps = np.diff(entry_times).astype(np.float64) / 86_400_000_000_000.0
    return float(gaps.max()) if gaps.size else np.inf
