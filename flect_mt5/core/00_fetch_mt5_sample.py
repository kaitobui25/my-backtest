"""
Script đa năng để lấy dữ liệu nến từ MetaTrader 5 cho mọi khung thời gian.

Cách chạy để lấy dữ liệu:
- Chọn timeframe: M1, M2, M3, M4, M5, M6, M10, M12, M15, M20, M30, H1, H2, H3, H4, H6, H8, H12, D1, W1, MN1
- Ví dụ lấy 60000 nến M5 trước tháng 3/2026:
  
  python 11_fetch_mt5.py --symbol XAUUSD --timeframe M5 --end_date 2026-03-01T00:00:00 --count 60000
- File sẽ lưu vào backtest/cache/gold/{timeframe}/ với tên {symbol}_{timeframe}_{count}_before_{date}.parquet
- Lưu ý: MT5 hiện tại chỉ có dữ liệu từ khoảng 2025-06-05 trở đi cho các timeframe.
"""

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    import MetaTrader5 as mt5
    import pandas as pd
    import pyarrow
except ImportError as e:
    print(f"Missing library: {e}")
    print("Please run: pip install MetaTrader5 pandas pyarrow")
    sys.exit(1)

import argparse

parser = argparse.ArgumentParser(description="Fetch MT5 bars for any timeframe ending before a target UTC date.")
parser.add_argument("--symbol", default=None, help="MT5 symbol name or alias (default: XAUUSD or GOLD if available)")
parser.add_argument("--out_dir", default=r"d:\Phong\03_Finance\finance-scanner\backtest\cache\gold", help="Base output directory")
parser.add_argument("--timeframe", default="M3", help="Timeframe: M1, M2, M3, M4, M5, M6, M10, M12, M15, M20, M30, H1, H2, H3, H4, H6, H8, H12, D1, W1, MN1")
parser.add_argument("--end_date", default="2024-10-01T00:00:00", help="UTC end datetime in ISO format, inclusive")
parser.add_argument("--count", type=int, default=60000, help="Number of candles to fetch")
args = parser.parse_args()

# Map timeframe string to MT5 constant
timeframe_map = {
    'M1': mt5.TIMEFRAME_M1,
    'M2': mt5.TIMEFRAME_M2,
    'M3': mt5.TIMEFRAME_M3,
    'M4': mt5.TIMEFRAME_M4,
    'M5': mt5.TIMEFRAME_M5,
    'M6': mt5.TIMEFRAME_M6,
    'M10': mt5.TIMEFRAME_M10,
    'M12': mt5.TIMEFRAME_M12,
    'M15': mt5.TIMEFRAME_M15,
    'M20': mt5.TIMEFRAME_M20,
    'M30': mt5.TIMEFRAME_M30,
    'H1': mt5.TIMEFRAME_H1,
    'H2': mt5.TIMEFRAME_H2,
    'H3': mt5.TIMEFRAME_H3,
    'H4': mt5.TIMEFRAME_H4,
    'H6': mt5.TIMEFRAME_H6,
    'H8': mt5.TIMEFRAME_H8,
    'H12': mt5.TIMEFRAME_H12,
    'D1': mt5.TIMEFRAME_D1,
    'W1': mt5.TIMEFRAME_W1,
    'MN1': mt5.TIMEFRAME_MN1,
}

if args.timeframe not in timeframe_map:
    print(f"Timeframe '{args.timeframe}' không hợp lệ. Các giá trị hợp lệ: {', '.join(timeframe_map.keys())}")
    sys.exit(1)

tf = timeframe_map[args.timeframe]

out_dir = os.path.join(args.out_dir, args.timeframe.lower())
os.makedirs(out_dir, exist_ok=True)


# Khởi tạo MT5
if not mt5.initialize():
    print("Không thể khởi tạo kết nối MT5. Code lỗi =", mt5.last_error())
    print("Vui lòng đảm bảo bạn đang mở phần mềm MetaTrader 5 trên máy tính.")
    sys.exit(1)

