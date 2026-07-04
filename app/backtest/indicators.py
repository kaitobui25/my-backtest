from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr_val = atr(df, window)
    plus_di = 100 * plus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean() / atr_val
    minus_di = 100 * minus_dm.ewm(alpha=1 / window, adjust=False, min_periods=window).mean() / atr_val
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


@njit(cache=True)
def calculate_supertrend(high, low, close, atr_val, multiplier):
    n = len(close)
    up = np.empty(n, dtype=np.float64)
    dn = np.empty(n, dtype=np.float64)
    trend = np.empty(n, dtype=np.int32)
    hl2 = (high + low) / 2
    for i in range(n):
        if np.isnan(atr_val[i]):
            up[i] = np.nan
            dn[i] = np.nan
            trend[i] = 1
            continue
        basic_up = hl2[i] - (multiplier * atr_val[i])
        basic_dn = hl2[i] + (multiplier * atr_val[i])
        if i == 0 or np.isnan(up[i-1]):
            up[i] = basic_up
            dn[i] = basic_dn
            trend[i] = 1
        else:
            up[i] = max(basic_up, up[i-1]) if close[i-1] > up[i-1] else basic_up
            dn[i] = min(basic_dn, dn[i-1]) if close[i-1] < dn[i-1] else basic_dn
            if trend[i-1] == -1 and close[i] > dn[i-1]:
                trend[i] = 1
            elif trend[i-1] == 1 and close[i] < up[i-1]:
                trend[i] = -1
            else:
                trend[i] = trend[i-1]
    return up, dn, trend


def supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> np.ndarray:
    atr_val = atr(df, period).to_numpy()
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    _, _, trend = calculate_supertrend(high, low, close, atr_val, multiplier)
    return trend


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal_len: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal_len, adjust=False, min_periods=signal_len).mean()
    return macd_line, signal_line, macd_line - signal_line


def wavetrend(df: pd.DataFrame, n1: int = 10, n2: int = 21) -> tuple[pd.Series, pd.Series]:
    ap = (df["high"] + df["low"] + df["close"]) / 3
    esa = ema(ap, n1)
    d = ema((ap - esa).abs(), n1)
    ci = (ap - esa) / (0.015 * d).replace(0, np.nan)
    wt1 = ema(ci, n2)
    wt2 = wt1.rolling(4, min_periods=4).mean()
    return wt1, wt2


@njit(cache=True)
def fast_linreg_val(y_arr, n):
    res = np.empty_like(y_arr)
    res[:] = np.nan
    i = np.arange(1, n + 1)
    w = (6 * i - 2 * n - 2) / (n * (n + 1))
    for j in range(n - 1, len(y_arr)):
        window = y_arr[j - n + 1 : j + 1]
        if np.isnan(window).any():
            res[j] = np.nan
        else:
            res[j] = np.sum(window * w)
    return res


def squeeze_momentum(df: pd.DataFrame, length: int = 20, bb_mult: float = 2.0, kc_mult: float = 1.5):
    close = df["close"]
    high = df["high"]
    low = df["low"]
    basis = close.rolling(length, min_periods=length).mean()
    dev = bb_mult * close.rolling(length, min_periods=length).std()
    upper_bb = basis + dev
    lower_bb = basis - dev
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    range_ma = tr.rolling(length, min_periods=length).mean()
    upper_kc = basis + kc_mult * range_ma
    lower_kc = basis - kc_mult * range_ma
    sqz_on = (lower_bb > lower_kc) & (upper_bb < upper_kc)
    sqz_off = (lower_bb < lower_kc) & (upper_bb > upper_kc)
    hh = high.rolling(length, min_periods=length).max()
    ll = low.rolling(length, min_periods=length).min()
    avg_hl = (hh + ll) / 2
    avg_val = (avg_hl + basis) / 2
    y_series = (close - avg_val).to_numpy()
    val = pd.Series(fast_linreg_val(y_series, length), index=df.index)
    return sqz_on, sqz_off, val


def williams_vix_fix(df: pd.DataFrame, pd_len: int = 22, bbl: int = 20, mult: float = 2.0, lb: int = 50, ph: float = 0.85):
    close = df["close"]
    low = df["low"]
    hc = close.rolling(pd_len, min_periods=pd_len).max()
    wvf = (hc - low) / hc * 100
    mid = wvf.rolling(bbl, min_periods=bbl).mean()
    s_dev = mult * wvf.rolling(bbl, min_periods=bbl).std()
    upper_band = mid + s_dev
    range_high = wvf.rolling(lb, min_periods=lb).max() * ph
    alert = (wvf >= upper_band) | (wvf >= range_high)
    return wvf, alert
