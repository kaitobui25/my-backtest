from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
import importlib.util
import sys

import numpy as np
import pandas as pd
from numba import njit


SEARCH_PATH = Path(__file__).with_name("20_btc_strategy_search.py")
spec = importlib.util.spec_from_file_location("btc_strategy_search", SEARCH_PATH)
search = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = search
assert spec.loader is not None
spec.loader.exec_module(search)

TEST_START_NS = np.datetime64(search.TEST_START).astype("datetime64[ns]").astype(np.int64)

OUT_DIR = search.OUT_DIR / "dense_high_winrate"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TIMEFRAMES = ["M15", "M30", "H1"]
MIN_WIN_RATE = 75.0
MIN_TEST_WIN_RATE = 75.0
MIN_TRADES_PER_DAY = 0.5
MIN_TEST_TRADES_PER_DAY = 0.5


@dataclass(frozen=True)
class DenseCandidate:
    timeframe: str
    strategy: str
    params: str
    side_mode: str
    sl: float
    tp: float
    max_hold: int
    trades: int
    win_rate: float
    total_return: float
    profit_factor: float
    expectancy: float
    max_drawdown: float
    avg_win: float
    avg_loss: float
    trades_per_day: float
    max_gap_days: float
    avg_bars_held: float
    test_trades: int
    test_win_rate: float
    test_total_return: float
    test_profit_factor: float
    test_expectancy: float
    test_trades_per_day: float
    test_max_gap_days: float
    test_avg_bars_held: float
    score: float


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


def build_vol_expansion_signals(df: pd.DataFrame) -> list[tuple[str, np.ndarray, np.ndarray, tuple[str, ...]]]:
    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]

    adx14 = search.adx(df, 14)
    ema100 = search.ema(close, 100)
    ema200 = search.ema(close, 200)
    rng = (high - low).replace(0, np.nan)
    ibs = (close - low) / rng
    range_pct = (high - low) / close
    range_ma = range_pct.rolling(50, min_periods=50).median()
    body_ratio = (close - open_).abs() / rng

    trend_filters = [
        ("none", None),
        ("ema100", ema100),
        ("ema200", ema200),
    ]

    signals: list[tuple[str, np.ndarray, np.ndarray, tuple[str, ...]]] = []
    for range_mult, (trend_name, trend_ema), adx_min, close_extreme, body_min in product(
        [0.8, 1.0, 1.2, 1.5, 2.0],
        trend_filters,
        [8, 12, 18, 24],
        [0.60, 0.65, 0.70, 0.75, 0.85],
        [0.45, 0.55],
    ):
        strong_range = range_pct >= range_mult * range_ma
        long_sig = strong_range & (body_ratio >= body_min) & (ibs >= close_extreme) & (adx14 >= adx_min)
        short_sig = strong_range & (body_ratio >= body_min) & (ibs <= 1.0 - close_extreme) & (adx14 >= adx_min)
        if trend_ema is not None:
            long_sig &= close > trend_ema
            short_sig &= close < trend_ema

        params = (
            f"range_mult={range_mult},trend={trend_name},adx_min={adx_min},"
            f"close_extreme={close_extreme},body_min={body_min}"
        )
        signals.append((params, search.shift_signal(long_sig), search.shift_signal(short_sig), ("both", "long_only")))

    return signals


def grid_for_timeframe(timeframe: str) -> tuple[list[float], list[float], list[int]]:
    if timeframe == "M15":
        return (
            [0.020, 0.030, 0.040, 0.060, 0.080],
            [0.0050, 0.0075, 0.0100, 0.0150, 0.0200, 0.0300],
            [16, 32, 64, 96],
        )
    if timeframe == "M30":
        return (
            [0.020, 0.030, 0.040, 0.060, 0.080],
            [0.0050, 0.0075, 0.0100, 0.0150, 0.0200, 0.0300],
            [8, 16, 32, 48],
        )
    return (
        [0.020, 0.030, 0.040, 0.060, 0.080, 0.100],
        [0.0050, 0.0075, 0.0100, 0.0150, 0.0200, 0.0300],
        [4, 8, 12, 24],
    )


