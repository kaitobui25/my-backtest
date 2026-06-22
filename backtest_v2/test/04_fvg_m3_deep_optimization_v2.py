"""
04_fvg_m3_deep_optimization_v2.py  (FIXED)

Sửa lỗi từ bản gốc:
  1. Không dùng run_sweep (tránh bug signal cache + dedup key thiếu tp1_rr).
  2. Simulate trực tiếp từng config trên toàn dataset → đo metric chính xác.
  3. Hỗ trợ WFO split (IS/OOS) để đánh giá robustness thực tế.
  4. Grid search mở rộng: thêm TRAILING mode, thêm nhiều SL/TP mốc.

Target data: XAUUSD_M3_v2_new.parquet (2025-10 -> 2026-04, ~60K bars)
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
    compute_metrics, generate_folds,
)


# ===========================================================================
#  Direct simulation (bypass run_sweep to avoid caching bugs)
# ===========================================================================

def simulate_config(cfg, high, low, close, signal, atr):
    """Dispatch to correct simulation kernel — same as wfo_engine._simulate."""
    mode = cfg["mode"]
    sl   = cfg["sl_mult"]
    wait = cfg["wait_candles"]
    if mode == "FIXED":
        return sim_fixed_nb(high, low, close, signal, atr, sl, cfg["rr"], wait)
    elif mode == "TRAILING":
        return sim_trailing_nb(high, low, close, signal, atr, sl, wait)
    else:  # PARTIAL_TP
        return sim_partial_tp_nb(high, low, close, signal, atr, sl, cfg["tp1_rr"], wait)


def build_filtered_signal(sig_name, registry, close_arr, ema_arr, adx_arr,
                           ema_period, adx_thresh):
    """Apply EMA + ADX filter to base signal."""
    sig = registry[sig_name].copy()
    if ema_period > 0 and ema_arr is not None:
        sig = apply_ema_filter(sig, close_arr, ema_arr)
    if adx_thresh > 0:
        sig = apply_adx_filter(sig, adx_arr, float(adx_thresh))
    return sig


def run_full_grid(df, atr, adx, ema_dict, registry, configs, min_trades=10):
    """
    Run ALL configs on full dataset directly (no folds, no caching).
    Returns list of result dicts sorted by composite score.
    """
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    # Pre-build signal cache: (sig_name, ema_period, adx_thresh) -> ndarray
    sig_cache = {}

    results = []
    t0 = time.time()

    for ci, cfg in enumerate(configs):
        # Get or build filtered signal
        cache_key = (cfg["signal"], cfg["ema_filter"], cfg["adx_thresh"])
        if cache_key not in sig_cache:
            ema_arr = ema_dict.get(cfg["ema_filter"])
            sig_cache[cache_key] = build_filtered_signal(
                cfg["signal"], registry, c, ema_arr, adx,
                cfg["ema_filter"], cfg["adx_thresh"]
            )
        fsig = sig_cache[cache_key]

        # Simulate
        trets, n_trades = simulate_config(cfg, h, l, c, fsig, atr)

        if n_trades < min_trades:
            continue

        m = compute_metrics(trets, n_trades)

        results.append({
            "cfg":        cfg,
            "trades":     n_trades,
            "wr":         m["wr"],
            "total_ret":  m["total_ret"],
            "max_dd":     m["max_dd"],
            "calmar":     m["calmar"],
            "sharpe":     m["sharpe"],
            "avg_rr":     m["avg_rr"],
            "trets":      trets,
        })

        if (ci + 1) % 500 == 0:
            elapsed = time.time() - t0
            print(f"    [{ci+1}/{len(configs)}] viable={len(results)} | {elapsed:.0f}s")

    print(f"  Grid done in {time.time()-t0:.1f}s | {len(results)} viable configs")
    return results


def run_wfo_validation(df, atr, adx, ema_dict, registry, cfg,
                       train_months=2, test_months=1):
    """
    Walk-Forward validation for a single config.
    Returns list of fold metrics.
    """
    folds = generate_folds(df.index, train_months=train_months,
                           test_months=test_months)
    if not folds:
        return []

    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    ema_arr = ema_dict.get(cfg["ema_filter"])
    fsig = build_filtered_signal(
        cfg["signal"], registry, c, ema_arr, adx,
        cfg["ema_filter"], cfg["adx_thresh"]
    )

    fold_results = []
    for fi, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
        # IS metrics
        is_trets, is_n = simulate_config(
            cfg, h[tr_s:tr_e], l[tr_s:tr_e], c[tr_s:tr_e],
            fsig[tr_s:tr_e], atr[tr_s:tr_e]
        )
        is_m = compute_metrics(is_trets, is_n) if is_n >= 5 else None

        # OOS metrics
        oos_trets, oos_n = simulate_config(
            cfg, h[te_s:te_e], l[te_s:te_e], c[te_s:te_e],
            fsig[te_s:te_e], atr[te_s:te_e]
        )
        oos_m = compute_metrics(oos_trets, oos_n) if oos_n >= 3 else None

        fold_results.append({
            "fold": fi + 1,
            "is_range":  f"{df.index[tr_s].date()} -> {df.index[min(tr_e-1, len(df)-1)].date()}",
            "oos_range": f"{df.index[te_s].date()} -> {df.index[min(te_e-1, len(df)-1)].date()}",
            "is_m":  is_m,
            "oos_m": oos_m,
            "is_n":  is_n,
            "oos_n": oos_n,
        })
    return fold_results


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    print("=" * 80)
    print("  04v2 - FVG M3 DEEP OPTIMIZATION (FIXED) — XAUUSD_M3_v2_new  ")
    print("=" * 80)

    # -----------------------------------------------------------------------
    #  1. Load Data
    # -----------------------------------------------------------------------
    DATA_PATH = r"d:\Phong\03_Finance\trade\vectorbt-master\my-data\cache\m3\XAUUSD_M3_v2_new.parquet"
    if not os.path.exists(DATA_PATH):
        print(f"[!] File not found: {DATA_PATH}")
        return

    df = pd.read_parquet(DATA_PATH)
    print(f"\n[1/5] Data loaded: {len(df):,} bars")
    print(f"      Range: {df.index[0]} -> {df.index[-1]}")

    # -----------------------------------------------------------------------
    #  2. Compute Indicators
    # -----------------------------------------------------------------------
    print("\n[2/5] Computing indicators...")
    t0 = time.time()
    atr200 = calc_atr_rma(df["high"], df["low"], df["close"], period=200)
    adx14  = calc_adx(df["high"], df["low"], df["close"], period=14)

    # Pre-compute all EMA variants
    ema_periods_list = [0, 50, 100, 200]
    ema_dict = {0: None}
    for ep in ema_periods_list:
        if ep > 0:
            ema_dict[ep] = vbt.MA.run(df["close"], ep, ewm=True).ma.values
            print(f"    EMA({ep}) computed")
    print(f"    Done in {time.time()-t0:.1f}s")

    # -----------------------------------------------------------------------
    #  3. Build Signal Registry
    # -----------------------------------------------------------------------
    print("\n[3/5] Building signal registry...")
    h_arr = df["high"].values
    l_arr = df["low"].values
    c_arr = df["close"].values

    print("    [sig] FVG ...")
    fvg_raw = fvg_nb(h_arr, l_arr, c_arr, atr200, filter_width=0.1)

    print("    [sig] SuperTrend mult=2 ...")
    st2 = supertrend_nb(h_arr, l_arr, c_arr, atr200, multiplier=2.0)

    print("    [sig] SuperTrend mult=3 ...")
    st3 = supertrend_nb(h_arr, l_arr, c_arr, atr200, multiplier=3.0)

    print("    [sig] RSI Reversal (14) ...")
    rsi_vals = vbt.RSI.run(df["close"], window=14).rsi.values
    rsi_rev  = rsi_reversal(df["close"], window=14)

    print("    [sig] BB Bounce (20/2.0) ...")
    bb_bnc = bb_bounce(df["close"], rsi_vals, window=20, alpha=2.0)

    print("    [sig] Triple EMA (9/21/50) ...")
    tema = triple_ema(df["close"], fast=9, mid=21, slow=50)

    registry = {
        "FVG":          fvg_raw,
        "SUPERTREND_2": st2,
        "SUPERTREND_3": st3,
        "RSI_REV":      rsi_rev,
        "BB_BOUNCE":    bb_bnc,
        "TRIPLE_EMA":   tema,
    }

    for name, sig in registry.items():
        n_long  = int(np.sum(sig == 1.0))
        n_short = int(np.sum(sig == -1.0))
        print(f"    {name}: {n_long} long, {n_short} short, total={n_long+n_short}")

    # -----------------------------------------------------------------------
    #  4. Grid Search (direct, no run_sweep)
    # -----------------------------------------------------------------------
    signals_list = ["FVG", "SUPERTREND_2", "SUPERTREND_3", "RSI_REV", "BB_BOUNCE", "TRIPLE_EMA"]
    modes        = ["FIXED", "PARTIAL_TP", "TRAILING"]
    sl_mults     = [0.75, 1.0, 1.5, 2.0, 2.5, 3.0]
    rr_ratios    = [0.5, 0.8, 1.0, 1.25, 1.5, 2.0, 3.0]
    adx_threshs  = [0, 15, 20, 25]
    ema_filters  = [0, 50, 100, 200]
    waits        = [0, 2, 5]

    configs = []
    for sig in signals_list:
        for mode in modes:
            for sl in sl_mults:
                rrs = rr_ratios if mode != "TRAILING" else [0.0]
                for rr in rrs:
                    for ema_f in ema_filters:
                        for adx_t in adx_threshs:
                            for wait in waits:
                                configs.append({
                                    "signal":       sig,
                                    "mode":         mode,
                                    "sl_mult":      sl,
                                    "rr":           rr,
                                    "tp1_rr":       rr,
                                    "ema_filter":   ema_f,
                                    "adx_thresh":   adx_t,
                                    "wait_candles": wait,
                                })

    print(f"\n[4/5] Grid Search: {len(configs):,} configs")
    results = run_full_grid(df, atr200, adx14, ema_dict, registry, configs,
                            min_trades=20)

    # -----------------------------------------------------------------------
    #  5. Rank & Report
    # -----------------------------------------------------------------------
    print(f"\n[5/5] Ranking {len(results)} viable configs...")

    # Sort by composite score: 60% Calmar + 40% Sharpe
    for r in results:
        r["composite"] = max(r["calmar"], 0.0) * 0.6 + max(r["sharpe"], 0.0) * 0.4

    results.sort(key=lambda x: x["composite"], reverse=True)

    # === TOP 30 by Composite ===
    print("\n" + "=" * 120)
    print(f"{'TOP 30 BY COMPOSITE SCORE (Calmar*0.6 + Sharpe*0.4)':^120}")
    print("=" * 120)
    hdr = (f"{'#':>3} {'Signal':<13} {'Mode':<11} {'SL':>4} {'RR/TP1':>6} {'EMA':>4} {'ADX':>4} "
           f"{'W':>2} | {'WR%':>6} {'Profit%':>8} {'DD%':>6} {'Calmar':>7} {'Sharpe':>7} "
           f"{'Comp':>6} {'Trades':>6}")
    print(hdr)
    print("-" * 120)

    top30 = results[:30]
    for i, r in enumerate(top30, 1):
        c = r["cfg"]
        rr_val = c["rr"] if c["mode"] == "FIXED" else (c["tp1_rr"] if c["mode"] == "PARTIAL_TP" else 0.0)
        print(f"{i:>3} {c['signal']:<13} {c['mode']:<11} {c['sl_mult']:>4.1f} {rr_val:>6.2f} "
              f"{c['ema_filter']:>4} {c['adx_thresh']:>4} {c['wait_candles']:>2} | "
              f"{r['wr']*100:>6.1f} {r['total_ret']*100:>+8.1f} {r['max_dd']*100:>6.1f} "
              f"{r['calmar']:>7.2f} {r['sharpe']:>7.2f} {r['composite']:>6.2f} {r['trades']:>6}")

    # === TOP 30 by Win Rate ===
    results_by_wr = sorted(results, key=lambda x: (x["wr"], x["total_ret"]), reverse=True)
    print("\n" + "=" * 120)
    print(f"{'TOP 30 BY WINRATE':^120}")
    print("=" * 120)
    print(hdr)
    print("-" * 120)

    for i, r in enumerate(results_by_wr[:30], 1):
        c = r["cfg"]
        rr_val = c["rr"] if c["mode"] == "FIXED" else (c["tp1_rr"] if c["mode"] == "PARTIAL_TP" else 0.0)
        print(f"{i:>3} {c['signal']:<13} {c['mode']:<11} {c['sl_mult']:>4.1f} {rr_val:>6.2f} "
              f"{c['ema_filter']:>4} {c['adx_thresh']:>4} {c['wait_candles']:>2} | "
              f"{r['wr']*100:>6.1f} {r['total_ret']*100:>+8.1f} {r['max_dd']*100:>6.1f} "
              f"{r['calmar']:>7.2f} {r['sharpe']:>7.2f} {r['composite']:>6.2f} {r['trades']:>6}")

    # === TOP 30 by Profit ===
    results_by_ret = sorted(results, key=lambda x: x["total_ret"], reverse=True)
    print("\n" + "=" * 120)
    print(f"{'TOP 30 BY NET PROFIT':^120}")
    print("=" * 120)
    print(hdr)
    print("-" * 120)

    for i, r in enumerate(results_by_ret[:30], 1):
        c = r["cfg"]
        rr_val = c["rr"] if c["mode"] == "FIXED" else (c["tp1_rr"] if c["mode"] == "PARTIAL_TP" else 0.0)
        print(f"{i:>3} {c['signal']:<13} {c['mode']:<11} {c['sl_mult']:>4.1f} {rr_val:>6.2f} "
              f"{c['ema_filter']:>4} {c['adx_thresh']:>4} {c['wait_candles']:>2} | "
              f"{r['wr']*100:>6.1f} {r['total_ret']*100:>+8.1f} {r['max_dd']*100:>6.1f} "
              f"{r['calmar']:>7.2f} {r['sharpe']:>7.2f} {r['composite']:>6.2f} {r['trades']:>6}")

    # -----------------------------------------------------------------------
    #  6. WFO Validation of Top 5
    # -----------------------------------------------------------------------
    print("\n" + "=" * 120)
    print("  WFO VALIDATION (2M Train / 1M Test) FOR TOP 5 COMPOSITE")
    print("=" * 120)

    for rank, r in enumerate(top30[:5], 1):
        cfg = r["cfg"]
        rr_val = cfg["rr"] if cfg["mode"] == "FIXED" else (cfg["tp1_rr"] if cfg["mode"] == "PARTIAL_TP" else 0.0)
        print(f"\n  --- Top {rank}: {cfg['signal']} | {cfg['mode']} | SL={cfg['sl_mult']} "
              f"| RR={rr_val} | EMA={cfg['ema_filter']} | ADX={cfg['adx_thresh']} | W={cfg['wait_candles']} ---")
        print(f"  Full-dataset: WR={r['wr']*100:.1f}% | Profit={r['total_ret']*100:+.1f}% "
              f"| DD={r['max_dd']*100:.1f}% | Calmar={r['calmar']:.2f}")

        fold_results = run_wfo_validation(
            df, atr200, adx14, ema_dict, registry, cfg,
            train_months=2, test_months=1
        )

        if not fold_results:
            print("  [!] No valid WFO folds generated.")
            continue

        print(f"  {'Fold':>4} {'OOS Range':>28} | {'IS_WR':>6} {'IS_Ret':>8} | "
              f"{'OOS_WR':>6} {'OOS_Ret':>8} {'OOS_DD':>7} {'OOS_T':>5}")
        print(f"  {'-'*90}")

        oos_rets_all = []
        for fr in fold_results:
            is_tag = ""
            if fr["is_m"]:
                is_tag = f"{fr['is_m']['wr']*100:>5.1f}% {fr['is_m']['total_ret']*100:>+7.1f}%"
            else:
                is_tag = f"{'N/A':>5} {'N/A':>8}"

            oos_tag = ""
            if fr["oos_m"]:
                oos_tag = (f"{fr['oos_m']['wr']*100:>5.1f}% {fr['oos_m']['total_ret']*100:>+7.1f}% "
                           f"{fr['oos_m']['max_dd']*100:>6.1f}% {fr['oos_n']:>5}")
                oos_rets_all.append(fr["oos_m"]["total_ret"])
            else:
                oos_tag = f"{'N/A':>5} {'N/A':>8} {'N/A':>7} {fr['oos_n']:>5}"

            print(f"  {fr['fold']:>4} {fr['oos_range']:>28} | {is_tag} | {oos_tag}")

        if oos_rets_all:
            avg_oos_ret = np.mean(oos_rets_all) * 100
            n_positive = sum(1 for r in oos_rets_all if r > 0)
            print(f"  {'':>4} {'SUMMARY':>28} | Avg OOS Ret: {avg_oos_ret:+.1f}% | "
                  f"Positive folds: {n_positive}/{len(oos_rets_all)}")

    # -----------------------------------------------------------------------
    #  7. Export CSV
    # -----------------------------------------------------------------------
    RESULT_DIR = os.path.join(BASE_DIR, "..", "result")
    os.makedirs(RESULT_DIR, exist_ok=True)
    out_path = os.path.join(RESULT_DIR, "04v2_fvg_m3_deep_strategies.csv")

    rows = []
    for rank, r in enumerate(results[:50], 1):
        c = r["cfg"]
        rr_val = c["rr"] if c["mode"] == "FIXED" else (c["tp1_rr"] if c["mode"] == "PARTIAL_TP" else 0.0)
        rows.append({
            "rank": rank,
            "signal": c["signal"],
            "mode": c["mode"],
            "sl_mult": c["sl_mult"],
            "rr": rr_val,
            "ema_filter": c["ema_filter"],
            "adx_thresh": c["adx_thresh"],
            "wait_candles": c["wait_candles"],
            "wr_pct": round(r["wr"] * 100, 2),
            "total_ret_pct": round(r["total_ret"] * 100, 2),
            "max_dd_pct": round(r["max_dd"] * 100, 2),
            "calmar": round(r["calmar"], 3),
            "sharpe": round(r["sharpe"], 3),
            "composite": round(r["composite"], 3),
            "trades": r["trades"],
        })

    df_out = pd.DataFrame(rows)
    df_out.to_csv(out_path, index=False)
    print(f"\n[OK] Saved top 50 to: {out_path}")

    # -----------------------------------------------------------------------
    #  8. Equity Chart for Top 1
    # -----------------------------------------------------------------------
    if results:
        _export_equity_chart(df, atr200, adx14, ema_dict, registry,
                             results[0], RESULT_DIR)

    print("\n[DONE]")


def _export_equity_chart(df, atr, adx, ema_dict, registry, top_result, out_dir):
    """Export interactive HTML equity chart for the top config."""
    import plotly.graph_objects as go

    cfg = top_result["cfg"]
    trets = top_result["trets"]
    nz = trets[trets != 0.0]

    if len(nz) == 0:
        print("[!] No trades for equity chart.")
        return

    eq_list = [10000.0]
    eq = 1.0
    for ret in nz:
        eq *= (1.0 + 0.01 * ret)
        eq_list.append(eq * 10000)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=eq_list, mode="lines",
        name="Equity",
        line=dict(color="#00d2ff", width=2),
        fill="tozeroy", fillcolor="rgba(0,210,255,0.07)"
    ))

    rr_val = cfg["rr"] if cfg["mode"] == "FIXED" else (
        cfg["tp1_rr"] if cfg["mode"] == "PARTIAL_TP" else 0.0
    )
    final_ret = ((eq_list[-1] / eq_list[0]) - 1) * 100

    fig.update_layout(
        title=(f"Equity Curve — 04v2 FIXED Grid Search (XAUUSD_M3_v2_new)<br>"
               f"<sub>{cfg['signal']} | {cfg['mode']} | SL={cfg['sl_mult']} | "
               f"RR={rr_val} | EMA={cfg['ema_filter']} | ADX={cfg['adx_thresh']}<br>"
               f"Trades={top_result['trades']} | WR={top_result['wr']*100:.1f}% | "
               f"DD={top_result['max_dd']*100:.1f}% | Net={final_ret:+.1f}%</sub>"),
        xaxis_title="Trade Number",
        yaxis_title="Portfolio Value ($, starting $10,000)",
        template="plotly_dark", height=550
    )

    chart_path = os.path.join(out_dir, "04v2_fvg_m3_best_chart.html")
    fig.write_html(chart_path)
    print(f"[OK] Equity chart exported: {chart_path}")


if __name__ == "__main__":
    main()
