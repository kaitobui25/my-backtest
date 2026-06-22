"""
wfo_engine_v3.py — Walk-Forward Optimization Engine (v3)

Architecture:
  1. generate_folds()      -> Rolling (IS, OOS) bar-index pairs
  2. build_grid()          -> 10,800 configs across 10 signals x 3 modes x params
  3. sim_fixed_nb()        -> Numba: Fixed TP/SL simulation
  4. sim_trailing_nb()     -> Numba: Trailing-stop simulation
  5. sim_partial_tp_nb()   -> Numba: Partial-TP (50% @ tp1_rr, trail rest)
  6. compute_metrics()     -> Calmar, Sharpe, WR, avg_R from trade results
  7. composite_score()     -> 40% Calmar + 35% Sharpe + 25% WR bonus
  8. run_sweep()           -> All configs x all folds -> top-20 OOS aggregation
  9. get_wfo_equity()      -> IS-optimal per fold -> stitched OOS equity curve
 10. get_holdout_equity()  -> Evaluate top-N configs on Final Holdout
"""

import time
from typing import List, Tuple, Dict, Optional

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from numba import njit

from signals_v3 import apply_ema_filter, apply_adx_filter, apply_vol_filter


# ===========================================================================
#  Fold Generation
# ===========================================================================

def generate_folds(
    index:        pd.DatetimeIndex,
    train_months: int = 24,
    test_months:  int = 6,
    pool_start:   Optional[str] = None,
    pool_end:     Optional[str] = None,
) -> List[Tuple[int, int, int, int]]:
    """
    Rolling WFO folds (slide = test_months).

    pool_start / pool_end: confine folding within a date window (WFO Pool only).
    Returns list of (train_start_idx, train_end_idx, test_start_idx, test_end_idx).
    """
    folds = []

    # Restrict to pool window
    if pool_start:
        ps_dt = pd.Timestamp(pool_start, tz=index.tz)
        anchor = ps_dt.to_pydatetime()
    else:
        anchor = index[0].to_pydatetime()

    if pool_end:
        pe_dt  = pd.Timestamp(pool_end, tz=index.tz)
        end_dt = pe_dt.to_pydatetime()
    else:
        end_dt = index[-1].to_pydatetime()

    while True:
        t_end = anchor + relativedelta(months=train_months)
        o_end = t_end  + relativedelta(months=test_months)
        if o_end > end_dt:
            break

        tr_s = int(index.searchsorted(anchor, side="left"))
        tr_e = int(index.searchsorted(t_end,  side="left"))
        te_s = tr_e
        te_e = int(index.searchsorted(o_end,  side="left"))

        # Minimum bars: IS >= 2000, OOS >= 500
        if (tr_e - tr_s) >= 2000 and (te_e - te_s) >= 500:
            folds.append((tr_s, tr_e, te_s, te_e))

        anchor += relativedelta(months=test_months)  # slide = OOS length

    return folds


# ===========================================================================
#  Grid Builder
# ===========================================================================

def build_grid(partial_tp1_rr: float = 2.0) -> List[Dict]:
    """
    Build full hyperparameter grid — 10,800 configs.

    Dimensions:
      signals      : 10
      mode         : FIXED / TRAILING / PARTIAL_TP
      sl_mult      : 0.75, 1.0, 1.5, 2.0, 2.5
      rr           : 1.5, 2.0, 2.5, 3.0  (FIXED + PARTIAL_TP)
      ema_filter   : 0 = off, 200 = EMA200 gate
      adx_thresh   : 0 = off, 20, 25
      vol_filter   : 0 = off, 1 = volume > SMA20
      wait_candles : 3, 6  (cooldown bars after trade closes)
    """
    signals     = [
        "SQUEEZE", "PREC_SNIPER", "SMC_FVG",
        "SUPERTREND_2", "SUPERTREND_3",
        "TRIPLE_EMA", "RSI_REV", "BB_BOUNCE",
        "MACD_CROSS", "ENGULFING",
    ]
    modes       = ["FIXED", "TRAILING", "PARTIAL_TP"]
    sl_mults    = [0.75, 1.0, 1.5, 2.0, 2.5]
    rr_ratios   = [1.5, 2.0, 2.5, 3.0]
    ema_filters = [0, 200]
    adx_threshs = [0, 20, 25]
    vol_filters = [0, 1]
    waits       = [3, 6]

    configs = []
    for sig in signals:
        for mode in modes:
            rrs = rr_ratios if mode != "TRAILING" else [0.0]
            for sl in sl_mults:
                for rr in rrs:
                    for ema_f in ema_filters:
                        for adx_t in adx_threshs:
                            for vol_f in vol_filters:
                                for wait in waits:
                                    configs.append({
                                        "signal":       sig,
                                        "mode":         mode,
                                        "sl_mult":      sl,
                                        "rr":           rr,
                                        "ema_filter":   ema_f,
                                        "adx_thresh":   adx_t,
                                        "vol_filter":   vol_f,
                                        "wait_candles": wait,
                                        "tp1_rr":       partial_tp1_rr,
                                    })
    return configs


