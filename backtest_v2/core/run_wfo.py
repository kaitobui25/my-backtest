"""
run_wfo.py — WFO Holy Grail Search Orchestrator.

Usage:
    .vbt_env/Scripts/python.exe my-data/backtest_v2/core/run_wfo.py

Outputs saved to:  my-data/backtest_v2/result/
  wfo_top10_setups.csv    → Top 10 cross-validated setups (params + OOS metrics)
  wfo_oos_equity.csv      → Stitched WFO OOS equity curve (per-trade compound)
  wfo_fold_summary.csv    → Per-fold WFO performance summary
  wfo_all_oos_trades.csv  → All OOS trade returns for Top 1 setup
  wfo_chart_equity.html   → Interactive WFO equity chart
  wfo_chart_top1.html     → Top 1 setup full-dataset equity chart (reference)
"""

import os
import sys
import time
import warnings
import numpy as np
import pandas as pd
import plotly.graph_objects as go

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
CORE_DIR   = os.path.dirname(os.path.abspath(__file__))
BASE_DIR   = os.path.abspath(os.path.join(CORE_DIR, "..", ".."))   # vectorbt-master/my-data
RESULT_DIR = os.path.join(os.path.dirname(CORE_DIR), "result")
DATA_PATH  = os.path.join(BASE_DIR, "cache", "XAUUSD_M15_oanda.parquet")

os.makedirs(RESULT_DIR, exist_ok=True)
sys.path.insert(0, CORE_DIR)

