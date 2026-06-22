"""
wfo_engine.py — Walk-Forward Optimization Engine.

Architecture:
  1. generate_folds()    → rolling (train, test) bar-index pairs
  2. build_grid()        → list of config dicts
  3. sim_fixed_nb()      → Numba: FIXED TP/SL simulation
  4. sim_trailing_nb()   → Numba: Trailing-stop simulation
  5. sim_partial_tp_nb() → Numba: Partial-TP (50% @ 3R, trail rest)
  6. compute_metrics()   → Calmar, Sharpe, WR, avg-R from trade results
  7. composite_score()   → 60% Calmar + 40% Sharpe (both floored at 0)
  8. run_sweep()         → Cross-validation: every config × every fold
  9. get_wfo_equity()    → IS-optimal selection per fold → stitched OOS equity
"""

import time
from typing import List, Tuple, Dict

import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from numba import njit

from signals import apply_ema_filter, apply_adx_filter


# ===========================================================================
#  Fold Generation
# ===========================================================================

def generate_folds(
    index: pd.DatetimeIndex,
    train_months: int = 3,
    test_months:  int = 2,
) -> List[Tuple[int, int, int, int]]:
    """
    Rolling WFO folds (slide = test_months).
    Returns list of (train_start_idx, train_end_idx, test_start_idx, test_end_idx).
    """
    folds      = []
    anchor     = index[0].to_pydatetime()
    end_dt     = index[-1].to_pydatetime()

    while True:
        t_end = anchor + relativedelta(months=train_months)
        o_end = t_end  + relativedelta(months=test_months)
        if o_end > end_dt:
            break

        tr_s = int(index.searchsorted(anchor, side="left"))
        tr_e = int(index.searchsorted(t_end,  side="left"))
        te_s = tr_e
        te_e = int(index.searchsorted(o_end,  side="left"))

        if (tr_e - tr_s) >= 500 and (te_e - te_s) >= 300:
            folds.append((tr_s, tr_e, te_s, te_e))

        anchor += relativedelta(months=test_months)

    return folds


# ===========================================================================
#  Grid Builder
# ===========================================================================

def build_grid(partial_tp1_rr: float = 3.0) -> List[Dict]:
    """
    Build full hyperparameter grid.
    TRAILING mode ignores rr (no fixed TP), the list is deduplicated.
    """
    signals     = ["FVG", "SUPERTREND_2", "SUPERTREND_3",
                   "TRIPLE_EMA", "RSI_REV", "BB_BOUNCE"]
    modes       = ["FIXED", "TRAILING", "PARTIAL_TP"]
    sl_mults    = [0.75, 1.0, 1.5, 2.0]
    rr_ratios   = [1.5, 2.0, 3.0]            # used by FIXED & PARTIAL_TP
    ema_filters = [0, 200]                    # 0=off, 200=EMA200 trend gate
    adx_threshs = [0, 25]                     # 0=off, 25=trending market
    waits       = [3, 5]                      # cooldown bars after exit

    configs = []
    for sig in signals:
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
                                    "ema_filter":   ema_f,
                                    "adx_thresh":   adx_t,
                                    "wait_candles": wait,
                                    "tp1_rr":       partial_tp1_rr,
                                })
    return configs


# ===========================================================================
#  Numba Simulations
# ===========================================================================

