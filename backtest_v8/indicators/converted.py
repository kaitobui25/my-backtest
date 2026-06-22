from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from .base import (
    IndicatorMetadata,
    SignalSet,
    adx,
    apply_regime_filter,
    atr,
    crossover,
    crossunder,
    ema,
    param_product,
    rolling_linreg_last,
    rsi,
    sma,
    true_range,
)


class IBSReversion:
    metadata = IndicatorMetadata(
        name="ibs_reversion",
        display_name="IBS Reversion",
        source="Python implementation from backtest_v7 research family",
        conversion_notes="Uses only current and historical OHLC; runner shifts entries by entry_lag_bars.",
        repaint_risk="low",
    )

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        close = df["close"]
        rng = (df["high"] - df["low"]).replace(0, np.nan)
        ibs = (close - df["low"]) / rng
        adx14 = adx(df, 14)
        signals: list[SignalSet] = []
        for p in param_product(params, ["ibs_low", "ibs_high", "regime", "adx_max", "ema_fast", "ema_slow"]):
            fast = ema(close, int(p["ema_fast"]))
            slow = ema(close, int(p["ema_slow"]))
            long_sig = ibs <= float(p["ibs_low"])
            short_sig = ibs >= float(p["ibs_high"])
            long_sig, short_sig = apply_regime_filter(long_sig, short_sig, close, fast, slow, adx14, str(p["regime"]), p["adx_max"])
            signals.append(SignalSet(self.metadata.name, "ibs_reversion", p, long_sig, short_sig))
        return signals


class BBRsiReversion:
    metadata = IndicatorMetadata(
        name="bb_rsi_reversion",
        display_name="Bollinger + RSI Reversion",
        source="Python implementation from simple BB/RSI formulas and backtest_v7 research family",
        converted_from=("bb.pine", "rsi.pine"),
        conversion_notes="No TradingView security() or future bars. Uses trailing rolling windows.",
        repaint_risk="low",
    )

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        close = df["close"]
        adx14 = adx(df, 14)
        rsi14 = rsi(close, 14)
        signals: list[SignalSet] = []
        for p in param_product(params, ["window", "std_mult", "rsi_low", "rsi_high", "regime", "adx_max", "ema_fast", "ema_slow"]):
            window = int(p["window"])
            mid = sma(close, window)
            std = close.rolling(window, min_periods=window).std()
            lower = mid - float(p["std_mult"]) * std
            upper = mid + float(p["std_mult"]) * std
            fast = ema(close, int(p["ema_fast"]))
            slow = ema(close, int(p["ema_slow"]))
            long_sig = (close < lower) & (rsi14 <= float(p["rsi_low"]))
            short_sig = (close > upper) & (rsi14 >= float(p["rsi_high"]))
            long_sig, short_sig = apply_regime_filter(long_sig, short_sig, close, fast, slow, adx14, str(p["regime"]), p["adx_max"])
            signals.append(SignalSet(self.metadata.name, "bb_rsi_reversion", p, long_sig, short_sig))
        return signals


class DonchianBreakout:
    metadata = IndicatorMetadata(
        name="donchian_breakout",
        display_name="Donchian Cycle Breakout",
        source="Python implementation from backtest_v7 research family",
        conversion_notes="Breakout level is previous rolling high/low via shift(1), so the current bar is not used in its own breakout threshold.",
        repaint_risk="low",
    )

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        close = df["close"]
        adx14 = adx(df, 14)
        signals: list[SignalSet] = []
        for p in param_product(params, ["window", "adx_min", "ema_fast", "ema_slow", "require_cycle"]):
            window = int(p["window"])
            prev_high = df["high"].rolling(window, min_periods=window).max().shift(1)
            prev_low = df["low"].rolling(window, min_periods=window).min().shift(1)
            fast = ema(close, int(p["ema_fast"]))
            slow = ema(close, int(p["ema_slow"]))
            long_sig = (close > prev_high) & (adx14 >= float(p["adx_min"])) & (close > slow)
            short_sig = (close < prev_low) & (adx14 >= float(p["adx_min"])) & (close < slow)
            if bool(p["require_cycle"]):
                long_sig = long_sig & (fast > slow)
                short_sig = short_sig & (fast < slow)
            signals.append(SignalSet(self.metadata.name, "donchian_breakout", p, long_sig.fillna(False), short_sig.fillna(False)))
        return signals


