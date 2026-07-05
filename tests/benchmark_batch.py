from __future__ import annotations

import time
from itertools import product

import numpy as np

from app.backtest.batch_engine import simulate_many_configs_summary, simulate_many_configs_with_entries_summary
from app.backtest.config import FEE_PER_SIDE
from app.backtest.data_loader import load_ohlc
from app.backtest.engine import simulate_trades, simulate_trades_with_entries
from app.backtest.grid import build_config_grid
from app.backtest.metrics import metrics


def _synthetic_entries(n: int) -> tuple[np.ndarray, np.ndarray]:
    longs = np.zeros(n, dtype=np.bool_)
    shorts = np.zeros(n, dtype=np.bool_)
    indices = np.arange(10, n, 15)
    longs[indices[::2]] = True
    shorts[indices[1::2]] = True
    return longs, shorts


def _old_normal_loop(open_, high, low, close, longs, shorts, sl_values, tp_values, max_holds, fee, test_start_idx):
    results = []
    for sl, tp, mh in product(sl_values, tp_values, max_holds):
        if tp <= 2.5 * fee:
            continue
        returns, exits = simulate_trades(open_, high, low, close, longs, shorts, sl, tp, fee, mh)
        trades, wr, tre, pf, exp, mdd, aw, al = metrics(returns)
        test_mask = exits >= test_start_idx
        test_ret = returns[test_mask]
        ttr, twr, tre2, tpf2, texp, _, _, _ = metrics(test_ret)
        results.append((trades, wr, tre, pf, exp, mdd, aw, al, ttr, twr, tre2, tpf2, texp))
    return results


def _old_dense_loop(open_, high, low, close, longs, shorts, sl_values, tp_values, max_holds, fee, test_start_idx, index_ns, total_days, test_days):
    results = []
    for sl, tp, mh in product(sl_values, tp_values, max_holds):
        if tp <= 2.5 * fee:
            continue
        returns, entries, exits, bars = simulate_trades_with_entries(open_, high, low, close, longs, shorts, sl, tp, fee, mh)
        trades, wr, tre, pf, exp, mdd, aw, al = metrics(returns)
        test_mask = exits >= test_start_idx
        test_ret = returns[test_mask]
        ttr, twr, tre2, tpf2, texp, _, _, _ = metrics(test_ret)
        safe_d = total_days if total_days > 0 else 1
        tpd_val = trades / safe_d
        mgd_val = _max_gap_days_py(index_ns, entries)
        abh_val = float(np.mean(bars)) if bars.size else np.nan
        safe_td = test_days if test_days > 0 else 1
        ttpd_val = ttr / safe_td
        tmgd_val = _max_gap_days_py(index_ns, entries[test_mask])
        tabh_val = float(np.mean(bars[test_mask])) if bars[test_mask].size else np.nan
        results.append((trades, wr, tre, pf, exp, mdd, aw, al, tpd_val, mgd_val, abh_val, ttr, twr, tre2, tpf2, texp, ttpd_val, tmgd_val, tabh_val))
    return results


def _max_gap_days_py(index_ns, entry_idx):
    if entry_idx.size < 2:
        return np.inf
    et = index_ns[entry_idx]
    gaps = np.diff(et).astype(np.float64) / 86_400_000_000_000.0
    return float(gaps.max()) if gaps.size else np.inf


def time_it(fn, label, warmup=False):
    if warmup:
        fn()
        return None
    N = 3
    times = []
    for _ in range(N):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    avg = sum(times) / N
    print(f"  {label}: {avg:.4f}s (min {min(times):.4f}s, max {max(times):.4f}s)")
    return avg


def main():
    print("=" * 60)
    print("Batch Engine Benchmark")
    print("=" * 60)

    df = load_ohlc("M30")
    open_ = df["open"].to_numpy(np.float64)
    high = df["high"].to_numpy(np.float64)
    low = df["low"].to_numpy(np.float64)
    close = df["close"].to_numpy(np.float64)
    n = open_.shape[0]
    print(f"\nData: {n} M30 bars")

    longs, shorts = _synthetic_entries(n)
    test_start_idx = n // 2

    sl_values = [0.01, 0.02, 0.04, 0.06]
    tp_values = [0.005, 0.01, 0.02, 0.03]
    max_holds = [0, 48, 96]

    sl_arr, tp_arr, mh_arr = build_config_grid(sl_values, tp_values, max_holds)
    num_configs = len(sl_arr)
    print(f"Configs: {num_configs} ({len(sl_values)} sl x {len(tp_values)} tp x {len(max_holds)} max_hold)")

    index_ns = df.index.astype("datetime64[ns]").asi8.astype(np.int64, copy=False)
    total_days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    is_test = index_ns >= index_ns[test_start_idx]
    test_days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    if is_test.any():
        test_first = np.where(is_test)[0][0]
        test_days = int((index_ns[-1] - index_ns[test_first]) // 86_400_000_000_000 + 1)

    print(f"\n--- Normal Mode ---")

    print("  Warming up Numba...")
    time_it(lambda: _old_normal_loop(open_, high, low, close, longs, shorts, sl_values[:1], tp_values[:1], max_holds[:1], FEE_PER_SIDE, test_start_idx), "old warmup", warmup=True)
    time_it(lambda: simulate_many_configs_summary(open_, high, low, close, longs, shorts, sl_arr[:1], tp_arr[:1], mh_arr[:1], FEE_PER_SIDE, test_start_idx), "new warmup", warmup=True)

    old_normal_t = time_it(lambda: _old_normal_loop(open_, high, low, close, longs, shorts, sl_values, tp_values, max_holds, FEE_PER_SIDE, test_start_idx), "old single-config loop")
    new_normal_t = time_it(lambda: simulate_many_configs_summary(open_, high, low, close, longs, shorts, sl_arr, tp_arr, mh_arr, FEE_PER_SIDE, test_start_idx), "new batch kernel")

    if old_normal_t is not None and new_normal_t is not None:
        ratio = old_normal_t / new_normal_t
        print(f"\n  Speedup: {ratio:.2f}x")

    print(f"\n--- Dense Mode ---")

    print("  Warming up Numba...")
    time_it(lambda: _old_dense_loop(open_, high, low, close, longs, shorts, sl_values[:1], tp_values[:1], max_holds[:1], FEE_PER_SIDE, test_start_idx, index_ns, total_days, test_days), "old dense warmup", warmup=True)
    time_it(lambda: simulate_many_configs_with_entries_summary(open_, high, low, close, longs, shorts, sl_arr[:1], tp_arr[:1], mh_arr[:1], FEE_PER_SIDE, test_start_idx, index_ns, total_days, test_days), "new dense warmup", warmup=True)

    old_dense_t = time_it(lambda: _old_dense_loop(open_, high, low, close, longs, shorts, sl_values, tp_values, max_holds, FEE_PER_SIDE, test_start_idx, index_ns, total_days, test_days), "old single-config loop")
    new_dense_t = time_it(lambda: simulate_many_configs_with_entries_summary(open_, high, low, close, longs, shorts, sl_arr, tp_arr, mh_arr, FEE_PER_SIDE, test_start_idx, index_ns, total_days, test_days), "new batch kernel")

    if old_dense_t is not None and new_dense_t is not None:
        ratio = old_dense_t / new_dense_t
        print(f"\n  Speedup: {ratio:.2f}x")

    print("\n" + "=" * 60)
    print("Benchmark complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
