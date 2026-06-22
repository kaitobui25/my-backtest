"""
run_wfo_v3.py — WFO Holy Grail Search Orchestrator (v3)
XAUUSD M5 — 10 Signals x 10,800 Configs x 11 Folds

Data split:
  WFO Pool  (IS + rolling OOS): 2016-01-01 -> 2023-06-30
  Final Holdout (locked):        2023-07-01 -> latest

WFO Config:
  IS window  = 24 months
  OOS window = 6 months
  Slide      = 6 months (= OOS length)
  Folds      = 11

Usage:
  python run_wfo_v3.py            # Full WFO sweep + stitched OOS equity
  python run_wfo_v3.py --smoke    # Quick smoke test (2 folds x 50 configs)
  python run_wfo_v3.py --run-holdout  # Unlock + evaluate Final Holdout

Output (my-data/backtest_v3/result/):
  top20_setups.csv        Top 20 configs (OOS metrics + rank)
  wfo_oos_equity.csv      Stitched OOS equity curve
  wfo_fold_summary.csv    Per-fold performance
  all_oos_trades.csv      Every OOS trade of Top-1 setup
  chart_wfo_equity.html   Interactive WFO OOS equity chart
  chart_top20.html        Top-20 equity curves overlay
  report_top20.html       Full HTML report
"""

import os
import sys
import time
import argparse
import warnings
import numpy as np
import pandas as pd
import pickle
import plotly.graph_objects as go
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

# Force UTF-8 stdout on Windows (avoids charmap errors with special chars)
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ---------------------------------------------------------------------------
#  Path setup
# ---------------------------------------------------------------------------
CORE_DIR   = os.path.dirname(os.path.abspath(__file__))
BASE_DIR   = os.path.abspath(os.path.join(CORE_DIR, "..", ".."))
RESULT_DIR = os.path.join(os.path.dirname(CORE_DIR), "result")
DATA_FILE  = "XAUUSD.sml_M5_800000_before_20260418.parquet"
DATA_PATH  = os.path.join(BASE_DIR, "cache", "m5", DATA_FILE)

os.makedirs(RESULT_DIR, exist_ok=True)
sys.path.insert(0, CORE_DIR)

import vectorbt as vbt
from signals_v3   import calc_atr_rma, calc_adx, build_registry
from wfo_engine_v3 import (
    generate_folds, build_grid,
    run_sweep, get_wfo_equity, get_holdout_equity,
    compute_metrics, composite_score, max_dd_pct, dd_series,
    _simulate, _prep_signal,
)

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
WFO_POOL_START   = "2016-01-01"
WFO_POOL_END     = "2023-06-30"
HOLDOUT_START    = "2023-07-01"

TRAIN_MONTHS     = 24
TEST_MONTHS      = 6
PARTIAL_TP1_RR   = 2.0      # close 50% at 2R, trail remainder
MIN_OOS_TRADES   = 15       # minimum OOS trades per fold to count
MIN_VALID_FOLDS  = 4        # folds where OOS must be valid
WR_MIN           = 0.50     # winrate floor for Top-20 filter
RISK_PCT         = 0.01     # 1% risk per trade
INITIAL_CAPITAL  = 1_000.0  # USD

COLORS = [
    "#00d2ff", "#f7931e", "#a8e063", "#ffd700", "#ff6b6b",
    "#c471ed", "#56ab2f", "#f953c6", "#43e97b", "#fa709a",
    "#4facfe", "#f77062", "#2af598", "#fccb90", "#d57eeb",
    "#a1c4fd", "#ffecd2", "#fd7043", "#80deea", "#ce93d8",
]
_DARK = "plotly_dark"