def score_candidate(row: dict[str, float]) -> float:
    return (
        0.35 * row["win_rate"]
        + 0.65 * row["test_win_rate"]
        + 18.0 * min(row["profit_factor"], 2.0)
        + 28.0 * min(row["test_profit_factor"], 2.0)
        + 45.0 * max(row["expectancy"], -0.1)
        + 75.0 * max(row["test_expectancy"], -0.1)
        + 0.04 * row["test_total_return"]
        - 0.20 * abs(row["max_drawdown"])
        + 2.0 * min(row["test_trades_per_day"], 3.0)
    )


def evaluate_timeframe(timeframe: str) -> list[DenseCandidate]:
    df = search.load_ohlc(timeframe)
    open_ = df["open"].to_numpy(np.float64)
    high = df["high"].to_numpy(np.float64)
    low = df["low"].to_numpy(np.float64)
    close = df["close"].to_numpy(np.float64)
    index_ns = df.index.astype("datetime64[ns]").asi8.astype(np.int64, copy=False)
    is_test_exit = index_ns >= TEST_START_NS
    days = calendar_days_ns(index_ns)
    test_days = calendar_days_ns(index_ns, is_test_exit)
    min_trades = int(np.ceil(days * MIN_TRADES_PER_DAY))
    min_test_trades = int(np.ceil(test_days * MIN_TEST_TRADES_PER_DAY))

    print(f"\n{timeframe}: {len(df):,} bars, {days} days, min trades {min_trades}, test min {min_test_trades}")

    signals = build_vol_expansion_signals(df)
    sl_values, tp_values, max_holds = grid_for_timeframe(timeframe)

    candidates: list[DenseCandidate] = []
    tested = 0
    for params, long_entries, short_entries, side_modes in signals:
        if long_entries.sum() + short_entries.sum() < min_trades:
            continue
        for side_mode in side_modes:
            longs, shorts = search.side_mode_arrays(long_entries, short_entries, side_mode)
            if longs.sum() + shorts.sum() < min_trades:
                continue
            for sl, tp, max_hold in product(sl_values, tp_values, max_holds):
                if tp <= 2.5 * search.FEE_PER_SIDE:
                    continue
                returns, entries, exits, bars_held = simulate_trades_with_entries(
                    open_, high, low, close, longs, shorts, sl, tp, search.FEE_PER_SIDE, max_hold
                )
                tested += 1
                trades, wr, total_ret, pf, exp, max_dd, avg_win, avg_loss = search.metrics(returns)
                if (
                    trades < min_trades
                    or wr < MIN_WIN_RATE
                    or total_ret <= 0
                    or pf < 1.0
                    or exp <= 0
                ):
                    continue

                test_mask = is_test_exit[exits]
                test_returns = returns[test_mask]
                test_entries = entries[test_mask]
                test_bars_held = bars_held[test_mask]
                test_trades, test_wr, test_ret, test_pf, test_exp, _, _, _ = search.metrics(test_returns)
                if (
                    test_trades < min_test_trades
                    or test_wr < MIN_TEST_WIN_RATE
                    or test_ret <= 0
                    or test_pf < 1.0
                    or test_exp <= 0
                ):
                    continue

                row = {
                    "win_rate": wr,
                    "profit_factor": pf,
                    "expectancy": exp,
                    "test_win_rate": test_wr,
                    "test_total_return": test_ret,
                    "test_profit_factor": test_pf,
                    "test_expectancy": test_exp,
                    "max_drawdown": max_dd,
                    "test_trades_per_day": test_trades / test_days,
                }
                candidates.append(
                    DenseCandidate(
                        timeframe=timeframe,
                        strategy="VOL_EXPANSION_CONT",
                        params=params,
                        side_mode=side_mode,
                        sl=sl,
                        tp=tp,
                        max_hold=max_hold,
                        trades=trades,
                        win_rate=wr,
                        total_return=total_ret,
                        profit_factor=pf,
                        expectancy=exp,
                        max_drawdown=max_dd,
                        avg_win=avg_win,
                        avg_loss=avg_loss,
                        trades_per_day=trades / days,
                        max_gap_days=max_gap_days_ns(index_ns, entries),
                        avg_bars_held=float(np.mean(bars_held)) if bars_held.size else np.nan,
                        test_trades=test_trades,
                        test_win_rate=test_wr,
                        test_total_return=test_ret,
                        test_profit_factor=test_pf,
                        test_expectancy=test_exp,
                        test_trades_per_day=test_trades / test_days,
                        test_max_gap_days=max_gap_days_ns(index_ns, test_entries),
                        test_avg_bars_held=float(np.mean(test_bars_held)) if test_bars_held.size else np.nan,
                        score=score_candidate(row),
                    )
                )

    print(f"{timeframe}: tested {tested:,} configs, kept {len(candidates):,}")
    return candidates


