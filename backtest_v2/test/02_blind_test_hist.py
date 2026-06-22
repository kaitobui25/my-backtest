"""
02_blind_test_hist.py — Blind Historical Test (XAUUSD M15 before Aug 2023)

Áp dụng top setups từ WFO (trained on Sep2023–Apr2026) vào holdout dataset
hoàn toàn chưa từng thấy (Jan2022–Jul2023).

Đây là BLIND TEST thực sự:
  - WFO params được lock cứng từ 01_WFO_HolyGrail_XAUUSD_M15_Results.md
  - Không có bất kỳ optimization nào trên data này
  - Mục tiêu: kiểm tra liệu các setup có GENERAL hay chỉ overfit 2023↑

Setups tested:
  A: SUPERTREND_2 | FIXED | SL=2.0 | RR=2.0 | EMA=off | ADX=off    [Top1 Calmar]
  B: RSI_REV      | FIXED | SL=1.5 | RR=1.5 | EMA=200 | ADX=25     [WR>=45%]
  C: TRIPLE_EMA   | FIXED | SL=0.75| RR=1.5 | EMA=200 | ADX=off    [Best fold5]
  D: SUPERTREND_2 | FIXED | SL=1.0 | RR=3.0 | EMA=off | ADX=off    [Top2 Calmar]
  E: RSI_REV      | FIXED | SL=1.5 | RR=3.0 | EMA=200 | ADX=25     [Top9 Calmar]

Usage:
  .vbt_env/Scripts/python.exe my-data/backtest_v2/core/02_blind_test_hist.py
"""

import os
import sys
import time
import warnings
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
CORE_DIR    = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.path.abspath(os.path.join(CORE_DIR, "..", ".."))
DATA_PATH   = os.path.join(BASE_DIR, "cache", "XAUUSD_M15_before_aug2023.parquet")
RESULT_DIR  = os.path.join(os.path.dirname(CORE_DIR), "result")
DOCS_DIR    = os.path.join(os.path.dirname(CORE_DIR), "docs")
os.makedirs(RESULT_DIR, exist_ok=True)
os.makedirs(DOCS_DIR,   exist_ok=True)

sys.path.insert(0, CORE_DIR)

import vectorbt as vbt
from signals    import calc_atr_rma, calc_adx, build_registry, apply_ema_filter, apply_adx_filter
from wfo_engine import _simulate, compute_metrics

# ---------------------------------------------------------------------------
# Setups to test (locked from WFO result — DO NOT modify)
# ---------------------------------------------------------------------------
SETUPS = [
    {
        "id":    "A",
        "label": "SUPERTREND_2 | FIXED | SL=2.0 | RR=2.0  [Top1 Calmar=13.01]",
        "cfg": {
            "signal": "SUPERTREND_2", "mode": "FIXED",
            "sl_mult": 2.0, "rr": 2.0, "ema_filter": 0, "adx_thresh": 0,
            "wait_candles": 3, "tp1_rr": 3.0,
        },
        "wfo_ref": {"calmar": 13.01, "wr_pct": 37.4, "ret_pct": 273.1, "dd_pct": 21.0},
    },
    {
        "id":    "B",
        "label": "RSI_REV | FIXED | SL=1.5 | RR=1.5 | EMA200+ADX25  [WR>=45%, Calmar=3.32]",
        "cfg": {
            "signal": "RSI_REV", "mode": "FIXED",
            "sl_mult": 1.5, "rr": 1.5, "ema_filter": 200, "adx_thresh": 25,
            "wait_candles": 3, "tp1_rr": 3.0,
        },
        "wfo_ref": {"calmar": 3.32, "wr_pct": 45.2, "ret_pct": 54.2, "dd_pct": 16.3},
    },
    {
        "id":    "C",
        "label": "TRIPLE_EMA | FIXED | SL=0.75 | RR=1.5 | EMA200  [Best WFO fold5]",
        "cfg": {
            "signal": "TRIPLE_EMA", "mode": "FIXED",
            "sl_mult": 0.75, "rr": 1.5, "ema_filter": 200, "adx_thresh": 0,
            "wait_candles": 3, "tp1_rr": 3.0,
        },
        "wfo_ref": {"calmar": 4.60, "wr_pct": 42.5, "ret_pct": 78.7, "dd_pct": 17.1},
    },
    {
        "id":    "D",
        "label": "SUPERTREND_2 | FIXED | SL=1.0 | RR=3.0  [Top2 Calmar=7.58]",
        "cfg": {
            "signal": "SUPERTREND_2", "mode": "FIXED",
            "sl_mult": 1.0, "rr": 3.0, "ema_filter": 0, "adx_thresh": 0,
            "wait_candles": 3, "tp1_rr": 3.0,
        },
        "wfo_ref": {"calmar": 7.58, "wr_pct": 27.3, "ret_pct": 236.1, "dd_pct": 31.1},
    },
    {
        "id":    "E",
        "label": "RSI_REV | FIXED | SL=1.5 | RR=3.0 | EMA200+ADX25  [Top9 Calmar=5.53]",
        "cfg": {
            "signal": "RSI_REV", "mode": "FIXED",
            "sl_mult": 1.5, "rr": 3.0, "ema_filter": 200, "adx_thresh": 25,
            "wait_candles": 3, "tp1_rr": 3.0,
        },
        "wfo_ref": {"calmar": 5.53, "wr_pct": 30.6, "ret_pct": 98.0, "dd_pct": 17.7},
    },
]