# ===========================================================================
def main():
    parser = argparse.ArgumentParser(description="WFO Backtest v3 — XAUUSD M5")
    parser.add_argument("--smoke",       action="store_true",
                        help="Quick smoke test: 2 folds x 50 random configs")
    parser.add_argument("--run-holdout", action="store_true",
                        help="Unlock Final Holdout evaluation")
    args = parser.parse_args()

    t_start = time.time()

    # ── Header ───────────────────────────────────────────────────────────────
    print("=" * 76)
    print("  WFO HOLY GRAIL SEARCH v3 — XAUUSD M5 (10 Signals)")
    print(f"  IS={TRAIN_MONTHS}mo | OOS={TEST_MONTHS}mo | Slide={TEST_MONTHS}mo | "
          f"PartialTP1@{PARTIAL_TP1_RR}R | Risk={RISK_PCT*100:.0f}%/trade")
    print(f"  WFO Pool: {WFO_POOL_START} -> {WFO_POOL_END}")
    print(f"  Holdout : {HOLDOUT_START} -> latest  [LOCKED — use --run-holdout]")
    print("=" * 76)

    # ── 1. Load Data ─────────────────────────────────────────────────────────
    print(f"\n[1/6] Loading {DATA_PATH} ...")
    if not os.path.exists(DATA_PATH):
        print(f"  [ERROR] File not found: {DATA_PATH}")
        sys.exit(1)
    df_full = pd.read_parquet(DATA_PATH)

    # Ensure UTC timezone for searchsorted compatibility
    if df_full.index.tz is None:
        df_full.index = df_full.index.tz_localize("UTC")

    print(f"  Full dataset: {len(df_full):,} rows | "
          f"{df_full.index[0].date()} -> {df_full.index[-1].date()}")

    # Split into WFO pool and holdout
    pool_end_ts   = pd.Timestamp(WFO_POOL_END,   tz="UTC")
    holdout_ts    = pd.Timestamp(HOLDOUT_START,   tz="UTC")

    df = df_full[df_full.index <= pool_end_ts].copy()
    df_hold = df_full[df_full.index >= holdout_ts].copy()

    print(f"  WFO Pool  : {len(df):,} bars | "
          f"{df.index[0].date()} -> {df.index[-1].date()}")
    print(f"  Holdout   : {len(df_hold):,} bars | "
          f"{df_hold.index[0].date()} -> {df_hold.index[-1].date()} "
          f"[{'UNLOCKED' if args.run_holdout else 'LOCKED'}]")

    # ── 2. Pre-compute Global Indicators (WFO Pool) ───────────────────────────
    print("\n[2/6] Pre-computing indicators on WFO Pool ...")
    t0     = time.time()
    atr14  = calc_atr_rma(df["high"], df["low"], df["close"], period=14)
    adx14  = calc_adx(    df["high"], df["low"], df["close"], period=14)
    ema200 = vbt.MA.run(df["close"], 200, ewm=True).ma.values
    volume = df["volume"].values
    print(f"  ATR(14), ADX(14), EMA(200) in {time.time() - t0:.1f}s")

    # ── 3. Build Signal Registry ──────────────────────────────────────────────
    print("\n[3/6] Building signal registry (Numba JIT ~20s first run) ...")
    t0 = time.time()
    registry, atr200, vwap = build_registry(df, atr14)
    print(f"  Registry built in {time.time() - t0:.1f}s")

    # ── 4. Generate Folds & Grid ──────────────────────────────────────────────
    print(f"\n[4/6] Generating folds & grid ...")
    folds   = generate_folds(df.index, TRAIN_MONTHS, TEST_MONTHS,
                             pool_start=WFO_POOL_START, pool_end=WFO_POOL_END)
    configs = build_grid(partial_tp1_rr=PARTIAL_TP1_RR)

    smoke_min_folds = MIN_VALID_FOLDS
    smoke_min_trades = MIN_OOS_TRADES
    if args.smoke:
        smoke_min_folds = 1
        smoke_min_trades = 5
        print("  [SMOKE] Limiting to 2 folds x 50 configs")
        folds   = folds[:2]
        import random; random.seed(42)
        configs = random.sample(configs, min(50, len(configs)))

    print(f"  Folds   : {len(folds)}")
    print(f"  Configs : {len(configs):,}")
    print(f"  Total   : {len(folds) * len(configs):,} simulations\n")
    for i, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
        print(f"    Fold {i+1:>2}: IS [{df.index[tr_s].date()} -> "
              f"{df.index[tr_e-1].date()}]  "
              f"OOS [{df.index[te_s].date()} -> {df.index[te_e-1].date()}]")

    CACHE_PATH = os.path.join(RESULT_DIR, "wfo_cache.pkl")
    use_cache = args.run_holdout and os.path.exists(CACHE_PATH) and not args.smoke

    if use_cache:
        print(f"\n[CACHE] Loading WFO sweep results from {CACHE_PATH} (skipping 6-min sweep)...")
        with open(CACHE_PATH, "rb") as f:
            cdata = pickle.load(f)
        sweep, top20_all, top20_wr, fold_results, wfo_equity = (
            cdata["sweep"], cdata["top20_all"], cdata["top20_wr"], 
            cdata["fold_results"], cdata["wfo_equity"]
        )
    else:
        # -- 5. Cross-Validation Sweep ─────────────────────────────────────────────
        print("\n[5/6] Running Cross-Validation Sweep ...")
        sweep = run_sweep(
            df, atr14, adx14, ema200, registry, folds, configs,
            volume=volume,
            min_oos_trades=smoke_min_trades,
            min_valid_folds=smoke_min_folds,
        )

        sweep.sort(key=lambda x: x["composite"], reverse=True)

        # Top-20 by composite (no WR floor) + separate WR-filtered list
        top20_all = sweep[:20]
        top20_wr  = [r for r in sweep if r["avg_wr"] >= WR_MIN][:20]
        top20     = top20_all  # canonical reference

        print(f"\n  Total viable unique configs: {len(sweep):,}")
        print(f"  Configs with avg OOS WR>={WR_MIN*100:.0f}%: {len([r for r in sweep if r['avg_wr'] >= WR_MIN]):,}")

        # -- 6. WFO Walk-Forward Equity ────────────────────────────────────────────
        print("\n[6/6] Running WFO Walk-Forward Equity ...")
        fold_results, wfo_equity, oos_trades = get_wfo_equity(
            df, atr14, adx14, ema200, registry, folds, configs,
            volume=volume,
            min_is_trades=5,
            min_oos_trades=smoke_min_trades,
            risk_pct=RISK_PCT,
        )
        
        if not args.smoke:
            print(f"\n[CACHE] Saving sweep results to {CACHE_PATH} ...")
            with open(CACHE_PATH, "wb") as f:
                pickle.dump({
                    "sweep": sweep, "top20_all": top20_all, "top20_wr": top20_wr,
                    "fold_results": fold_results, "wfo_equity": wfo_equity
                }, f)

    # ── Export ────────────────────────────────────────────────────────────────
    print(f"\n[EXPORT] Saving to {RESULT_DIR} ...")
    _export_top20(top20_all, top20_wr, RESULT_DIR)
    _export_wfo_equity(wfo_equity, fold_results, RESULT_DIR)
    _export_fold_summary(fold_results, RESULT_DIR)
    if top20_all:
        _export_top1_trades(top20_all[0], RESULT_DIR)
    _chart_wfo_equity(wfo_equity, fold_results, RESULT_DIR)
    _chart_top20(top20_all[:10], df, atr14, adx14, ema200, registry, volume, RESULT_DIR)
    _report_top20(top20_all, top20_wr, fold_results, wfo_equity, RESULT_DIR)

    # ── Holdout ───────────────────────────────────────────────────────────────
    if args.run_holdout and top20_all:
        print(f"\n[HOLDOUT] Computing indicators on holdout data ...")
        atr_h   = calc_atr_rma(df_hold["high"], df_hold["low"], df_hold["close"], 14)
        adx_h   = calc_adx(    df_hold["high"], df_hold["low"], df_hold["close"], 14)
        ema200_h = vbt.MA.run(df_hold["close"], 200, ewm=True).ma.values
        vol_h   = df_hold["volume"].values
        # Build holdout registry
        reg_h, _, _ = build_registry(df_hold, atr_h)
        hold_results = get_holdout_equity(
            top20_all, df_hold, atr_h, adx_h, ema200_h, reg_h, vol_h,
            risk_pct=RISK_PCT, n_top=5,
        )
        _export_holdout(hold_results, RESULT_DIR)
        _chart_holdout(hold_results, RESULT_DIR)
    else:
        print("\n  [HOLDOUT] Still locked. Use --run-holdout when WFO is complete.")

    # ── Final Summary ─────────────────────────────────────────────────────────
    wfo_ret = (wfo_equity[-1] - 1.0) * 100 if len(wfo_equity) > 1 else 0.0
    wfo_dd  = max_dd_pct(wfo_equity)
    elapsed = time.time() - t_start

    print("\n" + "=" * 76)
    print("  COMPLETE!")
    print(f"  WFO OOS Return  : {wfo_ret:+.2f}%  on ${INITIAL_CAPITAL * wfo_equity[-1]:.0f}  "
          f"(started ${INITIAL_CAPITAL:.0f})")
    print(f"  WFO Max DD      : {wfo_dd:.2f}%")
    print(f"  WFO Folds ran   : {len(fold_results)}")
    print(f"  Elapsed         : {elapsed:.0f}s")
    print("=" * 76)

    _print_top20_table(top20_all, top20_wr)
    _print_signal_analysis(sweep)