@njit
def sim_fixed_nb(
    high: np.ndarray, low: np.ndarray, close: np.ndarray,
    signal: np.ndarray, atr: np.ndarray,
    sl_mult: float, rr: float, wait_candles: int,
):
    """
    Fixed TP/SL simulation (enter at close, exit on next bar's OHLC).
    Returns (trets, n_trades) where trets[entry_bar] = pnl in R-multiples.
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
            if in_pos == 1:
                if   low[i]  <= sl_price: closed = True; pnl_r = -1.0
                elif high[i] >= tp_price: closed = True; pnl_r =  rr
            else:
                if   high[i] >= sl_price: closed = True; pnl_r = -1.0
                elif low[i]  <= tp_price: closed = True; pnl_r =  rr
            if closed:
                trets[e_bar]  = pnl_r
                n_trades     += 1
                last_dir      = in_pos; last_cls = i; in_pos = 0

        if signal[i] != 0.0 and in_pos == 0:
            valid = True
            if last_dir != 0:
                since = i - last_cls
                if since <= wait_candles:
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
    Trail distance = initial SL (= sl_mult × ATR), tracks the best excursion.
    Returns (trets, n_trades).
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
                # CHECK STOP FIRST (conservative: low may come before high)
                if low[i] <= sl_price:
                    closed = True; pnl_r = (sl_price - entry_px) / init_risk
                elif high[i] > trail_max:
                    trail_max = high[i]
                    nsl = trail_max - trail_dist
                    if nsl > sl_price: sl_price = nsl
            else:
                # CHECK STOP FIRST (conservative: high may come before low)
                if high[i] >= sl_price:
                    closed = True; pnl_r = (entry_px - sl_price) / init_risk
                elif low[i] < trail_max:
                    trail_max = low[i]
                    nsl = trail_max + trail_dist
                    if nsl < sl_price: sl_price = nsl
            if closed:
                trets[e_bar]  = pnl_r
                n_trades     += 1
                last_dir      = in_pos; last_cls = i; in_pos = 0

        if signal[i] != 0.0 and in_pos == 0:
            valid = True
            if last_dir != 0:
                since = i - last_cls
                if since <= wait_candles:
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
      Phase 1 (full position): SL at initial level, TP1 at tp1_rr × R.
      On TP1 hit:
        - Lock 50% of profit at tp1_rr × R.
        - Move SL to breakeven.
        - Trail remaining 50% with distance = initial SL.
      Close trade when trailing stop hit after TP1.
    Returns (trets, n_trades) where pnl_r = blended R-return.
    """
    n          = len(signal)
    trets      = np.zeros(n)
    n_trades   = 0
    in_pos     = 0
    sl_price   = np.nan; tp1_price = np.nan; init_risk = np.nan
    hit_tp1    = False;  trail_dist = np.nan; trail_max = np.nan
    entry_px   = np.nan
    last_dir   = 0;      last_cls   = -1;     e_bar     = -1

    for i in range(n):
        pnl_r  = 0.0
        closed = False

        if in_pos != 0:
            if in_pos == 1:
                if not hit_tp1:
                    if   low[i]  <= sl_price:
                        closed = True; pnl_r = -1.0        # full 1R loss
                    elif high[i] >= tp1_price:
                        hit_tp1    = True                   # lock first half
                        sl_price   = entry_px               # SL -> breakeven
                        trail_dist = init_risk
                        trail_max  = high[i]
                else:                                       # trailing second half
                    # CHECK STOP FIRST (conservative)
                    if low[i] <= sl_price:
                        closed   = True
                        second_r = (sl_price - entry_px) / init_risk
                        pnl_r    = 0.5 * tp1_rr + 0.5 * second_r
                    elif high[i] > trail_max:
                        trail_max = high[i]
                        nsl = trail_max - trail_dist
                        if nsl > sl_price: sl_price = nsl

            else:  # short
                if not hit_tp1:
                    if   high[i] >= sl_price:
                        closed = True; pnl_r = -1.0
                    elif low[i]  <= tp1_price:
                        hit_tp1    = True
                        sl_price   = entry_px
                        trail_dist = init_risk
                        trail_max  = low[i]
                else:
                    # CHECK STOP FIRST (conservative)
                    if high[i] >= sl_price:
                        closed   = True
                        second_r = (entry_px - sl_price) / init_risk
                        pnl_r    = 0.5 * tp1_rr + 0.5 * second_r
                    elif low[i] < trail_max:
                        trail_max = low[i]
                        nsl = trail_max + trail_dist
                        if nsl < sl_price: sl_price = nsl

            if closed:
                trets[e_bar]  = pnl_r
                n_trades     += 1
                last_dir      = in_pos; last_cls = i; in_pos = 0; hit_tp1 = False

        if signal[i] != 0.0 and in_pos == 0:
            valid = True
            if last_dir != 0:
                since = i - last_cls
                if since <= wait_candles:
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
#  Metrics
# ===========================================================================

def compute_metrics(trets: np.ndarray, n_trades: int,
                    risk_pct: float = 0.01, cost_r: float = 0.15) -> dict:
    """
    Compute performance metrics from simulation output.
    trets: sparse array (0 where no trade), indexed by entry bar.
    risk_pct: fraction of equity risked per trade (default 1%).
    cost_r: spread/commission cost in R-multiples deducted per trade (default 0.15R).
    """
    _null = {
        "calmar": 0.0, "sharpe": 0.0, "wr": 0.0,
        "total_ret": 0.0, "max_dd": 1.0, "trades": 0, "avg_rr": 0.0,
    }
    if n_trades < 1:
        return _null

    rets = trets[trets != 0.0] - cost_r
    if len(rets) == 0:
        return _null

    # Build equity curve (percent compound)
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

    calmar = total_ret / max_dd if total_ret > 0.0 else total_ret
    mean_r = float(np.mean(rets))
    std_r  = float(np.std(rets))
    sharpe = (mean_r / std_r * float(np.sqrt(max(len(rets), 1)))) if std_r > 1e-10 else 0.0
    wr     = float(np.sum(rets > 0.0)) / len(rets)
    avg_rr = mean_r

    return {
        "calmar": calmar, "sharpe": sharpe, "wr": wr,
        "total_ret": total_ret, "max_dd": max_dd,
        "trades": int(n_trades), "avg_rr": avg_rr,
    }