def write_report(df: pd.DataFrame) -> None:
    report = OUT_DIR / "summary.md"
    with report.open("w", encoding="utf-8") as f:
        f.write("# Dense High-Winrate BTCUSD Search\n\n")
        f.write(f"- Data root: `{search.DATA_ROOT}`\n")
        f.write(f"- Test/OOS starts: `{search.TEST_START.date()}`\n")
        f.write(f"- Fee model: `{search.FEE_PER_SIDE * 100:.3f}%` per side, `{search.FEE_PER_SIDE * 200:.3f}%` round trip.\n")
        f.write("- Entry signals are shifted one candle and filled at next candle open.\n")
        f.write("- TP/SL use OHLC high/low. If TP and SL touch in the same candle, SL is assumed first.\n")
        f.write("- `max_hold` is capped at one day for each timeframe.\n")
        f.write(f"- Frequency filter: full and OOS `trades_per_day >= {MIN_TRADES_PER_DAY}`.\n")
        f.write(f"- Winrate filter: full and OOS winrate >= `{MIN_WIN_RATE}%`.\n")
        f.write("- Equity compounds trade returns only, without mark-to-market drawdown between exits.\n\n")

        if df.empty:
            f.write("No candidate passed the filters.\n")
            return

        cols = [
            "timeframe",
            "params",
            "side_mode",
            "sl",
            "tp",
            "max_hold",
            "trades",
            "win_rate",
            "profit_factor",
            "total_return",
            "max_drawdown",
            "trades_per_day",
            "max_gap_days",
            "test_trades",
            "test_win_rate",
            "test_profit_factor",
            "test_total_return",
            "test_trades_per_day",
            "test_max_gap_days",
            "score",
        ]
        f.write("## Top Candidates\n\n")
        f.write(df[cols].head(30).to_markdown(index=False))
        f.write("\n")


def main() -> None:
    all_candidates: list[DenseCandidate] = []
    for timeframe in TIMEFRAMES:
        all_candidates.extend(evaluate_timeframe(timeframe))

    if not all_candidates:
        empty = pd.DataFrame()
        empty.to_csv(OUT_DIR / "candidates.csv", index=False)
        write_report(empty)
        print("No candidates survived filters.")
        return

    df = pd.DataFrame([c.__dict__ for c in all_candidates])
    df = df.sort_values(["score", "test_total_return", "test_profit_factor"], ascending=[False, False, False])
    df.to_csv(OUT_DIR / "candidates.csv", index=False)
    write_report(df)

    print("\nTop candidates:")
    print(df.head(20).to_string(index=False))
    strict_gap = df[(df["max_gap_days"] <= 2.0) & (df["test_max_gap_days"] <= 2.0)]
    print(f"\nStrict max-gap <= 2 days candidates: {len(strict_gap)}")
    if not strict_gap.empty:
        print(strict_gap.head(20).to_string(index=False))
    print(f"\nSaved under {OUT_DIR}")


if __name__ == "__main__":
    main()
