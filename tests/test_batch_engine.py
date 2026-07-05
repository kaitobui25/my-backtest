from __future__ import annotations

import numpy as np
import pytest

from app.backtest.batch_engine import (
    simulate_many_configs_summary,
    simulate_many_configs_with_entries_summary,
)
from app.backtest.engine import simulate_trades, simulate_trades_with_entries
from app.backtest.grid import build_config_grid
from app.backtest.metrics import metrics


def _synthetic_ohlc(n: int = 200) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    np.random.seed(42)
    close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 10.0)
    high = close + np.abs(np.random.randn(n)) * 0.3
    low = close - np.abs(np.random.randn(n)) * 0.3
    open_ = low + np.random.rand(n) * (high - low)
    return open_.astype(np.float64), high.astype(np.float64), low.astype(np.float64), close.astype(np.float64)


def _entries_all(n: int) -> tuple[np.ndarray, np.ndarray]:
    longs = np.zeros(n, dtype=np.bool_)
    shorts = np.zeros(n, dtype=np.bool_)
    longs[5] = True
    longs[30] = True
    longs[55] = True
    longs[80] = True
    longs[105] = True
    longs[130] = True
    longs[155] = True
    shorts[15] = True
    shorts[40] = True
    shorts[65] = True
    shorts[90] = True
    shorts[115] = True
    shorts[140] = True
    shorts[165] = True
    return longs, shorts


def _entries_long_only(n: int) -> tuple[np.ndarray, np.ndarray]:
    longs = np.zeros(n, dtype=np.bool_)
    longs[5] = True
    longs[30] = True
    longs[55] = True
    longs[80] = True
    longs[105] = True
    longs[130] = True
    longs[155] = True
    return longs, np.zeros(n, dtype=np.bool_)


def _entries_short_only(n: int) -> tuple[np.ndarray, np.ndarray]:
    shorts = np.zeros(n, dtype=np.bool_)
    shorts[15] = True
    shorts[40] = True
    shorts[65] = True
    shorts[90] = True
    shorts[115] = True
    shorts[140] = True
    shorts[165] = True
    return np.zeros(n, dtype=np.bool_), shorts


def _entries_no_trades(n: int) -> tuple[np.ndarray, np.ndarray]:
    return np.zeros(n, dtype=np.bool_), np.zeros(n, dtype=np.bool_)


def _entries_all_wins(n: int) -> tuple[np.ndarray, np.ndarray]:
    longs = np.zeros(n, dtype=np.bool_)
    longs[0] = True
    shorts = np.zeros(n, dtype=np.bool_)
    return longs, shorts


def _entries_all_losses(n: int) -> tuple[np.ndarray, np.ndarray]:
    longs = np.zeros(n, dtype=np.bool_)
    shorts = np.zeros(n, dtype=np.bool_)
    shorts[1] = True
    return longs, shorts


def _run_old_normal(open_, high, low, close, longs, shorts, sl, tp, max_hold, fee, test_start):
    returns, exits = simulate_trades(open_, high, low, close, longs, shorts, sl, tp, fee, max_hold)
    tr, wr, tr_ret, pf, exp, mdd, aw, al = metrics(returns)
    test_mask = exits >= test_start
    test_returns = returns[test_mask]
    ttr, twr, t_ret, tpf, texp, _, _, _ = metrics(test_returns)
    return {
        "trades": tr,
        "win_rate": wr,
        "total_return": tr_ret,
        "profit_factor": pf,
        "expectancy": exp,
        "max_drawdown": mdd,
        "avg_win": aw,
        "avg_loss": al,
        "test_trades": ttr,
        "test_win_rate": twr,
        "test_total_return": t_ret,
        "test_profit_factor": tpf,
        "test_expectancy": texp,
    }