def composite_score(m: dict) -> float:
    """60% Calmar + 40% Sharpe (both clipped to >= 0)."""
    return max(m["calmar"], 0.0) * 0.6 + max(m["sharpe"], 0.0) * 0.4


# ===========================================================================
#  Dispatcher + Signal Prep
# ===========================================================================

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


def _prep_signal(cfg: dict, registry: dict,
                 close: np.ndarray, ema200: np.ndarray,
                 adx: np.ndarray) -> np.ndarray:
    """Apply EMA and ADX filters to base signal."""
    sig = registry[cfg["signal"]].copy()
    if cfg["ema_filter"] > 0:
        sig = apply_ema_filter(sig, close, ema200)
    if cfg["adx_thresh"] > 0:
        sig = apply_adx_filter(sig, adx, float(cfg["adx_thresh"]))
    return sig


# ===========================================================================
#  Cross-Validation Sweep  (all configs × all folds — OOS aggregation)
# ===========================================================================

def run_sweep(
    df:       pd.DataFrame,
    atr:      np.ndarray,
    adx:      np.ndarray,
    ema200:   np.ndarray,
    registry: dict,
    folds:    list,
    configs:  list,
    min_oos_trades:  int = 10,
    min_valid_folds: int = 3,
) -> List[Dict]:
    """
    For every config × every fold: compute IS + OOS metrics.
    Aggregate OOS results across all folds.
    Returns list of result dicts, one per viable config.
    """
    h = df["high"].values; l = df["low"].values; c = df["close"].values
    n_cfg = len(configs); n_fld = len(folds)
    print(f"  Grid: {n_cfg} configs × {n_fld} folds = {n_cfg * n_fld:,} simulations")

    # Cache filtered signals: (signal, ema_filter, adx_thresh) -> ndarray
    sig_cache: Dict[tuple, np.ndarray] = {}

    def get_sig(cfg) -> np.ndarray:
        key = (cfg["signal"], cfg["ema_filter"], cfg["adx_thresh"])
        if key not in sig_cache:
            sig_cache[key] = _prep_signal(cfg, registry, c, ema200, adx)
        return sig_cache[key]

    results  = []
    t0       = time.time()

    for ci, cfg in enumerate(configs):
        fsig = get_sig(cfg)
        fold_data = []

        for fi, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
            # IS
            tr_rets, n_tr = _simulate(
                cfg, h[tr_s:tr_e], l[tr_s:tr_e], c[tr_s:tr_e],
                fsig[tr_s:tr_e], atr[tr_s:tr_e],
            )
            is_m = compute_metrics(tr_rets, n_tr) if n_tr >= 5 else None

            # OOS
            te_rets, n_te = _simulate(
                cfg, h[te_s:te_e], l[te_s:te_e], c[te_s:te_e],
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

        # Aggregate across valid OOS folds
        valid = [r for r in fold_data if r["oos_m"] is not None]
        if len(valid) < min_valid_folds:
            continue

        all_oos: List[float] = []
        for r in fold_data:
            nz = r["oos_rets"][r["oos_rets"] != 0.0]
            all_oos.extend(nz.tolist())

        if len(all_oos) < min_oos_trades:
            continue

        agg_arr  = np.array(all_oos, dtype=np.float64)
        agg_m    = compute_metrics(agg_arr, len(all_oos))
        agg_comp = composite_score(agg_m)

        avg_wr     = float(np.mean([r["oos_m"]["wr"]     for r in valid]))
        avg_calmar = float(np.mean([r["oos_m"]["calmar"] for r in valid]))
        avg_sharpe = float(np.mean([r["oos_m"]["sharpe"] for r in valid]))

        results.append({
            "cfg":              cfg,
            "valid_folds":      len(valid),
            "total_oos_trades": len(all_oos),
            "avg_wr":           avg_wr,
            "avg_calmar":       avg_calmar,
            "avg_sharpe":       avg_sharpe,
            "agg_calmar":       agg_m["calmar"],
            "agg_sharpe":       agg_m["sharpe"],
            "agg_total_ret":    agg_m["total_ret"],
            "agg_max_dd":       agg_m["max_dd"],
            "agg_avg_rr":       agg_m["avg_rr"],
            "composite":        agg_comp,
            "oos_rets":         all_oos,
            "fold_data":        fold_data,
        })

        if (ci + 1) % 100 == 0:
            best_c = max((r["composite"] for r in results), default=0.0)
            print(f"    [{ci + 1}/{n_cfg}] processed | "
                  f"viable={len(results)} | best_comp={best_c:.3f} | "
                  f"{time.time() - t0:.0f}s elapsed")

    # Deduplicate: keep best composite per unique parameter combination
    # (wait_candles alone doesn't define a different strategy)
    seen: Dict[tuple, Dict] = {}
    for r in results:
        cfg = r["cfg"]
        key = (cfg["signal"], cfg["mode"], cfg["sl_mult"],
               cfg["rr"], cfg["ema_filter"], cfg["adx_thresh"])
        if key not in seen or r["composite"] > seen[key]["composite"]:
            seen[key] = r
    results = list(seen.values())

    print(f"\n  Sweep done in {time.time() - t0:.1f}s | "
          f"{len(results)} unique viable configs found")
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
    min_is_trades:  int = 5,
    min_oos_trades: int = 10,
) -> Tuple[List[Dict], np.ndarray, List]:
    """
    For each fold:
      1. Grid-search on IS data → best config by composite score.
      2. Evaluate best config on OOS data.
      3. Stitch OOS equity curves together (compounding).
    Returns (fold_results, equity_array, oos_trade_rets_lists).
    """
    h = df["high"].values; l = df["low"].values; c = df["close"].values

    sig_cache: Dict[tuple, np.ndarray] = {}

    def get_sig(cfg) -> np.ndarray:
        key = (cfg["signal"], cfg["ema_filter"], cfg["adx_thresh"])
        if key not in sig_cache:
            sig_cache[key] = _prep_signal(cfg, registry, c, ema200, adx)
        return sig_cache[key]

    fold_results   = []
    equity_pieces  = []   # list of relative equity arrays (each starts at 1.0)
    oos_trade_list = []   # per-fold list of float trade returns

    for fi, (tr_s, tr_e, te_s, te_e) in enumerate(folds):
        print(
            f"\n  [WFO Fold {fi + 1}/{len(folds)}]"
            f"  Train: {df.index[tr_s].date()} → {df.index[tr_e - 1].date()}"
            f"  | OOS: {df.index[te_s].date()} → {df.index[te_e - 1].date()}"
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
            if is_m["wr"] < 0.35:          # pre-filter: IS WR >= 35%
                continue
            sc = composite_score(is_m)
            if sc > best_score:
                best_score = sc; best_cfg = cfg; best_is_m = is_m

        if best_cfg is None:
            print(f"    [!] No valid IS config — fold skipped.")
            continue

        # OOS evaluation with IS-best config
        fsig = get_sig(best_cfg)
        te_rets, n_te = _simulate(
            best_cfg, h[te_s:te_e], l[te_s:te_e], c[te_s:te_e],
            fsig[te_s:te_e], atr[te_s:te_e],
        )
        oos_m = compute_metrics(te_rets, n_te) if n_te >= min_oos_trades else None

        nz = te_rets[te_rets != 0.0]

        # Build relative equity for this OOS period
        eq    = np.ones(len(nz) + 1)
        for j in range(len(nz)):
            eq[j + 1] = eq[j] * (1.0 + 0.01 * nz[j])

        tag_is  = (f"IS  Score={best_score:.3f} | WR={best_is_m['wr']*100:.1f}% | "
                   f"Calmar={best_is_m['calmar']:.2f}")
        if oos_m:
            tag_oos = (f"WR={oos_m['wr']*100:.1f}% | Calmar={oos_m['calmar']:.2f} | "
                       f"Ret={oos_m['total_ret']*100:.1f}% | [{oos_m['trades']}T]")
        else:
            tag_oos = f"(only {n_te} OOS trades, below min={min_oos_trades})"

        print(f"    Best cfg : {best_cfg['signal']} | {best_cfg['mode']} | "
              f"SL={best_cfg['sl_mult']} RR={best_cfg['rr']} "
              f"EMA={best_cfg['ema_filter']} ADX={best_cfg['adx_thresh']}")
        print(f"    {tag_is}")
        print(f"    OOS      : {tag_oos}")

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
        scaled = eq_piece * running         # scale relative piece to running level
        combined.extend(scaled[1:].tolist())
        running = combined[-1]

    return fold_results, np.array(combined), oos_trade_list
