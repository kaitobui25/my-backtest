from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from app.backtest.indicators import adx, atr, ema, macd, rsi, squeeze_momentum, supertrend, wavetrend, williams_vix_fix
from app.backtest.strategy_params import VOL_EXPANSION_CONT_DEFAULTS


Signal = tuple[str, str, np.ndarray, np.ndarray, tuple[str, ...]]
DenseSignal = tuple[str, np.ndarray, np.ndarray, tuple[str, ...]]


@dataclass(frozen=True)
class SignalVariant:
    strategy: str
    params: str
    long_entries: np.ndarray
    short_entries: np.ndarray
    side_modes: tuple[str, ...]


def shift_signal(signal: pd.Series) -> np.ndarray:
    return signal.shift(1).fillna(False).to_numpy(dtype=np.bool_)


def side_mode_arrays(long_entries: np.ndarray, short_entries: np.ndarray, side_mode: str) -> tuple[np.ndarray, np.ndarray]:
    if side_mode == "long_only":
        return long_entries, np.zeros_like(short_entries)
    if side_mode == "short_only":
        return np.zeros_like(long_entries), short_entries
    return long_entries, short_entries


def build_signals(df: pd.DataFrame, timeframe: str, strategy_params: dict | None = None) -> list[Signal]:
    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    atr14 = atr(df, 14)
    atr100 = atr(df, 100)
    adx14 = adx(df, 14)
    rsi14 = rsi(close, 14)
    ema20 = ema(close, 20)
    ema34 = ema(close, 34)
    ema50 = ema(close, 50)
    ema100 = ema(close, 100)
    ema200 = ema(close, 200)
    ema300 = ema(close, 300)
    vol_ma = volume.rolling(50, min_periods=50).mean()
    vol_ok = volume >= vol_ma

    signals: list[Signal] = []

    for fast_name, fast_ema in [("34", ema34), ("50", ema50)]:
        for trend_name, trend_ema in [("200", ema200)]:
            for rsi_lo, rsi_hi, adx_min, atr_mult, use_vol in product(
                [40, 45],
                [55, 60],
                [12, 18],
                [0.60, 0.90],
                [False],
            ):
                near_ema = (close - fast_ema).abs() <= atr_mult * atr14
                lower_wick = np.minimum(open_, close) - low
                upper_wick = high - np.maximum(open_, close)
                bull_reject = (close > open_) & (lower_wick >= upper_wick)
                bear_reject = (close < open_) & (upper_wick >= lower_wick)
                long_sig = (close > trend_ema) & (ema50 > ema200) & near_ema & bull_reject & (rsi14 <= rsi_lo) & (adx14 >= adx_min)
                short_sig = (close < trend_ema) & (ema50 < ema200) & near_ema & bear_reject & (rsi14 >= rsi_hi) & (adx14 >= adx_min)
                if use_vol:
                    long_sig &= vol_ok
                    short_sig &= vol_ok
                params = f"fast={fast_name},trend={trend_name},rsi={rsi_lo}/{rsi_hi},adx_min={adx_min},atr_mult={atr_mult},vol={use_vol}"
                signals.append(("EMA_PULLBACK", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    for window, trend_name, trend_ema, adx_min, use_vol in product(
        [40, 80],
        ["200"],
        [ema200],
        [18, 24],
        [False],
    ):
        prev_high = high.rolling(window, min_periods=window).max().shift(1)
        prev_low = low.rolling(window, min_periods=window).min().shift(1)
        long_sig = (close > prev_high) & (close > trend_ema) & (adx14 >= adx_min)
        short_sig = (close < prev_low) & (close < trend_ema) & (adx14 >= adx_min)
        if use_vol:
            long_sig &= vol_ok
            short_sig &= vol_ok
        params = f"donchian={window},trend={trend_name},adx_min={adx_min},vol={use_vol}"
        signals.append(("DONCHIAN_BREAKOUT", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    for window, z, rsi_lo, rsi_hi, trend_mode, adx_max in product(
        [20, 40],
        [2.0, 2.4],
        [25, 30],
        [70, 75],
        ["trend", "range"],
        [None, 24],
    ):
        mid = close.rolling(window, min_periods=window).mean()
        std = close.rolling(window, min_periods=window).std()
        lower = mid - z * std
        upper = mid + z * std
        long_sig = (close < lower) & (rsi14 <= rsi_lo)
        short_sig = (close > upper) & (rsi14 >= rsi_hi)
        if trend_mode == "trend":
            long_sig &= close > ema200
            short_sig &= close < ema200
        elif trend_mode == "counter":
            long_sig &= close < ema200
            short_sig &= close > ema200
        elif trend_mode == "range":
            long_sig &= adx14 <= 18
            short_sig &= adx14 <= 18
        if adx_max is not None:
            long_sig &= adx14 <= adx_max
            short_sig &= adx14 <= adx_max
        params = f"bb={window},z={z},rsi={rsi_lo}/{rsi_hi},trend={trend_mode},adx_max={adx_max}"
        signals.append(("BB_RSI_REVERT", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    rng = (high - low).replace(0, np.nan)
    ibs = (close - low) / rng
    for ibs_lo, ibs_hi, trend_mode, adx_max in product(
        [0.05, 0.10, 0.20],
        [0.80, 0.90, 0.95],
        ["trend", "range"],
        [None, 24],
    ):
        long_sig = ibs <= ibs_lo
        short_sig = ibs >= ibs_hi
        if trend_mode == "trend":
            long_sig &= close > ema200
            short_sig &= close < ema200
        elif trend_mode == "counter":
            long_sig &= close < ema200
            short_sig &= close > ema200
        elif trend_mode == "range":
            long_sig &= adx14 <= 18
            short_sig &= adx14 <= 18
        if adx_max is not None:
            long_sig &= adx14 <= adx_max
            short_sig &= adx14 <= adx_max
        params = f"ibs={ibs_lo}/{ibs_hi},trend={trend_mode},adx_max={adx_max}"
        signals.append(("IBS_REVERT", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    range_pct = (high - low) / close
    range_ma = range_pct.rolling(50, min_periods=50).median()
    body = (close - open_).abs()
    body_ratio = body / (high - low).replace(0, np.nan)
    _vol_p = (strategy_params or {}).get("VOL_EXPANSION_CONT", VOL_EXPANSION_CONT_DEFAULTS)
    vol_range_mult = _vol_p.get("range_mult", VOL_EXPANSION_CONT_DEFAULTS["range_mult"])
    vol_trend_names = _vol_p.get("trend", VOL_EXPANSION_CONT_DEFAULTS["trend"])
    vol_adx_min = _vol_p.get("adx_min", VOL_EXPANSION_CONT_DEFAULTS["adx_min"])
    vol_close_extreme = _vol_p.get("close_extreme", VOL_EXPANSION_CONT_DEFAULTS["close_extreme"])
    vol_body_min = _vol_p.get("body_min", VOL_EXPANSION_CONT_DEFAULTS["body_min"])
    vol_trend_map: list[tuple[str, object]] = []
    for tn in vol_trend_names:
        if tn == "none":
            vol_trend_map.append(("none", None))
        elif tn == "ema100":
            vol_trend_map.append(("ema100", ema100))
        elif tn == "ema200":
            vol_trend_map.append(("ema200", ema200))
        elif tn == "200":
            vol_trend_map.append(("200", ema200))
    for mult, (trend_name, trend_ema), adx_min, close_extreme, body_min in product(
        vol_range_mult,
        vol_trend_map,
        vol_adx_min,
        vol_close_extreme,
        vol_body_min,
    ):
        strong_range = range_pct >= mult * range_ma
        long_sig = strong_range & (adx14 >= adx_min) & (body_ratio >= body_min) & (ibs >= close_extreme)
        short_sig = strong_range & (adx14 >= adx_min) & (body_ratio >= body_min) & (ibs <= 1 - close_extreme)
        if trend_ema is not None:
            long_sig &= close > trend_ema
            short_sig &= close < trend_ema
        params = f"range_mult={mult},trend={trend_name},adx_min={adx_min},close_extreme={close_extreme},body_min={body_min}"
        signals.append(("VOL_EXPANSION_CONT", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    for period, mult, trend_name, trend_ema in product(
        [10, 14, 20],
        [2.0, 3.0, 4.0],
        ["none", "200"],
        [None, ema200],
    ):
        trend = pd.Series(supertrend(df, period, mult), index=df.index)
        long_sig = (trend == 1) & (trend.shift(1) == -1)
        short_sig = (trend == -1) & (trend.shift(1) == 1)
        if trend_ema is not None:
            long_sig &= close > trend_ema
            short_sig &= close < trend_ema
        params = f"period={period},mult={mult},trend={trend_name}"
        signals.append(("SUPERTREND", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    for (fast, slow, sig_len), trend_name, trend_ema, adx_min in product(
        [(8, 21, 5), (12, 26, 9), (5, 34, 5)],
        ["none", "200"],
        [None, ema200],
        [12, 18],
    ):
        _, _, hist = macd(close, fast, slow, sig_len)
        long_sig = (hist > 0) & (hist.shift(1) <= 0) & (adx14 >= adx_min)
        short_sig = (hist < 0) & (hist.shift(1) >= 0) & (adx14 >= adx_min)
        if trend_ema is not None:
            long_sig &= close > trend_ema
            short_sig &= close < trend_ema
        params = f"macd={fast}/{slow}/{sig_len},trend={trend_name},adx_min={adx_min}"
        signals.append(("MACD_CROSS", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    for (n1, n2), (ob, os), trend_mode in product(
        [(10, 21), (10, 11), (14, 21)],
        [(53, -53), (60, -60)],
        ["trend", "range"],
    ):
        wt1, wt2 = wavetrend(df, n1, n2)
        long_sig = (wt1 < os) & (wt1 > wt2) & (wt1.shift(1) <= wt2.shift(1))
        short_sig = (wt1 > ob) & (wt1 < wt2) & (wt1.shift(1) >= wt2.shift(1))
        if trend_mode == "trend":
            long_sig &= close > ema200
            short_sig &= close < ema200
        elif trend_mode == "range":
            long_sig &= adx14 <= 18
            short_sig &= adx14 <= 18
        params = f"wt={n1}/{n2},ob_os={ob}/{os},trend={trend_mode}"
        signals.append(("WAVETREND", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    for length, bb_m, kc_m, trend_name, trend_ema in product(
        [20, 30],
        [2.0],
        [1.5, 2.0],
        ["none", "200"],
        [None, ema200],
    ):
        sqz_on, sqz_off, val = squeeze_momentum(df, length, bb_m, kc_m)
        squeeze_release = sqz_off & sqz_on.shift(1)
        long_sig = squeeze_release & (val > 0) & (val > val.shift(1))
        short_sig = squeeze_release & (val < 0) & (val < val.shift(1))
        if trend_ema is not None:
            long_sig &= close > trend_ema
            short_sig &= close < trend_ema
        params = f"sqz={length},bb={bb_m},kc={kc_m},trend={trend_name}"
        signals.append(("SQUEEZE_MOM", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    for pd_len, bbl, ph, trend_mode in product(
        [22, 30],
        [20],
        [0.85, 0.90],
        ["trend", "range"],
    ):
        _, alert = williams_vix_fix(df, pd_len, bbl, 2.0, 50, ph)
        long_sig = alert
        if trend_mode == "trend":
            long_sig &= close > ema200
        elif trend_mode == "range":
            long_sig &= adx14 <= 18
        short_sig = pd.Series(False, index=df.index)
        params = f"wvf={pd_len}/{bbl},ph={ph},trend={trend_mode}"
        signals.append(("WILLIAMS_VIX_FIX", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only",)))

    return signals


def _build_vol_expansion_dense_signals(df: pd.DataFrame) -> list[DenseSignal]:
    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]

    adx14 = adx(df, 14)
    ema100 = ema(close, 100)
    ema200 = ema(close, 200)
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

    signals: list[DenseSignal] = []
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
        signals.append((params, shift_signal(long_sig), shift_signal(short_sig), ("both", "long_only")))

    return signals


def _build_normal_variants(
    df: pd.DataFrame,
    timeframe: str,
    strategies: set[str] | None,
    strategy_params: dict | None = None,
) -> list[SignalVariant]:
    return [
        SignalVariant(strategy, params, le, se, sm)
        for strategy, params, le, se, sm in build_signals(df, timeframe, strategy_params)
        if strategies is None or strategy in strategies
    ]


def _build_dense_variants(
    df: pd.DataFrame,
    timeframe: str,
    strategies: set[str] | None,
    strategy_params: dict | None = None,
) -> list[SignalVariant]:
    results: list[SignalVariant] = []
    for strategy_name, mode_builders in STRATEGY_BUILDERS.items():
        if strategies is not None and strategy_name not in strategies:
            continue
        builder = mode_builders.get("dense_high_winrate")
        if builder is None:
            continue
        results.extend(builder(df, timeframe))
    return results


_MODE_BUILDERS: dict[str, Callable] = {
    "normal": _build_normal_variants,
    "dense_high_winrate": _build_dense_variants,
}


def build_signal_variants(
    df: pd.DataFrame,
    timeframe: str,
    mode: str,
    strategies: list[str] | set[str] | None = None,
    strategy_params: dict | None = None,
) -> list[SignalVariant]:
    if strategies is not None:
        strategies = set(strategies)

    if mode == "normal":
        return _build_normal_variants(df, timeframe, strategies, strategy_params)

    builder = _MODE_BUILDERS.get(mode)
    if builder is None:
        return []
    return builder(df, timeframe, strategies, strategy_params=strategy_params)


def _build_dense_vol_variants(df: pd.DataFrame, timeframe: str) -> list[SignalVariant]:
    return [
        SignalVariant("VOL_EXPANSION_CONT", params, le, se, sm)
        for params, le, se, sm in _build_vol_expansion_dense_signals(df)
    ]


STRATEGY_BUILDERS: dict[str, dict[str, Callable]] = {
    "VOL_EXPANSION_CONT": {
        "dense_high_winrate": _build_dense_vol_variants,
    },
}
