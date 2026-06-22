from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Any, Iterable, Mapping, Protocol

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IndicatorMetadata:
    name: str
    display_name: str
    source: str
    converted_from: tuple[str, ...] = ()
    conversion_notes: str = ""
    repaint_risk: str = "low"
    uses_future_data: bool = False


@dataclass(frozen=True)
class SignalSet:
    indicator: str
    strategy: str
    params: dict[str, Any]
    long_signal: pd.Series
    short_signal: pd.Series
    warnings: tuple[str, ...] = field(default_factory=tuple)


class Indicator(Protocol):
    metadata: IndicatorMetadata

    def generate(self, df: pd.DataFrame, params: Mapping[str, Any]) -> list[SignalSet]:
        ...


def as_list(value: Any) -> list[Any]:
    if value is None:
        return [None]
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def param_product(params: Mapping[str, Any], keys: Iterable[str]) -> Iterable[dict[str, Any]]:
    key_list = list(keys)
    values = [as_list(params.get(k)) for k in key_list]
    for combo in product(*values):
        yield dict(zip(key_list, combo))


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(int(window), min_periods=int(window)).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=int(span), adjust=False, min_periods=int(span)).mean()


def rma(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(alpha=1 / int(window), adjust=False, min_periods=int(window)).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def atr(df: pd.DataFrame, window: int, method: str = "rma") -> pd.Series:
    tr = true_range(df)
    if method == "sma":
        return sma(tr, window)
    return rma(tr, window)


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = rma(gain, window)
    avg_loss = rma(loss, window)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr_value = atr(df, window)
    plus_di = 100 * rma(plus_dm, window) / atr_value
    minus_di = 100 * rma(minus_dm, window) / atr_value
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return rma(dx, window)


def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))


def crossunder(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))


def rolling_linreg_last(series: pd.Series, window: int) -> pd.Series:
    window = int(window)
    x = np.arange(window, dtype=float)
    x_mean = x.mean()
    denom = ((x - x_mean) ** 2).sum()

    def fit_last(y: np.ndarray) -> float:
        y_mean = y.mean()
        slope = float(((x - x_mean) * (y - y_mean)).sum() / denom) if denom else 0.0
        intercept = float(y_mean - slope * x_mean)
        return intercept + slope * (window - 1)

    return series.rolling(window, min_periods=window).apply(fit_last, raw=True)


def apply_regime_filter(
    long_signal: pd.Series,
    short_signal: pd.Series,
    close: pd.Series,
    ema_fast: pd.Series,
    ema_slow: pd.Series,
    adx_value: pd.Series,
    regime: str,
    adx_max: float | None,
) -> tuple[pd.Series, pd.Series]:
    if regime == "cycle":
        long_signal = long_signal & (close > ema_slow) & (ema_fast > ema_slow)
        short_signal = short_signal & (close < ema_slow) & (ema_fast < ema_slow)
    elif regime == "trend":
        long_signal = long_signal & (close > ema_slow)
        short_signal = short_signal & (close < ema_slow)
    elif regime == "range":
        if adx_max is None:
            raise ValueError("range regime requires adx_max")
        long_signal = long_signal & (adx_value <= float(adx_max))
        short_signal = short_signal & (adx_value <= float(adx_max))
    elif regime == "all":
        pass
    else:
        raise ValueError(f"Unknown regime: {regime}")
    return long_signal.fillna(False), short_signal.fillna(False)