import vectorbt as vbt
from signals    import calc_atr_rma, calc_adx, build_registry, apply_ema_filter, apply_adx_filter
from wfo_engine import (
    generate_folds, build_grid,
    run_sweep, get_wfo_equity,
    _simulate, _prep_signal, compute_metrics, composite_score,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TRAIN_MONTHS    = 3
TEST_MONTHS     = 2
PARTIAL_TP1_RR  = 3.0      # close 50% at 3R, trail the rest
MIN_OOS_TRADES  = 10       # minimum OOS trades per fold
MIN_VALID_FOLDS = 3        # minimum folds where OOS is valid
WR_MIN          = 0.45     # winrate filter for top 10
RISK_PCT        = 0.01     # 1% risk per trade for equity curve


# ===========================================================================
def main():
    t_start = time.time()
    print("=" * 72)
    print("  WFO HOLY GRAIL SEARCH — XAUUSD M15 (OANDA)")
    print(f"  Train={TRAIN_MONTHS}mo | Test={TEST_MONTHS}mo | "
          f"Partial-TP1@{PARTIAL_TP1_RR}R | MinOOS={MIN_OOS_TRADES}T")
    print("=" * 72)

    # ── 1. Load Data ─────────────────────────────────────────────────────────
    print(f"\n[1/5] Loading {DATA_PATH} ...")
    if not os.path.exists(DATA_PATH):
        print(f"  [ERROR] File not found: {DATA_PATH}")
        sys.exit(1)
    df = pd.read_parquet(DATA_PATH)
    print(f"  Rows: {len(df):,} | Range: {df.index[0]} → {df.index[-1]}")

    # ── 2. Pre-compute Global Indicators ─────────────────────────────────────
    print("\n[2/5] Pre-computing indicators ...")
    t0     = time.time()
    atr200 = calc_atr_rma(df["high"], df["low"], df["close"], period=200)
    adx14  = calc_adx(df["high"], df["low"], df["close"], period=14)
    ema200 = vbt.MA.run(df["close"], 200, ewm=True).ma.values
    print(f"  ATR(200), ADX(14), EMA(200) in {time.time()-t0:.1f}s")

    print("\n  Building signal registry (Numba JIT compile on first run ~10s) ...")
    t0       = time.time()
    registry = build_registry(df, atr200)
    for name, arr in registry.items():
        n_sigs = int((arr != 0).sum())
        print(f"    {name:<15}: {n_sigs:,} raw signals")
    print(f"  Registry built in {time.time()-t0:.1f}s")

    # ── 3. Folds & Grid ──────────────────────────────────────────────────────
    print(f"\n[3/5] Generating folds & grid ...")
    folds   = generate_folds(df.index, TRAIN_MONTHS, TEST_MONTHS)
    configs = build_grid(partial_tp1_rr=PARTIAL_TP1_RR)
    print(f"  Folds : {len(folds)}")
    print(f"  Grid  : {len(configs):,} configurations")
    print(f"  Total : {len(folds) * len(configs):,} simulations\n")
    for i, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
        print(f"    Fold {i+1:2d}: Train [{df.index[tr_s].date()} → "
              f"{df.index[tr_e-1].date()}]  "
              f"OOS [{df.index[te_s].date()} → {df.index[te_e-1].date()}]")

    # ── 4. Cross-Validation Sweep ────────────────────────────────────────────
    print("\n[4/5] Running Cross-Validation Sweep ...")
    sweep = run_sweep(df, atr200, adx14, ema200, registry, folds, configs,
                      min_oos_trades=MIN_OOS_TRADES,
                      min_valid_folds=MIN_VALID_FOLDS)

    # Sort all viable results by composite score
    sweep.sort(key=lambda x: x["composite"], reverse=True)

    # Top 10 by composite (no WR floor) — the main ranked list
    top10_all = sweep[:10]

    # Separate list requiring avg_wr >= WR_MIN (the "safe" setups)
    passing_wr = [r for r in sweep if r["avg_wr"] >= WR_MIN]
    top10_wr   = passing_wr[:10]
    top10      = top10_all   # used for chart / trade export

    print(f"\n  Total unique viable configs   : {len(sweep)}")
    print(f"  Configs with avg OOS WR>={WR_MIN*100:.0f}%  : {len(passing_wr)}")
    print(f"  Reporting Top-10 by Composite Score (60% Calmar + 40% Sharpe)")

    # ── 5. WFO Walk-Forward Equity ───────────────────────────────────────────
    print("\n[5/5] Running WFO Walk-Forward Equity Simulation ...")
    fold_results, wfo_equity, oos_trade_lists = get_wfo_equity(
        df, atr200, adx14, ema200, registry, folds, configs,
        min_is_trades=5, min_oos_trades=MIN_OOS_TRADES,
    )

    # ── Export ───────────────────────────────────────────────────────────────
    print("\n[EXPORT] Saving results to:", RESULT_DIR)

    # 1. Top-10 setups CSV (by composite, no WR floor)
    _export_top10(top10_all, top10_wr, RESULT_DIR)

    # 2. WFO OOS equity CSV
    _export_wfo_equity(wfo_equity, fold_results, RESULT_DIR)

    # 3. Fold summary CSV
    _export_fold_summary(fold_results, RESULT_DIR)

    # 4. All OOS trades for Top-1
    if top10_all:
        _export_top1_trades(top10_all[0], RESULT_DIR)

    # 5. WFO equity chart (interactive)
    _chart_wfo_equity(wfo_equity, fold_results, RESULT_DIR)

    # 6. Top-1 full reference chart
    if top10_all:
        _chart_top1_full(top10_all[0], df, atr200, adx14, ema200, registry, RESULT_DIR)

    # ── Final summary ─────────────────────────────────────────────────────────
    wfo_final = (wfo_equity[-1] - 1.0) * 100 if len(wfo_equity) > 1 else 0.0
    wfo_dd    = _max_dd_pct(wfo_equity)
    elapsed   = time.time() - t_start

    print("\n" + "=" * 72)
    print("  COMPLETE!")
    print(f"  WFO OOS Return : {wfo_final:+.2f}%  | Max DD: {wfo_dd:.2f}%")
    print(f"  WFO Folds ran  : {len(fold_results)}")
    print(f"  Elapsed        : {elapsed:.0f}s")
    print(f"  Results at     : {RESULT_DIR}")
    print("=" * 72)

    _print_top10_table(top10_all, top10_wr)
    _print_signal_analysis(sweep)


# ===========================================================================
#  Export helpers
# ===========================================================================

def _export_top10(top10_all: list, top10_wr: list, out_dir: str):
    """Export top-10 by composite score; flag if also in top-10 WR list."""
    wr_keys = {
        (r["cfg"]["signal"], r["cfg"]["mode"], r["cfg"]["sl_mult"],
         r["cfg"]["rr"], r["cfg"]["ema_filter"], r["cfg"]["adx_thresh"])
        for r in top10_wr
    }
    rows = []
    for rank, r in enumerate(top10_all, 1):
        cfg = r["cfg"]
        key = (cfg["signal"], cfg["mode"], cfg["sl_mult"],
               cfg["rr"], cfg["ema_filter"], cfg["adx_thresh"])
        rows.append({
            "rank":               rank,
            "wr_ge45_flag":       key in wr_keys,
            "signal":             cfg["signal"],
            "mode":               cfg["mode"],
            "sl_mult":            cfg["sl_mult"],
            "rr":                 cfg["rr"],
            "ema_filter":         cfg["ema_filter"],
            "adx_thresh":         cfg["adx_thresh"],
            "tp1_rr":             cfg["tp1_rr"],
            "valid_folds":        r["valid_folds"],
            "total_oos_trades":   r["total_oos_trades"],
            "avg_wr_pct":         round(r["avg_wr"] * 100, 2),
            "avg_calmar":         round(r["avg_calmar"], 3),
            "avg_sharpe":         round(r["avg_sharpe"], 3),
            "agg_calmar":         round(r["agg_calmar"], 3),
            "agg_sharpe":         round(r["agg_sharpe"], 3),
            "agg_total_ret_pct":  round(r["agg_total_ret"] * 100, 2),
            "agg_max_dd_pct":     round(r["agg_max_dd"] * 100, 2),
            "agg_avg_rr":         round(r["agg_avg_rr"], 3),
            "composite":          round(r["composite"], 4),
        })
    path = os.path.join(out_dir, "wfo_top10_setups.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  -> {path}")


def _export_wfo_equity(equity: np.ndarray, folds: list, out_dir: str):
    if len(equity) <= 1:
        return
    eq_df = pd.DataFrame({
        "trade_num":     range(len(equity)),
        "equity":        equity,
        "equity_10k":    equity * 10_000,
        "drawdown_pct":  _dd_series(equity),
    })
    path = os.path.join(out_dir, "wfo_oos_equity.csv")
    eq_df.to_csv(path, index=False)
    print(f"  -> {path}")


def _export_fold_summary(fold_results: list, out_dir: str):
    rows = []
    for fr in fold_results:
        om = fr["oos_m"] or {}
        im = fr["is_m"]  or {}
        rows.append({
            "fold":          fr["fold"],
            "train_start":   fr["tr_range"][0].date(),
            "train_end":     fr["tr_range"][1].date(),
            "oos_start":     fr["oos_range"][0].date(),
            "oos_end":       fr["oos_range"][1].date(),
            "best_signal":   fr["best_cfg"]["signal"],
            "best_mode":     fr["best_cfg"]["mode"],
            "best_sl":       fr["best_cfg"]["sl_mult"],
            "best_rr":       fr["best_cfg"]["rr"],
            "best_ema":      fr["best_cfg"]["ema_filter"],
            "best_adx":      fr["best_cfg"]["adx_thresh"],
            "is_score":      round(fr["is_score"], 4),
            "is_wr_pct":     round(im.get("wr", 0) * 100, 2),
            "is_calmar":     round(im.get("calmar", 0), 3),
            "oos_wr_pct":    round(om.get("wr", 0) * 100, 2),
            "oos_calmar":    round(om.get("calmar", 0), 3),
            "oos_sharpe":    round(om.get("sharpe", 0), 3),
            "oos_ret_pct":   round(om.get("total_ret", 0) * 100, 2),
            "oos_max_dd_pct":round(om.get("max_dd", 0) * 100, 2),
            "oos_avg_rr":    round(om.get("avg_rr", 0), 3),
            "n_oos_trades":  fr["n_oos"],
        })
    path = os.path.join(out_dir, "wfo_fold_summary.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  -> {path}")


def _export_top1_trades(top1: dict, out_dir: str):
    rows = []
    trade_num = 0
    for fd in top1["fold_data"]:
        nz = fd["oos_rets"][fd["oos_rets"] != 0.0]
        for ret in nz:
            trade_num += 1
            rows.append({
                "trade_num":         trade_num,
                "fold":              fd["fold"] + 1,
                "pnl_r":             round(float(ret), 4),
                "result":            "WIN" if ret > 0 else "LOSS",
                "cumulative_equity": None,   # filled below
            })
    if not rows:
        return
    df_t  = pd.DataFrame(rows)
    eq    = 1.0
    eq_list = []
    for r in df_t["pnl_r"]:
        eq *= (1.0 + RISK_PCT * r)
        eq_list.append(round(eq * 10_000, 2))
    df_t["cumulative_equity"] = eq_list
    path = os.path.join(out_dir, "wfo_all_oos_trades.csv")
    df_t.to_csv(path, index=False)
    print(f"  -> {path}")


# ===========================================================================
#  Chart helpers
# ===========================================================================

COLORS = [
    "#00d2ff", "#f7931e", "#a8e063", "#ffd700",
    "#ff6b6b", "#c471ed", "#56ab2f", "#f953c6",
    "#43e97b", "#fa709a",
]

_DARK = "plotly_dark"


def _chart_wfo_equity(equity: np.ndarray, folds: list, out_dir: str):
    if len(equity) <= 1:
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=equity * 10_000,
        mode="lines", name="WFO OOS Equity",
        line=dict(color="#00d2ff", width=2),
        fill="tozeroy", fillcolor="rgba(0,210,255,0.07)",
    ))

    # Shade each fold's OOS period + annotate selected setup
    trade_ptr = 0
    for i, fr in enumerate(folds):
        n_t = fr["n_oos"]
        col = COLORS[i % len(COLORS)]
        fig.add_vrect(
            x0=trade_ptr, x1=trade_ptr + n_t,
            fillcolor=col, opacity=0.06,
            annotation_text=(f"F{fr['fold']}<br>"
                             f"{fr['best_cfg']['signal'][:3]}<br>"
                             f"{fr['best_cfg']['mode'][:3]}"),
            annotation_position="top left",
            annotation_font_size=9,
        )
        trade_ptr += n_t

    om_all = [fr["oos_m"] for fr in folds if fr["oos_m"]]
    agg_wr  = np.mean([m["wr"]     for m in om_all]) * 100 if om_all else 0
    agg_cal = np.mean([m["calmar"] for m in om_all]) if om_all else 0
    final_r = (equity[-1] - 1) * 100

    fig.update_layout(
        title=(f"WFO Out-of-Sample Equity Curve — XAUUSD M15<br>"
               f"<sub>OOS Return: {final_r:+.1f}% | "
               f"Avg WR: {agg_wr:.1f}% | Avg Calmar: {agg_cal:.2f} | "
               f"1% risk/trade | each shaded band = one OOS fold</sub>"),
        xaxis_title="OOS Trade Number (chronological)",
        yaxis_title="Portfolio Value ($, starting $10,000)",
        template=_DARK, height=550,
        legend=dict(orientation="h", y=1.02),
    )
    path = os.path.join(out_dir, "wfo_chart_equity.html")
    fig.write_html(path)
    print(f"  -> {path}")


