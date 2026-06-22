"""
Configuration script for FVG Strategy on XAUUSD Gold.
Parameters provided by user:
- ATR Period: 200
- TP Multiplier: 4
- SL Multiplier: 2
- TS Multiplier: 2
- FVG Width Filter: 0
"""

import pandas as pd
import sys
import os

# Project root path
PROJECT_ROOT = r'd:\Phong\03_Finance\finance-scanner'
sys.path.append(PROJECT_ROOT)

from indicators.fvg_core import detect_imfvg_from_bars, BULL, BEAR

# Strategy Configuration
CONFIG = {
    "ATR_PERIOD": 200,
    "TP_MULT": 4, # Take Profit = Close +/- (TP_MULT * ATR)
    "SL_MULT": 2, # Stop Loss = Close -/+ (SL_MULT * ATR)
    "TS_MULT": 2, # Trailing Stop distance = (TS_MULT * ATR)
    "FILTER_WIDTH": 0,
    "SYMBOL": "XAUUSD",
    "TIMEFRAME": "M3"
}

def calculate_atr(df, period):
    """Calculates ATR using RMA (Running Moving Average) logic common in Pine Script."""
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # RMA (Running Moving Average)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    return atr

def scan_fvg_signals(df):
    """
    Scans a dataframe for FVG signals using the specified configuration.
    Returns a dataframe with signals and trade levels.
    """
    # Ensure ATR is calculated
    df = df.copy()
    df['atr'] = calculate_atr(df, CONFIG["ATR_PERIOD"])
    
    signals = []
    
    # Need at least 4 bars
    for i in range(3, len(df)):
        b3 = df.iloc[i-3]
        b2 = df.iloc[i-2]
        b1 = df.iloc[i-1]
        b0 = df.iloc[i]
        
        result = detect_imfvg_from_bars(
            b3_low=float(b3['low']), b3_high=float(b3['high']), b3_close=float(b3['close']),
            b2_close=float(b2['close']),
            b1_low=float(b1['low']), b1_high=float(b1['high']),
            b0_close=float(b0['close']),
            filter_width=float(CONFIG["FILTER_WIDTH"]),
            atr=float(b0['atr'])
        )
        
        if result['signal']:
            atr_val = float(b0['atr'])
            sig_type = result['signal']
            
            # PINE LOGIC: Level = Midpoint of Gap
            if sig_type == BULL:
                gap_base = (float(b3['low']) + float(b1['high'])) / 2.0
                tp = gap_base + CONFIG["TP_MULT"] * atr_val
                sl = gap_base - CONFIG["SL_MULT"] * atr_val
            else: # BEAR
                gap_base = (float(b1['low']) + float(b3['high'])) / 2.0
                tp = gap_base - CONFIG["TP_MULT"] * atr_val
                sl = gap_base + CONFIG["SL_MULT"] * atr_val
                
            signals.append({
                "timestamp": df.index[i],
                "signal": sig_type,
                "entry": float(b0['close']),
                "gap_midpoint": gap_base,
                "gap_top": result['gap_top'],
                "gap_bottom": result['gap_bottom'],
                "tp": tp,
                "sl": sl,
                "ts_dist": CONFIG["TS_MULT"] * atr_val
            })
            
    return pd.DataFrame(signals)

if __name__ == "__main__":
    # Example usage
    DATA_PATH = r'd:\Phong\03_Finance\finance-scanner\backtest\cache\gold\3mi\XAUUSD_M3_HistData.parquet'
    if os.path.exists(DATA_PATH):
        print(f"Loading data from {DATA_PATH}...")
        df_hist = pd.read_parquet(DATA_PATH)
        print("Scanning for signals...")
        sig_df = scan_fvg_signals(df_hist)
        
        if not sig_df.empty:
            print(f"Found {len(sig_df)} signals total.")
            # Show last 10 signals
            print(sig_df.tail(10))
        else:
            print("No signals found.")
    else:
        print(f"Data file not found at {DATA_PATH}")