# ===========================================================================
#  Numba Simulation Kernels
# ===========================================================================

@njit
def sim_fixed_nb(
    high: np.ndarray, low: np.ndarray, close: np.ndarray,
    signal: np.ndarray, atr: np.ndarray,
    sl_mult: float, rr: float, wait_candles: int,
):
    """
    Fixed TP/SL simulation.
    Entry: close of signal bar.
    Exit:  OHLC of subsequent bars (check low first for longs).
    Returns (trets, n_trades): trets[entry_bar] = pnl in R-multiples.
    """
    n        = len(signal)
    trets    = np.zeros(n)
    n_trades = 0
    in_pos   = 0
    sl_price = np.nan; tp_price = np.nan; init_risk = np.nan
    last_dir = 0;      last_cls = -1;     e_bar     = -1

    for i in range(n):
        pnl_r  = 0.0
        closed = False

        if in_pos != 0:
            if in_pos == 1:        # Long
                if   low[i]  <= sl_price: closed = True; pnl_r = -1.0
                elif high[i] >= tp_price: closed = True; pnl_r =  rr
            else:                  # Short
                if   high[i] >= sl_price: closed = True; pnl_r = -1.0
                elif low[i]  <= tp_price: closed = True; pnl_r =  rr
            if closed:
                trets[e_bar] = pnl_r
                n_trades    += 1
                last_dir     = in_pos; last_cls = i; in_pos = 0

        if signal[i] != 0.0 and in_pos == 0:
            valid = True
            if last_dir != 0 and (i - last_cls) <= wait_candles:
                valid = False
            if valid:
                a = atr[i]
                if not np.isnan(a) and a > 0.0:
                    init_risk = sl_mult * a
                    entry     = close[i]
                    if signal[i] == 1.0:
                        sl_price = entry - init_risk
                        tp_price = entry + rr * init_risk
                        in_pos   =  1
                    else:
                        sl_price = entry + init_risk
                        tp_price = entry - rr * init_risk
                        in_pos   = -1
                    e_bar = i

    return trets, n_trades


@njit
def sim_trailing_nb(
    high: np.ndarray, low: np.ndarray, close: np.ndarray,
    signal: np.ndarray, atr: np.ndarray,
    sl_mult: float, wait_candles: int,
):
    """
    Trailing-stop simulation.
    Trail distance = initial SL = sl_mult x ATR.
    Tracks the best excursion incrementally.
    """
    n          = len(signal)
    trets      = np.zeros(n)
    n_trades   = 0
    in_pos     = 0
    sl_price   = np.nan; trail_dist = np.nan; trail_max = np.nan
    init_risk  = np.nan; entry_px   = np.nan
    last_dir   = 0;      last_cls   = -1;     e_bar     = -1

    for i in range(n):
        pnl_r  = 0.0
        closed = False

        if in_pos != 0:
            if in_pos == 1:
                if low[i] <= sl_price:
                    closed = True; pnl_r = (sl_price - entry_px) / init_risk
                elif high[i] > trail_max:
                    trail_max = high[i]
                    nsl = trail_max - trail_dist
                    if nsl > sl_price: sl_price = nsl
            else:
                if high[i] >= sl_price:
                    closed = True; pnl_r = (entry_px - sl_price) / init_risk
                elif low[i] < trail_max:
                    trail_max = low[i]
                    nsl = trail_max + trail_dist
                    if nsl < sl_price: sl_price = nsl
            if closed:
                trets[e_bar] = pnl_r
                n_trades    += 1
                last_dir     = in_pos; last_cls = i; in_pos = 0

        if signal[i] != 0.0 and in_pos == 0:
            valid = True
            if last_dir != 0 and (i - last_cls) <= wait_candles:
                valid = False
            if valid:
                a = atr[i]
                if not np.isnan(a) and a > 0.0:
                    entry_px   = close[i]
                    init_risk  = sl_mult * a
                    trail_dist = init_risk
                    if signal[i] == 1.0:
                        sl_price  = entry_px - init_risk
                        trail_max = high[i]
                        in_pos    =  1
                    else:
                        sl_price  = entry_px + init_risk
                        trail_max = low[i]
                        in_pos    = -1
                    e_bar = i

    return trets, n_trades