class EmaRejectPullback:
    metadata = IndicatorMetadata(
        name="ema_reject_pullback",
        display_name="EMA Reject Pullback",
        source="Python implementation from backtest_v7 research family",
        conversion_notes="Uses trailing ATR/ADX/RSI and current candle rejection; runner enters on a later candle.",
        repaint_risk="low",
    )

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        close = df["close"]
        open_ = df["open"]
        high = df["high"]
        low = df["low"]
        atr14 = atr(df, 14)
        adx14 = adx(df, 14)
        rsi14 = rsi(close, 14)
        lower_wick = np.minimum(open_, close) - low
        upper_wick = high - np.maximum(open_, close)
        bull_reject = (close > open_) & (lower_wick >= upper_wick)
        bear_reject = (close < open_) & (upper_wick >= lower_wick)
        signals: list[SignalSet] = []
        for p in param_product(params, ["fast_ema", "slow_ema", "rsi_low", "rsi_high", "atr_mult", "adx_min"]):
            fast = ema(close, int(p["fast_ema"]))
            slow = ema(close, int(p["slow_ema"]))
            near_fast = (close - fast).abs() <= float(p["atr_mult"]) * atr14
            long_sig = (close > slow) & (fast > slow) & near_fast & bull_reject & (rsi14 <= float(p["rsi_low"])) & (adx14 >= float(p["adx_min"]))
            short_sig = (close < slow) & (fast < slow) & near_fast & bear_reject & (rsi14 >= float(p["rsi_high"])) & (adx14 >= float(p["adx_min"]))
            signals.append(SignalSet(self.metadata.name, "ema_reject_pullback", p, long_sig.fillna(False), short_sig.fillna(False)))
        return signals


class WaveTrendCross:
    metadata = IndicatorMetadata(
        name="wavetrend_cross",
        display_name="WaveTrend Cross",
        source="Manual Python conversion from WaveTrend Oscillator.pine",
        converted_from=("WaveTrend Oscillator.pine",),
        conversion_notes="Converted formula: hlc3 -> EMA channel -> CI -> EMA TCI -> SMA signal. Entries are cross events, shifted by runner.",
        repaint_risk="low",
    )

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        close = df["close"]
        ap = (df["high"] + df["low"] + df["close"]) / 3.0
        signals: list[SignalSet] = []
        for p in param_product(params, ["channel_len", "average_len", "overbought", "oversold", "trend_ema", "use_trend_filter"]):
            n1 = int(p["channel_len"])
            n2 = int(p["average_len"])
            esa = ema(ap, n1)
            d = ema((ap - esa).abs(), n1)
            ci = (ap - esa) / (0.015 * d.replace(0, np.nan))
            wt1 = ema(ci, n2)
            wt2 = sma(wt1, 4)
            long_sig = crossover(wt1, wt2) & (wt1 <= float(p["oversold"]))
            short_sig = crossunder(wt1, wt2) & (wt1 >= float(p["overbought"]))
            if bool(p["use_trend_filter"]):
                trend = ema(close, int(p["trend_ema"]))
                long_sig = long_sig & (close > trend)
                short_sig = short_sig & (close < trend)
            signals.append(SignalSet(self.metadata.name, "wavetrend_cross", p, long_sig.fillna(False), short_sig.fillna(False)))
        return signals


class WilliamsVixFix:
    metadata = IndicatorMetadata(
        name="williams_vix_fix",
        display_name="Williams Vix Fix Reversal",
        source="Manual Python conversion from CM_Williams_Vix_Fix.pine",
        converted_from=("CM_Williams_Vix_Fix.pine",),
        conversion_notes="Converts WVF spike logic. A long signal fires when WVF spike relaxes after fear; short side is intentionally empty.",
        repaint_risk="low",
    )

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        close = df["close"]
        low = df["low"]
        signals: list[SignalSet] = []
        for p in param_product(params, ["lookback", "bb_length", "bb_mult", "percentile_lookback", "percentile_high", "trend_ema"]):
            lookback = int(p["lookback"])
            bb_length = int(p["bb_length"])
            highest_close = close.rolling(lookback, min_periods=lookback).max()
            wvf = ((highest_close - low) / highest_close.replace(0, np.nan)) * 100.0
            mid = sma(wvf, bb_length)
            upper = mid + float(p["bb_mult"]) * wvf.rolling(bb_length, min_periods=bb_length).std()
            range_high = wvf.rolling(int(p["percentile_lookback"]), min_periods=int(p["percentile_lookback"])).max() * float(p["percentile_high"])
            spike = (wvf >= upper) | (wvf >= range_high)
            trend = ema(close, int(p["trend_ema"]))
            long_sig = spike.shift(1).fillna(False) & (~spike.fillna(False)) & (close > trend)
            short_sig = pd.Series(False, index=df.index)
            signals.append(SignalSet(self.metadata.name, "williams_vix_fix_long", p, long_sig.fillna(False), short_sig))
        return signals