# ===========================================================================
#  Export Helpers
# ===========================================================================

def _export_top20(top20_all: list, top20_wr: list, out_dir: str):
    wr_keys = {
        (r["cfg"]["signal"], r["cfg"]["mode"], r["cfg"]["sl_mult"],
         r["cfg"]["rr"], r["cfg"]["ema_filter"], r["cfg"]["adx_thresh"],
         r["cfg"]["vol_filter"])
        for r in top20_wr
    }
    rows = []
    for rank, r in enumerate(top20_all, 1):
        cfg = r["cfg"]
        key = (cfg["signal"], cfg["mode"], cfg["sl_mult"], cfg["rr"],
               cfg["ema_filter"], cfg["adx_thresh"], cfg["vol_filter"])
        rows.append({
            "rank":               rank,
            "wr_ge50_flag":       key in wr_keys,
            "signal":             cfg["signal"],
            "mode":               cfg["mode"],
            "sl_mult":            cfg["sl_mult"],
            "rr":                 cfg["rr"],
            "ema_filter":         cfg["ema_filter"],
            "adx_thresh":         cfg["adx_thresh"],
            "vol_filter":         cfg["vol_filter"],
            "tp1_rr":             cfg["tp1_rr"],
            "wait_candles":       cfg["wait_candles"],
            "valid_folds":        r["valid_folds"],
            "total_oos_trades":   r["total_oos_trades"],
            "avg_wr_pct":         round(r["avg_wr"] * 100, 2),
            "avg_calmar":         round(r["avg_calmar"], 3),
            "avg_sharpe":         round(r["avg_sharpe"], 3),
            "avg_pf":             round(r["avg_pf"], 3),
            "agg_calmar":         round(r["agg_calmar"], 3),
            "agg_sharpe":         round(r["agg_sharpe"], 3),
            "agg_total_ret_pct":  round(r["agg_total_ret"] * 100, 2),
            "agg_max_dd_pct":     round(r["agg_max_dd"] * 100, 2),
            "agg_avg_rr":         round(r["agg_avg_rr"], 3),
            "agg_pf":             round(r["agg_pf"], 3),
            "composite":          round(r["composite"], 4),
        })
    path = os.path.join(out_dir, "top20_setups.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  -> {path}")