def _chart_top1_full(top1: dict, df, atr200, adx14, ema200, registry, out_dir: str):
    """Full-dataset equity for the Top-1 cross-validated config (IS+OOS — reference only)."""
    cfg = top1["cfg"]
    c   = df["close"].values
    h   = df["high"].values
    l   = df["low"].values

    sig = registry[cfg["signal"]].copy()
    if cfg["ema_filter"] > 0:
        sig = apply_ema_filter(sig, c, ema200)
    if cfg["adx_thresh"] > 0:
        sig = apply_adx_filter(sig, adx14, float(cfg["adx_thresh"]))

    trets, n_t = _simulate(cfg, h, l, c, sig, atr200)
    nz = trets[trets != 0.0]

    eq    = np.ones(len(nz) + 1)
    for j in range(len(nz)):
        eq[j + 1] = eq[j] * (1.0 + RISK_PCT * nz[j])

    wr  = float(np.sum(nz > 0)) / len(nz) * 100 if len(nz) else 0
    ret = (eq[-1] - 1) * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=eq * 10_000, mode="lines",
        name=f"{cfg['signal']} | {cfg['mode']} | SL={cfg['sl_mult']} RR={cfg['rr']}",
        line=dict(color="#f7931e", width=2),
    ))
    fig.update_layout(
        title=(f"Top-1 Setup — Full Dataset (IS+OOS combined — REFERENCE ONLY)<br>"
               f"<sub>{cfg['signal']} | {cfg['mode']} | SL={cfg['sl_mult']} ATR | "
               f"RR={cfg['rr']} | EMA={cfg['ema_filter']} | ADX={cfg['adx_thresh']}<br>"
               f"Trades={n_t} | WR={wr:.1f}% | Return={ret:+.1f}%</sub>"),
        xaxis_title="Trade Number",
        yaxis_title="Portfolio Value ($, starting $10,000)",
        template=_DARK, height=500,
    )
    path = os.path.join(out_dir, "wfo_chart_top1.html")
    fig.write_html(path)
    print(f"  -> {path}")