def _run_old_dense(open_, high, low, close, longs, shorts, sl, tp, max_hold, fee, test_start, index_ns, days, test_days):
    returns, entries, exits, bars = simulate_trades_with_entries(open_, high, low, close, longs, shorts, sl, tp, fee, max_hold)
    tr, wr, tr_ret, pf, exp, mdd, aw, al = metrics(returns)
    test_mask = exits >= test_start
    test_returns = returns[test_mask]
    ttr, twr, t_ret, tpf, texp, _, _, _ = metrics(test_returns)
    safe_d = days if days > 0 else 1
    safe_td = test_days if test_days > 0 else 1
    tpd = tr / safe_d
    test_tpd = ttr / safe_td
    mgd = _max_gap_days(index_ns, entries)
    test_mgd = _max_gap_days(index_ns, entries[test_mask])
    abh = float(np.mean(bars)) if bars.size else np.nan
    test_abh = float(np.mean(bars[test_mask])) if bars[test_mask].size else np.nan
    return {
        "trades": tr,
        "win_rate": wr,
        "total_return": tr_ret,
        "profit_factor": pf,
        "expectancy": exp,
        "max_drawdown": mdd,
        "avg_win": aw,
        "avg_loss": al,
        "trades_per_day": tpd,
        "max_gap_days": mgd,
        "avg_bars_held": abh,
        "test_trades": ttr,
        "test_win_rate": twr,
        "test_total_return": t_ret,
        "test_profit_factor": tpf,
        "test_expectancy": texp,
        "test_trades_per_day": test_tpd,
        "test_max_gap_days": test_mgd,
        "test_avg_bars_held": test_abh,
    }


def _max_gap_days(index_ns, entry_idx):
    if entry_idx.size < 2:
        return np.inf
    entry_times = index_ns[entry_idx]
    gaps = np.diff(entry_times).astype(np.float64) / 86_400_000_000_000.0
    return float(gaps.max()) if gaps.size else np.inf


def _batched_normal_result(open_, high, low, close, longs, shorts, configs, fee, test_start):
    sl_arr, tp_arr, mh_arr = configs
    (
        tr, wr, tre, pf, exp, mdd, aw, al,
        ttr, twr, tre2, tpf, texp,
    ) = simulate_many_configs_summary(open_, high, low, close, longs, shorts, sl_arr, tp_arr, mh_arr, fee, test_start)
    return {
        "trades": tr[0],
        "win_rate": wr[0],
        "total_return": tre[0],
        "profit_factor": pf[0],
        "expectancy": exp[0],
        "max_drawdown": mdd[0],
        "avg_win": aw[0],
        "avg_loss": al[0],
        "test_trades": ttr[0],
        "test_win_rate": twr[0],
        "test_total_return": tre2[0],
        "test_profit_factor": tpf[0],
        "test_expectancy": texp[0],
    }


def _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start, index_ns, days, test_days, entry_next_open=False, spread_pct=0.0, slippage_pct=0.0, use_position_sizing=False, risk_per_trade_pct=1.0, use_leverage=False, leverage=1.0, use_liquidation=False, maintenance_margin_pct=0.5):
    sl_arr, tp_arr, mh_arr = configs
    (
        tr, wr, tre, pf, exp, mdd, aw, al,
        tpd_a, mgd_a, abh_a,
        ttr, twr, tre2, tpf, texp,
        ttpd_a, tmgd_a, tabh_a,
        amb_a,
        eq_tr_a, eq_mdd_a, fin_eq_a, liq_a,
    ) = simulate_many_configs_with_entries_summary(open_, high, low, close, longs, shorts, sl_arr, tp_arr, mh_arr, fee, test_start, index_ns, days, test_days, entry_next_open, spread_pct, slippage_pct, use_position_sizing, risk_per_trade_pct, use_leverage, leverage, use_liquidation, maintenance_margin_pct)
    return {
        "trades": tr[0],
        "win_rate": wr[0],
        "total_return": tre[0],
        "profit_factor": pf[0],
        "expectancy": exp[0],
        "max_drawdown": mdd[0],
        "avg_win": aw[0],
        "avg_loss": al[0],
        "trades_per_day": tpd_a[0],
        "max_gap_days": mgd_a[0],
        "avg_bars_held": abh_a[0],
        "test_trades": ttr[0],
        "test_win_rate": twr[0],
        "test_total_return": tre2[0],
        "test_profit_factor": tpf[0],
        "test_expectancy": texp[0],
        "test_trades_per_day": ttpd_a[0],
        "test_max_gap_days": tmgd_a[0],
        "test_avg_bars_held": tabh_a[0],
        "ambiguous_trades": int(amb_a[0]),
        "equity_total_return": float(eq_tr_a[0]) if not np.isnan(eq_tr_a[0]) else float("nan"),
        "equity_max_drawdown": float(eq_mdd_a[0]) if not np.isnan(eq_mdd_a[0]) else float("nan"),
        "final_equity": float(fin_eq_a[0]) if not np.isnan(fin_eq_a[0]) else float("nan"),
        "liquidated_trades": int(liq_a[0]),
    }