def _export_wfo_equity(equity: np.ndarray, folds: list, out_dir: str):
    if len(equity) <= 1:
        return
    eq_df = pd.DataFrame({
        "trade_num":      range(len(equity)),
        "equity_factor":  equity,
        "equity_usd":     equity * INITIAL_CAPITAL,
        "drawdown_pct":   dd_series(equity),
    })
    path = os.path.join(out_dir, "wfo_oos_equity.csv")
    eq_df.to_csv(path, index=False)
    print(f"  -> {path}")


def _export_fold_summary(fold_results: list, out_dir: str):
    rows = []
    for fr in fold_results:
        om = fr["oos_m"] or {}
        im = fr["is_m"]  or {}
        cfg = fr["best_cfg"]
        rows.append({
            "fold":           fr["fold"],
            "train_start":    fr["tr_range"][0].date(),
            "train_end":      fr["tr_range"][1].date(),
            "oos_start":      fr["oos_range"][0].date(),
            "oos_end":        fr["oos_range"][1].date(),
            "best_signal":    cfg["signal"],
            "best_mode":      cfg["mode"],
            "best_sl":        cfg["sl_mult"],
            "best_rr":        cfg["rr"],
            "best_ema":       cfg["ema_filter"],
            "best_adx":       cfg["adx_thresh"],
            "best_vol":       cfg["vol_filter"],
            "is_score":       round(fr["is_score"], 4),
            "is_wr_pct":      round(im.get("wr", 0) * 100, 2),
            "is_calmar":      round(im.get("calmar", 0), 3),
            "is_pf":          round(im.get("profit_factor", 0), 3),
            "oos_wr_pct":     round(om.get("wr", 0) * 100, 2),
            "oos_calmar":     round(om.get("calmar", 0), 3),
            "oos_sharpe":     round(om.get("sharpe", 0), 3),
            "oos_ret_pct":    round(om.get("total_ret", 0) * 100, 2),
            "oos_max_dd_pct": round(om.get("max_dd", 0) * 100, 2),
            "oos_pf":         round(om.get("profit_factor", 0), 3),
            "n_oos_trades":   fr["n_oos"],
        })
    path = os.path.join(out_dir, "wfo_fold_summary.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  -> {path}")


def _export_top1_trades(top1: dict, out_dir: str):
    rows = []
    cumulative = 1.0
    trade_num  = 0
    for fd in top1["fold_data"]:
        nz = fd["oos_rets"][fd["oos_rets"] != 0.0]
        for ret in nz:
            trade_num += 1
            cumulative *= (1.0 + RISK_PCT * float(ret))
            rows.append({
                "trade_num":         trade_num,
                "fold":              fd["fold"] + 1,
                "pnl_r":             round(float(ret), 4),
                "result":            "WIN" if ret > 0 else ("BE" if ret == 0 else "LOSS"),
                "cumulative_equity": round(cumulative * INITIAL_CAPITAL, 2),
            })
    if not rows:
        return
    path = os.path.join(out_dir, "all_oos_trades.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  -> {path}")