RISK_PCT  = 0.01   # 1% equity risk per trade
INIT_CASH = 10_000

_DARK = "plotly_dark"
COLORS = ["#00d2ff", "#f7931e", "#a8e063", "#c471ed", "#ff6b6b"]


# ===========================================================================
def main():
    t0 = time.time()
    print("=" * 72)
    print("  BLIND HISTORICAL TEST — XAUUSD M15 (before Aug 2023)")
    print("  Setups locked from WFO (Sep2023–Apr2026). Zero re-optimization.")
    print("=" * 72)

    # ── 1. Load holdout data ──────────────────────────────────────────────
    print(f"\n[1/4] Loading holdout data ...")
    if not os.path.exists(DATA_PATH):
        print(f"  [ERROR] Not found: {DATA_PATH}"); sys.exit(1)
    df = pd.read_parquet(DATA_PATH)
    print(f"  Rows: {len(df):,} | Range: {df.index[0]} -> {df.index[-1]}")
    print(f"  Period: Jan2022 -> Jul2023 (~18.5 months) — NEVER SEEN BY WFO")

    h = df["high"].values; l = df["low"].values
    c = df["close"].values

    # ── 2. Pre-compute indicators ─────────────────────────────────────────
    print("\n[2/4] Computing indicators ...")
    atr200 = calc_atr_rma(df["high"], df["low"], df["close"], period=200)
    adx14  = calc_adx(df["high"], df["low"], df["close"], period=14)
    ema200 = vbt.MA.run(df["close"], 200, ewm=True).ma.values
    print("  ATR(200), ADX(14), EMA(200) done.")

    print("  Building signal registry (Numba JIT) ...")
    registry = build_registry(df, atr200)

    # ── 3. Run each setup ─────────────────────────────────────────────────
    print("\n[3/4] Running blind test on all setups ...\n")
    results = []

    for setup in SETUPS:
        sid  = setup["id"]
        cfg  = setup["cfg"]
        ref  = setup["wfo_ref"]

        # Apply filters
        sig = registry[cfg["signal"]].copy()
        if cfg["ema_filter"] > 0:
            sig = apply_ema_filter(sig, c, ema200)
        if cfg["adx_thresh"] > 0:
            sig = apply_adx_filter(sig, adx14, float(cfg["adx_thresh"]))

        # Simulate
        trets, n_trades = _simulate(cfg, h, l, c, sig, atr200)
        m = compute_metrics(trets, n_trades, risk_pct=RISK_PCT)

        # Build equity curve
        nz = trets[trets != 0.0]
        eq = np.ones(len(nz) + 1)
        for j in range(len(nz)):
            eq[j + 1] = eq[j] * (1.0 + RISK_PCT * nz[j])

        results.append({
            "setup":    setup,
            "metrics":  m,
            "equity":   eq,
            "nz_rets":  nz,
            "n_trades": n_trades,
        })

        # WFO reference vs Blind test comparison
        delta_wr  = m["wr"] * 100 - ref["wr_pct"]
        delta_cal = m["calmar"] - ref["calmar"]
        verdict   = _verdict(m, ref)

        print(f"  [{sid}] {setup['label']}")
        print(f"       Trades : {n_trades:>5}   |  WFO ref: {ref['wr_pct']:.1f}%  "
              f"->  Blind: {m['wr']*100:.1f}%  (Δ {delta_wr:+.1f}%)")
        print(f"       WR     : {m['wr']*100:.1f}%   |  Calmar  : {m['calmar']:.2f}  "
              f"(WFO ref: {ref['calmar']:.2f}  Δ {delta_cal:+.2f})")
        print(f"       Ret    : {m['total_ret']*100:.1f}%  |  Max DD  : {m['max_dd']*100:.1f}%  "
              f"|  Sharpe: {m['sharpe']:.2f}")
        print(f"       Verdict: {verdict}")
        print()

    # ── 4. Export ─────────────────────────────────────────────────────────
    print("[4/4] Exporting results ...")

    _export_csv(results, df, RESULT_DIR)
    _chart_equity_overlay(results, df, RESULT_DIR)
    _chart_individual(results, df, RESULT_DIR)
    _write_report(results, df, DOCS_DIR)

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed:.1f}s. Output at:\n  {RESULT_DIR}")
    _print_summary(results)