class SqueezeMomentum:
    metadata = IndicatorMetadata(
        name="squeeze_momentum",
        display_name="Squeeze Momentum",
        source="Manual Python conversion from Squeeze Momentum Indicator [LazyBear].pine",
        converted_from=("Squeeze Momentum Indicator [LazyBear].pine",),
        conversion_notes="Uses trailing BB/KC squeeze and rolling linear regression momentum.",
        repaint_risk="low",
    )

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        close = df["close"]
        tr = true_range(df)
        signals: list[SignalSet] = []
        for p in param_product(params, ["length", "bb_mult", "kc_length", "kc_mult", "trend_ema"]):
            length = int(p["length"])
            kc_length = int(p["kc_length"])
            basis = sma(close, length)
            dev = float(p["bb_mult"]) * close.rolling(length, min_periods=length).std()
            upper_bb = basis + dev
            lower_bb = basis - dev
            ma = sma(close, kc_length)
            range_ma = sma(tr, kc_length)
            upper_kc = ma + range_ma * float(p["kc_mult"])
            lower_kc = ma - range_ma * float(p["kc_mult"])
            sqz_off = (lower_bb < lower_kc) & (upper_bb > upper_kc)
            mean_anchor = ((df["high"].rolling(kc_length, min_periods=kc_length).max() + df["low"].rolling(kc_length, min_periods=kc_length).min()) / 2.0 + sma(close, kc_length)) / 2.0
            val = rolling_linreg_last(close - mean_anchor, kc_length)
            trend = ema(close, int(p["trend_ema"]))
            long_sig = sqz_off & crossover(val, pd.Series(0.0, index=df.index)) & (close > trend)
            short_sig = sqz_off & crossunder(val, pd.Series(0.0, index=df.index)) & (close < trend)
            signals.append(SignalSet(self.metadata.name, "squeeze_momentum_release", p, long_sig.fillna(False), short_sig.fillna(False)))
        return signals


class SuperTrendFlip:
    metadata = IndicatorMetadata(
        name="supertrend_flip",
        display_name="SuperTrend Flip",
        source="Manual Python conversion from SuperTrend by KivancOzbilgic.pine",
        converted_from=("SuperTrend by KivancOzbilgic.pine",),
        conversion_notes="Implements the Pine v4 recursive up/dn/trend bands with trailing ATR. Signals fire on trend flips.",
        repaint_risk="low",
    )

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        signals: list[SignalSet] = []
        for p in param_product(params, ["atr_period", "multiplier", "change_atr"]):
            trend = self._supertrend_direction(df, int(p["atr_period"]), float(p["multiplier"]), bool(p["change_atr"]))
            trend_series = pd.Series(trend, index=df.index)
            long_sig = (trend_series == 1) & (trend_series.shift(1) == -1)
            short_sig = (trend_series == -1) & (trend_series.shift(1) == 1)
            signals.append(SignalSet(self.metadata.name, "supertrend_flip", p, long_sig.fillna(False), short_sig.fillna(False)))
        return signals

    @staticmethod
    def _supertrend_direction(df: pd.DataFrame, period: int, multiplier: float, change_atr: bool) -> np.ndarray:
        src = (df["high"] + df["low"]) / 2.0
        atr_value = atr(df, period, method="rma" if change_atr else "sma")
        close = df["close"].to_numpy(float)
        up_raw = (src - multiplier * atr_value).to_numpy(float)
        dn_raw = (src + multiplier * atr_value).to_numpy(float)
        up = np.copy(up_raw)
        dn = np.copy(dn_raw)
        trend = np.ones(len(df), dtype=np.int64)
        for i in range(1, len(df)):
            up1 = up[i - 1] if np.isfinite(up[i - 1]) else up_raw[i]
            dn1 = dn[i - 1] if np.isfinite(dn[i - 1]) else dn_raw[i]
            if np.isfinite(up_raw[i]):
                up[i] = max(up_raw[i], up1) if close[i - 1] > up1 else up_raw[i]
            if np.isfinite(dn_raw[i]):
                dn[i] = min(dn_raw[i], dn1) if close[i - 1] < dn1 else dn_raw[i]
            prev = trend[i - 1]
            if prev == -1 and close[i] > dn1:
                trend[i] = 1
            elif prev == 1 and close[i] < up1:
                trend[i] = -1
            else:
                trend[i] = prev
        return trend


