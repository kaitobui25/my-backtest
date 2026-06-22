import vectorbt as vbt
import numpy as np
from numba import njit

@njit
def get_ha_nb(open_p, high_p, low_p, close_p):
    """
    Numba-accelerated function to calculate Heikin-Ashi candles.
    Using renamed variables to avoid conflicts with built-ins.
    """
    ha_open = np.empty_like(open_p)
    ha_high = np.empty_like(high_p)
    ha_low = np.empty_like(low_p)
    ha_close = np.empty_like(close_p)
    
    for i in range(len(close_p)):
        # HA_Close is the average of the current bar's OHLC
        ha_close[i] = (open_p[i] + high_p[i] + low_p[i] + close_p[i]) / 4
        
        if i == 0:
            # For the first bar, HA_Open is the average of current Open and Close
            ha_open[i] = (open_p[i] + close_p[i]) / 2
        else:
            # For subsequent bars, HA_Open is the average of previous HA_Open and HA_Close
            ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2
            
        # HA_High and HA_Low are the extremes of (Actual High/Low, HA_Open, HA_Close)
        # Using explicit comparisons for maximum compatibility with Numba
        
        # Calculate HA_High
        val_h = high_p[i]
        if ha_open[i] > val_h: val_h = ha_open[i]
        if ha_close[i] > val_h: val_h = ha_close[i]
        ha_high[i] = val_h
        
        # Calculate HA_Low
        val_l = low_p[i]
        if ha_open[i] < val_l: val_l = ha_open[i]
        if ha_close[i] < val_l: val_l = ha_close[i]
        ha_low[i] = val_l
        
    return ha_open, ha_high, ha_low, ha_close

# Define the HeikinAshi indicator using VectorBT IndicatorFactory
HeikinAshi = vbt.IndicatorFactory(
    class_name='HeikinAshi',
    short_name='ha',
    input_names=['open', 'high', 'low', 'close'],
    output_names=['ha_open', 'ha_high', 'ha_low', 'ha_close']
).from_apply_func(get_ha_nb)