def _export_holdout(hold_results: list, out_dir: str):
    rows = []
    for h in hold_results:
        m = h["metrics"]
        cfg = h["cfg"]
        rows.append({
            "rank":             h["rank"],
            "signal":           cfg["signal"],
            "mode":             cfg["mode"],
            "sl_mult":          cfg["sl_mult"],
            "rr":               cfg["rr"],
            "wfo_avg_wr_pct":   round(h["oos_wr"] * 100, 2),
            "hold_wr_pct":      round(m["wr"] * 100, 2),
            "hold_ret_pct":     round(m["total_ret"] * 100, 2),
            "hold_max_dd_pct":  round(m["max_dd"] * 100, 2),
            "hold_calmar":      round(m["calmar"], 3),
            "hold_sharpe":      round(m["sharpe"], 3),
            "hold_pf":          round(m["profit_factor"], 3),
            "hold_trades":      h["n_trades"],
        })
    path = os.path.join(out_dir, "holdout_results.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  -> {path}")


# ===========================================================================
#  Chart Helpers
# ===========================================================================

def _chart_wfo_equity(equity: np.ndarray, folds: list, out_dir: str):
    if len(equity) <= 1:
        return

    eq_usd = equity * INITIAL_CAPITAL
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=eq_usd, mode="lines", name="WFO OOS Equity",
        line=dict(color="#00d2ff", width=2),
        fill="tozeroy", fillcolor="rgba(0,210,255,0.07)",
    ))
    fig.add_hline(y=INITIAL_CAPITAL, line_dash="dash",
                  line_color="rgba(255,255,255,0.2)", line_width=1)

    # Shade OOS folds
    trade_ptr = 0
    for i, fr in enumerate(folds):
        n_t = fr["n_oos"]
        col = COLORS[i % len(COLORS)]
        cfg = fr["best_cfg"]
        oos_wr = (fr["oos_m"]["wr"] * 100) if fr["oos_m"] else 0
        fig.add_vrect(
            x0=trade_ptr, x1=trade_ptr + n_t,
            fillcolor=col, opacity=0.07,
            annotation_text=(f"F{fr['fold']}<br>"
                             f"{cfg['signal'][:5]}<br>"
                             f"{cfg['mode'][:3]}<br>"
                             f"WR:{oos_wr:.0f}%"),
            annotation_position="top left",
            annotation_font_size=8,
        )
        trade_ptr += n_t

    om_list = [fr["oos_m"] for fr in folds if fr["oos_m"]]
    agg_wr  = np.mean([m["wr"] for m in om_list]) * 100 if om_list else 0
    agg_cal = np.mean([m["calmar"] for m in om_list]) if om_list else 0
    final_r = (equity[-1] - 1) * 100
    final_usd = equity[-1] * INITIAL_CAPITAL

    fig.update_layout(
        title=(f"WFO Out-of-Sample Equity — XAUUSD M5 (${INITIAL_CAPITAL:.0f} -> ${final_usd:.0f})<br>"
               f"<sub>OOS Return: {final_r:+.1f}% | Avg WR: {agg_wr:.1f}% | "
               f"Avg Calmar: {agg_cal:.2f} | {RISK_PCT*100:.0f}% risk/trade | "
               f"Shaded = OOS fold</sub>"),
        xaxis_title="OOS Trade Number (chronological)",
        yaxis_title=f"Portfolio Value (USD, start ${INITIAL_CAPITAL:.0f})",
        template=_DARK, height=580,
        legend=dict(orientation="h", y=1.02),
    )
    path = os.path.join(out_dir, "chart_wfo_equity.html")
    fig.write_html(path)
    print(f"  -> {path}")


def _chart_top20(top_items: list, df, atr, adx, ema200, registry,
                 volume, out_dir: str):
    """Overlay equity curves of top-10 configs (full IS+OOS — reference)."""
    if not top_items:
        return

    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    fig = go.Figure()
    for rank, item in enumerate(top_items, 1):
        cfg = item["cfg"]
        sig = _prep_signal(cfg, registry, c, ema200, adx, volume)
        rets, n_t = _simulate(cfg, h, l, c, sig, atr)
        nz = rets[rets != 0.0]
        eq = np.ones(len(nz) + 1)
        for j in range(len(nz)):
            eq[j + 1] = eq[j] * (1.0 + RISK_PCT * nz[j])

        eq_usd = eq * INITIAL_CAPITAL
        wr  = float(np.sum(nz > 0)) / len(nz) * 100 if len(nz) else 0
        ret = (eq[-1] - 1) * 100
        label = (f"#{rank} {cfg['signal'][:8]}|{cfg['mode'][:3]} "
                 f"SL={cfg['sl_mult']} RR={cfg['rr']} "
                 f"WR={wr:.0f}%")
        fig.add_trace(go.Scatter(
            y=eq_usd, mode="lines", name=label,
            line=dict(color=COLORS[(rank - 1) % len(COLORS)], width=1.5),
            opacity=0.85,
        ))

    fig.add_hline(y=INITIAL_CAPITAL, line_dash="dash",
                  line_color="rgba(255,255,255,0.2)")
    fig.update_layout(
        title=(f"Top-10 Setups — Full Dataset Equity (IS+OOS combined — REFERENCE)<br>"
               f"<sub>Warning: IS data is included. Use WFO chart for true OOS performance.</sub>"),
        xaxis_title="Trade Number",
        yaxis_title=f"Portfolio Value (USD, start ${INITIAL_CAPITAL:.0f})",
        template=_DARK, height=600,
        legend=dict(orientation="v", x=1.01, y=1),
    )
    path = os.path.join(out_dir, "chart_top20.html")
    fig.write_html(path)
    print(f"  -> {path}")