class MacdCross:
    metadata = IndicatorMetadata(
        name="macd_cross",
        display_name="MACD Cross",
        source="Manual current-timeframe implementation inspired by MacD Custom.pine",
        converted_from=("MacD Custom.pine",),
        conversion_notes="The raw Pine uses security() for optional MTF. V8 intentionally implements current-timeframe MACD only to avoid MTF lookahead ambiguity.",
        repaint_risk="medium",
    )

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        close = df["close"]
        signals: list[SignalSet] = []
        for p in param_product(params, ["fast", "slow", "signal", "trend_ema", "use_trend_filter"]):
            macd = ema(close, int(p["fast"])) - ema(close, int(p["slow"]))
            signal_line = sma(macd, int(p["signal"]))
            long_sig = crossover(macd, signal_line)
            short_sig = crossunder(macd, signal_line)
            if bool(p["use_trend_filter"]):
                trend = ema(close, int(p["trend_ema"]))
                long_sig = long_sig & (close > trend)
                short_sig = short_sig & (close < trend)
            warnings = ("Raw Pine contains security(); Python version uses current timeframe only.",)
            signals.append(SignalSet(self.metadata.name, "macd_cross", p, long_sig.fillna(False), short_sig.fillna(False), warnings))
        return signals


class AdxEmaTrend:
    metadata = IndicatorMetadata(
        name="adx_ema_trend",
        display_name="ADX + EMA Trend",
        source="Manual Python conversion from adx_ema_combined.pine",
        converted_from=("adx_ema_combined.pine",),
        conversion_notes="Converted only calculation logic: EMA stack plus ADX/DI trend state. Visual table/barstate logic is ignored. No security(), pivot, or future bars found.",
        repaint_risk="low",
    )

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        close = df["close"]
        signals: list[SignalSet] = []
        for p in param_product(params, ["ema_fast", "ema_mid", "ema_slow", "di_length", "adx_smoothing", "adx_threshold"]):
            fast = ema(close, int(p["ema_fast"]))
            mid = ema(close, int(p["ema_mid"]))
            slow = ema(close, int(p["ema_slow"]))
            di_plus, di_minus, adx_value = self._dmi(df, int(p["di_length"]), int(p["adx_smoothing"]))
            trend_ok = adx_value >= float(p["adx_threshold"])
            bull_state = trend_ok & (di_plus > di_minus) & (close > mid) & (fast > mid) & (mid > slow)
            bear_state = trend_ok & (di_minus > di_plus) & (close < mid) & (fast < mid) & (mid < slow)
            long_sig = bull_state & (~bull_state.shift(1).fillna(False))
            short_sig = bear_state & (~bear_state.shift(1).fillna(False))
            signals.append(SignalSet(self.metadata.name, "adx_ema_trend_state_start", p, long_sig.fillna(False), short_sig.fillna(False)))
        return signals

    @staticmethod
    def _dmi(df: pd.DataFrame, di_length: int, adx_smoothing: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        high = df["high"]
        low = df["low"]
        up = high.diff()
        down = -low.diff()
        plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
        tr = atr(df, di_length)
        plus = 100 * plus_dm.ewm(alpha=1 / di_length, adjust=False, min_periods=di_length).mean() / tr
        minus = 100 * minus_dm.ewm(alpha=1 / di_length, adjust=False, min_periods=di_length).mean() / tr
        di_sum = plus + minus
        adx_value = 100 * ((plus - minus).abs() / di_sum.replace(0, np.nan)).ewm(
            alpha=1 / adx_smoothing,
            adjust=False,
            min_periods=adx_smoothing,
        ).mean()
        return plus.fillna(0.0), minus.fillna(0.0), adx_value.fillna(0.0)


class SignalForgeLite:
    metadata = IndicatorMetadata(
        name="signal_forge_lite",
        display_name="Signal Forge Lite",
        source="Manual partial Python conversion from Signal Forge [LuxAlgo] by LuxAlgo.pine",
        converted_from=("Signal Forge [LuxAlgo] by LuxAlgo.pine",),
        conversion_notes="Audit found no security()/pivot/lookahead in the signal logic. This conversion implements current-timeframe indicator alignment only and omits dashboards, drawing, standalone performance tables, SAR/CCI/AO/stochastic to keep behavior auditable.",
        repaint_risk="medium",
    )

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        close = df["close"]
        signals: list[SignalSet] = []
        keys = [
            "require_all",
            "use_sma",
            "use_rsi",
            "use_macd",
            "use_supertrend",
            "use_bb",
            "use_ema",
            "use_adx",
            "sma_fast",
            "sma_slow",
            "rsi_length",
            "rsi_long_level",
            "rsi_short_level",
            "macd_fast",
            "macd_slow",
            "macd_signal",
            "supertrend_atr_period",
            "supertrend_multiplier",
            "bb_length",
            "bb_mult",
            "ema_fast",
            "ema_slow",
            "adx_length",
            "di_length",
            "adx_threshold",
        ]
        for p in param_product(params, keys):
            states: list[tuple[pd.Series, pd.Series]] = []
            if bool(p["use_sma"]):
                fast = sma(close, int(p["sma_fast"]))
                slow = sma(close, int(p["sma_slow"]))
                states.append((fast > slow, fast < slow))
            if bool(p["use_rsi"]):
                rsi_value = rsi(close, int(p["rsi_length"]))
                states.append((rsi_value > float(p["rsi_long_level"]), rsi_value < float(p["rsi_short_level"])))
            if bool(p["use_macd"]):
                macd = ema(close, int(p["macd_fast"])) - ema(close, int(p["macd_slow"]))
                sig = sma(macd, int(p["macd_signal"]))
                states.append((macd > sig, macd < sig))
            if bool(p["use_supertrend"]):
                trend = pd.Series(
                    SuperTrendFlip._supertrend_direction(df, int(p["supertrend_atr_period"]), float(p["supertrend_multiplier"]), True),
                    index=df.index,
                )
                states.append((trend == 1, trend == -1))
            if bool(p["use_bb"]):
                mid = sma(close, int(p["bb_length"]))
                states.append((close > mid, close < mid))
            if bool(p["use_ema"]):
                fast = ema(close, int(p["ema_fast"]))
                slow = ema(close, int(p["ema_slow"]))
                states.append((fast > slow, fast < slow))
            if bool(p["use_adx"]):
                plus, minus, adx_value = AdxEmaTrend._dmi(df, int(p["di_length"]), int(p["adx_length"]))
                trend_ok = adx_value > float(p["adx_threshold"])
                states.append((trend_ok & (plus > minus), trend_ok & (minus > plus)))
            if not states:
                continue
            if bool(p["require_all"]):
                long_state = states[0][0].copy()
                short_state = states[0][1].copy()
                for bull, bear in states[1:]:
                    long_state = long_state & bull
                    short_state = short_state & bear
            else:
                long_state = pd.Series(False, index=df.index)
                short_state = pd.Series(False, index=df.index)
                for bull, bear in states:
                    long_state = long_state | bull
                    short_state = short_state | bear
            long_sig = long_state & (~long_state.shift(1).fillna(False))
            short_sig = short_state & (~short_state.shift(1).fillna(False))
            warnings = ("Partial Signal Forge conversion; disabled by default until parity-tested against TradingView.",)
            signals.append(SignalSet(self.metadata.name, "signal_forge_lite_alignment_start", p, long_sig.fillna(False), short_sig.fillna(False), warnings))
        return signals


INDICATORS = [
    IBSReversion(),
    BBRsiReversion(),
    DonchianBreakout(),
    EmaRejectPullback(),
    WaveTrendCross(),
    WilliamsVixFix(),
    SqueezeMomentum(),
    SuperTrendFlip(),
    MacdCross(),
    AdxEmaTrend(),
    SignalForgeLite(),
]
