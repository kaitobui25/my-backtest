from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit


ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = ROOT / "my-data" / "flect_mt5" / "cache" / "btc"
OUT_DIR = ROOT / "my-data" / "flect_mt5" / "result" / "btc_strategy_search"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SYMBOL = "BTCUSD"
TEST_START = pd.Timestamp("2025-01-01")

# Current BTCUSD MT5 spread observed near 48 USD on 73,600 USD BTC, roughly 0.065% round trip.
# Use a slightly rounded conservative cost model. Change this before running if broker terms differ.
FEE_PER_SIDE = 0.00035

MIN_FULL_TRADES = {
    "M15": 80,
    "M30": 70,
    "H1": 55,
    "H4": 28,
    "D1": 12,
}
MIN_TEST_TRADES = {
    "M15": 20,
    "M30": 18,
    "H1": 14,
    "H4": 7,
    "D1": 4,
}


@dataclass(frozen=True)
class Candidate:
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
    test_trades: int
    test_win_rate: float
    test_total_return: float
    test_profit_factor: float
    test_expectancy: float
    score: float


def load_ohlc(timeframe: str) -> pd.DataFrame:
    folder = timeframe.lower()
    if timeframe == "D1":
        folder = "d1"
    files = sorted((DATA_ROOT / folder).glob(f"{SYMBOL}_{timeframe}_*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet for {timeframe} under {DATA_ROOT / folder}")
    df = pd.read_parquet(files[-1]).sort_index()
    df.index = pd.to_datetime(df.index)
    return df[["open", "high", "low", "close", "volume"]].dropna().astype(float)


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


def shift_signal(signal: pd.Series) -> np.ndarray:
    return signal.shift(1).fillna(False).to_numpy(dtype=np.bool_)


def side_mode_arrays(long_entries: np.ndarray, short_entries: np.ndarray, side_mode: str) -> tuple[np.ndarray, np.ndarray]:
    if side_mode == "long_only":
        return long_entries, np.zeros_like(short_entries)
    if side_mode == "short_only":
        return np.zeros_like(long_entries), short_entries
    return long_entries, short_entries


def build_signals(df: pd.DataFrame, timeframe: str) -> list[tuple[str, str, np.ndarray, np.ndarray, tuple[str, ...]]]:
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

    signals: list[tuple[str, str, np.ndarray, np.ndarray, tuple[str, ...]]] = []

    # Trend pullback: participate with BTC drift after a reset into fast EMA.
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

    # Donchian breakout: BTC literature often supports momentum/trend following.
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

    # Bollinger pullback/reversion, separated by regime because BTC reversion breaks in strong trends.
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

    # Internal bar strength reversal. This tends to maximize winrate, so later filters must police payoff.
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

    # Volatility expansion continuation: require candle range expansion and close near the extreme.
    range_pct = (high - low) / close
    range_ma = range_pct.rolling(50, min_periods=50).median()
    body = (close - open_).abs()
    body_ratio = body / (high - low).replace(0, np.nan)
    for mult, trend_name, trend_ema, adx_min, close_extreme in product(
        [1.5, 2.0],
        ["200"],
        [ema200],
        [18, 24],
        [0.75, 0.85],
    ):
        strong_range = range_pct >= mult * range_ma
        long_sig = strong_range & (close > trend_ema) & (adx14 >= adx_min) & (body_ratio >= 0.55) & (ibs >= close_extreme)
        short_sig = strong_range & (close < trend_ema) & (adx14 >= adx_min) & (body_ratio >= 0.55) & (ibs <= 1 - close_extreme)
        params = f"range_mult={mult},trend={trend_name},adx_min={adx_min},extreme={close_extreme}"
        signals.append(("VOL_EXPANSION_CONT", params, shift_signal(long_sig), shift_signal(short_sig), ("long_only", "both")))

    # --- SUPERTREND ---
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

    # --- MACD CROSSOVER ---
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

    # --- WAVETREND ---
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

    # --- SQUEEZE MOMENTUM ---
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

    # --- WILLIAMS VIX FIX ---
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

    print(f"{timeframe}: built {len(signals)} signal variants")
    return signals


@njit(cache=True)
def simulate_trades(open_, high, low, close, long_entries, short_entries, sl, tp, fee_per_side, max_hold):
    n = open_.shape[0]
    trade_returns = np.empty(n, dtype=np.float64)
    exit_idx = np.empty(n, dtype=np.int64)
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
                    exit_idx[count] = i
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
                    exit_idx[count] = i
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
        exit_idx[count] = n - 1
        count += 1

    return trade_returns[:count], exit_idx[:count]


def metrics(returns: np.ndarray) -> tuple[int, float, float, float, float, float, float, float]:
    if returns.size == 0:
        return 0, np.nan, 0.0, np.nan, np.nan, np.nan, np.nan, np.nan
    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    equity = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(equity)
    drawdown = np.where(peak > 0, equity / peak - 1, 0)
    gross_profit = wins.sum()
    gross_loss = -losses.sum()
    pf = gross_profit / gross_loss if gross_loss > 0 else np.inf
    return (
        returns.size,
        wins.size / returns.size * 100,
        (equity[-1] - 1) * 100,
        pf,
        returns.mean() * 100,
        drawdown.min() * 100,
        wins.mean() * 100 if wins.size else np.nan,
        losses.mean() * 100 if losses.size else np.nan,
    )


def score_candidate(
    win_rate: float,
    total_return: float,
    profit_factor: float,
    expectancy: float,
    max_drawdown: float,
    trades: int,
    test_win_rate: float,
    test_total_return: float,
    test_profit_factor: float,
    test_expectancy: float,
) -> float:
    if np.isnan(win_rate) or np.isnan(test_win_rate) or np.isnan(expectancy) or np.isnan(test_expectancy):
        return -np.inf
    return (
        0.55 * win_rate
        + 0.75 * test_win_rate
        + 10.0 * min(profit_factor, 4.0)
        + 14.0 * min(test_profit_factor, 4.0)
        + 0.10 * total_return
        + 0.18 * test_total_return
        + 50.0 * max(expectancy, -0.5)
        + 65.0 * max(test_expectancy, -0.5)
        - 0.45 * abs(max_drawdown)
        + min(trades, 800) / 100.0
    )


def grid_for_timeframe(timeframe: str) -> tuple[list[float], list[float], list[int]]:
    if timeframe in {"M15", "M30"}:
        return (
            [0.010, 0.020, 0.040, 0.060],
            [0.005, 0.010, 0.020, 0.030],
            [48, 96, 0],
        )
    if timeframe == "H1":
        return (
            [0.015, 0.030, 0.060, 0.100],
            [0.0075, 0.015, 0.030, 0.050],
            [24, 72, 0],
        )
    if timeframe == "H4":
        return (
            [0.020, 0.040, 0.080, 0.140],
            [0.010, 0.020, 0.050, 0.100],
            [6, 18, 0],
        )
    return (
        [0.030, 0.060, 0.120, 0.180],
        [0.015, 0.030, 0.080, 0.120],
        [5, 10, 0],
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
    for strategy, params, long_entries, short_entries, side_modes in signals:
        if long_entries.sum() + short_entries.sum() < 8:
            continue
        for side_mode in side_modes:
            longs, shorts = side_mode_arrays(long_entries, short_entries, side_mode)
            if longs.sum() + shorts.sum() < 8:
                continue
            for sl, tp, max_hold in product(sl_values, tp_values, max_holds):
                if tp <= 2.5 * FEE_PER_SIDE:
                    continue
                returns, exits = simulate_trades(open_, high, low, close, longs, shorts, sl, tp, FEE_PER_SIDE, max_hold)
                tested += 1
                trades, wr, total_ret, pf, exp, max_dd, avg_win, avg_loss = metrics(returns)
                if trades < MIN_FULL_TRADES[timeframe] or total_ret <= 0 or pf < 1.05 or exp <= 0:
                    continue
                test_returns = returns[is_test_exit[exits]]
                test_trades, test_wr, test_ret, test_pf, test_exp, _, _, _ = metrics(test_returns)
                if (
                    test_trades < MIN_TEST_TRADES[timeframe]
                    or test_ret <= 0
                    or test_pf < 1.0
                    or test_exp <= 0
                    or test_wr < 48
                ):
                    continue
                score = score_candidate(wr, total_ret, pf, exp, max_dd, trades, test_wr, test_ret, test_pf, test_exp)
                candidates.append(
                    Candidate(
                        timeframe=timeframe,
                        strategy=strategy,
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


def summarize_buy_hold() -> pd.DataFrame:
    rows = []
    for timeframe in ["M15", "M30", "H1", "H4", "D1"]:
        df = load_ohlc(timeframe)
        full_return = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
        test = df[df.index >= TEST_START]
        test_return = (test["close"].iloc[-1] / test["close"].iloc[0] - 1) * 100 if len(test) else np.nan
        rows.append(
            {
                "timeframe": timeframe,
                "first": df.index.min(),
                "last": df.index.max(),
                "bars": len(df),
                "buy_hold_return_pct": full_return,
                "test_buy_hold_return_pct": test_return,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    all_candidates: list[Candidate] = []
    for timeframe in ["M15", "M30", "H1", "H4", "D1"]:
        all_candidates.extend(evaluate_timeframe(timeframe))

    buy_hold = summarize_buy_hold()
    buy_hold.to_csv(OUT_DIR / "buy_hold_benchmark.csv", index=False)

    if not all_candidates:
        print("No candidates survived filters.")
        return

    df = pd.DataFrame([c.__dict__ for c in all_candidates])
    df = df.sort_values(["score", "test_profit_factor", "test_total_return"], ascending=[False, False, False])
    df.to_csv(OUT_DIR / "btc_candidates_all.csv", index=False)

    high_wr = df[
        (df["win_rate"] >= 65)
        & (df["test_win_rate"] >= 58)
        & (df["profit_factor"] >= 1.20)
        & (df["test_profit_factor"] >= 1.10)
        & (df["test_total_return"] > 0)
    ].sort_values(["test_win_rate", "test_profit_factor", "test_total_return"], ascending=[False, False, False])
    high_wr.to_csv(OUT_DIR / "btc_candidates_high_winrate.csv", index=False)

    high_profit = df[
        (df["profit_factor"] >= 1.25)
        & (df["test_profit_factor"] >= 1.15)
        & (df["test_total_return"] >= 10)
        & (df["test_win_rate"] >= 50)
    ].sort_values(["test_total_return", "test_profit_factor", "score"], ascending=[False, False, False])
    high_profit.to_csv(OUT_DIR / "btc_candidates_high_profit.csv", index=False)

    report = OUT_DIR / "summary.md"
    with report.open("w", encoding="utf-8") as f:
        f.write("# BTCUSD Strategy Search\n\n")
        f.write(f"- Data root: `{DATA_ROOT}`\n")
        f.write(f"- Test/OOS starts: `{TEST_START.date()}`\n")
        f.write(f"- Cost model: `{FEE_PER_SIDE * 100:.3f}%` per side, `{FEE_PER_SIDE * 200:.3f}%` round trip.\n")
        f.write("- Entry signals are shifted by one candle and filled at next candle open.\n")
        f.write("- TP/SL use OHLC high/low. If TP and SL touch in the same candle, SL is assumed first.\n")
        f.write("- Equity compounds trade returns only, without mark-to-market drawdown between exits.\n\n")
        f.write("## Buy And Hold Benchmark\n\n")
        f.write(buy_hold.to_markdown(index=False))
        f.write("\n\n## Top Score Candidates\n\n")
        f.write(df.head(30).to_markdown(index=False))
        f.write("\n\n## High Winrate Candidates\n\n")
        f.write(high_wr.head(30).to_markdown(index=False) if not high_wr.empty else "No candidate passed high-winrate filters.\n")
        f.write("\n\n## High Profit Candidates\n\n")
        f.write(high_profit.head(30).to_markdown(index=False) if not high_profit.empty else "No candidate passed high-profit filters.\n")
        f.write("\n")

    print("\nTop score:")
    print(df.head(20).to_string(index=False))
    print("\nHigh winrate:")
    print((high_wr.head(20) if not high_wr.empty else high_wr).to_string(index=False))
    print("\nHigh profit:")
    print((high_profit.head(20) if not high_profit.empty else high_profit).to_string(index=False))
    print(f"\nSaved under {OUT_DIR}")


if __name__ == "__main__":
    main()
