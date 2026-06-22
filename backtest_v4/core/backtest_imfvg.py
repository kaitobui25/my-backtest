import pandas as pd
import numpy as np
import vectorbt as vbt
import os

def backtest():
    # 1. Load Data
    data_path = r'd:\Phong\03_Finance\trade\vectorbt-master\my-data\cache\m5\XAUUSD.sml_M5_800000_before_20260418.parquet'
    if not os.path.exists(data_path):
        print(f"Data file not found: {data_path}")
        return

    print("Loading data...")
    df = pd.read_parquet(data_path)
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    print("Calculating indicators...")
    ema200 = close.ewm(span=200, adjust=False).mean()
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rsi = 100 - (100 / (1 + gain / loss))
    vol_sma = volume.rolling(window=20).mean()
    
    tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    plus_dm = high.diff()
    minus_dm = low.shift(1) - low
    plus_dm = np.where((plus_dm > 0) & (plus_dm > minus_dm), plus_dm, 0)
    minus_dm = np.where((minus_dm > 0) & (minus_dm > plus_dm), minus_dm, 0)
    
    def wilder_smooth(series, period):
        return series.ewm(alpha=1/period, adjust=False).mean()

    tr_s = wilder_smooth(tr, 14)
    plus_di = 100 * (wilder_smooth(pd.Series(plus_dm, index=df.index), 14) / tr_s)
    minus_di = 100 * (wilder_smooth(pd.Series(minus_dm, index=df.index), 14) / tr_s)
    adx = wilder_smooth(100 * (plus_di - minus_di).abs() / (plus_di + minus_di), 14)

    # 2. IMFVG Detection
    print("Detecting IMFVG...")
    active_bear_top = low.shift(2).where(high < low.shift(2)).ffill(limit=50)
    active_bear_bot = high.where(high < low.shift(2)).ffill(limit=50)
    active_bull_top = low.where(low > high.shift(2)).ffill(limit=50)
    active_bull_bot = high.shift(2).where(low > high.shift(2)).ffill(limit=50)
    
    imfvg_bull_signal = (close > active_bear_top) & (close.shift(1) <= active_bear_top.shift(1))
    imfvg_bear_signal = (close < active_bull_bot) & (close.shift(1) >= active_bull_bot.shift(1))

    # 3. Entry Logic
    print("Generating entries...")
    long_entries = imfvg_bull_signal & (close > ema200) & (adx > 20) & (rsi < 60) & (volume > vol_sma)
    short_entries = imfvg_bear_signal & (close < ema200) & (adx > 20) & (rsi > 40) & (volume > vol_sma)

    # 4. SL/TP Calculation
    sl_long_price = active_bear_bot.where(imfvg_bull_signal).ffill()
    sl_short_price = active_bull_top.where(imfvg_bear_signal).ffill()
    
    sl_ratio_long = ((close - sl_long_price) / close).clip(lower=0.001, upper=0.03)
    sl_ratio_short = ((sl_short_price - close) / close).clip(lower=0.001, upper=0.03)
    
    # Combine SL/TP ratios into single Series
    sl_stop = pd.Series(np.nan, index=df.index)
    sl_stop.loc[long_entries] = sl_ratio_long.loc[long_entries]
    sl_stop.loc[short_entries] = sl_ratio_short.loc[short_entries]
    sl_stop = sl_stop.ffill() # Maintain for the trade duration

    # 5. Simulation
    print("Running simulation...")
    try:
        pf = vbt.Portfolio.from_signals(
            close,
            entries=long_entries,
            short_entries=short_entries,
            sl_stop=sl_stop,
            tp_stop=sl_stop, # RR 1:1
            init_cash=10000,
            fees=0.0002,
            freq='5min'
        )
        
        # Access value safely
        tr_val = pf.total_return()
        sr_val = pf.sharpe_ratio()
        wr_val = pf.trades.win_rate()
        nt_val = pf.trades.count()
        
        # If they are still series, take the first element
        if isinstance(tr_val, pd.Series): tr_val = tr_val.iloc[0]
        if isinstance(sr_val, pd.Series): sr_val = sr_val.iloc[0]
        if isinstance(wr_val, pd.Series): wr_val = wr_val.iloc[0]
        if isinstance(nt_val, pd.Series): nt_val = nt_val.iloc[0]

        print("\n=== STRATEGY RESULTS ===")
        print(f"Total Return: {tr_val * 100:.2f}%")
        print(f"Sharpe Ratio: {sr_val:.4f}")
        print(f"Win Rate: {wr_val * 100:.2f}%")
        print(f"Total Trades: {nt_val}")
        
        trades = pf.trades.records_readable
        trades.to_csv(r"d:\Phong\03_Finance\trade\vectorbt-master\my-data\imfvg_trades.csv")
        print("Trades saved to imfvg_trades.csv")

    except Exception as e:
        print(f"Simulation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    backtest()