def _chart_holdout(hold_results: list, out_dir: str):
    if not hold_results:
        return
    fig = go.Figure()
    for h in hold_results:
        eq_usd = h["equity"] * INITIAL_CAPITAL
        cfg = h["cfg"]
        m   = h["metrics"]
        label = (f"#{h['rank']} {cfg['signal'][:8]}|{cfg['mode'][:3]} "
                 f"WR={m['wr']*100:.0f}% Ret={m['total_ret']*100:+.1f}%")
        fig.add_trace(go.Scatter(
            y=eq_usd, mode="lines", name=label,
            line=dict(color=COLORS[(h["rank"] - 1) % len(COLORS)], width=2),
        ))
    fig.add_hline(y=INITIAL_CAPITAL, line_dash="dash",
                  line_color="rgba(255,100,100,0.5)",
                  annotation_text=f"Start ${INITIAL_CAPITAL:.0f}")
    fig.update_layout(
        title="FINAL HOLDOUT — Blind Test (2023-07 -> latest)<br>"
              "<sub>These results were NEVER used in training or selection.</sub>",
        xaxis_title="Trade Number",
        yaxis_title=f"Portfolio Value (USD)",
        template=_DARK, height=500,
    )
    path = os.path.join(out_dir, "chart_holdout.html")
    fig.write_html(path)
    print(f"  -> {path}")