_NORMAL_KEYS = ["trades", "win_rate", "total_return", "profit_factor", "expectancy", "max_drawdown", "avg_win", "avg_loss", "test_trades", "test_win_rate", "test_total_return", "test_profit_factor", "test_expectancy"]
_DENSE_KEYS = _NORMAL_KEYS + ["trades_per_day", "max_gap_days", "avg_bars_held", "test_trades_per_day", "test_max_gap_days", "test_avg_bars_held"]


def _assert_close(old, new, keys):
    for k in keys:
        ov = old[k]
        nv = new[k]
        if np.isnan(ov) and np.isnan(nv):
            continue
        if np.isinf(ov) and np.isinf(nv):
            continue
        if abs(ov) < 1e-6 or abs(nv) < 1e-6:
            assert abs(ov - nv) < 1e-5, f"{k}: old={ov} new={nv}"
        else:
            assert abs(ov - nv) / max(abs(ov), 1e-6) < 1e-4, f"{k}: old={ov} new={nv}"


def _synthetic_index(n: int) -> np.ndarray:
    start = np.datetime64("2024-01-01", "ns").astype(np.int64)
    return start + np.arange(n, dtype=np.int64) * 86_400_000_000_00  # every 10 hours


@pytest.mark.parametrize("longs_fn,shorts_fn", [
    (_entries_long_only, _entries_long_only),
    (_entries_short_only, _entries_short_only),
    (_entries_all, _entries_all),
])
@pytest.mark.parametrize("max_hold", [0, 10])
def test_normal_batch_matches_single(longs_fn, shorts_fn, max_hold):
    np.random.seed(42)
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    longs, shorts = longs_fn(n)
    test_start = 100
    fee = 0.00035
    sl, tp = 0.04, 0.02

    old = _run_old_normal(open_, high, low, close, longs, shorts, sl, tp, max_hold, fee, test_start)
    configs = build_config_grid([sl], [tp], [max_hold])
    new = _batched_normal_result(open_, high, low, close, longs, shorts, configs, fee, test_start)
    _assert_close(old, new, _NORMAL_KEYS)


@pytest.mark.parametrize("longs_fn,shorts_fn", [
    (_entries_long_only, _entries_long_only),
    (_entries_short_only, _entries_short_only),
    (_entries_all, _entries_all),
])
@pytest.mark.parametrize("max_hold", [0, 10])
def test_dense_batch_matches_single(longs_fn, shorts_fn, max_hold):
    np.random.seed(42)
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    index_ns = _synthetic_index(n)
    longs, shorts = longs_fn(n)
    test_start_idx = 100
    test_mask = index_ns >= index_ns[test_start_idx]
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    fee = 0.00035
    sl, tp = 0.04, 0.02

    old = _run_old_dense(open_, high, low, close, longs, shorts, sl, tp, max_hold, fee, test_start_idx, index_ns, days, test_days)
    configs = build_config_grid([sl], [tp], [max_hold])
    new = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days)
    _assert_close(old, new, _DENSE_KEYS)


def test_no_trades_normal():
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    longs, shorts = _entries_no_trades(n)
    fee = 0.00035
    test_start = 100
    sl, tp, max_hold = 0.04, 0.02, 0

    old = _run_old_normal(open_, high, low, close, longs, shorts, sl, tp, max_hold, fee, test_start)
    configs = build_config_grid([sl], [tp], [max_hold])
    new = _batched_normal_result(open_, high, low, close, longs, shorts, configs, fee, test_start)

    assert new["trades"] == 0
    assert np.isnan(new["win_rate"])
    assert new["total_return"] == 0.0
    assert np.isnan(new["profit_factor"])
    assert np.isnan(new["expectancy"])
    assert np.isnan(new["max_drawdown"])
    _assert_close(old, new, _NORMAL_KEYS)


