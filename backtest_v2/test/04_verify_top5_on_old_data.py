"""
Verify Top 5 Composite configs (found on v2_new Oct2025-Apr2026)
against the OLD dataset: XAUUSD.sml_M3_60000_before_20251001.parquet (Jun-Sep 2025)

This is TRUE out-of-sample: configs were optimized on completely different time period.
"""

import os
import sys
import time
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
    sl   = cfg["sl_mult"]
    wait = cfg["wait_candles"]
    if mode == "FIXED":
        return sim_fixed_nb(high, low, close, signal, atr, sl, cfg["rr"], wait)
    elif mode == "TRAILING":
        return sim_trailing_nb(high, low, close, signal, atr, sl, wait)
    else:
        return sim_partial_tp_nb(high, low, close, signal, atr, sl, cfg["tp1_rr"], wait)


def monthly_breakdown(df, trets):
    nz_idx = np.where(trets != 0.0)[0]
    if len(nz_idx) == 0:
        print("    No trades.")
        return

    trades_df = pd.DataFrame({
        "date": df.index[nz_idx],
        "pnl_r": trets[nz_idx],
    })
    trades_df["month"] = trades_df["date"].dt.to_period("M")
    trades_df["win"] = trades_df["pnl_r"] > 0

    monthly = trades_df.groupby("month").agg(
        trades=("pnl_r", "count"),
        wins=("win", "sum"),
        total_r=("pnl_r", "sum"),
        avg_r=("pnl_r", "mean"),
    )
    monthly["wr_pct"] = (monthly["wins"] / monthly["trades"] * 100).round(1)

    for period in monthly.index:
        month_trades = trades_df[trades_df["month"] == period]["pnl_r"].values
        eq = 1.0
        for r in month_trades:
            eq *= (1.0 + 0.01 * r)
        monthly.loc[period, "eq_ret_pct"] = round((eq - 1.0) * 100, 2)

    print(f"    {'Month':>10s} {'Trades':>7s} {'Wins':>5s} {'WR%':>6s} {'Sum(R)':>8s} {'Avg(R)':>7s} {'Equity%':>8s}")
    print(f"    {'─'*55}")
    for period, row in monthly.iterrows():
        print(f"    {str(period):>10s} {int(row['trades']):>7d} {int(row['wins']):>5d} "
              f"{row['wr_pct']:>5.1f}% {row['total_r']:>+7.2f} {row['avg_r']:>+6.3f} "
              f"{row['eq_ret_pct']:>+7.2f}%")

    total_trades = int(monthly["trades"].sum())
    total_wins = int(monthly["wins"].sum())
    total_wr = total_wins / total_trades * 100 if total_trades > 0 else 0
    total_r = monthly["total_r"].sum()
    all_rets = trades_df["pnl_r"].values
    eq = 1.0
    for r in all_rets:
        eq *= (1.0 + 0.01 * r)
    total_eq = (eq - 1.0) * 100
    print(f"    {'─'*55}")
    print(f"    {'TOTAL':>10s} {total_trades:>7d} {total_wins:>5d} "
          f"{total_wr:>5.1f}% {total_r:>+7.2f}             {total_eq:>+7.2f}%")