def _report_top20(top20_all: list, top20_wr: list,
                  fold_results: list, wfo_equity: np.ndarray,
                  out_dir: str):
    """Generate a comprehensive HTML report."""
    wfo_ret = (wfo_equity[-1] - 1.0) * 100 if len(wfo_equity) > 1 else 0.0
    wfo_dd  = max_dd_pct(wfo_equity)

    rows_html = ""
    wr_keys = {
        (r["cfg"]["signal"], r["cfg"]["mode"], r["cfg"]["sl_mult"],
         r["cfg"]["rr"], r["cfg"]["ema_filter"], r["cfg"]["adx_thresh"],
         r["cfg"]["vol_filter"])
        for r in top20_wr
    }
    for rank, r in enumerate(top20_all, 1):
        cfg = r["cfg"]
        key = (cfg["signal"], cfg["mode"], cfg["sl_mult"], cfg["rr"],
               cfg["ema_filter"], cfg["adx_thresh"], cfg["vol_filter"])
        wr_flag = "✅" if key in wr_keys else ""
        wr_color = "#00e676" if r["avg_wr"] >= WR_MIN else (
                   "#ffd700" if r["avg_wr"] >= 0.45 else "#ff5252")
        rows_html += f"""
        <tr>
          <td>{rank}</td>
          <td>{wr_flag}</td>
          <td><b>{cfg['signal']}</b></td>
          <td>{cfg['mode']}</td>
          <td>{cfg['sl_mult']:.2f}</td>
          <td>{cfg['rr']:.1f}</td>
          <td>{'EMA200' if cfg['ema_filter'] else '-'}</td>
          <td>{'ADX'+str(cfg['adx_thresh']) if cfg['adx_thresh'] else '-'}</td>
          <td>{'Vol' if cfg['vol_filter'] else '-'}</td>
          <td style="color:{wr_color}">{r['avg_wr']*100:.1f}%</td>
          <td>{r['avg_calmar']:.2f}</td>
          <td>{r['avg_sharpe']:.2f}</td>
          <td>{r['avg_pf']:.2f}</td>
          <td>{r['agg_total_ret']*100:.1f}%</td>
          <td>{r['agg_max_dd']*100:.1f}%</td>
          <td>{r['total_oos_trades']}</td>
          <td><b>{r['composite']:.4f}</b></td>
        </tr>"""

    fold_rows = ""
    for fr in fold_results:
        om = fr["oos_m"] or {}
        cfg = fr["best_cfg"]
        oos_wr = om.get("wr", 0) * 100
        wr_c = "#00e676" if oos_wr >= 50 else ("#ffd700" if oos_wr >= 45 else "#ff5252")
        fold_rows += f"""
        <tr>
          <td>{fr['fold']}</td>
          <td>{fr['tr_range'][0].date()} -> {fr['tr_range'][1].date()}</td>
          <td>{fr['oos_range'][0].date()} -> {fr['oos_range'][1].date()}</td>
          <td><b>{cfg['signal']}</b></td>
          <td>{cfg['mode']}</td>
          <td>{cfg['sl_mult']:.2f}/{cfg['rr']:.1f}</td>
          <td style="color:{wr_c}">{oos_wr:.1f}%</td>
          <td>{om.get('calmar',0):.2f}</td>
          <td>{om.get('total_ret',0)*100:.1f}%</td>
          <td>{om.get('max_dd',0)*100:.1f}%</td>
          <td>{om.get('profit_factor',0):.2f}</td>
          <td>{fr['n_oos']}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>WFO Backtest v3 — XAUUSD M5 — Top 20 Report</title>
<style>
  body {{ background:#0d1117; color:#c9d1d9; font-family:'Segoe UI',sans-serif; margin:20px; }}
  h1   {{ color:#58a6ff; border-bottom:1px solid #30363d; padding-bottom:10px; }}
  h2   {{ color:#79c0ff; margin-top:30px; }}
  .summary {{ display:flex; gap:20px; flex-wrap:wrap; margin:16px 0; }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:8px;
            padding:16px 24px; min-width:160px; }}
  .card .val {{ font-size:1.6em; font-weight:bold; color:#58a6ff; }}
  .card .lbl {{ font-size:0.8em; color:#8b949e; margin-top:4px; }}
  table {{ border-collapse:collapse; width:100%; margin-top:12px; font-size:0.82em; }}
  th    {{ background:#21262d; color:#8b949e; padding:6px 10px;
            border-bottom:2px solid #30363d; text-align:left; }}
  td    {{ padding:5px 10px; border-bottom:1px solid #21262d; }}
  tr:hover td {{ background:#161b22; }}
  .note {{ background:#161b22; border-left:4px solid #388bfd; padding:10px 16px;
            border-radius:4px; margin:16px 0; font-size:0.85em; color:#8b949e; }}
  .green {{ color:#3fb950; }} .red {{ color:#f85149; }} .gold {{ color:#ffd700; }}
</style>
</head>
<body>
<h1>🔍 WFO Holy Grail Search v3 — XAUUSD M5</h1>
<p style="color:#8b949e">
  10 Strategies | IS={TRAIN_MONTHS}mo | OOS={TEST_MONTHS}mo | 11 Folds |
  WFO Pool: {WFO_POOL_START} -> {WFO_POOL_END} | Holdout: {HOLDOUT_START}+
</p>

<div class="summary">
  <div class="card"><div class="val {'green' if wfo_ret>0 else 'red'}">{wfo_ret:+.1f}%</div>
    <div class="lbl">WFO OOS Return</div></div>
  <div class="card"><div class="val red">{wfo_dd:.1f}%</div>
    <div class="lbl">WFO Max Drawdown</div></div>
  <div class="card"><div class="val">{len(fold_results)}</div>
    <div class="lbl">Successful Folds</div></div>
  <div class="card"><div class="val">{len(top20_all)}</div>
    <div class="lbl">Top-20 Configs Found</div></div>
  <div class="card"><div class="val">{len(top20_wr)}</div>
    <div class="lbl">Configs with WR>={WR_MIN*100:.0f}%</div></div>
</div>

<div class="note">
  <b>Scoring formula:</b> Composite = 40% Calmar + 35% Sharpe + 25% WR Bonus
  (WR bonus linear: 0 at WR=40%, 1 at WR=60%). All metrics computed on OOS data only.
  <br><b>Cost:</b> 0.12R per trade (spread + commission). <b>Risk:</b> 1% equity per trade.
</div>

<h2>📊 Top 20 Setups (Ranked by Composite Score)</h2>
<table>
<thead><tr>
  <th>#</th><th>WR>=50%</th><th>Signal</th><th>Mode</th>
  <th>SLxATR</th><th>RR</th><th>EMA</th><th>ADX</th><th>Vol</th>
  <th>Avg WR</th><th>Calmar</th><th>Sharpe</th><th>PF</th>
  <th>OOS Ret</th><th>Max DD</th><th>Trades</th><th>Score</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>

<h2>📅 WFO Fold Summary</h2>
<table>
<thead><tr>
  <th>Fold</th><th>IS Range</th><th>OOS Range</th>
  <th>Best Signal</th><th>Mode</th><th>SL/RR</th>
  <th>WR</th><th>Calmar</th><th>OOS Ret</th><th>DD</th><th>PF</th><th>Trades</th>
</tr></thead>
<tbody>{fold_rows}</tbody>
</table>

<p style="color:#8b949e;font-size:0.75em;margin-top:40px">
  Generated by WFO Backtest v3 | XAUUSD M5 | {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} UTC
</p>
</body>
</html>"""

    path = os.path.join(out_dir, "report_top20.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  -> {path}")