def test_no_trades_dense():
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    index_ns = _synthetic_index(n)
    longs, shorts = _entries_no_trades(n)
    test_start_idx = 100
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    fee = 0.00035
    sl, tp, max_hold = 0.04, 0.02, 0

    old = _run_old_dense(open_, high, low, close, longs, shorts, sl, tp, max_hold, fee, test_start_idx, index_ns, days, test_days)
    configs = build_config_grid([sl], [tp], [max_hold])
    new = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days)

    assert new["trades"] == 0
    assert np.isnan(new["win_rate"])
    assert new["total_return"] == 0.0
    _assert_close(old, new, _DENSE_KEYS)


def test_all_wins_normal():
    np.random.seed(42)
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    open_[0] = 50.0
    close[-1] = 200.0
    longs, shorts = _entries_all_wins(n)
    fee = 0.00035
    test_start = 100
    sl, tp, max_hold = 0.5, 0.5, 0

    old = _run_old_normal(open_, high, low, close, longs, shorts, sl, tp, max_hold, fee, test_start)
    configs = build_config_grid([sl], [tp], [max_hold])
    new = _batched_normal_result(open_, high, low, close, longs, shorts, configs, fee, test_start)
    _assert_close(old, new, _NORMAL_KEYS)


def test_all_losses_normal():
    np.random.seed(42)
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    open_[1] = 200.0
    close[-1] = 50.0
    longs, shorts = _entries_all_losses(n)
    fee = 0.00035
    test_start = 100
    sl, tp, max_hold = 0.5, 0.5, 0

    old = _run_old_normal(open_, high, low, close, longs, shorts, sl, tp, max_hold, fee, test_start)
    configs = build_config_grid([sl], [tp], [max_hold])
    new = _batched_normal_result(open_, high, low, close, longs, shorts, configs, fee, test_start)
    _assert_close(old, new, _NORMAL_KEYS)


def test_config_order_matches_product():
    sl_values = [0.01, 0.02, 0.04]
    tp_values = [0.005, 0.01, 0.02]
    max_holds = [0, 48, 96]

    sl_arr, tp_arr, mh_arr = build_config_grid(sl_values, tp_values, max_holds)

    from itertools import product
    expected = list(product(sl_values, tp_values, max_holds))
    assert len(sl_arr) == len(expected)
    for i, (s, t, m) in enumerate(expected):
        assert sl_arr[i] == s, f"sl mismatch at {i}"
        assert tp_arr[i] == t, f"tp mismatch at {i}"
        assert mh_arr[i] == m, f"max_hold mismatch at {i}"


def test_tp_filter_handled():
    np.random.seed(42)
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    longs, shorts = _entries_all(n)
    fee = 0.00035
    test_start = 100
    sl_arr = np.array([0.04, 0.04], dtype=np.float64)
    tp_arr = np.array([0.00001, 0.02], dtype=np.float64)
    mh_arr = np.array([0, 0], dtype=np.int64)

    tr, wr, tre, pf, exp, mdd, aw, al, ttr, twr, tre2, tpf2, texp = simulate_many_configs_summary(
        open_, high, low, close, longs, shorts, sl_arr, tp_arr, mh_arr, fee, test_start,
    )
    assert tr[0] == 0, "tp too small should produce 0 trades"
    assert tr[1] > 0, "valid tp should produce trades"


def test_normal_same_candle_sl_wins_over_tp():
    n = 20
    open_ = np.full(n, 100.0, dtype=np.float64)
    high = np.full(n, 106.0, dtype=np.float64)
    low = np.full(n, 94.0, dtype=np.float64)
    close = np.full(n, 100.0, dtype=np.float64)
    longs = np.zeros(n, dtype=np.bool_)
    longs[0] = True
    shorts = np.zeros(n, dtype=np.bool_)
    sl, tp = 0.05, 0.05
    fee = 0.0
    test_start = 5

    old = _run_old_normal(open_, high, low, close, longs, shorts, sl, tp, 0, fee, test_start)
    configs = build_config_grid([sl], [tp], [0])
    new = _batched_normal_result(open_, high, low, close, longs, shorts, configs, fee, test_start)
    _assert_close(old, new, _NORMAL_KEYS)
    assert new["trades"] == 1
    sl_entry = 100.0
    sl_price = sl_entry * (1.0 - sl)
    expected_return = (sl_price / sl_entry - 1.0) * 100
    assert abs(new["total_return"] - expected_return) < 1e-9


