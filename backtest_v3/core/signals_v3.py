"""
signals_v3.py — Signal Generator Library (10 strategies)
XAUUSD M5 — WFO Backtest v3

Strategies implemented:
  1. SQUEEZE     — Squeeze Momentum Indicator (LazyBear / smi.pine)
  2. PREC_SNIPER — Precision Sniper (WillyAlgoTrader / PrecSniper.pine)
  3. SMC_FVG     — Smart Money Concepts Fair Value Gap (LuxAlgo / SMC.pipe)
  4. SUPERTREND  — SuperTrend flip (ATR-based direction change)
  5. TRIPLE_EMA  — Triple EMA alignment crossover (9/21/50)
  6. RSI_REV     — RSI oversold/overbought cross-back
  7. BB_BOUNCE   — Bollinger Band outer-band touch + pullback
  8. MACD_CROSS  — MACD line crossover signal line
  9. VWAP_REV    — VWAP deviation reversion
 10. ENGULFING   — Bullish/Bearish engulfing with ATR body filter

All signals:
  - CAUSAL only (no look-ahead)
  - Computed globally on full dataset once
  - +1.0 = long, -1.0 = short, 0.0 = no signal
"""

import numpy as np
import pandas as pd
from numba import njit
import vectorbt as vbt
import warnings
warnings.filterwarnings("ignore")


# ===========================================================================
#  Shared Indicator Helpers
# ===========================================================================

