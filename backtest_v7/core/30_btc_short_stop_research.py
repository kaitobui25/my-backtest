from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path

import hashlib
import importlib.util
import sys

import numpy as np
import pandas as pd


SEARCH_PATH = Path(__file__).with_name("20_btc_strategy_search.py")
spec = importlib.util.spec_from_file_location("btc_strategy_search", SEARCH_PATH)
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
assert spec.loader is not None
spec.loader.exec_module(base)


OUT_DIR = base.ROOT / "my-data" / "backtest_v7" / "result" / "04_short_stop_research"
AUDIT_DIR = OUT_DIR / "audit"
VALIDATION_DIR = OUT_DIR / "validation"
for path in (OUT_DIR, AUDIT_DIR, VALIDATION_DIR):
    path.mkdir(parents=True, exist_ok=True)

TEST_START = pd.Timestamp("2025-01-01")

TIMEFRAMES = [
    "M5",
    "M6",
    "M10",
    "M12",
    "M15",
    "M20",
    "M30",
    "H1",
    "H2",
    "H3",
    "H4",
    "H6",
    "H8",
    "H12",
    "D1",
]

MIN_FULL_TRADES = {
    "M5": 280,
    "M6": 260,
    "M10": 220,
    "M12": 200,
    "M15": 170,
    "M20": 150,
    "M30": 120,
    "H1": 80,
    "H2": 55,
    "H3": 45,
    "H4": 34,
    "H6": 28,
    "H8": 24,
    "H12": 18,
    "D1": 12,
}

MIN_TEST_TRADES = {
    "M5": 65,
    "M6": 60,
    "M10": 50,
    "M12": 45,
    "M15": 40,
    "M20": 35,
    "M30": 28,
    "H1": 18,
    "H2": 13,
    "H3": 11,
    "H4": 8,
    "H6": 7,
    "H8": 6,
    "H12": 5,
    "D1": 4,
}


@dataclass(frozen=True)
class SignalSpec:
    strategy: str
    params: str
    long_entries: np.ndarray
    short_entries: np.ndarray


@dataclass(frozen=True)
class Candidate:
    timeframe: str
    strategy: str
    params: str
    side_mode: str
    sl: float
    tp: float
    max_hold: int
    signal_count: int
    trades: int
    win_rate: float
    total_return: float
    profit_factor: float
    expectancy: float
    max_drawdown: float
    avg_win: float
    avg_loss: float
    test_trades: int
    test_win_rate: float
    test_total_return: float
    test_profit_factor: float
    test_expectancy: float
    score: float


def pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def load_ohlc(timeframe: str) -> pd.DataFrame:
    return base.load_ohlc(timeframe)


def timeframe_minutes(timeframe: str) -> int:
    if timeframe.startswith("M"):
        return int(timeframe[1:])
    if timeframe.startswith("H"):
        return int(timeframe[1:]) * 60
    if timeframe == "D1":
        return 1440
    raise ValueError(timeframe)


