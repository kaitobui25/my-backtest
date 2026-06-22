from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .config import BacktestConfig


def timeframe_folder(timeframe: str) -> str:
    return timeframe.lower()


def find_data_file(config: BacktestConfig, timeframe: str) -> Path:
    folder = config.data_path / timeframe_folder(timeframe)
    symbol = config.symbol
    patterns = [
        f"{symbol}_{timeframe.upper()}_*.parquet",
        f"{symbol}_{timeframe.upper()}_*.csv",
        f"*_{timeframe.upper()}_*.parquet",
        f"*_{timeframe.upper()}_*.csv",
    ]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(folder.glob(pattern)))
        if files:
            break
    if not files:
        raise FileNotFoundError(f"No OHLCV file for {symbol} {timeframe} under {folder}")
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name))[-1]


def load_ohlcv(config: BacktestConfig, timeframe: str) -> pd.DataFrame:
    path = find_data_file(config, timeframe)
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported data file: {path}")
    df = normalize_ohlcv(df)
    if config.start is not None:
        df = df[df.index >= config.start]
    if config.end is not None:
        df = df[df.index <= config.end]
    if df.empty:
        raise ValueError(f"No bars left after date filter for {config.symbol} {timeframe}")
    return df


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    frame.columns = [str(c).lower() for c in frame.columns]
    if not isinstance(frame.index, pd.DatetimeIndex):
        time_col = next((c for c in ["time", "datetime", "date", "timestamp"] if c in frame.columns), None)
        if time_col is None:
            raise ValueError("OHLCV data needs a DatetimeIndex or a time/datetime/date/timestamp column")
        frame[time_col] = pd.to_datetime(frame[time_col])
        frame = frame.set_index(time_col)
    frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"Missing OHLC columns: {', '.join(missing)}")
    if "volume" not in frame.columns:
        frame["volume"] = 0.0
    frame = frame[["open", "high", "low", "close", "volume"]]
    frame = frame[~frame.index.duplicated(keep="last")]
    frame = frame.dropna()
    return frame.astype(float)


def timeframe_to_timedelta(timeframe: str) -> pd.Timedelta | None:
    tf = timeframe.upper()
    if tf.startswith("M") and tf[1:].isdigit():
        return pd.Timedelta(minutes=int(tf[1:]))
    if tf.startswith("H") and tf[1:].isdigit():
        return pd.Timedelta(hours=int(tf[1:]))
    if tf == "D1":
        return pd.Timedelta(days=1)
    if tf == "W1":
        return pd.Timedelta(weeks=1)
    return None


def audit_data(config: BacktestConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for timeframe in config.timeframes:
        row: dict[str, Any] = {"timeframe": timeframe}
        try:
            file_path = find_data_file(config, timeframe)
            df = load_ohlcv(config, timeframe)
            diffs = df.index.to_series().diff().dropna()
            expected = timeframe_to_timedelta(timeframe)
            gap_count = int((diffs > expected * 1.5).sum()) if expected is not None and not diffs.empty else 0
            gap_rows = _gap_rows(df.index, expected)
            missing_bars = int(gap_rows["missing_bars"].sum()) if not gap_rows.empty else 0
            expected_bars = int(len(df) + missing_bars)
            missing_bar_ratio = float(missing_bars / expected_bars) if expected_bars else 0.0
            weekend_gap_count = int(gap_rows["contains_weekend"].sum()) if not gap_rows.empty else 0
            weekday_gap_count = int((~gap_rows["contains_weekend"]).sum()) if not gap_rows.empty else 0
            max_gap_missing_bars = int(gap_rows["missing_bars"].max()) if not gap_rows.empty else 0
            gap_warn = _gap_warning(config, gap_count, missing_bar_ratio)
            row.update(
                {
                    "file": str(file_path),
                    "rows": len(df),
                    "first": df.index.min(),
                    "last": df.index.max(),
                    "duplicate_index": int(df.index.duplicated().sum()),
                    "na_rows": int(df.isna().any(axis=1).sum()),
                    "expected_step": str(expected) if expected is not None else "",
                    "max_gap": str(diffs.max()) if not diffs.empty else "",
                    "gap_count_gt_1_5x": gap_count,
                    "weekend_gap_count": weekend_gap_count,
                    "weekday_gap_count": weekday_gap_count,
                    "estimated_missing_bars": missing_bars,
                    "expected_bars": expected_bars,
                    "missing_bar_ratio": missing_bar_ratio,
                    "max_gap_missing_bars": max_gap_missing_bars,
                    "data_gap_warning": gap_warn,
                    "close_return_pct": (df["close"].iloc[-1] / df["close"].iloc[0] - 1.0) * 100.0,
                    "status": "ok",
                }
            )
        except Exception as exc:
            row.update({"status": "error", "error": str(exc)})
        rows.append(row)
    return pd.DataFrame(rows)


def _gap_rows(index: pd.DatetimeIndex, expected: pd.Timedelta | None) -> pd.DataFrame:
    if expected is None or len(index) < 2:
        return pd.DataFrame(columns=["prev_time", "next_time", "gap", "missing_bars", "contains_weekend"])
    rows: list[dict[str, Any]] = []
    prev_values = index[:-1]
    next_values = index[1:]
    for prev_time, next_time in zip(prev_values, next_values):
        gap = next_time - prev_time
        if gap <= expected * 1.5:
            continue
        missing_bars = max(0, int(round(gap / expected)) - 1)
        rows.append(
            {
                "prev_time": prev_time,
                "next_time": next_time,
                "gap": gap,
                "missing_bars": missing_bars,
                "contains_weekend": _contains_weekend(prev_time, next_time),
            }
        )
    return pd.DataFrame(rows)


def _contains_weekend(start: pd.Timestamp, end: pd.Timestamp) -> bool:
    day = start.normalize()
    last = end.normalize()
    while day <= last:
        if day.weekday() >= 5:
            return True
        day += pd.Timedelta(days=1)
    return False


def _gap_warning(config: BacktestConfig, gap_count: int, missing_bar_ratio: float) -> str:
    dq = config.data_quality
    max_gap_count = int(dq.get("max_gap_count_warn", 20))
    max_missing_ratio = float(dq.get("max_missing_bar_ratio_warn", 0.05))
    if gap_count > max_gap_count or missing_bar_ratio > max_missing_ratio:
        return "large_data_gaps"
    return ""