def trade_distribution(trets):
    nz = trets[trets != 0.0]
    if len(nz) == 0:
        print("    No trades.")
        return
    wins = nz[nz > 0]
    losses = nz[nz < 0]
    print(f"    Total: {len(nz)} | Wins: {len(wins)} ({len(wins)/len(nz)*100:.1f}%) | "
          f"Losses: {len(losses)} ({len(losses)/len(nz)*100:.1f}%)")
    if len(wins) > 0:
        print(f"    Avg Win: {np.mean(wins):+.3f}R | Max Win: {np.max(wins):+.3f}R")
    if len(losses) > 0:
        print(f"    Avg Loss: {np.mean(losses):+.3f}R | Max Loss: {np.min(losses):+.3f}R")
    print(f"    Expectancy: {np.mean(nz):+.4f}R per trade")


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 90)
    print("  CROSS-PERIOD VALIDATION: Top 5 (v2_new) → Old Data (before_20251001)")
    print("=" * 90)

    # --- Load OLD data ---
    DATA_PATH = r"d:\Phong\03_Finance\trade\vectorbt-master\my-data\cache\m3\XAUUSD.sml_M3_60000_before_20251001.parquet"
    df = pd.read_parquet(DATA_PATH)
    print(f"\n[DATA] {len(df):,} bars | {df.index[0]} -> {df.index[-1]}")

    # --- Indicators ---
    print("[INDICATORS] Computing...")
    atr200 = calc_atr_rma(df["high"], df["low"], df["close"], period=200)
    adx14  = calc_adx(df["high"], df["low"], df["close"], period=14)

    ema_dict = {0: None}
    for ep in [50, 100, 200]:
        ema_dict[ep] = vbt.MA.run(df["close"], ep, ewm=True).ma.values

    # --- Signal Registry ---
    print("[SIGNALS] Building registry...")
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    fvg_raw = fvg_nb(h, l, c, atr200, filter_width=0.1)
    rsi_vals = vbt.RSI.run(df["close"], window=14).rsi.values
    bb_bnc = bb_bounce(df["close"], rsi_vals, window=20, alpha=2.0)

    registry = {
        "FVG":      fvg_raw,
        "BB_BOUNCE": bb_bnc,
    }

    for name, sig in registry.items():
        n_l = int(np.sum(sig == 1.0))
        n_s = int(np.sum(sig == -1.0))
        print(f"  {name}: {n_l} long, {n_s} short, total={n_l+n_s}")

    # --- Top 5 Configs from v2_new optimization ---
    top5 = [
        {"label": "Top1: BB_BOUNCE | FIXED | SL=1.5 | RR=1.5 | ADX>=25 | Wait=2",
         "cfg": {"signal": "BB_BOUNCE", "mode": "FIXED", "sl_mult": 1.5,
                 "rr": 1.5, "tp1_rr": 1.5, "ema_filter": 0, "adx_thresh": 25, "wait_candles": 2}},
        {"label": "Top2: BB_BOUNCE | FIXED | SL=1.5 | RR=1.5 | ADX>=25 | Wait=0",
         "cfg": {"signal": "BB_BOUNCE", "mode": "FIXED", "sl_mult": 1.5,
                 "rr": 1.5, "tp1_rr": 1.5, "ema_filter": 0, "adx_thresh": 25, "wait_candles": 0}},
        {"label": "Top3: BB_BOUNCE | FIXED | SL=2.0 | RR=2.0 | No Filter | Wait=0",
         "cfg": {"signal": "BB_BOUNCE", "mode": "FIXED", "sl_mult": 2.0,
                 "rr": 2.0, "tp1_rr": 2.0, "ema_filter": 0, "adx_thresh": 0, "wait_candles": 0}},
        {"label": "Top4: BB_BOUNCE | FIXED | SL=1.5 | RR=1.5 | ADX>=25 | Wait=5",
         "cfg": {"signal": "BB_BOUNCE", "mode": "FIXED", "sl_mult": 1.5,
                 "rr": 1.5, "tp1_rr": 1.5, "ema_filter": 0, "adx_thresh": 25, "wait_candles": 5}},
        {"label": "Top5: FVG | PARTIAL_TP | SL=3.0 | TP1=3.0R | EMA50 | ADX>=20",
         "cfg": {"signal": "FVG", "mode": "PARTIAL_TP", "sl_mult": 3.0,
                 "rr": 3.0, "tp1_rr": 3.0, "ema_filter": 50, "adx_thresh": 20, "wait_candles": 0}},
    ]

    # --- Run each config ---
    summary_rows = []

    for item in top5:
        cfg = item["cfg"]
        label = item["label"]

        print(f"\n{'='*90}")
        print(f"  {label}")
        print(f"{'='*90}")

        # Build filtered signal
        sig = registry[cfg["signal"]].copy()
        if cfg["ema_filter"] > 0:
            ema_arr = ema_dict.get(cfg["ema_filter"])
            if ema_arr is not None:
                sig = apply_ema_filter(sig, c, ema_arr)
        if cfg["adx_thresh"] > 0:
            sig = apply_adx_filter(sig, adx14, float(cfg["adx_thresh"]))

        n_sig = int(np.sum(sig != 0.0))
        print(f"  Signals after filter: {n_sig}")

        # Simulate
        trets, n_trades = simulate_config(cfg, h, l, c, sig, atr200)
        m = compute_metrics(trets, n_trades)

        print(f"\n  PERFORMANCE:")
        print(f"  {'─'*60}")
        print(f"  Trades:     {n_trades:>6d}     Winrate:    {m['wr']*100:>6.1f}%")
        print(f"  Net Profit: {m['total_ret']*100:>+7.1f}%    Max DD:     {m['max_dd']*100:>6.1f}%")
        print(f"  Calmar:     {m['calmar']:>7.2f}    Sharpe:     {m['sharpe']:>7.2f}")
        print(f"  Avg R:      {m['avg_rr']:>+7.3f}")

        composite = max(m["calmar"], 0.0) * 0.6 + max(m["sharpe"], 0.0) * 0.4

        print(f"\n  TRADE DISTRIBUTION:")
        trade_distribution(trets)

        print(f"\n  MONTHLY BREAKDOWN:")
        monthly_breakdown(df, trets)

        summary_rows.append({
            "label": label,
            "trades": n_trades,
            "wr": m["wr"],
            "total_ret": m["total_ret"],
            "max_dd": m["max_dd"],
            "calmar": m["calmar"],
            "sharpe": m["sharpe"],
            "composite": composite,
        })

    # --- Summary Table ---
    print(f"\n\n{'='*110}")
    print(f"{'CROSS-PERIOD VALIDATION SUMMARY':^110}")
    print(f"{'Trained on: v2_new (Oct2025-Apr2026) | Tested on: before_20251001 (Jun-Sep 2025)':^110}")
    print(f"{'='*110}")
    print(f"{'#':>2} {'Setup':>55} | {'Trades':>6} {'WR%':>6} {'Profit%':>8} {'DD%':>6} {'Calmar':>7} {'Sharpe':>7} {'Comp':>6}")
    print(f"{'-'*110}")
    for i, r in enumerate(summary_rows, 1):
        print(f"{i:>2} {r['label']:>55} | {r['trades']:>6} {r['wr']*100:>5.1f}% "
              f"{r['total_ret']*100:>+7.1f}% {r['max_dd']*100:>5.1f}% "
              f"{r['calmar']:>7.2f} {r['sharpe']:>7.2f} {r['composite']:>6.2f}")

    # Verdict
    print(f"\n{'='*110}")
    profitable = [r for r in summary_rows if r["total_ret"] > 0]
    if profitable:
        best = max(profitable, key=lambda x: x["composite"])
        print(f"  VERDICT: {len(profitable)}/{len(summary_rows)} configs profitable on old data.")
        print(f"  Best cross-period: {best['label']}")
        print(f"    Profit={best['total_ret']*100:+.1f}% | WR={best['wr']*100:.1f}% | "
              f"DD={best['max_dd']*100:.1f}% | Calmar={best['calmar']:.2f}")
    else:
        print(f"  VERDICT: 0/{len(summary_rows)} configs profitable. All setups FAIL on old data.")
    print(f"{'='*110}")


if __name__ == "__main__":
    main()
