from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def _metrics_numba(
    returns: np.ndarray, count: int
) -> tuple[int, float, float, float, float, float, float, float]:
    if count == 0:
        return 0, np.nan, 0.0, np.nan, np.nan, np.nan, np.nan, np.nan

    win_count = 0
    loss_count = 0
    win_sum = 0.0
    loss_sum = 0.0
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    has_first = False

    for j in range(count):
        r = returns[j]
        if r > 0:
            win_count += 1
            win_sum += r
        else:
            loss_count += 1
            loss_sum += r
        equity *= 1.0 + r
        if not has_first:
            peak = equity
            has_first = True
        if equity > peak:
            peak = equity
        dd = equity / peak - 1.0
        if dd < max_dd:
            max_dd = dd

    trades = count
    win_rate = win_count / count * 100.0
    total_return = (equity - 1.0) * 100.0
    gross_profit = win_sum
    gross_loss = -loss_sum
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
    mean_ret = 0.0
    for j in range(count):
        mean_ret += returns[j]
    expectancy = mean_ret / count * 100.0
    max_drawdown = max_dd * 100.0
    avg_win = win_sum / win_count * 100.0 if win_count > 0 else np.nan
    avg_loss = loss_sum / loss_count * 100.0 if loss_count > 0 else np.nan

    return trades, win_rate, total_return, profit_factor, expectancy, max_drawdown, avg_win, avg_loss


@njit(cache=True)
def _max_gap_days_numba(index_ns: np.ndarray, entry_indices: np.ndarray, count: int) -> float:
    if count < 2:
        return np.inf
    max_gap = 0.0
    for j in range(1, count):
        diff = index_ns[entry_indices[j]] - index_ns[entry_indices[j - 1]]
        gap = diff / 86400000000000.0
        if gap > max_gap:
            max_gap = gap
    return max_gap