# ===========================================================================
#  Helpers
# ===========================================================================

def _verdict(m: dict, ref: dict) -> str:
    """Simple pass/warn/fail verdict."""
    wr    = m["wr"] * 100
    cal   = m["calmar"]
    ret   = m["total_ret"] * 100

    if ret <= 0:
        return "FAIL   ❌  — Negative return on blind data"
    if cal >= ref["calmar"] * 0.5 and wr >= ref["wr_pct"] - 10:
        return "PASS   ✅  — Robust: metrics within acceptable range of WFO"
    if cal >= ref["calmar"] * 0.3 or wr >= ref["wr_pct"] - 15:
        return "WARN   ⚠️  — Degraded but still positive"
    return "WEAK   🟡  — Positive but significantly weaker than WFO period"


def _build_equity_series(nz: np.ndarray) -> np.ndarray:
    eq = np.ones(len(nz) + 1)
    for j in range(len(nz)):
        eq[j + 1] = eq[j] * (1.0 + RISK_PCT * nz[j])
    return eq


def _export_csv(results: list, df, out_dir: str):
    rows = []
    for r in results:
        s  = r["setup"]
        m  = r["metrics"]
        ref = s["wfo_ref"]
        cfg = s["cfg"]
        rows.append({
            "id":               s["id"],
            "label":            s["label"],
            "signal":           cfg["signal"],
            "mode":             cfg["mode"],
            "sl_mult":          cfg["sl_mult"],
            "rr":               cfg["rr"],
            "ema_filter":       cfg["ema_filter"],
            "adx_thresh":       cfg["adx_thresh"],
            # Blind test
            "blind_trades":     r["n_trades"],
            "blind_wr_pct":     round(m["wr"] * 100, 2),
            "blind_calmar":     round(m["calmar"], 3),
            "blind_sharpe":     round(m["sharpe"], 3),
            "blind_ret_pct":    round(m["total_ret"] * 100, 2),
            "blind_maxdd_pct":  round(m["max_dd"] * 100, 2),
            "blind_avg_rr":     round(m["avg_rr"], 3),
            # WFO reference
            "wfo_wr_pct":       ref["wr_pct"],
            "wfo_calmar":       ref["calmar"],
            "wfo_ret_pct":      ref["ret_pct"],
            "wfo_dd_pct":       ref["dd_pct"],
            # Delta
            "delta_wr":         round(m["wr"] * 100 - ref["wr_pct"], 2),
            "delta_calmar":     round(m["calmar"] - ref["calmar"], 3),
            "verdict":          _verdict(m, ref),
        })
    path = os.path.join(out_dir, "blind_test_hist_summary.csv")
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"  -> {path}")


def _chart_equity_overlay(results: list, df, out_dir: str):
    """All 5 equity curves on one chart."""
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.7, 0.3],
        shared_xaxes=False,
        subplot_titles=("Equity Curves (all setups)", "Gold Close Price (holdout period)"),
        vertical_spacing=0.08,
    )

    # Equity curves (per trade index)
    for i, r in enumerate(results):
        s  = r["setup"]
        eq = r["equity"]
        fig.add_trace(go.Scatter(
            y=eq * INIT_CASH,
            mode="lines",
            name=f"[{s['id']}] {s['cfg']['signal']} {s['cfg']['mode']} SL={s['cfg']['sl_mult']} RR={s['cfg']['rr']}",
            line=dict(color=COLORS[i], width=1.8),
        ), row=1, col=1)

    # Gold price
    fig.add_trace(go.Scatter(
        x=df.index, y=df["close"].values,
        mode="lines", name="XAUUSD Close",
        line=dict(color="#888888", width=1),
        showlegend=True,
    ), row=2, col=1)

    fig.update_layout(
        title=(
            "BLIND TEST — XAUUSD M15 Jan2022–Jul2023<br>"
            "<sub>WFO setups applied to holdout data (zero re-optimization) | 1% risk/trade</sub>"
        ),
        template=_DARK, height=700,
        legend=dict(orientation="h", y=-0.12, font_size=10),
        yaxis_title="Portfolio Value ($)",
        yaxis2_title="Gold Price ($)",
    )
    path = os.path.join(out_dir, "blind_test_hist_equity.html")
    fig.write_html(path)
    print(f"  -> {path}")