def calc_atr_rma(high: pd.Series, low: pd.Series,
                 close: pd.Series, period: int) -> np.ndarray:
    """ATR via Wilder RMA — matches TradingView default."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low  - close.shift(1)).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean().values


def calc_adx_full(high: pd.Series, low: pd.Series,
                  close: pd.Series, period: int = 14):
    """Wilder ADX — returns (adx, pdi, ndi) arrays."""
    up   = high.diff()
    down = -low.diff()
    pdm  = pd.Series(np.where((up > down) & (up > 0), up.values, 0.0), index=close.index)
    ndm  = pd.Series(np.where((down > up) & (down > 0), down.values, 0.0), index=close.index)
    tr1  = high - low
    tr2  = (high - close.shift(1)).abs()
    tr3  = (low  - close.shift(1)).abs()
    tr   = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr  = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    pdi  = 100 * pdm.ewm(alpha=1.0 / period, adjust=False).mean() / atr
    ndi  = 100 * ndm.ewm(alpha=1.0 / period, adjust=False).mean() / atr
    dx   = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, 1e-10)
    adx  = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    return adx.values, pdi.values, ndi.values


def calc_adx(high: pd.Series, low: pd.Series,
             close: pd.Series, period: int = 14) -> np.ndarray:
    """Wilder ADX only (scalar)."""
    adx, _, _ = calc_adx_full(high, low, close, period)
    return adx


def compute_daily_vwap(close: np.ndarray, volume: np.ndarray,
                       index: pd.DatetimeIndex) -> np.ndarray:
    """Daily VWAP — resets at midnight UTC each trading day."""
    result  = np.full(len(close), np.nan, dtype=np.float64)
    dates   = index.date
    prev_d  = None
    pv_cum  = 0.0
    v_cum   = 0.0
    for i, d in enumerate(dates):
        if d != prev_d:
            pv_cum = 0.0
            v_cum  = 0.0
            prev_d = d
        v = float(volume[i])
        pv_cum += close[i] * v
        v_cum  += v
        if v_cum > 0:
            result[i] = pv_cum / v_cum
    return result


# ===========================================================================
#  1. SQUEEZE MOMENTUM (LazyBear — smi.pipe)
# ===========================================================================

def squeeze_momentum(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                     bb_len: int = 20, bb_mult: float = 2.0,
                     kc_len: int = 20, kc_mult: float = 1.5) -> np.ndarray:
    """
    Squeeze Momentum Indicator (LazyBear).

    Logic:
      BB: SMA(close, bb_len) +- bb_mult x STD
      KC: SMA(close, kc_len) +- kc_mult x ATR_SMA(kc_len)
      Squeeze ON  when BB is inside KC.
      val = linreg(close − avg(avg(HH, LL), SMA), kc_len)
      Signal: val crosses zero when squeeze NOT on.
        val crosses 0 upward   -> long
        val crosses 0 downward -> short
    """
    n  = len(close)
    cs = pd.Series(close)
    hs = pd.Series(high)
    ls = pd.Series(low)

    # Bollinger Bands
    bb_sma  = cs.rolling(bb_len).mean().values
    bb_std  = cs.rolling(bb_len).std(ddof=0).values
    bb_up   = bb_sma + bb_mult * bb_std
    bb_lo   = bb_sma - bb_mult * bb_std

    # Keltner Channels (ATR = simple mean of TR, not EMA, to match Pine v1)
    tr      = pd.concat([hs - ls,
                         (hs - cs.shift(1)).abs(),
                         (ls - cs.shift(1)).abs()], axis=1).max(axis=1)
    kc_atr  = tr.rolling(kc_len).mean().values
    kc_sma  = cs.rolling(kc_len).mean().values
    kc_up   = kc_sma + kc_mult * kc_atr
    kc_lo   = kc_sma - kc_mult * kc_atr

    # Squeeze state
    sqz_on  = (bb_lo > kc_lo) & (bb_up < kc_up)

    # val source: close - avg(avg(HH_kc, LL_kc), SMA_kc)
    hh      = hs.rolling(kc_len).max().values
    ll      = ls.rolling(kc_len).min().values
    mid     = ((hh + ll) / 2.0 + kc_sma) / 2.0
    source  = close - mid

    # Linear regression of source at last point using pre-computed weights
    #   x = [0, 1, ..., kc_len-1], predict at x = kc_len-1
    x       = np.arange(kc_len, dtype=np.float64)
    x_bar   = x.mean()
    denom_x = np.sum((x - x_bar) ** 2)
    # Weights such that dot(w, window) = linreg value at last bar
    w       = 1.0 / kc_len + (x - x_bar) * ((kc_len - 1) - x_bar) / denom_x

    val = np.full(n, np.nan, dtype=np.float64)
    for i in range(kc_len - 1, n):
        window = source[i - kc_len + 1: i + 1]
        if not np.any(np.isnan(window)):
            val[i] = np.dot(w, window)

    # Signal: zero crossing while NOT in squeeze
    sig = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        if np.isnan(val[i]) or np.isnan(val[i - 1]):
            continue
        if sqz_on[i]:
            continue
        if val[i] > 0.0 and val[i - 1] <= 0.0:
            sig[i] = 1.0
        elif val[i] < 0.0 and val[i - 1] >= 0.0:
            sig[i] = -1.0
    return sig


# ===========================================================================
#  2. PRECISION SNIPER (WillyAlgoTrader — PrecSniper.pine)
# ===========================================================================

def prec_sniper(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                volume: np.ndarray, index: pd.DatetimeIndex,
                ema_fast: int = 5, ema_slow: int = 13, ema_trend: int = 34,
                rsi_len: int = 8, min_score: float = 4.0) -> np.ndarray:
    """
    Precision Sniper: EMA crossover + 8-factor confluence score.

    Score factors (max 9.5):
      +1.0 emaFast > emaSlow
      +1.0 close > emaTrend (bullish) / close < emaTrend (bearish)
      +1.0 RSI in (50,75) long / (25,50) short
      +1.0 MACD histogram > 0 / < 0
      +1.0 MACD line > signal line / < signal line
      +1.0 close > VWAP / < VWAP
      +1.0 volume > SMA20 x 1.2
      +1.0 ADX > 20 AND DI+ > DI- (long) / DI- > DI+ (short)
      +0.5 close > emaFast / close < emaFast

    Signal fires on EMA fast/slow crossover when score >= min_score.
    Consecutive same-direction signals suppressed (matches Pine behavior).
    """
    n  = len(close)
    cs = pd.Series(close, index=index)
    hs = pd.Series(high,  index=index)
    ls = pd.Series(low,   index=index)

    # EMAs
    ef  = cs.ewm(span=ema_fast,  adjust=False).mean().values
    es  = cs.ewm(span=ema_slow,  adjust=False).mean().values
    et  = cs.ewm(span=ema_trend, adjust=False).mean().values

    # RSI
    rsi = vbt.RSI.run(cs, window=rsi_len).rsi.values

    # MACD (fixed 12/26/9)
    ml_s     = cs.ewm(span=12, adjust=False).mean() - cs.ewm(span=26, adjust=False).mean()
    sig_line = ml_s.ewm(span=9, adjust=False).mean()
    macd_l   = ml_s.values
    macd_sig = sig_line.values
    macd_h   = macd_l - macd_sig

    # Volume SMA20
    vol_sma  = pd.Series(volume, dtype=float, index=index).rolling(20).mean().values

    # ADX + DI+-
    adx_v, pdi_v, ndi_v = calc_adx_full(hs, ls, cs, period=14)

    # Daily VWAP
    vwap = compute_daily_vwap(close, volume, index)

    sig      = np.zeros(n, dtype=np.float64)
    last_dir = 0
    warmup   = max(ema_trend, 26, 34) + 10

    for i in range(warmup, n):
        if np.isnan(ef[i]) or np.isnan(es[i]) or np.isnan(et[i]):
            continue

        bull_cross = (ef[i] > es[i]) and (ef[i - 1] <= es[i - 1])
        bear_cross = (ef[i] < es[i]) and (ef[i - 1] >= es[i - 1])
        if not bull_cross and not bear_cross:
            continue

        bull_mom = close[i] > ef[i] and close[i] > es[i]
        bear_mom = close[i] < ef[i] and close[i] < es[i]

        if bull_cross and bull_mom:
            sc = 0.0
            sc += 1.0 if ef[i] > es[i] else 0.0
            sc += 1.0 if close[i] > et[i] else 0.0
            if not np.isnan(rsi[i]):
                sc += 1.0 if 50.0 < rsi[i] < 75.0 else 0.0
            if not np.isnan(macd_h[i]):
                sc += 1.0 if macd_h[i] > 0.0 else 0.0
            if not np.isnan(macd_l[i]) and not np.isnan(macd_sig[i]):
                sc += 1.0 if macd_l[i] > macd_sig[i] else 0.0
            if not np.isnan(vwap[i]):
                sc += 1.0 if close[i] > vwap[i] else 0.0
            if not np.isnan(vol_sma[i]) and vol_sma[i] > 0:
                sc += 1.0 if volume[i] > vol_sma[i] * 1.2 else 0.0
            if not np.isnan(adx_v[i]) and adx_v[i] > 20.0:
                sc += 1.0 if pdi_v[i] > ndi_v[i] else 0.0
            sc += 0.5 if close[i] > ef[i] else 0.0

            if sc >= min_score and last_dir != 1:
                sig[i]   = 1.0
                last_dir = 1

        elif bear_cross and bear_mom:
            sc = 0.0
            sc += 1.0 if ef[i] < es[i] else 0.0
            sc += 1.0 if close[i] < et[i] else 0.0
            if not np.isnan(rsi[i]):
                sc += 1.0 if 25.0 < rsi[i] < 50.0 else 0.0
            if not np.isnan(macd_h[i]):
                sc += 1.0 if macd_h[i] < 0.0 else 0.0
            if not np.isnan(macd_l[i]) and not np.isnan(macd_sig[i]):
                sc += 1.0 if macd_l[i] < macd_sig[i] else 0.0
            if not np.isnan(vwap[i]):
                sc += 1.0 if close[i] < vwap[i] else 0.0
            if not np.isnan(vol_sma[i]) and vol_sma[i] > 0:
                sc += 1.0 if volume[i] > vol_sma[i] * 1.2 else 0.0
            if not np.isnan(adx_v[i]) and adx_v[i] > 20.0:
                sc += 1.0 if ndi_v[i] > pdi_v[i] else 0.0
            sc += 0.5 if close[i] < ef[i] else 0.0

            if sc >= min_score and last_dir != -1:
                sig[i]   = -1.0
                last_dir = -1

    return sig


# ===========================================================================
#  3. SMC FAIR VALUE GAP (LuxAlgo — SMC.pipe)
# ===========================================================================

@njit
def smc_fvg_nb(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               atr: np.ndarray, min_gap_atr: float = 0.0) -> np.ndarray:
    """
    Smart Money Concepts — Fair Value Gap (causal).

    Bullish FVG at bar i:
      low[i]   > high[i-2]   (gap above)
      close[i-1] > high[i-2] (confirming candle closed above gap)

    Bearish FVG at bar i:
      high[i]  < low[i-2]    (gap below)
      close[i-1] < low[i-2]  (confirming candle closed below gap)

    Optional filter: gap size > min_gap_atr x ATR.
    """
    n   = len(close)
    sig = np.zeros(n)
    for i in range(2, n):
        if np.isnan(atr[i]):
            continue
        a   = atr[i]
        # Bullish FVG
        gap_b = low[i] - high[i - 2]
        if gap_b > 0.0 and close[i - 1] > high[i - 2]:
            if min_gap_atr <= 0.0 or gap_b >= min_gap_atr * a:
                sig[i] = 1.0
                continue
        # Bearish FVG
        gap_s = low[i - 2] - high[i]
        if gap_s > 0.0 and close[i - 1] < low[i - 2]:
            if min_gap_atr <= 0.0 or gap_s >= min_gap_atr * a:
                sig[i] = -1.0
    return sig


# ===========================================================================
#  4. SUPERTREND (ATR-based direction flip)
# ===========================================================================

@njit
def supertrend_nb(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                  atr: np.ndarray, multiplier: float = 2.0) -> np.ndarray:
    """SuperTrend direction-flip signal (fires only on direction change)."""
    n    = len(close)
    st   = np.zeros(n)
    dir_ = np.ones(n)
    sig  = np.zeros(n)
    if n == 0:
        return sig
    st[0] = (high[0] + low[0]) / 2.0

    for i in range(1, n):
        if np.isnan(atr[i]):
            st[i] = st[i - 1]; dir_[i] = dir_[i - 1]; continue
        hl2  = (high[i] + low[i]) / 2.0
        matr = multiplier * atr[i]
        b_ub = hl2 + matr
        b_lb = hl2 - matr
        c_lb = b_lb if (b_lb > st[i-1] or close[i-1] < st[i-1]) else st[i-1]
        c_ub = b_ub if (b_ub < st[i-1] or close[i-1] > st[i-1]) else st[i-1]

        if   st[i-1] == c_ub and close[i] > c_ub: dir_[i] =  1.0
        elif st[i-1] == c_lb and close[i] < c_lb: dir_[i] = -1.0
        else:                                       dir_[i] = dir_[i-1]
        st[i] = c_lb if dir_[i] == 1.0 else c_ub

        if   dir_[i] ==  1.0 and dir_[i-1] == -1.0: sig[i] =  1.0
        elif dir_[i] == -1.0 and dir_[i-1] ==  1.0: sig[i] = -1.0
    return sig


# ===========================================================================
#  5. TRIPLE EMA (9/21/50 alignment crossover)
# ===========================================================================

def triple_ema(close_s: pd.Series,
               fast: int = 9, mid: int = 21, slow: int = 50) -> np.ndarray:
    """Triple EMA alignment cross — fires when all 3 EMAs first align."""
    ef  = vbt.MA.run(close_s, fast, ewm=True).ma.values
    em  = vbt.MA.run(close_s, mid,  ewm=True).ma.values
    es  = vbt.MA.run(close_s, slow, ewm=True).ma.values
    sig = np.zeros(len(close_s))
    for i in range(1, len(sig)):
        if np.isnan(ef[i]) or np.isnan(em[i]) or np.isnan(es[i]):
            continue
        bn = ef[i] > em[i] > es[i];  bp = ef[i-1] > em[i-1] > es[i-1]
        dn = ef[i] < em[i] < es[i];  dp = ef[i-1] < em[i-1] < es[i-1]
        if bn and not bp: sig[i] =  1.0
        if dn and not dp: sig[i] = -1.0
    return sig


# ===========================================================================
#  6. RSI REVERSAL (OB/OS cross-back)
# ===========================================================================

def rsi_reversal(close_s: pd.Series,
                 window: int = 14, ob: float = 70.0, os_: float = 30.0) -> np.ndarray:
    """RSI oversold/overbought cross-back signal."""
    rsi = vbt.RSI.run(close_s, window=window).rsi.values
    sig = np.zeros(len(close_s))
    for i in range(1, len(sig)):
        if np.isnan(rsi[i]): continue
        if   rsi[i-1] <= os_ and rsi[i] > os_: sig[i] =  1.0
        elif rsi[i-1] >= ob  and rsi[i] < ob:  sig[i] = -1.0
    return sig


# ===========================================================================
#  7. BOLLINGER BAND BOUNCE
# ===========================================================================

def bb_bounce(close_s: pd.Series, rsi_vals: np.ndarray,
              window: int = 20, alpha: float = 2.0) -> np.ndarray:
    """BB outer-band pierce + close-back, confirmed by RSI not at extremes."""
    bb    = vbt.BBANDS.run(close_s, window=window, alpha=alpha)
    lower = bb.lower.values
    upper = bb.upper.values
    c     = close_s.values
    sig   = np.zeros(len(c))
    for i in range(1, len(c)):
        if np.isnan(lower[i]): continue
        if c[i-1] < lower[i-1] and c[i] > lower[i] and rsi_vals[i] < 45.0:
            sig[i] =  1.0
        elif c[i-1] > upper[i-1] and c[i] < upper[i] and rsi_vals[i] > 55.0:
            sig[i] = -1.0
    return sig


# ===========================================================================
#  8. MACD CROSS (line over signal line)
# ===========================================================================

def macd_cross(close_s: pd.Series,
               fast: int = 12, slow: int = 26, signal_len: int = 9) -> np.ndarray:
    """MACD line crosses signal line."""
    ema_f  = close_s.ewm(span=fast,       adjust=False).mean()
    ema_s  = close_s.ewm(span=slow,       adjust=False).mean()
    ml     = (ema_f - ema_s)
    sig_l  = ml.ewm(span=signal_len, adjust=False).mean()
    ml_v   = ml.values
    sig_v  = sig_l.values
    sig    = np.zeros(len(close_s))
    for i in range(1, len(sig)):
        if np.isnan(ml_v[i]) or np.isnan(sig_v[i]): continue
        if   ml_v[i] > sig_v[i] and ml_v[i-1] <= sig_v[i-1]: sig[i] =  1.0
        elif ml_v[i] < sig_v[i] and ml_v[i-1] >= sig_v[i-1]: sig[i] = -1.0
    return sig


# ===========================================================================
#  9. VWAP REVERSION (price extends from VWAP then reverts)
# ===========================================================================

def vwap_reversion(close: np.ndarray, atr: np.ndarray,
                   vwap: np.ndarray, mult: float = 1.5) -> np.ndarray:
    """
    Long when price is below VWAP − multxATR and closes back up.
    Short when price is above VWAP + multxATR and closes back down.
    """
    n   = len(close)
    sig = np.zeros(n)
    for i in range(1, n):
        if np.isnan(vwap[i]) or np.isnan(atr[i]): continue
        band = mult * atr[i]
        # Long: prev close below lower VWAP band, current bar bounces up
        if close[i-1] < vwap[i] - band and close[i] > close[i-1]:
            sig[i] =  1.0
        # Short: prev close above upper VWAP band, current bar falls
        elif close[i-1] > vwap[i] + band and close[i] < close[i-1]:
            sig[i] = -1.0
    return sig


# ===========================================================================
#  10. ENGULFING CANDLE (ATR body size filter)
# ===========================================================================

@njit
def engulfing_atr_nb(open_: np.ndarray, high: np.ndarray, low: np.ndarray,
                     close: np.ndarray, atr: np.ndarray,
                     min_body_atr: float = 0.4) -> np.ndarray:
    """
    Bullish/Bearish engulfing pattern filtered by ATR body size.

    Bullish: prev bar bearish, curr bar bullish, curr body engulfs prev body.
    Bearish: prev bar bullish, curr bar bearish, curr body engulfs prev body.
    Body of current bar must be >= min_body_atr x ATR.
    """
    n   = len(close)
    sig = np.zeros(n)
    for i in range(1, n):
        if np.isnan(atr[i]): continue
        prev_bull = close[i-1] > open_[i-1]
        prev_bear = close[i-1] < open_[i-1]
        curr_bull = close[i]   > open_[i]
        curr_bear = close[i]   < open_[i]
        # Bullish engulfing
        if prev_bear and curr_bull:
            if close[i] > open_[i-1] and open_[i] < close[i-1]:
                body = close[i] - open_[i]
                if body >= min_body_atr * atr[i]:
                    sig[i] = 1.0
        # Bearish engulfing
        elif prev_bull and curr_bear:
            if open_[i] > close[i-1] and close[i] < open_[i-1]:
                body = open_[i] - close[i]
                if body >= min_body_atr * atr[i]:
                    sig[i] = -1.0
    return sig


# ===========================================================================
#  Filter Helpers (vectorized)
# ===========================================================================

def apply_ema_filter(sig: np.ndarray, close: np.ndarray,
                     ema_vals: np.ndarray) -> np.ndarray:
    """Keep longs only when price > EMA; shorts only when price < EMA."""
    valid = ~np.isnan(ema_vals)
    lon   = valid & (sig ==  1.0) & (close > ema_vals)
    sho   = valid & (sig == -1.0) & (close < ema_vals)
    return np.where(lon, 1.0, np.where(sho, -1.0, 0.0))


def apply_adx_filter(sig: np.ndarray, adx_vals: np.ndarray,
                     thresh: float) -> np.ndarray:
    """Keep signals only when ADX >= thresh."""
    if thresh <= 0.0:
        return sig
    active = ~np.isnan(adx_vals) & (adx_vals >= thresh)
    return np.where(active, sig, 0.0)


def apply_vol_filter(sig: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """Keep signals only when volume > rolling SMA20 of volume."""
    vol_s   = pd.Series(volume, dtype=float)
    vol_sma = vol_s.rolling(20).mean().values
    valid   = ~np.isnan(vol_sma) & (volume > vol_sma)
    return np.where(valid, sig, 0.0)


# ===========================================================================
#  Build Full Signal Registry (called once on full dataset)
# ===========================================================================

def build_registry(df: pd.DataFrame, atr14: np.ndarray) -> dict:
    """
    Pre-compute all 10 base signals on the full dataset.
    Returns: {name -> np.ndarray of shape (n,) values in {-1, 0, +1}}
    """
    h  = df["high"].values
    l  = df["low"].values
    c  = df["close"].values
    o  = df["open"].values
    v  = df["volume"].values
    cs = df["close"]
    idx = df.index

    # Shared pre-computations
    print("    [pre] ATR(200) for SuperTrend / FVG filter ...")
    atr200 = calc_atr_rma(df["high"], df["low"], df["close"], period=200)
    print("    [pre] VWAP (daily reset) ...")
    vwap   = compute_daily_vwap(c, v, idx)
    print("    [pre] RSI(14) for BB Bounce ...")
    rsi14  = vbt.RSI.run(cs, window=14).rsi.values

    print("    [1/10] SQUEEZE ...")
    sig_sqz = squeeze_momentum(h, l, c)

    print("    [2/10] PREC_SNIPER (EMA 5/13/34, score >= 4) ...")
    sig_sniper = prec_sniper(h, l, c, v, idx,
                             ema_fast=5, ema_slow=13, ema_trend=34,
                             rsi_len=8, min_score=4.0)

    print("    [3/10] SMC_FVG ...")
    sig_fvg = smc_fvg_nb(h, l, c, atr14, min_gap_atr=0.1)

    print("    [4/10] SUPERTREND (mult=2) ...")
    sig_st2 = supertrend_nb(h, l, c, atr14, multiplier=2.0)

    print("    [5/10] SUPERTREND (mult=3) ...")
    sig_st3 = supertrend_nb(h, l, c, atr14, multiplier=3.0)

    print("    [6/10] TRIPLE EMA (9/21/50) ...")
    sig_tema = triple_ema(cs, fast=9, mid=21, slow=50)

    print("    [7/10] RSI REVERSAL (14 / 70-30) ...")
    sig_rsir = rsi_reversal(cs, window=14)

    print("    [8/10] BB BOUNCE (20/2.0) ...")
    sig_bbb  = bb_bounce(cs, rsi14, window=20, alpha=2.0)

    print("    [9/10] MACD CROSS (12/26/9) ...")
    sig_macd = macd_cross(cs, fast=12, slow=26, signal_len=9)

    print("    [10/10] ENGULFING ATR (body >= 0.4xATR) ...")
    sig_eng  = engulfing_atr_nb(o, h, l, c, atr14, min_body_atr=0.4)

    registry = {
        "SQUEEZE":      sig_sqz,
        "PREC_SNIPER":  sig_sniper,
        "SMC_FVG":      sig_fvg,
        "SUPERTREND_2": sig_st2,
        "SUPERTREND_3": sig_st3,
        "TRIPLE_EMA":   sig_tema,
        "RSI_REV":      sig_rsir,
        "BB_BOUNCE":    sig_bbb,
        "MACD_CROSS":   sig_macd,
        "ENGULFING":    sig_eng,
    }

    # Print signal count summary
    for name, arr in registry.items():
        n_l = int((arr ==  1.0).sum())
        n_s = int((arr == -1.0).sum())
        print(f"    -> {name:<15}: {n_l:>5} long | {n_s:>5} short | {n_l+n_s:>6} total")

    return registry, atr200, vwap