def test_dense_same_candle_sl_wins_over_tp():
    n = 20
    open_ = np.full(n, 100.0, dtype=np.float64)
    high = np.full(n, 106.0, dtype=np.float64)
    low = np.full(n, 94.0, dtype=np.float64)
    close = np.full(n, 100.0, dtype=np.float64)
    longs = np.zeros(n, dtype=np.bool_)
    longs[0] = True
    shorts = np.zeros(n, dtype=np.bool_)
    index_ns = _synthetic_index(n)
    sl, tp = 0.05, 0.05
    fee = 0.0
    test_start_idx = 5
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)

    old = _run_old_dense(open_, high, low, close, longs, shorts, sl, tp, 0, fee, test_start_idx, index_ns, days, test_days)
    configs = build_config_grid([sl], [tp], [0])
    new = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days)
    _assert_close(old, new, _DENSE_KEYS)
    assert new["trades"] == 1
    sl_entry = 100.0
    sl_price = sl_entry * (1.0 - sl)
    expected_return = (sl_price / sl_entry - 1.0) * 100
    assert abs(new["total_return"] - expected_return) < 1e-9


def test_final_bar_forced_exit_normal():
    n = 10
    open_ = np.full(n, 100.0, dtype=np.float64)
    high = np.full(n, 101.0, dtype=np.float64)
    low = np.full(n, 99.0, dtype=np.float64)
    close = np.arange(100.0, 110.0, dtype=np.float64)
    longs = np.zeros(n, dtype=np.bool_)
    longs[0] = True
    shorts = np.zeros(n, dtype=np.bool_)
    fee = 0.0
    test_start = 5
    sl, tp = 0.5, 0.5

    old = _run_old_normal(open_, high, low, close, longs, shorts, sl, tp, 0, fee, test_start)
    configs = build_config_grid([sl], [tp], [0])
    new = _batched_normal_result(open_, high, low, close, longs, shorts, configs, fee, test_start)
    _assert_close(old, new, _NORMAL_KEYS)
    assert new["trades"] == 1
    expected_ret = (close[-1] / open_[0] - 1.0) * 100
    assert abs(new["total_return"] - expected_ret) < 1e-9


def test_rr_computation():
    from app.backtest.result_builder import _compute_rr, _compute_realized_rr
    assert _compute_rr(0.02, 0.01) == 2.0
    assert _compute_rr(0.03, 0.01) == 3.0
    assert np.isnan(_compute_rr(0.02, 0.0))
    assert np.isnan(_compute_rr(0.02, -0.01))

    assert _compute_realized_rr(5.0, -2.5) == 2.0
    assert _compute_realized_rr(6.0, -3.0) == 2.0
    assert np.isnan(_compute_realized_rr(float("nan"), -2.5))
    assert np.isnan(_compute_realized_rr(5.0, float("nan")))
    assert np.isnan(_compute_realized_rr(5.0, 0.0))
    assert np.isnan(_compute_realized_rr(5.0, 1.0))


def test_ambiguous_rate_computation():
    from app.backtest.result_builder import _compute_ambiguous_rate
    assert _compute_ambiguous_rate(3, 10) == 30.0
    assert _compute_ambiguous_rate(0, 10) == 0.0
    assert np.isnan(_compute_ambiguous_rate(0, 0))


def test_entry_next_open_uses_next_candle():
    np.random.seed(42)
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    index_ns = _synthetic_index(n)
    longs = np.zeros(n, dtype=np.bool_)
    longs[5] = True
    shorts = np.zeros(n, dtype=np.bool_)
    test_start_idx = 100
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    fee = 0.0
    configs = build_config_grid([0.1], [0.05], [0])

    same = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days, entry_next_open=False)
    next_ = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days, entry_next_open=True)

    assert same["trades"] > 0
    assert next_["trades"] > 0
    assert abs(same["total_return"] - next_["total_return"]) > 0.001