# ===========================================================================
#  Console summary
# ===========================================================================

def _print_top10_table(top10_all: list, top10_wr: list):
    wr_keys = {
        (r["cfg"]["signal"], r["cfg"]["mode"], r["cfg"]["sl_mult"],
         r["cfg"]["rr"], r["cfg"]["ema_filter"], r["cfg"]["adx_thresh"])
        for r in top10_wr
    }

    def _table(results, title):
        if not results:
            print(f"  --- {title}: none ---")
            return
        print(f"\n{'=' * 72}")
        print(f"  {title}")
        print(f"  Ranked by: 60% Calmar + 40% Sharpe  (*=WR>=45%)")
        print("=" * 72)
        hdr = (f"  {'#':>3}  {'F':>2} {'Signal':<15} {'Mode':<11} "
               f"{'SL':>5} {'RR':>4} {'EMA':>5} {'ADX':>5} "
               f"{'WR%':>6} {'Calmar':>7} {'Sharpe':>7} "
               f"{'Ret%':>7} {'DD%':>6} {'T':>5}")
        print(hdr)
        print("  " + "-" * 68)
        for i, r in enumerate(results, 1):
            cfg = r["cfg"]
            key = (cfg["signal"], cfg["mode"], cfg["sl_mult"],
                   cfg["rr"], cfg["ema_filter"], cfg["adx_thresh"])
            star = "*" if key in wr_keys else " "
            print(
                f"  {i:>3}{star} {r['valid_folds']:>2} {cfg['signal']:<15} {cfg['mode']:<11} "
                f"{cfg['sl_mult']:>5.2f} {cfg['rr']:>4.1f} "
                f"{cfg['ema_filter']:>5} {cfg['adx_thresh']:>5}  "
                f"{r['avg_wr']*100:>6.1f} {r['agg_calmar']:>7.2f} {r['agg_sharpe']:>7.2f} "
                f"{r['agg_total_ret']*100:>7.1f} {r['agg_max_dd']*100:>6.1f} "
                f"{r['total_oos_trades']:>5}"
            )
        if any(k in wr_keys for r in results
               for k in [(r["cfg"]["signal"], r["cfg"]["mode"], r["cfg"]["sl_mult"],
                          r["cfg"]["rr"], r["cfg"]["ema_filter"], r["cfg"]["adx_thresh"])]):
            print("  * = avg OOS WR >= 45% (meets holy grail WR constraint)")

    _table(top10_all, "TOP-10 BY COMPOSITE SCORE (all viable setups)")

    if top10_wr:
        print(f"\n--- {len(top10_wr)} setup(s) also meet WR>=45% across OOS folds ---")
        for r in top10_wr:
            cfg = r["cfg"]
            print(f"  {cfg['signal']:<15} {cfg['mode']:<11} "
                  f"SL={cfg['sl_mult']} RR={cfg['rr']} EMA={cfg['ema_filter']} ADX={cfg['adx_thresh']:>2}"
                  f"  WR={r['avg_wr']*100:.1f}%  Calmar={r['agg_calmar']:.2f}  "
                  f"Ret={r['agg_total_ret']*100:.1f}%  [{r['total_oos_trades']}T]")
    else:
        print(f"\n  [NOTE] No single config maintained avg OOS WR>=45% across all {len(top10_all[0]['valid_folds'] if top10_all else 0)} folds.")
        print("  This is expected: XAUUSD M15 has strong regime changes.")
        print("  The top composite setups above are the best risk-adj performers.")


