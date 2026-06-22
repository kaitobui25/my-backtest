import os
import sys
import numpy as np
import pandas as pd
import warnings

warnings.filterwarnings("ignore")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_DIR = os.path.join(BASE_DIR, "..", "core")
sys.path.insert(0, CORE_DIR)

import vectorbt as vbt
from signals import (
    calc_atr_rma, calc_adx, fvg_nb,
    supertrend_nb, rsi_reversal, bb_bounce, triple_ema,
    apply_ema_filter, apply_adx_filter,
)
from wfo_engine import (
    sim_fixed_nb, sim_trailing_nb, sim_partial_tp_nb,
    compute_metrics,
)

def simulate_config(cfg, high, low, close, signal, atr):
    mode = cfg["mode"]
    sl   = float(cfg["sl_mult"])
    wait = int(cfg["wait_candles"])
    rr = float(cfg["rr"])
    tp1_rr = float(cfg["rr"]) # Using rr as tp1_rr for PARTIAL_TP
    if mode == "FIXED":
        return sim_fixed_nb(high, low, close, signal, atr, sl, rr, wait)
    elif mode == "TRAILING":
        return sim_trailing_nb(high, low, close, signal, atr, sl, wait)
    else:
        return sim_partial_tp_nb(high, low, close, signal, atr, sl, tp1_rr, wait)

def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 90)
    print("  CROSS-PERIOD VALIDATION: Top 20 (v3 spread) → Old Data (before_20251001)")
    print("=" * 90)

    DATA_PATH = r"d:\Phong\03_Finance\trade\vectorbt-master\my-data\cache\m3\XAUUSD.sml_M3_60000_before_20251001.parquet"
    df = pd.read_parquet(DATA_PATH)
    print(f"\n[DATA] {len(df):,} bars | {df.index[0]} -> {df.index[-1]}")

    print("[INDICATORS] Computing...")
    atr200 = calc_atr_rma(df["high"], df["low"], df["close"], period=200)
    adx14  = calc_adx(df["high"], df["low"], df["close"], period=14)

    ema_dict = {0: None}
    for ep in [50, 100, 200]:
        ema_dict[ep] = vbt.MA.run(df["close"], ep, ewm=True).ma.values

    print("[SIGNALS] Computing base signals...")
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    fvg_raw = fvg_nb(h, l, c, atr200, filter_width=0.1)
    
    registry = {
        "FVG": fvg_raw,
    }

    print("[CONFIGS] Loading Top 20 from v3 report...")
    csv_path = r"d:\Phong\03_Finance\trade\vectorbt-master\my-data\backtest_v2\result\05\05v3_fvg_m3_deep_strategies.csv"
    top_df = pd.read_csv(csv_path).head(20)

    summary_rows = []

    for idx, row in top_df.iterrows():
        cfg = row.to_dict()
        label = f"Top{int(row['rank'])}: {cfg['signal']} | {cfg['mode']} | SL={cfg['sl_mult']} | RR={cfg['rr']} | EMA={cfg['ema_filter']} | ADX={cfg['adx_thresh']} | W={cfg['wait_candles']}"

        sig = registry[cfg["signal"]].copy()
        ema_f = int(cfg["ema_filter"])
        if ema_f > 0:
            ema_arr = ema_dict.get(ema_f)
            if ema_arr is not None:
                sig = apply_ema_filter(sig, c, ema_arr)
        
        adx_t = float(cfg["adx_thresh"])
        if adx_t > 0:
            sig = apply_adx_filter(sig, adx14, adx_t)

        trets, n_trades = simulate_config(cfg, h, l, c, sig, atr200)
        m = compute_metrics(trets, n_trades) # Cost 0.15R inside compute_metrics!
        
        composite = max(m["calmar"], 0.0) * 0.6 + max(m["sharpe"], 0.0) * 0.4
        
        summary_rows.append({
            "rank": int(cfg["rank"]),
            "label": label,
            "trades": n_trades,
            "wr": m["wr"],
            "total_ret": m["total_ret"],
            "max_dd": m["max_dd"],
            "calmar": m["calmar"],
            "sharpe": m["sharpe"],
            "composite": composite,
        })
        print(f"Tested Top {int(cfg['rank']):>2}: Trades={n_trades:>4}, Profit={m['total_ret']*100:>+6.2f}%, WR={m['wr']*100:>4.1f}%")

    print(f"\n\n{'='*115}")
    print(f"{'CROSS-PERIOD VALIDATION SUMMARY (Test on OLD DATA)':^115}")
    print(f"{'='*115}")
    print(f"{'#':>2} {'Setup':>75} | {'Trades':>6} {'WR%':>6} {'Profit%':>8} {'DD%':>6} {'Calmar':>7} {'Comp':>6}")
    print(f"{'-'*115}")
    for r in summary_rows:
        print(f"{r['rank']:>2} {r['label']:>75} | {r['trades']:>6} {r['wr']*100:>5.1f}% "
              f"{r['total_ret']*100:>+7.1f}% {r['max_dd']*100:>5.1f}% "
              f"{r['calmar']:>7.2f} {r['composite']:>6.2f}")

    profitable = [r for r in summary_rows if r["total_ret"] > 0]
    print(f"\n  VERDICT: {len(profitable)}/20 configs profitable on old data.")

if __name__ == '__main__':
    main()
