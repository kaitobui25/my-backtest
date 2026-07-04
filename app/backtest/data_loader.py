from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.backtest.config import SYMBOL
from app.backtest.paths import DATA_ROOT


def load_ohlc(timeframe: str, data_root: Path = DATA_ROOT, symbol: str = SYMBOL) -> pd.DataFrame:
    folder = timeframe.lower()
    if timeframe == "D1":
        folder = "d1"
    files = sorted((data_root / folder).glob(f"{symbol}_{timeframe}_*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet for {timeframe} under {data_root / folder}")
    df = pd.read_parquet(files[-1]).sort_index()
    df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    return df[["open", "high", "low", "close", "volume"]].dropna().astype(float)
