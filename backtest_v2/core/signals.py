"""
signals.py — Signal Generator Library for WFO Holy Grail Search.
XAUUSD M15 (OANDA data)

All indicators are CAUSAL (zero look-ahead):
  - Computed globally on the full dataset once.
  - Each bar's value depends only on bars UP TO that bar.

Signals returned:
  +1.0 = long entry
  -1.0 = short entry
   0.0 = no signal
"""

import numpy as np
import pandas as pd
from numba import njit
import vectorbt as vbt
import warnings
warnings.filterwarnings("ignore")


# ===========================================================================
#  ATR / ADX helpers
# ===========================================================================

def calc_atr_rma(high: pd.Series, low: pd.Series,
                 close: pd.Series, period: int) -> np.ndarray:
    """ATR via Wilder RMA — matches TradingView default."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low  - close.shift(1)).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean().values


def calc_adx(high: pd.Series, low: pd.Series,
             close: pd.Series, period: int = 14) -> np.ndarray:
    """Wilder ADX (14-period default)."""
    up   = high.diff()
    down = -low.diff()
    pdm  = pd.Series(np.where((up > down) & (up > 0),   up.values,   0.0), index=close.index)
    ndm  = pd.Series(np.where((down > up) & (down > 0), down.values, 0.0), index=close.index)
    tr1  = high - low
    tr2  = (high - close.shift(1)).abs()
    tr3  = (low  - close.shift(1)).abs()
    tr   = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr  = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    pdi  = 100 * pdm.ewm(alpha=1.0 / period, adjust=False).mean() / atr
    ndi  = 100 * ndm.ewm(alpha=1.0 / period, adjust=False).mean() / atr
    dx   = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, 1e-10)
    return dx.ewm(alpha=1.0 / period, adjust=False).mean().values


# ===========================================================================
#  Numba Signal Generators
# ===========================================================================

@njit
def fvg_nb(high: np.ndarray, low: np.ndarray, close: np.ndarray,
           atr: np.ndarray, filter_width: float) -> np.ndarray:
    """
    Fair Value Gap (ICT / Imbalance) signal.
    Bullish FVG: candle[-3] is above candle[-1], candle[-2] fills gap,
                 current candle closes above candle[-3].low.
    filter_width: minimum gap size in ATR units (0 = no filter).
    """
    n   = len(high)
    sig = np.zeros(n)
    for i in range(3, n):
        if np.isnan(atr[i]):
            continue
        b3l = low[i - 3];   b3h = high[i - 3]
        b2c = close[i - 2]
        b1l = low[i - 1];   b1h = high[i - 1]
        b0c = close[i];      a   = atr[i]

        # --- Bullish FVG ---
        bull = b3l > b1h and b2c < b3l and b0c > b3l
        if bull and filter_width > 0.0:
            bull = (b3l - b1h) > (a * filter_width)

        # --- Bearish FVG ---
        bear = b1l > b3h and b2c > b3h and b0c < b3h
        if bear and filter_width > 0.0:
            bear = (b1l - b3h) > (a * filter_width)

        if bull:
            sig[i] =  1.0
        elif bear:
            sig[i] = -1.0
    return sig


@njit
def supertrend_nb(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                  atr: np.ndarray, multiplier: float) -> np.ndarray:
    """SuperTrend flip signal (fire on direction change only)."""
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
        c_lb = b_lb if (b_lb > st[i - 1] or close[i - 1] < st[i - 1]) else st[i - 1]
        c_ub = b_ub if (b_ub < st[i - 1] or close[i - 1] > st[i - 1]) else st[i - 1]

        if   st[i - 1] == c_ub and close[i] > c_ub: dir_[i] =  1.0
        elif st[i - 1] == c_lb and close[i] < c_lb: dir_[i] = -1.0
        else:                                         dir_[i] = dir_[i - 1]
        st[i] = c_lb if dir_[i] == 1.0 else c_ub

        if   dir_[i] ==  1.0 and dir_[i - 1] == -1.0: sig[i] =  1.0
        elif dir_[i] == -1.0 and dir_[i - 1] ==  1.0: sig[i] = -1.0
    return sig


# ===========================================================================
#  Python Signal Generators (use vectorbt internally)
# ===========================================================================

def triple_ema(close_s: pd.Series, fast: int, mid: int, slow: int) -> np.ndarray:
    """Triple EMA alignment cross — fires when all 3 EMAs align for the first time."""
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


def rsi_reversal(close_s: pd.Series,
                 window: int = 14, ob: float = 70.0, os_: float = 30.0) -> np.ndarray:
    """RSI oversold/overbought cross-back signal."""
    rsi = vbt.RSI.run(close_s, window=window).rsi.values
    sig = np.zeros(len(close_s))
    for i in range(1, len(sig)):
        if np.isnan(rsi[i]): continue
        if rsi[i-1] <= os_ and rsi[i] > os_: sig[i] =  1.0
        elif rsi[i-1] >= ob and rsi[i] < ob: sig[i] = -1.0
    return sig


def bb_bounce(close_s: pd.Series, rsi_vals: np.ndarray,
              window: int = 20, alpha: float = 2.0) -> np.ndarray:
    """Bollinger Band outer-band touch + close-back, confirmed by RSI."""
    bb    = vbt.BBANDS.run(close_s, window=window, alpha=alpha)
    lower = bb.lower.values; upper = bb.upper.values
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
#  Filter helpers (vectorized)
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
    """Keep signals only when ADX >= thresh (trending market)."""
    if thresh <= 0.0:
        return sig
    active = ~np.isnan(adx_vals) & (adx_vals >= thresh)
    return np.where(active, sig, 0.0)


# ===========================================================================
#  Build full signal registry (called once on full dataset)
# ===========================================================================

def build_registry(df: pd.DataFrame, atr200: np.ndarray) -> dict:
    """
    Pre-compute all 6 base signals on the full dataset.
    Returns: {name -> np.ndarray of shape (n,) with values {-1, 0, +1}}
    """
    h = df["high"].values
    l = df["low"].values

    print("    [sig] FVG ...")
    fvg_raw = fvg_nb(h, l, df["close"].values, atr200, filter_width=0.1)

    print("    [sig] SuperTrend mult=2 ...")
    st2 = supertrend_nb(h, l, df["close"].values, atr200, multiplier=2.0)
    print("    [sig] SuperTrend mult=3 ...")
    st3 = supertrend_nb(h, l, df["close"].values, atr200, multiplier=3.0)

    print("    [sig] Triple EMA (9/21/50) ...")
    tema = triple_ema(df["close"], fast=9, mid=21, slow=50)

    print("    [sig] RSI Reversal (14) ...")
    rsi_vals = vbt.RSI.run(df["close"], window=14).rsi.values
    rsi_rev  = rsi_reversal(df["close"], window=14)

    print("    [sig] BB Bounce (20/2.0) ...")
    bb_bnc = bb_bounce(df["close"], rsi_vals, window=20, alpha=2.0)

    return {
        "FVG":          fvg_raw,
        "SUPERTREND_2": st2,
        "SUPERTREND_3": st3,
        "TRIPLE_EMA":   tema,
        "RSI_REV":      rsi_rev,
        "BB_BOUNCE":    bb_bnc,
    }