def _chart_individual(results: list, df, out_dir: str):
    """Separate chart per setup: equity + drawdown."""
    for i, r in enumerate(results):
        s   = r["setup"]
        m   = r["metrics"]
        eq  = r["equity"]
        nz  = r["nz_rets"]
        ref = s["wfo_ref"]

        # Drawdown series
        peak = np.maximum.accumulate(eq)
        peak = np.where(peak < 1e-12, 1e-12, peak)
        dd   = (eq - peak) / peak * 100

        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.65, 0.35],
            subplot_titles=("Equity", "Drawdown (%)"),
            vertical_spacing=0.1,
        )
        fig.add_trace(go.Scatter(
            y=eq * INIT_CASH, mode="lines",
            name="Equity",
            line=dict(color=COLORS[i], width=2),
            fill="tozeroy", fillcolor=f"rgba({_hex_to_rgb(COLORS[i])},0.08)",
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            y=dd, mode="lines",
            name="Drawdown %",
            line=dict(color="#ff4444", width=1.2),
            fill="tozeroy", fillcolor="rgba(255,68,68,0.12)",
        ), row=2, col=1)

        verdict = _verdict(m, ref)
        fig.update_layout(
            title=(
                f"[{s['id']}] {s['label']}<br>"
                f"<sub>Blind: WR={m['wr']*100:.1f}% | Calmar={m['calmar']:.2f} | "
                f"Ret={m['total_ret']*100:.1f}% | DD={m['max_dd']*100:.1f}% | "
                f"Trades={r['n_trades']} | {verdict}</sub>"
            ),
            template=_DARK, height=580,
            yaxis_title="Portfolio ($)",
            yaxis2_title="DD %",
            showlegend=False,
        )
        path = os.path.join(out_dir, f"blind_test_hist_{s['id']}.html")
        fig.write_html(path)
        print(f"  -> {path}")


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return ",".join(str(int(h[i:i+2], 16)) for i in (0, 2, 4))