# ===========================================================================
#  Console Summaries
# ===========================================================================

def _print_top20_table(top20_all: list, top20_wr: list):
    if not top20_all:
        return
    wr_keys = {
        (r["cfg"]["signal"], r["cfg"]["mode"], r["cfg"]["sl_mult"],
         r["cfg"]["rr"], r["cfg"]["ema_filter"], r["cfg"]["adx_thresh"],
         r["cfg"]["vol_filter"])
        for r in top20_wr
    }
    print(f"\n{'=' * 100}")
    print("  TOP-20 BY COMPOSITE SCORE  (* = avg OOS WR >= 50%)")
    print(f"  Score = 40% Calmar + 35% Sharpe + 25% WR-Bonus")
    print("=" * 100)
    hdr = (f"  {'#':>3}  {'F':>2}  {'Signal':<15} {'Mode':<11} "
           f"{'SL':>5} {'RR':>4} {'EMA':>5} {'ADX':>5} {'Vol':>4} "
           f"{'WR%':>6} {'Calmar':>7} {'Sharpe':>7} {'PF':>5} "
           f"{'Ret%':>7} {'DD%':>6} {'T':>5} {'Score':>7}")
    print(hdr)
    print("  " + "-" * 96)
    for i, r in enumerate(top20_all, 1):
        cfg  = r["cfg"]
        key  = (cfg["signal"], cfg["mode"], cfg["sl_mult"], cfg["rr"],
                cfg["ema_filter"], cfg["adx_thresh"], cfg["vol_filter"])
        star = "*" if key in wr_keys else " "
        print(
            f"  {i:>3}{star} {r['valid_folds']:>2}  {cfg['signal']:<15} {cfg['mode']:<11} "
            f"{cfg['sl_mult']:>5.2f} {cfg['rr']:>4.1f} "
            f"{cfg['ema_filter']:>5} {cfg['adx_thresh']:>5} {cfg['vol_filter']:>4} "
            f"{r['avg_wr']*100:>6.1f} {r['agg_calmar']:>7.2f} {r['agg_sharpe']:>7.2f} "
            f"{r['agg_pf']:>5.2f} "
            f"{r['agg_total_ret']*100:>7.1f} {r['agg_max_dd']*100:>6.1f} "
            f"{r['total_oos_trades']:>5} {r['composite']:>7.4f}"
        )
    wr_count = len(top20_wr)
    if wr_count:
        print(f"\n  * {wr_count} setup(s) have avg OOS WR >= {WR_MIN*100:.0f}%")
    else:
        print(f"\n  [NOTE] No config maintained avg OOS WR >= {WR_MIN*100:.0f}% — "
              f"try lowering threshold or extending data.")


def _print_signal_analysis(sweep: list):
    if not sweep:
        return
    from collections import defaultdict
    sig_stats = defaultdict(list)
    for r in sweep:
        sig_stats[r["cfg"]["signal"]].append(r)

    print(f"\n{'=' * 80}")
    print("  SIGNAL-LEVEL AGGREGATE (best config per signal type)")
    print("=" * 80)
    hdr = (f"  {'Signal':<16} {'BestMode':<11} {'WR%':>6} "
           f"{'Calmar':>7} {'Sharpe':>7} {'PF':>5} {'Ret%':>7} {'DD%':>6} {'T':>5}")
    print(hdr)
    print("  " + "-" * 70)

    sig_bests = []
    for sig, items in sig_stats.items():
        best = max(items, key=lambda x: x["composite"])
        sig_bests.append((sig, best))
    sig_bests.sort(key=lambda x: x[1]["composite"], reverse=True)

    for sig, best in sig_bests:
        cfg = best["cfg"]
        print(
            f"  {sig:<16} {cfg['mode']:<11} "
            f"{best['avg_wr']*100:>6.1f} "
            f"{best['agg_calmar']:>7.2f} {best['agg_sharpe']:>7.2f} "
            f"{best['agg_pf']:>5.2f} "
            f"{best['agg_total_ret']*100:>7.1f} {best['agg_max_dd']*100:>6.1f} "
            f"{best['total_oos_trades']:>5}"
        )


# ===========================================================================
if __name__ == "__main__":
    main()