# Cố gắng tìm mã vàng (XAUUSD hoặc GOLD) phụ thuộc vào sàn
symbols = mt5.symbols_get()

def resolve_symbol(requested, symbols_list):
    if requested:
        requested_upper = requested.upper()
        for s in symbols_list:
            if requested_upper == s.name.upper():
                return s.name
        for s in symbols_list:
            if requested_upper in s.name.upper():
                return s.name
    return None


def find_oldest_bar(symbol, timeframe, max_search=500000):
    pos = 1
    last_ok = None
    while pos <= max_search:
        r = mt5.copy_rates_from_pos(symbol, timeframe, pos, 1)
        if r is None:
            break
        last_ok = pos
        pos *= 2
    if last_ok is None:
        return None
    low = last_ok
    high = min(pos, max_search + 1)
    while low + 1 < high:
        mid = (low + high) // 2
        r = mt5.copy_rates_from_pos(symbol, timeframe, mid, 1)
        if r is None:
            high = mid
        else:
            low = mid
    r = mt5.copy_rates_from_pos(symbol, timeframe, low, 1)
    return r[0]['time'] if r is not None else None

if symbols:
    if args.symbol:
        target_symbol = resolve_symbol(args.symbol, symbols)
        if target_symbol is None:
            print(f"Không tìm thấy symbol phù hợp cho '{args.symbol}' trên MT5. Thử dùng symbol trực tiếp.")
            target_symbol = args.symbol
    else:
        target_symbol = resolve_symbol("XAUUSD", symbols)
        if target_symbol is None:
            target_symbol = resolve_symbol("GOLD", symbols)
else:
    target_symbol = None

if target_symbol is None:
    target_symbol = "XAUUSD"  # Mặc định

# Đưa mã vào Market Watch
selected = mt5.symbol_select(target_symbol, True)
if not selected:
    print(f"Không thể chọn mã {target_symbol}, hãy đảm bảo bạn bật mã này trong MT5. Lỗi: {mt5.last_error()}")
    mt5.shutdown()
    sys.exit(1)

import pytz
from datetime import datetime

timezone = pytz.timezone("Etc/UTC")

try:
    utc_to = datetime.fromisoformat(args.end_date)
except ValueError:
    print(f"Định dạng end_date không hợp lệ: {args.end_date}. Ví dụ hợp lệ: 2024-10-01T00:00:00")
    mt5.shutdown()
    sys.exit(1)

if utc_to.tzinfo is None:
    utc_to = timezone.localize(utc_to)

print(f"Đang lấy {args.count} nến khung {args.timeframe} cho mã {target_symbol} kết thúc tại {utc_to.isoformat()} UTC...")
rates = mt5.copy_rates_from(target_symbol, tf, utc_to, args.count)

if rates is None or len(rates) == 0:
    err = mt5.last_error()
    print(f"Không lấy được dữ liệu nến cho mã {target_symbol}. Lỗi: {err}")
    oldest_ts = find_oldest_bar(target_symbol, tf)
    if oldest_ts is not None:
        oldest_dt = datetime.fromtimestamp(oldest_ts, pytz.utc)
        print(f"Dữ liệu {args.timeframe} hiện tại chỉ có từ {oldest_dt.isoformat()} UTC trở đi. Vui lòng chọn end_date muộn hơn.")
    mt5.shutdown()
    sys.exit(1)

df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
df.set_index('time', inplace=True)
df = df[['open', 'high', 'low', 'close', 'tick_volume']]
df.rename(columns={'tick_volume': 'volume'}, inplace=True)

out_file = os.path.join(out_dir, f"{target_symbol}_{args.timeframe}_{args.count}_before_{utc_to.strftime('%Y%m%d')}.parquet")
df.to_parquet(out_file, engine='pyarrow')

print(f"THÀNH CÔNG! Đã lưu {len(df)} nến {args.timeframe} của {target_symbol} vào file: {out_file}")
mt5.shutdown()