def _write_report(results: list, df, docs_dir: str):
    """Write markdown report to docs."""
    lines = [
        "# Blind Historical Test — XAUUSD M15 (Jan2022–Jul2023)",
        "",
        "> **Mục đích**: Áp dụng các setup đã tìm được từ WFO (Sep2023–Apr2026) vào",
        "> dataset lịch sử hoàn toàn chưa từng dùng trong training. Đây là kiểm tra tính",
        "> tổng quát (generalization) của chiến lược.",
        "",
        "## Thông số Blind Test",
        "",
        "| Item                | Giá trị                               |",
        "|---------------------|---------------------------------------|",
        f"| Holdout data        | XAUUSD_M15_before_aug2023.parquet     |",
        f"| Holdout range       | {df.index[0].date()} → {df.index[-1].date()} |",
        f"| Holdout bars        | {len(df):,}                              |",
        "| WFO source          | Sep2023–Apr2026 (13 folds, ~672 configs) |",
        "| Re-optimization     | **ZERO** — params locked from WFO     |",
        "| Risk per trade      | 1% equity                             |",
        "",
        "---",
        "",
        "## Kết quả Blind Test vs WFO Reference",
        "",
        "| ID | Setup | Blind WR% | WFO WR% | Δ WR | Blind Calmar | WFO Calmar | Δ Calmar | Blind Ret% | WFO Ret% | Verdict |",
        "|----|-------|----------:|--------:|-----:|-------------:|-----------:|---------:|-----------:|---------:|---------|",
    ]

    for r in results:
        s   = r["setup"]
        m   = r["metrics"]
        ref = s["wfo_ref"]
        cfg = s["cfg"]
        label_short = f"{cfg['signal']} {cfg['mode']} SL={cfg['sl_mult']} RR={cfg['rr']}"
        v = _verdict(m, ref)
        v_short = v.split("—")[0].strip()
        lines.append(
            f"| {s['id']} | {label_short} "
            f"| {m['wr']*100:.1f} | {ref['wr_pct']:.1f} "
            f"| {m['wr']*100 - ref['wr_pct']:+.1f} "
            f"| {m['calmar']:.2f} | {ref['calmar']:.2f} "
            f"| {m['calmar'] - ref['calmar']:+.2f} "
            f"| {m['total_ret']*100:.1f} | {ref['ret_pct']:.1f} "
            f"| {v_short} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Chi tiết từng Setup",
        "",
    ]

    for r in results:
        s   = r["setup"]
        m   = r["metrics"]
        ref = s["wfo_ref"]
        verdict = _verdict(m, ref)
        lines += [
            f"### [{s['id']}] {s['label']}",
            "",
            f"| Metric       | Blind Test | WFO Ref  | Delta     |",
            f"|--------------|------------|----------|-----------|",
            f"| Win Rate     | {m['wr']*100:.2f}%     | {ref['wr_pct']:.2f}% | {m['wr']*100 - ref['wr_pct']:+.2f}%  |",
            f"| Calmar Ratio | {m['calmar']:.3f}      | {ref['calmar']:.3f}  | {m['calmar'] - ref['calmar']:+.3f}   |",
            f"| Sharpe       | {m['sharpe']:.3f}      | —        | —         |",
            f"| Total Return | {m['total_ret']*100:.2f}%    | {ref['ret_pct']:.2f}% | {m['total_ret']*100 - ref['ret_pct']:+.2f}% |",
            f"| Max Drawdown | {m['max_dd']*100:.2f}%    | {ref['dd_pct']:.2f}% | {m['max_dd']*100 - ref['dd_pct']:+.2f}% |",
            f"| Avg R/trade  | {m['avg_rr']:.4f}     | —        | —         |",
            f"| Trades       | {r['n_trades']:,}         | —        | —         |",
            "",
            f"> **Verdict**: {verdict}",
            "",
        ]

    lines += [
        "---",
        "",
        "## Kết luận",
        "",
        "*(Tự động generate — xem chi tiết tại `blind_test_hist_summary.csv`)*",
        "",
    ]

    # Auto conclusion
    pass_count = sum(1 for r in results if "PASS" in _verdict(r["metrics"], r["setup"]["wfo_ref"]))
    warn_count = sum(1 for r in results if "WARN" in _verdict(r["metrics"], r["setup"]["wfo_ref"]))
    fail_count = len(results) - pass_count - warn_count

    lines += [
        f"- **{pass_count} setup(s) PASS** — metrics giữ được trên dữ liệu chưa thấy",
        f"- **{warn_count} setup(s) WARN** — degraded nhưng vẫn dương",
        f"- **{fail_count} setup(s) FAIL/WEAK** — không maintain trên holdout",
        "",
        "### Nhận định Tổng thể",
    ]

    if pass_count >= 2:
        lines.append("Các setup **có khả năng generalize**. Chiến lược KHÔNG chỉ overfit 2023+.")
    elif pass_count == 1:
        lines.append("Chỉ 1 setup pass — kết quả **thận trọng**. Cần thêm data để xác nhận.")
    else:
        lines.append("Không setup nào pass đầy đủ — **overfit cảnh báo**. Xem xét thêm regularization.")

    lines += [
        "",
        "---",
        "",
        f"*Generated: {pd.Timestamp.now(tz='Asia/Tokyo').strftime('%Y-%m-%d %H:%M JST')}*",
    ]

    path = os.path.join(docs_dir, "02_BlindTest_Hist_Jan2022_Jul2023.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  -> {path}")


def _print_summary(results: list):
    print("\n" + "=" * 72)
    print("  BLIND TEST SUMMARY")
    print("=" * 72)
    hdr = (f"  {'ID':>2}  {'Signal':<15} {'Mode':<11} {'SL':>4} {'RR':>4}"
           f"  {'WR%':>6} {'Calmar':>7} {'Ret%':>7} {'DD%':>6} {'T':>5}  Verdict")
    print(hdr)
    print("  " + "-" * 68)
    for r in results:
        s   = r["setup"]
        m   = r["metrics"]
        cfg = s["cfg"]
        v   = _verdict(m, s["wfo_ref"])
        v_icon = v.split()[1] if len(v.split()) > 1 else ""
        print(
            f"  {s['id']:>2}  {cfg['signal']:<15} {cfg['mode']:<11} "
            f"{cfg['sl_mult']:>4.2f} {cfg['rr']:>4.1f} "
            f"  {m['wr']*100:>6.1f} {m['calmar']:>7.2f} "
            f"{m['total_ret']*100:>7.1f} {m['max_dd']*100:>6.1f} "
            f"{r['n_trades']:>5}  {v_icon}"
        )
    print()


# ===========================================================================
if __name__ == "__main__":
    main()
