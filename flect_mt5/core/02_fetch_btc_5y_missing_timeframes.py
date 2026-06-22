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

        existing_files = []
        df_existing = pd.DataFrame()
        if not args.overwrite:
            existing_files = list(out_dir.glob(f"{symbol}_{name}_*.parquet"))
            if existing_files:
                dfs = []
                for f in existing_files:
                    try:
                        dfs.append(pd.read_parquet(f))
                    except Exception as e:
                        print(f"Error reading {f.name}: {e}")
                if dfs:
                    df_existing = pd.concat(dfs)
                    df_existing = df_existing[~df_existing.index.duplicated(keep="last")]
                    df_existing.sort_index(inplace=True)

        start_dt_naive = start_dt.replace(tzinfo=None)
        end_dt_naive = end_dt.replace(tzinfo=None)

        df_new_parts = []
        if df_existing.empty:
            print(f"{name}: Fetching full range {start_dt.isoformat()} -> {end_dt.isoformat()}...")
            rates = mt5.copy_rates_range(symbol, timeframe, start_dt, end_dt)
            if rates is not None and len(rates) > 0:
                df_new = pd.DataFrame(rates)
                df_new["time"] = pd.to_datetime(df_new["time"], unit="s", utc=True).dt.tz_localize(None)
                df_new.set_index("time", inplace=True)
                df_new = df_new[["open", "high", "low", "close", "tick_volume"]]
                df_new.rename(columns={"tick_volume": "volume"}, inplace=True)
                df_new_parts.append(df_new)
            else:
                print(f"{name}: NO_DATA or error: {mt5.last_error()}")
        else:
            exist_min = df_existing.index.min()
            exist_max = df_existing.index.max()

            # 1. Fetch older prefix if target start_dt is earlier than existing min
            if exist_min > start_dt_naive:
                print(f"{name}: Fetching missing history prefix {start_dt.isoformat()} -> {exist_min.isoformat()}...")
                prefix_end = exist_min.to_pydatetime().replace(tzinfo=timezone.utc)
                rates = mt5.copy_rates_range(symbol, timeframe, start_dt, prefix_end)
                if rates is not None and len(rates) > 0:
                    df_prefix = pd.DataFrame(rates)
                    df_prefix["time"] = pd.to_datetime(df_prefix["time"], unit="s", utc=True).dt.tz_localize(None)
                    df_prefix.set_index("time", inplace=True)
                    df_prefix = df_prefix[["open", "high", "low", "close", "tick_volume"]]
                    df_prefix.rename(columns={"tick_volume": "volume"}, inplace=True)
                    df_new_parts.append(df_prefix)

            # 2. Fetch newer suffix if target end_dt is later than existing max
            if exist_max < end_dt_naive:
                print(f"{name}: Fetching missing recent suffix {exist_max.isoformat()} -> {end_dt.isoformat()}...")
                suffix_start = exist_max.to_pydatetime().replace(tzinfo=timezone.utc)
                rates = mt5.copy_rates_range(symbol, timeframe, suffix_start, end_dt)
                if rates is not None and len(rates) > 0:
                    df_suffix = pd.DataFrame(rates)
                    df_suffix["time"] = pd.to_datetime(df_suffix["time"], unit="s", utc=True).dt.tz_localize(None)
                    df_suffix.set_index("time", inplace=True)
                    df_suffix = df_suffix[["open", "high", "low", "close", "tick_volume"]]
                    df_suffix.rename(columns={"tick_volume": "volume"}, inplace=True)
                    df_new_parts.append(df_suffix)

        if df_new_parts:
            all_dfs = [df_existing] + df_new_parts if not df_existing.empty else df_new_parts
            df_combined = pd.concat(all_dfs)
            df_combined = df_combined[~df_combined.index.duplicated(keep="last")]
            df_combined.sort_index(inplace=True)
        else:
            df_combined = df_existing

        if df_combined.empty:
            print(f"{name}: No data available.")
            continue

        df_final = df_combined.loc[start_dt_naive:end_dt_naive]
        if df_final.empty:
            print(f"{name}: No data in requested 5-year window ({start_dt_naive} to {end_dt_naive})")
            continue

        start_label = df_final.index.min().strftime("%Y%m%d")
        end_label = df_final.index.max().strftime("%Y%m%d")
        out_file = out_dir / f"{symbol}_{name}_5y_{start_label}_{end_label}.parquet"

        if out_file.exists() and not args.overwrite:
            print(f"{name}: Up to date {out_file.name}")
        else:
            df_final.to_parquet(out_file, engine="pyarrow")
            print(f"{name}: saved {len(df_final):,} bars -> {out_file}")

        # Clean up old files
        for f in existing_files:
            if f.resolve() != out_file.resolve():
                try:
                    f.unlink()
                    print(f"{name}: Cleaned up old cache file {f.name}")
                except Exception as e:
                    print(f"Warning: could not delete old cache file {f.name}: {e}")

    mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