@njit
def sim_partial_tp_nb(
    high: np.ndarray, low: np.ndarray, close: np.ndarray,
    signal: np.ndarray, atr: np.ndarray,
    sl_mult: float, tp1_rr: float, wait_candles: int,
):
    """
    Partial-TP simulation:
      Phase 1: Full position, SL at initial, TP1 at tp1_rr x R.
      On TP1 hit:
        - Lock 50% profit at tp1_rr x R.
        - SL -> breakeven.
        - Trail remaining 50% (distance = initial SL).
      pnl_r = blended: 0.5 x tp1_rr + 0.5 x trailing_exit_R.
    """
    n          = len(signal)
    trets      = np.zeros(n)
    n_trades   = 0
    in_pos     = 0
    sl_price   = np.nan; tp1_price  = np.nan; init_risk = np.nan
    hit_tp1    = False;  trail_dist = np.nan; trail_max = np.nan
    entry_px   = np.nan
    last_dir   = 0;      last_cls  = -1;     e_bar     = -1

    for i in range(n):
        pnl_r  = 0.0
        closed = False

        if in_pos != 0:
            if in_pos == 1:
                if not hit_tp1:
                    if   low[i]  <= sl_price:
                        closed = True; pnl_r = -1.0
                    elif high[i] >= tp1_price:
                        hit_tp1    = True
                        sl_price   = entry_px
                        trail_dist = init_risk
                        trail_max  = high[i]
                else:
                    if low[i] <= sl_price:
                        closed   = True
                        second_r = (sl_price - entry_px) / init_risk
                        pnl_r    = 0.5 * tp1_rr + 0.5 * second_r
                    elif high[i] > trail_max:
                        trail_max = high[i]
                        nsl = trail_max - trail_dist
                        if nsl > sl_price: sl_price = nsl
            else:
                if not hit_tp1:
                    if   high[i] >= sl_price:
                        closed = True; pnl_r = -1.0
                    elif low[i]  <= tp1_price:
                        hit_tp1    = True
                        sl_price   = entry_px
                        trail_dist = init_risk
                        trail_max  = low[i]
                else:
                    if high[i] >= sl_price:
                        closed   = True
                        second_r = (entry_px - sl_price) / init_risk
                        pnl_r    = 0.5 * tp1_rr + 0.5 * second_r
                    elif low[i] < trail_max:
                        trail_max = low[i]
                        nsl = trail_max + trail_dist
                        if nsl < sl_price: sl_price = nsl

            if closed:
                trets[e_bar] = pnl_r
                n_trades    += 1
                last_dir     = in_pos; last_cls = i; in_pos = 0; hit_tp1 = False

        if signal[i] != 0.0 and in_pos == 0:
            valid = True
            if last_dir != 0 and (i - last_cls) <= wait_candles:
                valid = False
            if valid:
                a = atr[i]
                if not np.isnan(a) and a > 0.0:
                    entry_px  = close[i]
                    init_risk = sl_mult * a
                    if signal[i] == 1.0:
                        sl_price  = entry_px - init_risk
                        tp1_price = entry_px + tp1_rr * init_risk
                        in_pos    =  1
                    else:
                        sl_price  = entry_px + init_risk
                        tp1_price = entry_px - tp1_rr * init_risk
                        in_pos    = -1
                    hit_tp1 = False; e_bar = i

    return trets, n_trades


# ===========================================================================
#  Metrics & Scoring
# ===========================================================================

