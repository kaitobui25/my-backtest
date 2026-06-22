"""
Fetch recent 5-year BTCUSD MT5 bars for missing higher timeframes.

Skipped because already cached:
  M5, M15, M30, H1, H4, D1, W1, MN1

Default target timeframes:
  M6, M10, M12, M20, H2, H3, H6, H8, H12
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    relativedelta = None

try:
    import MetaTrader5 as mt5
    import pandas as pd
except ImportError as e:
    print(f"Missing library: {e}")
    print("Please run: pip install MetaTrader5 pandas pyarrow python-dateutil")
    sys.exit(1)


ROOT = Path(__file__).resolve().parents[3]
OUT_ROOT = ROOT / "my-data" / "flect_mt5" / "cache" / "btc"

TIMEFRAMES = {
    "M6": mt5.TIMEFRAME_M6,
    "M10": mt5.TIMEFRAME_M10,
    "M12": mt5.TIMEFRAME_M12,
    "M20": mt5.TIMEFRAME_M20,
    "H2": mt5.TIMEFRAME_H2,
    "H3": mt5.TIMEFRAME_H3,
    "H6": mt5.TIMEFRAME_H6,
    "H8": mt5.TIMEFRAME_H8,
    "H12": mt5.TIMEFRAME_H12,
}


def resolve_symbol(requested: str) -> str:
    symbols = mt5.symbols_get()
    if not symbols:
        return requested

    requested_upper = requested.upper()
    for symbol in symbols:
        if symbol.name.upper() == requested_upper:
            return symbol.name
    for symbol in symbols:
        if requested_upper in symbol.name.upper():
            return symbol.name
    return requested


def parse_utc(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)

    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def five_years_before(dt: datetime) -> datetime:
    if relativedelta is not None:
        return dt - relativedelta(years=5)
    return dt.replace(year=dt.year - 5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch recent 5-year BTCUSD MT5 data for missing timeframes.")
    parser.add_argument("--symbol", default="BTCUSD", help="MT5 symbol or partial symbol name")
    parser.add_argument("--end-date", default=None, help="UTC end datetime, for example 2026-06-07T00:00:00")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files for these timeframes")
    args = parser.parse_args()

    end_dt = parse_utc(args.end_date)
    start_dt = five_years_before(end_dt)

    if not mt5.initialize():
        print(f"Cannot initialize MT5: {mt5.last_error()}")
        print("Open MetaTrader 5 and log in to the trading account first.")
        return 1

    symbol = resolve_symbol(args.symbol)
    if not mt5.symbol_select(symbol, True):
        print(f"Cannot select symbol {symbol}: {mt5.last_error()}")
        mt5.shutdown()
        return 1

    print(f"Symbol: {symbol}")
    print(f"Range UTC: {start_dt.isoformat()} -> {end_dt.isoformat()}")
    print(f"Output root: {OUT_ROOT}")

    for name, timeframe in TIMEFRAMES.items():
        out_dir = OUT_ROOT / name.lower()
        out_dir.mkdir(parents=True, exist_ok=True)

        existing = sorted(out_dir.glob(f"{symbol}_{name}_*.parquet"))
        if existing and not args.overwrite:
            print(f"{name}: SKIP existing {existing[-1].name}")
            continue

        print(f"{name}: fetching...")
        rates = mt5.copy_rates_range(symbol, timeframe, start_dt, end_dt)
        if rates is None or len(rates) == 0:
            print(f"{name}: NO_DATA {mt5.last_error()}")
            continue

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None)
        df.set_index("time", inplace=True)
        df = df[["open", "high", "low", "close", "tick_volume"]]
        df.rename(columns={"tick_volume": "volume"}, inplace=True)
        df.sort_index(inplace=True)

        start_label = df.index.min().strftime("%Y%m%d")
        end_label = df.index.max().strftime("%Y%m%d")
        out_file = out_dir / f"{symbol}_{name}_5y_{start_label}_{end_label}.parquet"
        if out_file.exists() and not args.overwrite:
            print(f"{name}: SKIP existing {out_file.name}")
            continue

        df.to_parquet(out_file, engine="pyarrow")
        print(f"{name}: saved {len(df):,} bars -> {out_file}")

    mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
