from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from app.backtest.indicators import adx, atr, ema, macd, rsi, squeeze_momentum, supertrend, wavetrend, williams_vix_fix
from app.backtest.strategy_params import STRATEGY_PARAM_SCHEMAS


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


def _expand_range(value, step) -> list:
    if isinstance(value, (list, tuple)) and len(value) == 2 and step and step > 0:
        start, end = value
        count = int(round((end - start) / step)) + 1
        return [round(start + i * step, 10) for i in range(count)]
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _expand_select(value) -> list:
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _params_for(strategy_name: str, strategy_params: dict | None) -> dict[str, list]:
    user_params = (strategy_params or {}).get(strategy_name, {})
    schema = STRATEGY_PARAM_SCHEMAS.get(strategy_name, {})
    result: dict[str, list] = {}
    for param, meta in schema.items():
        value = user_params.get(param, list(meta["default"]))
        if meta["type"] == "range":
            result[param] = _expand_range(value, meta.get("step"))
        else:
            result[param] = _expand_select(value)
    return result


AUTO_TRENDS = ["none", "ema20", "ema50", "ema100", "ema200", "ema300"]


def _resolve_trend_selection(trend_names: list[str]) -> list[str]:
    if "auto" in trend_names:
        expanded = [t for t in trend_names if t != "auto"]
        expanded.extend(AUTO_TRENDS)
        seen: set[str] = set()
        deduped: list[str] = []
        for t in expanded:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        return deduped
    return trend_names