def compute_metrics(trets: np.ndarray, n_trades: int,
                    risk_pct: float = 0.01,
                    cost_r:   float = 0.12) -> dict:
    """
    Compute performance metrics from simulation output.

    trets    : sparse array indexed by entry bar, value = pnl in R.
    risk_pct : fraction of equity risked per trade (default 1%).
    cost_r   : spread + commission in R per trade (default 0.12R for M5 XAU).
    """
    _null = {
        "calmar": 0.0, "sharpe": 0.0, "wr": 0.0,
        "total_ret": 0.0, "max_dd": 1.0, "trades": 0, "avg_rr": 0.0,
        "profit_factor": 0.0,
    }
    if n_trades < 1:
        return _null

    rets = trets[trets != 0.0] - cost_r
    if len(rets) == 0:
        return _null

    # Compound equity curve
    eq    = np.empty(len(rets) + 1)
    eq[0] = 1.0
    for j in range(len(rets)):
        eq[j + 1] = eq[j] * (1.0 + risk_pct * rets[j])

    total_ret = float(eq[-1] - 1.0)
    peak      = np.maximum.accumulate(eq)
    peak      = np.where(peak < 1e-12, 1e-12, peak)
    dd        = (eq - peak) / peak
    max_dd    = float(np.abs(dd.min()))
    if max_dd < 1e-12:
        max_dd = 1e-12

    calmar  = total_ret / max_dd if total_ret > 0.0 else total_ret
    mean_r  = float(np.mean(rets))
    std_r   = float(np.std(rets))
    sharpe  = (mean_r / std_r * float(np.sqrt(max(len(rets), 1)))) if std_r > 1e-10 else 0.0
    wr      = float(np.sum(rets > 0.0)) / len(rets)

    gross_win  = float(np.sum(rets[rets > 0.0]))
    gross_loss = float(np.abs(np.sum(rets[rets < 0.0])))
    pf         = gross_win / gross_loss if gross_loss > 1e-10 else (999.0 if gross_win > 0 else 0.0)

    return {
        "calmar": calmar, "sharpe": sharpe, "wr": wr,
        "total_ret": total_ret, "max_dd": max_dd,
        "trades": int(n_trades), "avg_rr": mean_r,
        "profit_factor": pf,
    }


def composite_score(m: dict) -> float:
    """
    40% Calmar + 35% Sharpe + 25% WinRate Bonus.

    WR bonus: linear scale from 0 (WR=40%) to 1 (WR=60%), capped.
    This strongly rewards strategies hitting WR > 50%.
    """
    calmar   = max(m["calmar"], 0.0)
    sharpe   = max(m["sharpe"], 0.0)
    wr_bonus = max(0.0, min(1.0, (m["wr"] - 0.40) / 0.20))
    return 0.40 * calmar + 0.35 * sharpe + 0.25 * wr_bonus


# ===========================================================================
#  Signal Preparation (apply filters)
# ===========================================================================

def _prep_signal(cfg: dict, registry: dict,
                 close: np.ndarray, ema200: np.ndarray,
                 adx: np.ndarray,   volume: np.ndarray) -> np.ndarray:
    """Apply EMA, ADX, and Volume filters to base signal."""
    sig = registry[cfg["signal"]].copy()
    if cfg["ema_filter"] > 0:
        sig = apply_ema_filter(sig, close, ema200)
    if cfg["adx_thresh"] > 0:
        sig = apply_adx_filter(sig, adx, float(cfg["adx_thresh"]))
    if cfg["vol_filter"] > 0:
        sig = apply_vol_filter(sig, volume)
    return sig


def _simulate(cfg: dict,
              high: np.ndarray, low: np.ndarray, close: np.ndarray,
              signal: np.ndarray, atr: np.ndarray):
    """Dispatch to correct simulation kernel."""
    mode = cfg["mode"]
    sl   = cfg["sl_mult"]
    wait = cfg["wait_candles"]
    if mode == "FIXED":
        return sim_fixed_nb(high, low, close, signal, atr, sl, cfg["rr"], wait)
    elif mode == "TRAILING":
        return sim_trailing_nb(high, low, close, signal, atr, sl, wait)
    else:  # PARTIAL_TP
        return sim_partial_tp_nb(high, low, close, signal, atr, sl, cfg["tp1_rr"], wait)


# ===========================================================================
#  Cross-Validation Sweep (all configs x all folds)
# ===========================================================================