def _print_signal_analysis(sweep: list):
    """Aggregate OOS performance broken down by signal type."""
    if not sweep:
        return
    from collections import defaultdict
    sig_stats = defaultdict(list)
    for r in sweep:
        sig_stats[r["cfg"]["signal"]].append(r)

    print("\n" + "=" * 72)
    print("  SIGNAL-LEVEL AGGREGATE ANALYSIS (best config per signal type)")
    print("=" * 72)
    hdr = (f"  {'Signal':<15} {'BestMode':<11} {'WR%':>6} "
           f"{'Calmar':>7} {'Sharpe':>7} {'Ret%':>7} {'DD%':>6} {'T':>5}")
    print(hdr)
    print("  " + "-" * 60)

    sig_bests = []
    for sig, items in sig_stats.items():
        best = max(items, key=lambda x: x["composite"])
        sig_bests.append((sig, best))
    sig_bests.sort(key=lambda x: x[1]["composite"], reverse=True)

    for sig, best in sig_bests:
        cfg = best["cfg"]
        print(
            f"  {sig:<15} {cfg['mode']:<11} "
            f"{best['avg_wr']*100:>6.1f} "
            f"{best['agg_calmar']:>7.2f} {best['agg_sharpe']:>7.2f} "
            f"{best['agg_total_ret']*100:>7.1f} {best['agg_max_dd']*100:>6.1f} "
            f"{best['total_oos_trades']:>5}"
        )


# ===========================================================================
#  Utility
# ===========================================================================

def _max_dd_pct(equity: np.ndarray) -> float:
    if len(equity) <= 1:
        return 0.0
    peak = np.maximum.accumulate(equity)
    peak = np.where(peak < 1e-12, 1e-12, peak)
    dd   = (equity - peak) / peak
    return float(np.abs(dd.min()) * 100)


def _dd_series(equity: np.ndarray) -> list:
    peak = np.maximum.accumulate(equity)
    peak = np.where(peak < 1e-12, 1e-12, peak)
    dd   = (equity - peak) / peak * 100
    return [round(float(x), 4) for x in dd]


# ===========================================================================
if __name__ == "__main__":
    main()