def build_signals(
    df: pd.DataFrame,
    timeframe: str,
    strategy_params: dict | None = None,
    strategies: set[str] | None = None,
) -> list[Signal]:
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
    rng = (high - low).replace(0, np.nan)
    ibs = (close - low) / rng
    selected_strategies = set(strategies) if strategies is not None else None

    def wants(strategy_name: str) -> bool:
        return selected_strategies is None or strategy_name in selected_strategies

    TREND_MAP: dict[str, np.ndarray | None] = {
        "none": None,
        "ema20": ema20,
        "ema50": ema50,
        "ema100": ema100,
        "ema200": ema200,
        "ema300": ema300,
    }

    signals: list[Signal] = []

    # ---- EMA_PULLBACK ----
    if wants("EMA_PULLBACK"):
        ep = _params_for("EMA_PULLBACK", strategy_params)
        ep_fast_map: dict[str, np.ndarray] = {"34": ema34, "50": ema50}
        ep_trend_names = _resolve_trend_selection(ep["trend"])
        for fast_name in ep["fast"]:
            fast_ema = ep_fast_map.get(fast_name)
            if fast_ema is None:
                continue
            for trend_name in ep_trend_names:
                trend_ema = TREND_MAP.get(trend_name)
                for rsi_lo, rsi_hi, adx_min, atr_mult, use_vol_str in product(
                    ep["rsi_lo"], ep["rsi_hi"], ep["adx_min"], ep["atr_mult"], ep["use_vol"]
                ):
                    use_vol = use_vol_str == "true"
                    near_ema = (close - fast_ema).abs() <= atr_mult * atr14
                    lower_wick = np.minimum(open_, close) - low
                    upper_wick = high - np.maximum(open_, close)
                    bull_reject = (close > open_) & (lower_wick >= upper_wick)
                    bear_reject = (close < open_) & (upper_wick >= lower_wick)
                    base_long = (ema50 > ema200) & near_ema & bull_reject & (rsi14 <= rsi_lo) & (adx14 >= adx_min)
                    base_short = (ema50 < ema200) & near_ema & bear_reject & (rsi14 >= rsi_hi) & (adx14 >= adx_min)
                    if trend_ema is not None:
                        long_sig = (close > trend_ema) & base_long
                        short_sig = (close < trend_ema) & base_short
                    else:
                        long_sig = base_long
                        short_sig = base_short
                    if use_vol:
                        long_sig &= vol_ok
                        short_sig &= vol_ok
                    params = f"fast={fast_name},trend={trend_name},rsi={rsi_lo}/{rsi_hi},adx_min={adx_min},atr_mult={atr_mult},vol={use_vol_str}"
                    signals.append(("EMA_PULLBACK", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    # ---- DONCHIAN_BREAKOUT ----
    if wants("DONCHIAN_BREAKOUT"):
        db = _params_for("DONCHIAN_BREAKOUT", strategy_params)
        dc_trend_names = _resolve_trend_selection(db["trend"])
        for window_str in db["window"]:
            window = int(window_str)
            for trend_name in dc_trend_names:
                trend_ema = TREND_MAP.get(trend_name)
                for adx_min, use_vol_str in product(db["adx_min"], db["use_vol"]):
                    use_vol = use_vol_str == "true"
                    prev_high = high.rolling(window, min_periods=window).max().shift(1)
                    prev_low = low.rolling(window, min_periods=window).min().shift(1)
                    long_sig = (close > prev_high) & (adx14 >= adx_min)
                    short_sig = (close < prev_low) & (adx14 >= adx_min)
                    if trend_ema is not None:
                        long_sig &= close > trend_ema
                        short_sig &= close < trend_ema
                    if use_vol:
                        long_sig &= vol_ok
                        short_sig &= vol_ok
                    params = f"donchian={window},trend={trend_name},adx_min={adx_min},vol={use_vol_str}"
                    signals.append(("DONCHIAN_BREAKOUT", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    # ---- BB_RSI_REVERT ----
    if wants("BB_RSI_REVERT"):
        bb = _params_for("BB_RSI_REVERT", strategy_params)
        for window_str in bb["window"]:
            window = int(window_str)
            for z_str in bb["z"]:
                z = float(z_str)
                for rsi_lo, rsi_hi in product(bb["rsi_lo"], bb["rsi_hi"]):
                    for trend_mode in bb["trend_mode"]:
                        for adx_max_str in bb["adx_max"]:
                            adx_max = int(adx_max_str) if adx_max_str != "none" else None
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
                            params = f"bb={window},z={z},rsi={rsi_lo}/{rsi_hi},trend={trend_mode},adx_max={adx_max_str}"
                            signals.append(("BB_RSI_REVERT", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    # ---- IBS_REVERT ----
    if wants("IBS_REVERT"):
        ib = _params_for("IBS_REVERT", strategy_params)
        for ibs_lo_str in ib["ibs_lo"]:
            ibs_lo = float(ibs_lo_str)
            for ibs_hi_str in ib["ibs_hi"]:
                ibs_hi = float(ibs_hi_str)
                for trend_mode in ib["trend_mode"]:
                    for adx_max_str in ib["adx_max"]:
                        adx_max = int(adx_max_str) if adx_max_str != "none" else None
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
                        params = f"ibs={ibs_lo}/{ibs_hi},trend={trend_mode},adx_max={adx_max_str}"
                        signals.append(("IBS_REVERT", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    # ---- VOL_EXPANSION_CONT ----
    if wants("VOL_EXPANSION_CONT"):
        for params, long_entries, short_entries, side_modes in _iter_vol_expansion_signals(
            df, strategy_params, ("long_only", "both")
        ):
            signals.append(("VOL_EXPANSION_CONT", params, long_entries, short_entries, side_modes))

    # ---- SUPERTREND ----
    if wants("SUPERTREND"):
        sp = _params_for("SUPERTREND", strategy_params)
        sp_trend_names = _resolve_trend_selection(sp["trend"])
        for period_str in sp["period"]:
            period = int(period_str)
            for mult_str in sp["mult"]:
                mult = float(mult_str)
                for trend_name in sp_trend_names:
                    trend_ema = TREND_MAP.get(trend_name)
                    trend = pd.Series(supertrend(df, period, mult), index=df.index)
                    long_sig = (trend == 1) & (trend.shift(1) == -1)
                    short_sig = (trend == -1) & (trend.shift(1) == 1)
                    if trend_ema is not None:
                        long_sig &= close > trend_ema
                        short_sig &= close < trend_ema
                    params = f"period={period},mult={mult},trend={trend_name}"
                    signals.append(("SUPERTREND", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    # ---- MACD_CROSS ----
    if wants("MACD_CROSS"):
        mc = _params_for("MACD_CROSS", strategy_params)
        mc_trend_names = _resolve_trend_selection(mc["trend"])
        for preset_str in mc["preset"]:
            parts = [int(x) for x in preset_str.split("/")]
            fast, slow, sig_len = parts[0], parts[1], parts[2]
            for trend_name in mc_trend_names:
                trend_ema = TREND_MAP.get(trend_name)
                for adx_min in mc["adx_min"]:
                    _, _, hist = macd(close, fast, slow, sig_len)
                    long_sig = (hist > 0) & (hist.shift(1) <= 0) & (adx14 >= adx_min)
                    short_sig = (hist < 0) & (hist.shift(1) >= 0) & (adx14 >= adx_min)
                    if trend_ema is not None:
                        long_sig &= close > trend_ema
                        short_sig &= close < trend_ema
                    params = f"macd={fast}/{slow}/{sig_len},trend={trend_name},adx_min={adx_min}"
                    signals.append(("MACD_CROSS", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    # ---- WAVETREND ----
    if wants("WAVETREND"):
        wt = _params_for("WAVETREND", strategy_params)
        for preset_str in wt["preset"]:
            ns = [int(x) for x in preset_str.split("/")]
            n1, n2 = ns[0], ns[1]
            for ob_os_str in wt["ob_os"]:
                obs = [int(x) for x in ob_os_str.split("/")]
                ob, os = obs[0], obs[1]
                for trend_mode in wt["trend_mode"]:
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

    # ---- SQUEEZE_MOM ----
    if wants("SQUEEZE_MOM"):
        sq = _params_for("SQUEEZE_MOM", strategy_params)
        sq_trend_names = _resolve_trend_selection(sq["trend"])
        for length_str in sq["length"]:
            length = int(length_str)
            for bb_m_str in sq["bb_mult"]:
                bb_m = float(bb_m_str)
                for kc_m_str in sq["kc_mult"]:
                    kc_m = float(kc_m_str)
                    for trend_name in sq_trend_names:
                        trend_ema = TREND_MAP.get(trend_name)
                        sqz_on, sqz_off, val = squeeze_momentum(df, length, bb_m, kc_m)
                        squeeze_release = sqz_off & sqz_on.shift(1)
                        long_sig = squeeze_release & (val > 0) & (val > val.shift(1))
                        short_sig = squeeze_release & (val < 0) & (val < val.shift(1))
                        if trend_ema is not None:
                            long_sig &= close > trend_ema
                            short_sig &= close < trend_ema
                        params = f"sqz={length},bb={bb_m},kc={kc_m},trend={trend_name}"
                        signals.append(("SQUEEZE_MOM", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    # ---- WILLIAMS_VIX_FIX ----
    if wants("WILLIAMS_VIX_FIX"):
        wv = _params_for("WILLIAMS_VIX_FIX", strategy_params)
        for pd_len_str in wv["pd_len"]:
            pd_len = int(pd_len_str)
            for bbl_str in wv["bbl"]:
                bbl = int(bbl_str)
                for ph_str in wv["ph"]:
                    ph = float(ph_str)
                    for trend_mode in wv["trend_mode"]:
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


def _iter_vol_expansion_signals(
    df: pd.DataFrame,
    strategy_params: dict | None,
    side_modes: tuple[str, ...],
):
    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]

    adx14 = adx(df, 14)
    ema100 = ema(close, 100)
    ema200 = ema(close, 200)
    ema20 = ema(close, 20)
    ema50 = ema(close, 50)
    ema300 = ema(close, 300)

    TREND_MAP: dict[str, np.ndarray | None] = {
        "none": None,
        "ema20": ema20,
        "ema50": ema50,
        "ema100": ema100,
        "ema200": ema200,
        "ema300": ema300,
    }

    vp = _params_for("VOL_EXPANSION_CONT", strategy_params)
    vol_trend_names = _resolve_trend_selection(vp["trend"])
    vol_trend_map: list[tuple[str, object]] = []
    for tn in vol_trend_names:
        ema_arr = TREND_MAP.get(tn)
        vol_trend_map.append((tn, ema_arr))

    rng = (high - low).replace(0, np.nan)
    ibs = (close - low) / rng
    range_pct = (high - low) / close
    range_ma = range_pct.rolling(50, min_periods=50).median()
    body_ratio = (close - open_).abs() / rng

    for mult, (trend_name, trend_ema), adx_min, close_extreme, body_min in product(
        vp["range_mult"],
        vol_trend_map,
        vp["adx_min"],
        vp["close_extreme"],
        vp["body_min"],
    ):
        strong_range = range_pct >= mult * range_ma
        long_sig = strong_range & (body_ratio >= body_min) & (ibs >= close_extreme) & (adx14 >= adx_min)
        short_sig = strong_range & (body_ratio >= body_min) & (ibs <= 1.0 - close_extreme) & (adx14 >= adx_min)
        if trend_ema is not None:
            long_sig &= close > trend_ema
            short_sig &= close < trend_ema

        params = (
            f"range_mult={mult},trend={trend_name},adx_min={adx_min},"
            f"close_extreme={close_extreme},body_min={body_min}"
        )
        yield params, shift_signal(long_sig), shift_signal(short_sig), side_modes


def _build_vol_expansion_dense_signals(df: pd.DataFrame, strategy_params: dict | None = None) -> list[DenseSignal]:
    return list(_iter_vol_expansion_signals(df, strategy_params, ("both", "long_only")))


def _build_normal_variants(
    df: pd.DataFrame,
    timeframe: str,
    strategies: set[str] | None,
    strategy_params: dict | None = None,
) -> list[SignalVariant]:
    return [
        SignalVariant(strategy, params, le, se, sm)
        for strategy, params, le, se, sm in build_signals(df, timeframe, strategy_params, strategies)
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
        results.extend(builder(df, timeframe, strategy_params=strategy_params))
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


def _build_dense_vol_variants(df: pd.DataFrame, timeframe: str, strategy_params: dict | None = None) -> list[SignalVariant]:
    return [
        SignalVariant("VOL_EXPANSION_CONT", params, le, se, sm)
        for params, le, se, sm in _build_vol_expansion_dense_signals(df, strategy_params)
    ]


STRATEGY_BUILDERS: dict[str, dict[str, Callable]] = {
    "VOL_EXPANSION_CONT": {
        "dense_high_winrate": _build_dense_vol_variants,
    },
}


def iter_signal_variants(
    df: pd.DataFrame,
    timeframe: str,
    mode: str,
    strategies: list[str] | set[str] | None = None,
    strategy_params: dict | None = None,
    max_signal_variants: int | None = None,
):
    selected = set(strategies) if strategies is not None else None
    emitted = 0

    def can_emit(strategy_name: str) -> bool:
        return selected is None or strategy_name in selected

    def yield_variant(variant: SignalVariant):
        nonlocal emitted
        if max_signal_variants is not None and emitted >= max_signal_variants:
            return None
        emitted += 1
        return variant

    if mode == "normal":
        for strategy_name in STRATEGY_PARAM_SCHEMAS:
            if not can_emit(strategy_name):
                continue
            if strategy_name == "VOL_EXPANSION_CONT":
                vol_iter = _iter_vol_expansion_signals(df, strategy_params, ("long_only", "both"))
                while max_signal_variants is None or emitted < max_signal_variants:
                    try:
                        params, le, se, sm = next(vol_iter)
                    except StopIteration:
                        break
                    variant = yield_variant(SignalVariant(strategy_name, params, le, se, sm))
                    if variant is None:
                        return
                    yield variant
                continue
            for strategy, params, le, se, sm in build_signals(df, timeframe, strategy_params, {strategy_name}):
                variant = yield_variant(SignalVariant(strategy, params, le, se, sm))
                if variant is None:
                    return
                yield variant
        return

    if mode == "dense_high_winrate":
        if can_emit("VOL_EXPANSION_CONT"):
            vol_iter = _iter_vol_expansion_signals(df, strategy_params, ("both", "long_only"))
            while max_signal_variants is None or emitted < max_signal_variants:
                try:
                    params, le, se, sm = next(vol_iter)
                except StopIteration:
                    break
                variant = yield_variant(SignalVariant("VOL_EXPANSION_CONT", params, le, se, sm))
                if variant is None:
                    return
                yield variant