def run_sweep(
    df:              pd.DataFrame,
    atr:             np.ndarray,
    adx:             np.ndarray,
    ema200:          np.ndarray,
    registry:        dict,
    folds:           list,
    configs:         list,
    volume:          np.ndarray,
    min_oos_trades:  int = 15,
    min_valid_folds: int = 4,
    min_is_wr:       float = 0.35,
) -> List[Dict]:
    """
    Full grid x fold sweep.

    For every config:
      1. Run IS + OOS simulation per fold.
      2. Aggregate OOS results across all valid folds.
      3. Filter: min valid folds, min OOS trades.
    Returns list of result dicts sorted by composite score.
    """
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n_cfg = len(configs)
    n_fld = len(folds)
    print(f"  Grid: {n_cfg:,} configs x {n_fld} folds = {n_cfg * n_fld:,} simulations")

    # Cache filtered signals: (signal, ema_f, adx_t, vol_f) -> ndarray
    sig_cache: Dict[tuple, np.ndarray] = {}

    def get_sig(cfg) -> np.ndarray:
        key = (cfg["signal"], cfg["ema_filter"], cfg["adx_thresh"], cfg["vol_filter"])
        if key not in sig_cache:
            sig_cache[key] = _prep_signal(cfg, registry, c, ema200, adx, volume)
        return sig_cache[key]

    results = []
    t0      = time.time()

    for ci, cfg in enumerate(configs):
        fsig      = get_sig(cfg)
        fold_data = []

        for fi, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
            # IS simulation
            tr_rets, n_tr = _simulate(
                cfg,
                h[tr_s:tr_e], l[tr_s:tr_e], c[tr_s:tr_e],
                fsig[tr_s:tr_e], atr[tr_s:tr_e],
            )
            is_m = compute_metrics(tr_rets, n_tr) if n_tr >= 5 else None

            # OOS simulation
            te_rets, n_te = _simulate(
                cfg,
                h[te_s:te_e], l[te_s:te_e], c[te_s:te_e],
                fsig[te_s:te_e], atr[te_s:te_e],
            )
            oos_m = compute_metrics(te_rets, n_te) if n_te >= min_oos_trades else None

            fold_data.append({
                "fold":     fi,
                "is_m":     is_m,
                "oos_m":    oos_m,
                "oos_rets": te_rets,
                "n_oos":    n_te,
            })

        # Aggregate valid OOS folds
        valid = [f for f in fold_data if f["oos_m"] is not None]
        if len(valid) < min_valid_folds:
            continue

        all_oos: List[float] = []
        for f in fold_data:
            nz = f["oos_rets"][f["oos_rets"] != 0.0]
            all_oos.extend(nz.tolist())

        if len(all_oos) < min_oos_trades:
            continue

        agg_arr  = np.array(all_oos, dtype=np.float64)
        agg_m    = compute_metrics(agg_arr, len(all_oos))
        agg_comp = composite_score(agg_m)

        avg_wr     = float(np.mean([f["oos_m"]["wr"]     for f in valid]))
        avg_calmar = float(np.mean([f["oos_m"]["calmar"] for f in valid]))
        avg_sharpe = float(np.mean([f["oos_m"]["sharpe"] for f in valid]))
        avg_pf     = float(np.mean([f["oos_m"]["profit_factor"] for f in valid]))

        results.append({
            "cfg":              cfg,
            "valid_folds":      len(valid),
            "total_oos_trades": len(all_oos),
            "avg_wr":           avg_wr,
            "avg_calmar":       avg_calmar,
            "avg_sharpe":       avg_sharpe,
            "avg_pf":           avg_pf,
            "agg_calmar":       agg_m["calmar"],
            "agg_sharpe":       agg_m["sharpe"],
            "agg_total_ret":    agg_m["total_ret"],
            "agg_max_dd":       agg_m["max_dd"],
            "agg_avg_rr":       agg_m["avg_rr"],
            "agg_pf":           agg_m["profit_factor"],
            "composite":        agg_comp,
            "oos_rets":         all_oos,
            "fold_data":        fold_data,
        })

        if (ci + 1) % 200 == 0:
            best_c = max((r["composite"] for r in results), default=0.0)
            best_w = max((r["avg_wr"] for r in results), default=0.0)
            elapsed = time.time() - t0
            eta     = elapsed / (ci + 1) * (n_cfg - ci - 1)
            print(f"    [{ci + 1:>6}/{n_cfg}] viable={len(results):>4} | "
                  f"best_comp={best_c:.3f} | best_wr={best_w*100:.1f}% | "
                  f"elapsed={elapsed:.0f}s ETA={eta:.0f}s")

    # Deduplicate: keep best composite per unique param combination
    # (wait_candles can differ, keep the one with highest composite)
    seen: Dict[tuple, Dict] = {}
    for r in results:
        cfg = r["cfg"]
        key = (cfg["signal"], cfg["mode"], cfg["sl_mult"],
               cfg["rr"], cfg["ema_filter"], cfg["adx_thresh"], cfg["vol_filter"])
        if key not in seen or r["composite"] > seen[key]["composite"]:
            seen[key] = r
    results = list(seen.values())
    results.sort(key=lambda x: x["composite"], reverse=True)

    elapsed = time.time() - t0
    print(f"\n  Sweep done in {elapsed:.1f}s | {len(results):,} unique viable configs")
    return results