def test_entry_next_open_skips_last_candle_signal():
    n = 200
    open_ = np.full(n, 100.0, dtype=np.float64)
    high = np.full(n, 105.0, dtype=np.float64)
    low = np.full(n, 95.0, dtype=np.float64)
    close = np.full(n, 100.0, dtype=np.float64)
    index_ns = _synthetic_index(n)
    longs = np.zeros(n, dtype=np.bool_)
    longs[n - 1] = True
    shorts = np.zeros(n, dtype=np.bool_)
    test_start_idx = 100
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    fee = 0.0
    configs = build_config_grid([0.1], [0.05], [0])

    result = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days, entry_next_open=True)
    assert result["trades"] == 0


def test_spread_slippage_reduces_return():
    np.random.seed(42)
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    index_ns = _synthetic_index(n)
    longs, shorts = _entries_all(n)
    test_start_idx = 100
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    fee = 0.0
    configs = build_config_grid([0.1], [0.05], [0])

    base = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days)
    with_cost = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days, spread_pct=0.001, slippage_pct=0.001)

    if base["trades"] > 0:
        assert with_cost["total_return"] < base["total_return"]


def test_ambiguous_trades_detected():
    n = 200
    open_ = np.full(n, 100.0, dtype=np.float64)
    high = np.full(n, 108.0, dtype=np.float64)
    low = np.full(n, 92.0, dtype=np.float64)
    close = np.full(n, 100.0, dtype=np.float64)
    index_ns = _synthetic_index(n)
    longs = np.zeros(n, dtype=np.bool_)
    longs[0] = True
    shorts = np.zeros(n, dtype=np.bool_)
    fee = 0.0
    test_start_idx = 100
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    sl, tp = 0.05, 0.05
    configs = build_config_grid([sl], [tp], [0])

    result = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days)
    assert result["ambiguous_trades"] > 0


def test_ambiguous_trades_sl_prioritized():
    n = 200
    open_ = np.full(n, 100.0, dtype=np.float64)
    high = np.full(n, 108.0, dtype=np.float64)
    low = np.full(n, 92.0, dtype=np.float64)
    close = np.full(n, 100.0, dtype=np.float64)
    index_ns = _synthetic_index(n)
    longs = np.zeros(n, dtype=np.bool_)
    longs[0] = True
    shorts = np.zeros(n, dtype=np.bool_)
    fee = 0.0
    test_start_idx = 100
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    sl, tp = 0.05, 0.05
    configs = build_config_grid([sl], [tp], [0])

    result = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days)
    entry = 100.0
    sl_price = entry * (1.0 - sl)
    expected_sl_return = (sl_price / entry - 1.0) * 100
    assert abs(result["total_return"] - expected_sl_return) < 1e-9


def test_default_same_open_preserved():
    np.random.seed(42)
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    index_ns = _synthetic_index(n)
    longs, shorts = _entries_all(n)
    test_start_idx = 100
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    fee = 0.00035
    sl, tp = 0.04, 0.02
    max_hold = 0

    old = _run_old_dense(open_, high, low, close, longs, shorts, sl, tp, max_hold, fee, test_start_idx, index_ns, days, test_days)
    configs = build_config_grid([sl], [tp], [max_hold])
    new = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days)
    _assert_close(old, new, _DENSE_KEYS)


def test_final_bar_forced_exit_dense():
    n = 10
    open_ = np.full(n, 100.0, dtype=np.float64)
    high = np.full(n, 101.0, dtype=np.float64)
    low = np.full(n, 99.0, dtype=np.float64)
    close = np.arange(100.0, 110.0, dtype=np.float64)
    longs = np.zeros(n, dtype=np.bool_)
    longs[0] = True
    shorts = np.zeros(n, dtype=np.bool_)
    index_ns = _synthetic_index(n)
    fee = 0.0
    test_start_idx = 5
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    sl, tp = 0.5, 0.5

    old = _run_old_dense(open_, high, low, close, longs, shorts, sl, tp, 0, fee, test_start_idx, index_ns, days, test_days)
    configs = build_config_grid([sl], [tp], [0])
    new = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days)
    _assert_close(old, new, _DENSE_KEYS)
    assert new["trades"] == 1
    expected_ret = (close[-1] / open_[0] - 1.0) * 100
    assert abs(new["total_return"] - expected_ret) < 1e-9