@njit(cache=True)
def simulate_many_configs_summary(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    long_entries: np.ndarray,
    short_entries: np.ndarray,
    sl_arr: np.ndarray,
    tp_arr: np.ndarray,
    max_hold_arr: np.ndarray,
    fee_per_side: float,
    test_start_idx: int,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    num_configs = sl_arr.shape[0]
    n = open_.shape[0]

    trades_arr = np.zeros(num_configs, dtype=np.int64)
    win_rate_arr = np.full(num_configs, np.nan, dtype=np.float64)
    total_return_arr = np.zeros(num_configs, dtype=np.float64)
    profit_factor_arr = np.full(num_configs, np.nan, dtype=np.float64)
    expectancy_arr = np.full(num_configs, np.nan, dtype=np.float64)
    max_drawdown_arr = np.full(num_configs, np.nan, dtype=np.float64)
    avg_win_arr = np.full(num_configs, np.nan, dtype=np.float64)
    avg_loss_arr = np.full(num_configs, np.nan, dtype=np.float64)
    test_trades_arr = np.zeros(num_configs, dtype=np.int64)
    test_win_rate_arr = np.full(num_configs, np.nan, dtype=np.float64)
    test_total_return_arr = np.zeros(num_configs, dtype=np.float64)
    test_profit_factor_arr = np.full(num_configs, np.nan, dtype=np.float64)
    test_expectancy_arr = np.full(num_configs, np.nan, dtype=np.float64)

    returns_buf = np.empty(n, dtype=np.float64)
    exits_buf = np.empty(n, dtype=np.int64)
    test_returns_buf = np.empty(n, dtype=np.float64)

    for c in range(num_configs):
        sl = sl_arr[c]
        tp = tp_arr[c]
        max_hold = max_hold_arr[c]

        if tp <= 2.5 * fee_per_side:
            continue

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
                        returns_buf[count] = (exit_price / entry - 1.0) - 2.0 * fee_per_side
                        exits_buf[count] = i
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
                        returns_buf[count] = (entry / exit_price - 1.0) - 2.0 * fee_per_side
                        exits_buf[count] = i
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
                returns_buf[count] = (close[n - 1] / entry - 1.0) - 2.0 * fee_per_side
            else:
                returns_buf[count] = (entry / close[n - 1] - 1.0) - 2.0 * fee_per_side
            exits_buf[count] = n - 1
            count += 1

        if count == 0:
            continue

        (
            trades_arr[c],
            win_rate_arr[c],
            total_return_arr[c],
            profit_factor_arr[c],
            expectancy_arr[c],
            max_drawdown_arr[c],
            avg_win_arr[c],
            avg_loss_arr[c],
        ) = _metrics_numba(returns_buf, count)

        test_count = 0
        for j in range(count):
            if exits_buf[j] >= test_start_idx:
                test_returns_buf[test_count] = returns_buf[j]
                test_count += 1

        if test_count == 0:
            continue

        (
            test_trades_arr[c],
            test_win_rate_arr[c],
            test_total_return_arr[c],
            test_profit_factor_arr[c],
            test_expectancy_arr[c],
            _,
            _,
            _,
        ) = _metrics_numba(test_returns_buf, test_count)

    return (
        trades_arr,
        win_rate_arr,
        total_return_arr,
        profit_factor_arr,
        expectancy_arr,
        max_drawdown_arr,
        avg_win_arr,
        avg_loss_arr,
        test_trades_arr,
        test_win_rate_arr,
        test_total_return_arr,
        test_profit_factor_arr,
        test_expectancy_arr,
    )


@njit(cache=True)
def simulate_many_configs_with_entries_summary(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    long_entries: np.ndarray,
    short_entries: np.ndarray,
    sl_arr: np.ndarray,
    tp_arr: np.ndarray,
    max_hold_arr: np.ndarray,
    fee_per_side: float,
    test_start_idx: int,
    index_ns: np.ndarray,
    total_days: int,
    test_days: int,
) -> tuple[
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
]:
    num_configs = sl_arr.shape[0]
    n = open_.shape[0]

    trades_arr = np.zeros(num_configs, dtype=np.int64)
    win_rate_arr = np.full(num_configs, np.nan, dtype=np.float64)
    total_return_arr = np.zeros(num_configs, dtype=np.float64)
    profit_factor_arr = np.full(num_configs, np.nan, dtype=np.float64)
    expectancy_arr = np.full(num_configs, np.nan, dtype=np.float64)
    max_drawdown_arr = np.full(num_configs, np.nan, dtype=np.float64)
    avg_win_arr = np.full(num_configs, np.nan, dtype=np.float64)
    avg_loss_arr = np.full(num_configs, np.nan, dtype=np.float64)
    trades_per_day_arr = np.zeros(num_configs, dtype=np.float64)
    max_gap_days_arr = np.full(num_configs, np.inf, dtype=np.float64)
    avg_bars_held_arr = np.full(num_configs, np.nan, dtype=np.float64)
    test_trades_arr = np.zeros(num_configs, dtype=np.int64)
    test_win_rate_arr = np.full(num_configs, np.nan, dtype=np.float64)
    test_total_return_arr = np.zeros(num_configs, dtype=np.float64)
    test_profit_factor_arr = np.full(num_configs, np.nan, dtype=np.float64)
    test_expectancy_arr = np.full(num_configs, np.nan, dtype=np.float64)
    test_trades_per_day_arr = np.zeros(num_configs, dtype=np.float64)
    test_max_gap_days_arr = np.full(num_configs, np.inf, dtype=np.float64)
    test_avg_bars_held_arr = np.full(num_configs, np.nan, dtype=np.float64)

    returns_buf = np.empty(n, dtype=np.float64)
    entries_buf = np.empty(n, dtype=np.int64)
    exits_buf = np.empty(n, dtype=np.int64)
    bars_buf = np.empty(n, dtype=np.int64)
    test_returns_buf = np.empty(n, dtype=np.float64)
    test_entries_buf = np.empty(n, dtype=np.int64)
    test_bars_buf = np.empty(n, dtype=np.int64)

    for c in range(num_configs):
        sl = sl_arr[c]
        tp = tp_arr[c]
        max_hold = max_hold_arr[c]

        if tp <= 2.5 * fee_per_side:
            continue

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
                        returns_buf[count] = (exit_price / entry - 1.0) - 2.0 * fee_per_side
                        entries_buf[count] = entry_i
                        exits_buf[count] = i
                        bars_buf[count] = held
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
                        returns_buf[count] = (entry / exit_price - 1.0) - 2.0 * fee_per_side
                        entries_buf[count] = entry_i
                        exits_buf[count] = i
                        bars_buf[count] = held
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
                        returns_buf[count] = (exit_price / entry - 1.0) - 2.0 * fee_per_side
                        entries_buf[count] = entry_i
                        exits_buf[count] = i
                        bars_buf[count] = 0
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
                        returns_buf[count] = (entry / exit_price - 1.0) - 2.0 * fee_per_side
                        entries_buf[count] = entry_i
                        exits_buf[count] = i
                        bars_buf[count] = 0
                        count += 1
                        in_pos = False

        if in_pos:
            if direction == 1:
                returns_buf[count] = (close[n - 1] / entry - 1.0) - 2.0 * fee_per_side
            else:
                returns_buf[count] = (entry / close[n - 1] - 1.0) - 2.0 * fee_per_side
            entries_buf[count] = entry_i
            exits_buf[count] = n - 1
            bars_buf[count] = n - 1 - entry_i
            count += 1

        if count == 0:
            continue

        (
            trades_arr[c],
            win_rate_arr[c],
            total_return_arr[c],
            profit_factor_arr[c],
            expectancy_arr[c],
            max_drawdown_arr[c],
            avg_win_arr[c],
            avg_loss_arr[c],
        ) = _metrics_numba(returns_buf, count)

        safe_days = total_days if total_days > 0 else 1
        trades_per_day_arr[c] = count / safe_days
        max_gap_days_arr[c] = _max_gap_days_numba(index_ns, entries_buf, count)
        total_bars = 0.0
        for j in range(count):
            total_bars += bars_buf[j]
        avg_bars_held_arr[c] = total_bars / count

        test_count = 0
        for j in range(count):
            if exits_buf[j] >= test_start_idx:
                test_returns_buf[test_count] = returns_buf[j]
                test_entries_buf[test_count] = entries_buf[j]
                test_bars_buf[test_count] = bars_buf[j]
                test_count += 1

        if test_count == 0:
            continue

        (
            test_trades_arr[c],
            test_win_rate_arr[c],
            test_total_return_arr[c],
            test_profit_factor_arr[c],
            test_expectancy_arr[c],
            _,
            _,
            _,
        ) = _metrics_numba(test_returns_buf, test_count)

        safe_test_days_ = test_days if test_days > 0 else 1
        test_trades_per_day_arr[c] = test_count / safe_test_days_
        test_max_gap_days_arr[c] = _max_gap_days_numba(index_ns, test_entries_buf, test_count)
        total_test_bars = 0.0
        for j in range(test_count):
            total_test_bars += test_bars_buf[j]
        test_avg_bars_held_arr[c] = total_test_bars / test_count

    return (
        trades_arr,
        win_rate_arr,
        total_return_arr,
        profit_factor_arr,
        expectancy_arr,
        max_drawdown_arr,
        avg_win_arr,
        avg_loss_arr,
        trades_per_day_arr,
        max_gap_days_arr,
        avg_bars_held_arr,
        test_trades_arr,
        test_win_rate_arr,
        test_total_return_arr,
        test_profit_factor_arr,
        test_expectancy_arr,
        test_trades_per_day_arr,
        test_max_gap_days_arr,
        test_avg_bars_held_arr,
    )