# ===========================================================================
#  WFO Walk-Forward Equity (IS-optimal per fold, stitched OOS curve)
# ===========================================================================

def get_wfo_equity(
    df:             pd.DataFrame,
    atr:            np.ndarray,
    adx:            np.ndarray,
    ema200:         np.ndarray,
    registry:       dict,
    folds:          list,
    configs:        list,
    volume:         np.ndarray,
    min_is_trades:  int = 5,
    min_oos_trades: int = 15,
    risk_pct:       float = 0.01,
) -> Tuple[List[Dict], np.ndarray, List]:
    """
    Per fold:
      1. Grid-search on IS -> best config by composite score.
      2. Evaluate best config on OOS.
      3. Stitch OOS equity curves (compounding across folds).
    """
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    sig_cache: Dict[tuple, np.ndarray] = {}

    def get_sig(cfg) -> np.ndarray:
        key = (cfg["signal"], cfg["ema_filter"], cfg["adx_thresh"], cfg["vol_filter"])
        if key not in sig_cache:
            sig_cache[key] = _prep_signal(cfg, registry, c, ema200, adx, volume)
        return sig_cache[key]

    fold_results   = []
    equity_pieces  = []
    oos_trade_list = []

    for fi, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
        print(
            f"\n  [WFO Fold {fi + 1}/{len(folds)}]"
            f"  Train: {df.index[tr_s].date()} -> {df.index[tr_e - 1].date()}"
            f"  | OOS: {df.index[te_s].date()} -> {df.index[te_e - 1].date()}"
        )

        best_score = -np.inf
        best_cfg   = None
        best_is_m  = None

        for cfg in configs:
            fsig = get_sig(cfg)
            tr_rets, n_tr = _simulate(
                cfg, h[tr_s:tr_e], l[tr_s:tr_e], c[tr_s:tr_e],
                fsig[tr_s:tr_e], atr[tr_s:tr_e],
            )
            if n_tr < min_is_trades:
                continue
            is_m = compute_metrics(tr_rets, n_tr)
            if is_m["wr"] < 0.35:
                continue
            sc = composite_score(is_m)
            if sc > best_score:
                best_score = sc; best_cfg = cfg; best_is_m = is_m

        if best_cfg is None:
            print(f"    [!] No valid IS config — fold skipped.")
            continue

        fsig = get_sig(best_cfg)
        te_rets, n_te = _simulate(
            best_cfg, h[te_s:te_e], l[te_s:te_e], c[te_s:te_e],
            fsig[te_s:te_e], atr[te_s:te_e],
        )
        oos_m = compute_metrics(te_rets, n_te) if n_te >= min_oos_trades else None

        nz = te_rets[te_rets != 0.0]
        eq = np.ones(len(nz) + 1)
        for j in range(len(nz)):
            eq[j + 1] = eq[j] * (1.0 + risk_pct * nz[j])

        tag_is = (f"IS  Score={best_score:.3f} | WR={best_is_m['wr']*100:.1f}% | "
                  f"Calmar={best_is_m['calmar']:.2f}")
        if oos_m:
            tag_oos = (f"WR={oos_m['wr']*100:.1f}% | Calmar={oos_m['calmar']:.2f} | "
                       f"Ret={oos_m['total_ret']*100:.1f}% | PF={oos_m['profit_factor']:.2f} | "
                       f"[{oos_m['trades']}T]")
        else:
            tag_oos = f"(only {n_te} OOS trades, min={min_oos_trades})"

        print(f"    Best: {best_cfg['signal']:<15} {best_cfg['mode']:<11} "
              f"SL={best_cfg['sl_mult']:.2f} RR={best_cfg['rr']:.1f} "
              f"EMA={best_cfg['ema_filter']:>3} ADX={best_cfg['adx_thresh']:>2} "
              f"VOL={best_cfg['vol_filter']}")
        print(f"    {tag_is}")
        print(f"    OOS : {tag_oos}")

        fold_results.append({
            "fold":      fi + 1,
            "tr_range":  (df.index[tr_s], df.index[tr_e - 1]),
            "oos_range": (df.index[te_s], df.index[te_e - 1]),
            "best_cfg":  best_cfg,
            "is_score":  best_score,
            "is_m":      best_is_m,
            "oos_m":     oos_m,
            "n_oos":     int(n_te),
            "oos_rets":  nz.tolist(),
        })
        equity_pieces.append(eq)
        oos_trade_list.append(nz.tolist())

    # Stitch OOS equity (compound across folds)
    if not equity_pieces:
        return fold_results, np.array([1.0]), oos_trade_list

    combined = [1.0]
    running  = 1.0
    for eq_piece in equity_pieces:
        scaled = eq_piece * running
        combined.extend(scaled[1:].tolist())
        running = combined[-1]

    return fold_results, np.array(combined), oos_trade_list