def data_audit() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for timeframe in TIMEFRAMES:
        df = load_ohlc(timeframe)
        idx = pd.to_datetime(df.index)
        diffs = idx.to_series().diff().dropna()
        expected = pd.Timedelta(minutes=timeframe_minutes(timeframe))
        gap_count = int((diffs > expected * 1.5).sum())
        rows.append(
            {
                "timeframe": timeframe,
                "rows": len(df),
                "first": idx.min(),
                "last": idx.max(),
                "na_rows": int(df.isna().any(axis=1).sum()),
                "duplicate_index": int(idx.duplicated().sum()),
                "expected_step": str(expected),
                "max_gap": str(diffs.max()) if len(diffs) else "",
                "gap_count_gt_1_5x": gap_count,
                "close_return_pct": (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100,
            }
        )
    audit = pd.DataFrame(rows)
    audit.to_csv(OUT_DIR / "data_audit.csv", index=False)
    return audit


def regime_filter(
    long_sig: pd.Series,
    short_sig: pd.Series,
    close: pd.Series,
    ema50: pd.Series,
    ema200: pd.Series,
    adx14: pd.Series,
    regime: str,
    adx_limit: int | None,
) -> tuple[pd.Series, pd.Series]:
    if regime == "cycle":
        long_sig = long_sig & (close > ema200) & (ema50 > ema200)
        short_sig = short_sig & (close < ema200) & (ema50 < ema200)
    elif regime == "trend":
        long_sig = long_sig & (close > ema200)
        short_sig = short_sig & (close < ema200)
    elif regime == "range":
        limit = 20 if adx_limit is None else adx_limit
        long_sig = long_sig & (adx14 <= limit)
        short_sig = short_sig & (adx14 <= limit)
    elif regime == "all":
        pass
    else:
        raise ValueError(regime)
    return long_sig, short_sig


def add_signal(
    signals: list[SignalSpec],
    strategy: str,
    params: str,
    long_sig: pd.Series,
    short_sig: pd.Series,
) -> None:
    signals.append(
        SignalSpec(
            strategy=strategy,
            params=params,
            long_entries=base.shift_signal(long_sig),
            short_entries=base.shift_signal(short_sig),
        )
    )


def build_signals(df: pd.DataFrame, timeframe: str) -> list[SignalSpec]:
    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    atr14 = base.atr(df, 14)
    adx14 = base.adx(df, 14)
    rsi14 = base.rsi(close, 14)
    ema20 = base.ema(close, 20)
    ema34 = base.ema(close, 34)
    ema50 = base.ema(close, 50)
    ema200 = base.ema(close, 200)
    vol_ma = volume.rolling(50, min_periods=50).mean()
    vol_ok = volume >= vol_ma

    rng = (high - low).replace(0, np.nan)
    ibs = (close - low) / rng
    body = (close - open_).abs()
    body_ratio = body / rng
    lower_wick = np.minimum(open_, close) - low
    upper_wick = high - np.maximum(open_, close)
    bull_reject = (close > open_) & (lower_wick >= upper_wick)
    bear_reject = (close < open_) & (upper_wick >= lower_wick)

    signals: list[SignalSpec] = []

    # Mean reversion at candle extremes. This is the high-winrate family, but now
    # the search is forced to use much shorter fixed stops than the old D1 setup.
    minutes = timeframe_minutes(timeframe)

    for ibs_lo, ibs_hi, regime, adx_limit in product(
        [0.05, 0.10, 0.15],
        [0.85, 0.90, 0.95],
        ["cycle", "range"],
        [None, 20],
    ):
        if regime == "cycle" and adx_limit is not None:
            continue
        if regime == "range" and adx_limit is None:
            continue
        long_sig = ibs <= ibs_lo
        short_sig = ibs >= ibs_hi
        long_sig, short_sig = regime_filter(long_sig, short_sig, close, ema50, ema200, adx14, regime, adx_limit)
        params = f"ibs={ibs_lo}/{ibs_hi},regime={regime},adx_limit={adx_limit if regime == 'range' else None}"
        add_signal(signals, "IBS_REVERT_SHORT_SL", params, long_sig, short_sig)

    # Bollinger + RSI reversion. The regime filter keeps shorts mostly in weak
    # cycles or sideways markets, avoiding permanent short bias in BTC bull legs.
    for window, z, rsi_lo, rsi_hi, regime, adx_limit in product(
        [20, 40],
        [2.0, 2.2],
        [30, 35],
        [65, 70],
        ["cycle", "range"],
        [20],
    ):
        if rsi_lo + rsi_hi != 100:
            continue
        mid = close.rolling(window, min_periods=window).mean()
        std = close.rolling(window, min_periods=window).std()
        lower = mid - z * std
        upper = mid + z * std
        long_sig = (close < lower) & (rsi14 <= rsi_lo)
        short_sig = (close > upper) & (rsi14 >= rsi_hi)
        long_sig, short_sig = regime_filter(long_sig, short_sig, close, ema50, ema200, adx14, regime, adx_limit)
        params = f"bb={window},z={z},rsi={rsi_lo}/{rsi_hi},regime={regime},adx_limit={adx_limit if regime == 'range' else None}"
        add_signal(signals, "BB_RSI_REVERT_SHORT_SL", params, long_sig, short_sig)

    # Trend pullback with rejection candle. This targets higher payoff with
    # shorter stops, but is expected to have lower winrate than IBS.
    if minutes > 12:
        for fast_pair, rsi_lo, rsi_hi, atr_mult, adx_min in product(
            [("20", ema20), ("34", ema34), ("50", ema50)],
            [35, 40],
            [60, 65],
            [0.5, 0.8],
            [12, 18],
        ):
            if rsi_lo + rsi_hi != 100:
                continue
            fast_name, fast_ema = fast_pair
            near_ema = (close - fast_ema).abs() <= atr_mult * atr14
            long_sig = (close > ema200) & (ema50 > ema200) & near_ema & bull_reject & (rsi14 <= rsi_lo) & (adx14 >= adx_min)
            short_sig = (close < ema200) & (ema50 < ema200) & near_ema & bear_reject & (rsi14 >= rsi_hi) & (adx14 >= adx_min)
            params = f"fast={fast_name},rsi={rsi_lo}/{rsi_hi},atr_mult={atr_mult},adx_min={adx_min}"
            add_signal(signals, "EMA_REJECT_PULLBACK", params, long_sig, short_sig)

    # Donchian breakout and volatility expansion are included as profit-seeking
    # alternatives; the final ranking still enforces short stop and OOS filters.
    if minutes > 12:
        for window, adx_min, use_vol in product([20, 40, 80], [18, 24], [False]):
            prev_high = high.rolling(window, min_periods=window).max().shift(1)
            prev_low = low.rolling(window, min_periods=window).min().shift(1)
            long_sig = (close > prev_high) & (close > ema200) & (ema50 > ema200) & (adx14 >= adx_min)
            short_sig = (close < prev_low) & (close < ema200) & (ema50 < ema200) & (adx14 >= adx_min)
            if use_vol:
                long_sig = long_sig & vol_ok
                short_sig = short_sig & vol_ok
            params = f"donchian={window},adx_min={adx_min},vol={use_vol}"
            add_signal(signals, "DONCHIAN_CYCLE_BREAKOUT", params, long_sig, short_sig)

        range_pct = (high - low) / close
        range_med = range_pct.rolling(50, min_periods=50).median()
        for mult, extreme, adx_min in product([1.5, 2.0], [0.75, 0.85], [18]):
            strong_range = range_pct >= mult * range_med
            long_sig = (
                strong_range
                & (close > ema200)
                & (ema50 > ema200)
                & (adx14 >= adx_min)
                & (body_ratio >= 0.55)
                & (ibs >= extreme)
            )
            short_sig = (
                strong_range
                & (close < ema200)
                & (ema50 < ema200)
                & (adx14 >= adx_min)
                & (body_ratio >= 0.55)
                & (ibs <= 1 - extreme)
            )
            params = f"range_mult={mult},extreme={extreme},adx_min={adx_min}"
            add_signal(signals, "VOL_EXPANSION_CYCLE_CONT", params, long_sig, short_sig)

    print(f"{timeframe}: built {len(signals)} signal variants")
    return signals


def side_mode_arrays(long_entries: np.ndarray, short_entries: np.ndarray, side_mode: str) -> tuple[np.ndarray, np.ndarray]:
    if side_mode == "long_only":
        return long_entries, np.zeros_like(short_entries)
    if side_mode == "short_only":
        return np.zeros_like(long_entries), short_entries
    if side_mode == "both":
        return long_entries, short_entries
    raise ValueError(side_mode)


def grid_for_timeframe(timeframe: str) -> tuple[list[float], list[float], list[int]]:
    minutes = timeframe_minutes(timeframe)
    if minutes <= 30:
        return (
            [0.005, 0.0075, 0.010, 0.015, 0.020],
            [0.005, 0.010, 0.015, 0.020, 0.030],
            [24, 48, 96],
        )
    if minutes <= 180:
        return (
            [0.0075, 0.010, 0.015, 0.020, 0.030, 0.040],
            [0.0075, 0.010, 0.015, 0.020, 0.030, 0.050],
            [8, 16, 24, 48],
        )
    if minutes <= 720:
        return (
            [0.010, 0.015, 0.020, 0.030, 0.040],
            [0.010, 0.015, 0.020, 0.030, 0.050, 0.080],
            [4, 8, 12, 24],
        )
    return (
        [0.020, 0.030, 0.040, 0.060, 0.080, 0.100],
        [0.020, 0.030, 0.040, 0.060, 0.080, 0.100, 0.120],
        [3, 5, 10, 0],
    )


def score_candidate(
    sl: float,
    trades: int,
    win_rate: float,
    total_return: float,
    profit_factor: float,
    expectancy: float,
    max_drawdown: float,
    test_trades: int,
    test_win_rate: float,
    test_total_return: float,
    test_profit_factor: float,
    test_expectancy: float,
) -> float:
    if any(np.isnan(x) for x in [win_rate, profit_factor, expectancy, test_win_rate, test_profit_factor, test_expectancy]):
        return -np.inf
    return (
        0.75 * win_rate
        + 1.15 * test_win_rate
        + 9.0 * min(profit_factor, 5.0)
        + 14.0 * min(test_profit_factor, 5.0)
        + 0.045 * min(total_return, 800.0)
        + 0.090 * min(test_total_return, 300.0)
        + 32.0 * max(min(expectancy, 3.0), -1.0)
        + 48.0 * max(min(test_expectancy, 3.0), -1.0)
        - 620.0 * sl
        - 0.30 * abs(max_drawdown)
        + min(trades, 500) / 45.0
        + min(test_trades, 120) / 5.0
    )


def evaluate_timeframe(timeframe: str) -> list[Candidate]:
    df = load_ohlc(timeframe)
    print(f"\n{timeframe}: {len(df):,} bars from {df.index.min()} to {df.index.max()}")

    open_ = df["open"].to_numpy(np.float64)
    high = df["high"].to_numpy(np.float64)
    low = df["low"].to_numpy(np.float64)
    close = df["close"].to_numpy(np.float64)
    is_test_exit = df.index.to_numpy() >= np.datetime64(TEST_START)

    signals = build_signals(df, timeframe)
    sl_values, tp_values, max_holds = grid_for_timeframe(timeframe)
    candidates: list[Candidate] = []
    tested = 0

    for signal in signals:
        raw_count = int(signal.long_entries.sum() + signal.short_entries.sum())
        if raw_count < max(8, MIN_TEST_TRADES[timeframe]):
            continue
        for side_mode in ["both", "long_only", "short_only"]:
            longs, shorts = side_mode_arrays(signal.long_entries, signal.short_entries, side_mode)
            signal_count = int(longs.sum() + shorts.sum())
            if signal_count < max(8, MIN_TEST_TRADES[timeframe]):
                continue
            for sl, tp, max_hold in product(sl_values, tp_values, max_holds):
                if tp <= 2.5 * base.FEE_PER_SIDE:
                    continue
                returns, exits = base.simulate_trades(open_, high, low, close, longs, shorts, sl, tp, base.FEE_PER_SIDE, max_hold)
                tested += 1
                trades, wr, total_ret, pf, exp, max_dd, avg_win, avg_loss = base.metrics(returns)
                if (
                    trades < MIN_FULL_TRADES[timeframe]
                    or total_ret <= 0
                    or pf < 1.05
                    or exp <= 0
                    or wr < 50
                ):
                    continue

                test_returns = returns[is_test_exit[exits]]
                test_trades, test_wr, test_ret, test_pf, test_exp, _, _, _ = base.metrics(test_returns)
                if (
                    test_trades < MIN_TEST_TRADES[timeframe]
                    or test_ret <= 0
                    or test_pf < 1.02
                    or test_exp <= 0
                    or test_wr < 50
                ):
                    continue

                score = score_candidate(
                    sl,
                    trades,
                    wr,
                    total_ret,
                    pf,
                    exp,
                    max_dd,
                    test_trades,
                    test_wr,
                    test_ret,
                    test_pf,
                    test_exp,
                )
                candidates.append(
                    Candidate(
                        timeframe=timeframe,
                        strategy=signal.strategy,
                        params=signal.params,
                        side_mode=side_mode,
                        sl=sl,
                        tp=tp,
                        max_hold=max_hold,
                        signal_count=signal_count,
                        trades=trades,
                        win_rate=wr,
                        total_return=total_ret,
                        profit_factor=pf,
                        expectancy=exp,
                        max_drawdown=max_dd,
                        avg_win=avg_win,
                        avg_loss=avg_loss,
                        test_trades=test_trades,
                        test_win_rate=test_wr,
                        test_total_return=test_ret,
                        test_profit_factor=test_pf,
                        test_expectancy=test_exp,
                        score=score,
                    )
                )

    print(f"{timeframe}: tested {tested:,} configs, kept {len(candidates):,}")
    return candidates


def metrics_dict(returns: np.ndarray) -> dict[str, float]:
    trades, wr, total, pf, exp, dd, avg_win, avg_loss = base.metrics(returns)
    return {
        "trades": trades,
        "win_rate": wr,
        "total_return": total,
        "profit_factor": pf,
        "expectancy": exp,
        "max_drawdown": dd,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
    }


def simulate_records(
    df: pd.DataFrame,
    long_entries: np.ndarray,
    short_entries: np.ndarray,
    sl: float,
    tp: float,
    max_hold: int,
) -> pd.DataFrame:
    records = []
    in_pos = False
    direction = 0
    entry = 0.0
    entry_i = 0
    entry_time = None

    open_ = df["open"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    close = df["close"].to_numpy(float)
    times = df.index

    def excursions(exit_i: int) -> tuple[float, float]:
        lo = low[entry_i : exit_i + 1].min()
        hi = high[entry_i : exit_i + 1].max()
        if direction == 1:
            mae = (lo / entry - 1.0) * 100
            mfe = (hi / entry - 1.0) * 100
        else:
            mae = (entry / hi - 1.0) * 100
            mfe = (entry / lo - 1.0) * 100
        return mae, mfe

    for i in range(len(df)):
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
                        reason = "sl"
                    elif hit_tp:
                        exit_price = tp_price
                        reason = "tp"
                    else:
                        exit_price = close[i]
                        reason = "time"
                    ret = (exit_price / entry - 1.0) - 2.0 * base.FEE_PER_SIDE
                    mae, mfe = excursions(i)
                    records.append((entry_time, times[i], "long", entry, exit_price, held, reason, ret, mae, mfe))
                    in_pos = False
            else:
                sl_price = entry * (1.0 + sl)
                tp_price = entry * (1.0 - tp)
                hit_sl = high[i] >= sl_price
                hit_tp = low[i] <= tp_price
                if hit_sl or hit_tp or should_time_exit:
                    if hit_sl:
                        exit_price = sl_price
                        reason = "sl"
                    elif hit_tp:
                        exit_price = tp_price
                        reason = "tp"
                    else:
                        exit_price = close[i]
                        reason = "time"
                    ret = (entry / exit_price - 1.0) - 2.0 * base.FEE_PER_SIDE
                    mae, mfe = excursions(i)
                    records.append((entry_time, times[i], "short", entry, exit_price, held, reason, ret, mae, mfe))
                    in_pos = False

        if not in_pos:
            if long_entries[i]:
                in_pos = True
                direction = 1
                entry = open_[i]
                entry_i = i
                entry_time = times[i]
            elif short_entries[i]:
                in_pos = True
                direction = -1
                entry = open_[i]
                entry_i = i
                entry_time = times[i]

    if in_pos:
        if direction == 1:
            ret = (close[-1] / entry - 1.0) - 2.0 * base.FEE_PER_SIDE
            side = "long"
        else:
            ret = (entry / close[-1] - 1.0) - 2.0 * base.FEE_PER_SIDE
            side = "short"
        mae, mfe = excursions(len(df) - 1)
        records.append((entry_time, times[-1], side, entry, close[-1], len(df) - 1 - entry_i, "end", ret, mae, mfe))

    trades = pd.DataFrame(
        records,
        columns=["entry_time", "exit_time", "side", "entry", "exit", "bars_held", "exit_reason", "return", "mae_pct", "mfe_pct"],
    )
    if not trades.empty:
        trades["return_pct"] = trades["return"] * 100
        trades["equity"] = (1 + trades["return"]).cumprod()
        trades["win"] = trades["return"] > 0
    return trades


def period_breakdown(trades: pd.DataFrame, period: str) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    key = pd.to_datetime(trades["exit_time"]).dt.to_period(period).astype(str)
    rows = []
    for name, group in trades.groupby(key):
        stats = metrics_dict(group["return"].to_numpy(float))
        stats["period"] = name
        rows.append(stats)
    return pd.DataFrame(rows)[["period", "trades", "win_rate", "total_return", "profit_factor", "expectancy", "max_drawdown"]]


def validate_selected(all_candidates: pd.DataFrame) -> pd.DataFrame:
    selected = []
    balanced = all_candidates[all_candidates["sl"] <= 0.04]
    robust = balanced[(balanced["trades"] >= 50) & (balanced["test_trades"] >= 15)]
    buckets = {
        "top_score_sl4": balanced.sort_values(["score", "test_win_rate", "test_total_return"], ascending=[False, False, False]).head(4),
        "top_high_winrate_sl4": balanced.sort_values(
            ["test_win_rate", "win_rate", "test_total_return", "total_return", "sl"],
            ascending=[False, False, False, False, True],
        ).head(4),
        "robust_high_winrate": robust[
            (robust["win_rate"] >= 65)
            & (robust["test_win_rate"] >= 65)
            & (robust["profit_factor"] >= 1.10)
            & (robust["test_profit_factor"] >= 1.10)
        ]
        .sort_values(["test_win_rate", "win_rate", "test_total_return", "total_return"], ascending=[False, False, False, False])
        .head(6),
        "robust_high_profit": robust.sort_values(
            ["test_total_return", "total_return", "test_win_rate", "score"],
            ascending=[False, False, False, False],
        ).head(6),
        "balanced_short_only_profit": robust[
            (robust["side_mode"] == "short_only")
            & (robust["win_rate"] >= 75)
            & (robust["test_win_rate"] >= 80)
            & (robust["profit_factor"] >= 1.20)
            & (robust["test_profit_factor"] >= 1.50)
        ]
        .sort_values(["test_total_return", "total_return", "test_win_rate", "score"], ascending=[False, False, False, False])
        .head(4),
        "robust_long_only": robust[robust["side_mode"] == "long_only"]
        .sort_values(["test_win_rate", "test_total_return", "score"], ascending=[False, False, False])
        .head(4),
        "robust_short_only": robust[robust["side_mode"] == "short_only"]
        .sort_values(["test_win_rate", "test_total_return", "score"], ascending=[False, False, False])
        .head(4),
    }
    seen: set[tuple[object, ...]] = set()
    for bucket, frame in buckets.items():
        for _, row in frame.iterrows():
            key = (row["timeframe"], row["strategy"], row["params"], row["side_mode"], row["sl"], row["tp"], row["max_hold"])
            if key in seen:
                continue
            seen.add(key)
            item = row.to_dict()
            item["bucket"] = bucket
            selected.append(item)

    summaries = []
    signal_cache: dict[str, list[SignalSpec]] = {}
    df_cache: dict[str, pd.DataFrame] = {}
    for item in selected:
        timeframe = str(item["timeframe"])
        if timeframe not in df_cache:
            df_cache[timeframe] = load_ohlc(timeframe)
            signal_cache[timeframe] = build_signals(df_cache[timeframe], timeframe)
        signal = next(
            sig
            for sig in signal_cache[timeframe]
            if sig.strategy == item["strategy"] and sig.params == item["params"]
        )
        longs, shorts = side_mode_arrays(signal.long_entries, signal.short_entries, str(item["side_mode"]))
        trades = simulate_records(
            df_cache[timeframe],
            longs,
            shorts,
            float(item["sl"]),
            float(item["tp"]),
            int(item["max_hold"]),
        )
        slug_key = (
            f"{timeframe}|{item['side_mode']}|{item['strategy']}|{item['params']}|"
            f"{item['sl']}|{item['tp']}|{item['max_hold']}"
        )
        slug_hash = hashlib.sha1(slug_key.encode("utf-8")).hexdigest()[:8]
        slug = (
            f"{timeframe.lower()}_{item['side_mode']}_{item['strategy']}_"
            f"sl{int(float(item['sl']) * 10000):04d}_tp{int(float(item['tp']) * 10000):04d}_mh{int(item['max_hold'])}_{slug_hash}"
        ).lower()
        slug = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in slug)
        trades.to_csv(VALIDATION_DIR / f"{slug}_trades.csv", index=False)
        period_breakdown(trades, "Y").to_csv(VALIDATION_DIR / f"{slug}_yearly.csv", index=False)
        period_breakdown(trades, "M").to_csv(VALIDATION_DIR / f"{slug}_monthly.csv", index=False)
        side_rows = []
        for side, group in trades.groupby("side"):
            row = metrics_dict(group["return"].to_numpy(float))
            row["side"] = side
            side_rows.append(row)
        pd.DataFrame(side_rows).to_csv(VALIDATION_DIR / f"{slug}_side.csv", index=False)

        returns = trades["return"].to_numpy(float)
        test_mask = pd.to_datetime(trades["exit_time"]) >= TEST_START
        full = metrics_dict(returns)
        test = metrics_dict(trades.loc[test_mask, "return"].to_numpy(float))
        summaries.append(
            {
                "bucket": item["bucket"],
                "slug": slug,
                "timeframe": timeframe,
                "strategy": item["strategy"],
                "params": item["params"],
                "side_mode": item["side_mode"],
                "sl": item["sl"],
                "tp": item["tp"],
                "max_hold": item["max_hold"],
                "worst_mae_pct": trades["mae_pct"].min() if not trades.empty else np.nan,
                "avg_mae_pct": trades["mae_pct"].mean() if not trades.empty else np.nan,
                "best_mfe_pct": trades["mfe_pct"].max() if not trades.empty else np.nan,
                **{f"full_{k}": v for k, v in full.items()},
                **{f"test_{k}": v for k, v in test.items()},
            }
        )

    summary = pd.DataFrame(summaries)
    summary.to_csv(VALIDATION_DIR / "validation_summary.csv", index=False)
    return summary


def write_report(audit: pd.DataFrame, candidates: pd.DataFrame, validation: pd.DataFrame) -> None:
    strict = candidates[candidates["sl"] <= 0.02]
    balanced = candidates[candidates["sl"] <= 0.04]
    robust = balanced[(balanced["trades"] >= 50) & (balanced["test_trades"] >= 15)]
    high_wr = balanced[
        (balanced["win_rate"] >= 60)
        & (balanced["test_win_rate"] >= 60)
        & (balanced["profit_factor"] >= 1.15)
        & (balanced["test_profit_factor"] >= 1.08)
    ].sort_values(["test_win_rate", "win_rate", "test_total_return", "total_return", "sl"], ascending=[False, False, False, False, True])

    with (OUT_DIR / "summary.md").open("w", encoding="utf-8") as f:
        f.write("# BTCUSD Short-Stop Research\n\n")
        f.write(f"- Data root: `{base.DATA_ROOT}`\n")
        f.write(f"- Timeframes searched: `{', '.join(TIMEFRAMES)}`\n")
        f.write(f"- OOS/test starts: `{TEST_START.date()}`\n")
        f.write(f"- Cost model: `{base.FEE_PER_SIDE * 100:.3f}%` per side, `{base.FEE_PER_SIDE * 200:.3f}%` round trip.\n")
        f.write("- Entry signals are shifted by one candle and filled at next candle open.\n")
        f.write("- TP/SL use OHLC high/low. If TP and SL touch in the same candle, SL is assumed first.\n")
        f.write("- This search intentionally caps the grid around shorter fixed SL values than the previous D1/H4 work.\n\n")

        f.write("## Data Audit\n\n")
        f.write(audit.to_markdown(index=False))
        f.write("\n\n## Top Score Candidates, SL <= 4%\n\n")
        f.write(balanced.sort_values(["score", "test_win_rate", "test_total_return"], ascending=[False, False, False]).head(30).to_markdown(index=False))
        f.write("\n\n## High Winrate, SL <= 4%\n\n")
        f.write(high_wr.head(30).to_markdown(index=False) if not high_wr.empty else "No candidate passed this filter.\n")
        f.write("\n\n## Robust High Winrate, SL <= 4%, Trades >= 50, OOS Trades >= 15\n\n")
        robust_wr = robust[
            (robust["win_rate"] >= 65)
            & (robust["test_win_rate"] >= 65)
            & (robust["profit_factor"] >= 1.10)
            & (robust["test_profit_factor"] >= 1.10)
        ].sort_values(["test_win_rate", "win_rate", "test_total_return", "total_return"], ascending=[False, False, False, False])
        f.write(robust_wr.head(30).to_markdown(index=False) if not robust_wr.empty else "No candidate passed this filter.\n")
        f.write("\n\n## Robust High Profit, SL <= 4%, Trades >= 50, OOS Trades >= 15\n\n")
        robust_profit = robust.sort_values(
            ["test_total_return", "total_return", "test_win_rate", "score"],
            ascending=[False, False, False, False],
        )
        f.write(robust_profit.head(30).to_markdown(index=False) if not robust_profit.empty else "No candidate passed this filter.\n")
        f.write("\n\n## Strict Short Stop, SL <= 2%\n\n")
        f.write(
            strict.sort_values(["test_win_rate", "win_rate", "test_total_return", "score"], ascending=[False, False, False, False])
            .head(30)
            .to_markdown(index=False)
            if not strict.empty
            else "No candidate passed this filter.\n"
        )
        f.write("\n\n## Long Only\n\n")
        long_only = balanced[balanced["side_mode"] == "long_only"].sort_values(
            ["test_win_rate", "test_total_return", "score"], ascending=[False, False, False]
        )
        f.write(long_only.head(30).to_markdown(index=False) if not long_only.empty else "No candidate passed this filter.\n")
        f.write("\n\n## Short Only\n\n")
        short_only = balanced[balanced["side_mode"] == "short_only"].sort_values(
            ["test_win_rate", "test_total_return", "score"], ascending=[False, False, False]
        )
        f.write(short_only.head(30).to_markdown(index=False) if not short_only.empty else "No candidate passed this filter.\n")
        f.write("\n\n## Selected Validation\n\n")
        cols = [
            "bucket",
            "slug",
            "timeframe",
            "strategy",
            "params",
            "side_mode",
            "sl",
            "tp",
            "max_hold",
            "full_trades",
            "full_win_rate",
            "full_total_return",
            "full_profit_factor",
            "full_max_drawdown",
            "worst_mae_pct",
            "test_trades",
            "test_win_rate",
            "test_total_return",
            "test_profit_factor",
        ]
        f.write(validation[cols].to_markdown(index=False) if not validation.empty else "No selected validation.\n")
        f.write("\n")


def main() -> None:
    audit = data_audit()
    all_candidates: list[Candidate] = []
    for timeframe in TIMEFRAMES:
        all_candidates.extend(evaluate_timeframe(timeframe))

    if not all_candidates:
        print("No candidates survived filters.")
        return

    candidates = pd.DataFrame([c.__dict__ for c in all_candidates])
    candidates = candidates.sort_values(["score", "test_win_rate", "test_total_return"], ascending=[False, False, False])
    candidates.to_csv(AUDIT_DIR / "btc_short_stop_candidates_all.csv", index=False)

    balanced = candidates[candidates["sl"] <= 0.04]
    balanced.sort_values(["score", "test_win_rate", "test_total_return"], ascending=[False, False, False]).head(100).to_csv(
        OUT_DIR / "btc_short_stop_top_score.csv",
        index=False,
    )
    high_wr = balanced[
        (balanced["win_rate"] >= 60)
        & (balanced["test_win_rate"] >= 60)
        & (balanced["profit_factor"] >= 1.15)
        & (balanced["test_profit_factor"] >= 1.08)
    ].sort_values(["test_win_rate", "win_rate", "test_total_return", "total_return", "sl"], ascending=[False, False, False, False, True])
    high_wr.to_csv(OUT_DIR / "btc_short_stop_high_winrate.csv", index=False)

    candidates[candidates["side_mode"] == "long_only"].sort_values(
        ["test_win_rate", "test_total_return", "score"], ascending=[False, False, False]
    ).to_csv(OUT_DIR / "btc_short_stop_long_only.csv", index=False)
    candidates[candidates["side_mode"] == "short_only"].sort_values(
        ["test_win_rate", "test_total_return", "score"], ascending=[False, False, False]
    ).to_csv(OUT_DIR / "btc_short_stop_short_only.csv", index=False)
    robust = balanced[(balanced["trades"] >= 50) & (balanced["test_trades"] >= 15)]
    robust.sort_values(["test_win_rate", "win_rate", "test_total_return", "score"], ascending=[False, False, False, False]).to_csv(
        OUT_DIR / "btc_short_stop_robust_high_winrate.csv",
        index=False,
    )
    robust.sort_values(["test_total_return", "total_return", "test_win_rate", "score"], ascending=[False, False, False, False]).to_csv(
        OUT_DIR / "btc_short_stop_robust_high_profit.csv",
        index=False,
    )

    validation = validate_selected(candidates)
    write_report(audit, candidates, validation)

    print("\nTop score:")
    print(balanced.sort_values(["score", "test_win_rate", "test_total_return"], ascending=[False, False, False]).head(20).to_string(index=False))
    print("\nHigh winrate SL <= 4%:")
    print((high_wr.head(20) if not high_wr.empty else high_wr).to_string(index=False))
    print("\nSelected validation:")
    print(validation.to_string(index=False))
    print(f"\nSaved under {OUT_DIR}")


if __name__ == "__main__":
    main()
