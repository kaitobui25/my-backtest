"""
Check which MT5 timeframes can return bars for a symbol.

Example:
  python 01_check_mt5_timeframes.py --symbol BTCUSD --count 10
"""

import argparse
import sys
from datetime import datetime, timezone

try:
    import MetaTrader5 as mt5
    import pandas as pd
except ImportError as e:
    print(f"Missing library: {e}")
    print("Please run: pip install MetaTrader5 pandas")
    sys.exit(1)


TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M2": mt5.TIMEFRAME_M2,
    "M3": mt5.TIMEFRAME_M3,
    "M4": mt5.TIMEFRAME_M4,
    "M5": mt5.TIMEFRAME_M5,
    "M6": mt5.TIMEFRAME_M6,
    "M10": mt5.TIMEFRAME_M10,
    "M12": mt5.TIMEFRAME_M12,
    "M15": mt5.TIMEFRAME_M15,
    "M20": mt5.TIMEFRAME_M20,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H2": mt5.TIMEFRAME_H2,
    "H3": mt5.TIMEFRAME_H3,
    "H4": mt5.TIMEFRAME_H4,
    "H6": mt5.TIMEFRAME_H6,
    "H8": mt5.TIMEFRAME_H8,
    "H12": mt5.TIMEFRAME_H12,
    "D1": mt5.TIMEFRAME_D1,
    "W1": mt5.TIMEFRAME_W1,
    "MN1": mt5.TIMEFRAME_MN1,
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Check fetchable MT5 timeframes for one symbol.")
    parser.add_argument("--symbol", default="BTCUSD", help="Symbol or partial symbol name, for example BTCUSD or BTC")
    parser.add_argument("--count", type=int, default=10, help="Bars to request per timeframe")
    args = parser.parse_args()

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
    print("Timeframe, status, bars, oldest_time_utc, newest_time_utc")

    ok = []
    for name, timeframe in TIMEFRAMES.items():
        mt5.last_error()
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, args.count)
        if rates is None or len(rates) == 0:
            print(f"{name}, NO_DATA, 0, , ")
            continue

        df = pd.DataFrame(rates)
        times = pd.to_datetime(df["time"], unit="s", utc=True)
        oldest = times.min().isoformat()
        newest = times.max().isoformat()
        print(f"{name}, OK, {len(df)}, {oldest}, {newest}")
        ok.append(name)

    print("")
    print("Fetchable:", ", ".join(ok) if ok else "none")
    mt5.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