# ===========================================================================
#  Final Holdout Evaluation
# ===========================================================================

def get_holdout_equity(
    top_configs:   List[dict],
    df_holdout:    pd.DataFrame,
    atr_holdout:   np.ndarray,
    adx_holdout:   np.ndarray,
    ema200_hold:   np.ndarray,
    registry_hold: dict,
    vol_holdout:   np.ndarray,
    risk_pct:      float = 0.01,
    n_top:         int = 5,
) -> List[Dict]:
    """
    Evaluate top-N configs from sweep on the Final Holdout data.
    Called only with --run-holdout flag.
    """
    h = df_holdout["high"].values
    l = df_holdout["low"].values
    c = df_holdout["close"].values
    results = []

    print(f"\n  [HOLDOUT] Evaluating top-{n_top} configs on "
          f"{df_holdout.index[0].date()} -> {df_holdout.index[-1].date()}")

    for rank, item in enumerate(top_configs[:n_top], 1):
        cfg  = item["cfg"]
        sig  = _prep_signal(cfg, registry_hold, c, ema200_hold, adx_holdout, vol_holdout)
        rets, n_t = _simulate(cfg, h, l, c, sig, atr_holdout)
        m    = compute_metrics(rets, n_t)
        nz   = rets[rets != 0.0]
        eq   = np.ones(len(nz) + 1)
        for j in range(len(nz)):
            eq[j + 1] = eq[j] * (1.0 + risk_pct * nz[j])

        results.append({
            "rank":       rank,
            "cfg":        cfg,
            "metrics":    m,
            "equity":     eq,
            "oos_wr":     item["avg_wr"],    # from WFO OOS
            "hold_wr":    m["wr"],
            "hold_ret":   m["total_ret"],
            "hold_dd":    m["max_dd"],
            "hold_pf":    m["profit_factor"],
            "n_trades":   n_t,
        })
        print(f"    Rank {rank:>2}: {cfg['signal']:<15} {cfg['mode']:<11} "
              f"SL={cfg['sl_mult']:.2f} RR={cfg['rr']:.1f} -> "
              f"WR={m['wr']*100:.1f}% "
              f"Ret={m['total_ret']*100:+.1f}% "
              f"DD={m['max_dd']*100:.1f}% "
              f"PF={m['profit_factor']:.2f} "
              f"[{n_t}T]")

    return results


# ===========================================================================
#  Utility
# ===========================================================================

def max_dd_pct(equity: np.ndarray) -> float:
    if len(equity) <= 1:
        return 0.0
    peak = np.maximum.accumulate(equity)
    peak = np.where(peak < 1e-12, 1e-12, peak)
    dd   = (equity - peak) / peak
    return float(np.abs(dd.min()) * 100)


def dd_series(equity: np.ndarray) -> list:
    peak = np.maximum.accumulate(equity)
    peak = np.where(peak < 1e-12, 1e-12, peak)
    dd   = (equity - peak) / peak * 100
    return [round(float(x), 4) for x in dd]