def test_phase2_defaults_return_nan_equity():
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    longs, shorts = _entries_long_only(n)
    index_ns = _synthetic_index(n)
    fee = 0.00035
    test_start_idx = 150
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    configs = build_config_grid([0.04], [0.02], [0])
    result = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days)
    assert np.isnan(result.get("equity_total_return", np.nan))
    assert np.isnan(result.get("equity_max_drawdown", np.nan))


def test_phase2_position_sizing_equity_metrics():
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    longs, shorts = _entries_long_only(n)
    index_ns = _synthetic_index(n)
    fee = 0.00035
    test_start_idx = 150
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    configs = build_config_grid([0.04], [0.02], [0])
    result = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days, use_position_sizing=True, risk_per_trade_pct=1.0)
    assert result["trades"] > 0
    eq_tr = result.get("equity_total_return")
    eq_mdd = result.get("equity_max_drawdown")
    assert not np.isnan(eq_tr), f"equity_total_return should not be NaN when position sizing is on, got {eq_tr}"
    assert not np.isnan(eq_mdd), f"equity_max_drawdown should not be NaN when position sizing is on, got {eq_mdd}"
    assert isinstance(eq_tr, float)
    assert isinstance(eq_mdd, float)


def test_phase2_leverage_scales_equity():
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    longs, shorts = _entries_long_only(n)
    index_ns = _synthetic_index(n)
    fee = 0.0
    test_start_idx = 150
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    sl, tp = 0.1, 0.1
    configs = build_config_grid([sl], [tp], [0])
    no_lev = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days, use_position_sizing=True, risk_per_trade_pct=1.0)
    with_lev = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days, use_position_sizing=True, risk_per_trade_pct=1.0, use_leverage=True, leverage=2.0)
    if no_lev["trades"] > 0 and not np.isnan(no_lev.get("equity_total_return", np.nan)):
        lev_eq = abs(with_lev.get("equity_total_return", 0))
        no_lev_eq = abs(no_lev.get("equity_total_return", 0))
        assert lev_eq >= no_lev_eq * 1.5, f"2x leverage should amplify equity return magnitude: no_lev={no_lev_eq}, lev={lev_eq}"


def test_phase2_liquidation_tracking():
    n = 50
    close = np.arange(100.0, 150.0, 1.0, dtype=np.float64)
    open_ = close - 0.5
    high = close + 1.0
    low = close - 1.0
    longs = np.zeros(n, dtype=np.bool_)
    longs[0] = True
    shorts = np.zeros(n, dtype=np.bool_)
    index_ns = _synthetic_index(n)
    fee = 0.0
    test_start_idx = 40
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    configs = build_config_grid([0.5], [0.01], [0])
    result = _batched_dense_result(open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days, use_liquidation=True, maintenance_margin_pct=0.5, use_leverage=True, leverage=2.0)
    assert result["trades"] > 0
    assert "liquidated_trades" in result


def test_phase2_all_features_enabled():
    n = 200
    open_, high, low, close = _synthetic_ohlc(n)
    longs, shorts = _entries_all(n)
    index_ns = _synthetic_index(n)
    fee = 0.00035
    test_start_idx = 150
    days = int((index_ns[-1] - index_ns[0]) // 86_400_000_000_000 + 1)
    test_days = int((index_ns[-1] - index_ns[test_start_idx]) // 86_400_000_000_000 + 1)
    configs = build_config_grid([0.04], [0.02], [0])
    result = _batched_dense_result(
        open_, high, low, close, longs, shorts, configs, fee, test_start_idx, index_ns, days, test_days,
        use_position_sizing=True, risk_per_trade_pct=2.0,
        use_leverage=True, leverage=3.0,
        use_liquidation=True, maintenance_margin_pct=0.5,
    )
    assert result["trades"] > 0
    assert not np.isnan(result.get("equity_total_return", np.nan))
    assert not np.isnan(result.get("equity_max_drawdown", np.nan))
    assert isinstance(result.get("liquidated_trades", 0), int)
