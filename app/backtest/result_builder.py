from __future__ import annotations

from typing import Any

import numpy as np

from app.backtest.metrics import score_candidate, score_dense_candidate


def _compute_rr(tp: float, sl: float) -> float:
    if sl <= 0:
        return float("nan")
    return tp / sl


def _compute_realized_rr(avg_win: float, avg_loss: float) -> float:
    if np.isnan(avg_win) or np.isnan(avg_loss) or avg_loss >= 0:
        return float("nan")
    return avg_win / abs(avg_loss)


def _compute_ambiguous_rate(ambiguous_trades: int, trades: int) -> float:
    if trades == 0:
        return float("nan")
    return ambiguous_trades / trades * 100.0


def _compute_liquidation_rate(liquidated_trades: int, trades: int) -> float:
    if trades == 0:
        return float("nan")
    return liquidated_trades / trades * 100.0


def compute_stability_score(
    neighbor_count: int,
    neighbor_pass_count: int,
    neighbor_avg_test_profit_factor: float,
    neighbor_avg_test_win_rate: float,
    neighbor_avg_max_drawdown: float,
) -> float:
    if neighbor_count <= 0:
        return 0.0
    pass_rate = neighbor_pass_count / neighbor_count
    score = pass_rate * 100.0
    if not np.isnan(neighbor_avg_test_profit_factor):
        score += 12.0 * max(min(neighbor_avg_test_profit_factor, 2.5) - 1.0, 0.0)
    if not np.isnan(neighbor_avg_test_win_rate):
        score += 0.20 * max(neighbor_avg_test_win_rate - 50.0, 0.0)
    if not np.isnan(neighbor_avg_max_drawdown):
        score -= 0.35 * min(abs(neighbor_avg_max_drawdown), 80.0)
    return float(max(0.0, min(score, 100.0)))


def compute_robustness_fields(row: dict[str, Any]) -> dict[str, Any]:
    pf = float(row.get("profit_factor", np.nan))
    test_pf = float(row.get("test_profit_factor", np.nan))
    wr = float(row.get("win_rate", np.nan))
    test_wr = float(row.get("test_win_rate", np.nan))
    trades = int(row.get("trades", 0))
    test_trades = int(row.get("test_trades", 0))
    max_gap = float(row.get("max_gap_days", np.nan))
    test_gap = float(row.get("test_max_gap_days", np.nan))
    total_return = float(row.get("total_return", np.nan))
    max_drawdown = float(row.get("max_drawdown", np.nan))
    stability = float(row.get("stability_score", 0.0) or 0.0)
    neighbor_count = int(row.get("neighbor_count", 0) or 0)

    pf_gap = abs(pf - test_pf) if np.isfinite(pf) and np.isfinite(test_pf) else float("nan")
    wr_gap = abs(wr - test_wr) if np.isfinite(wr) and np.isfinite(test_wr) else float("nan")
    flags: list[str] = []
    risk = 0.0

    if trades < 30:
        flags.append("low_full_trades")
        risk += 15.0
    if test_trades < 10:
        flags.append("low_test_trades")
        risk += 20.0
    if (np.isfinite(max_gap) and max_gap > 21.0) or (np.isfinite(test_gap) and test_gap > 21.0):
        flags.append("high_max_gap")
        risk += 15.0
    if neighbor_count > 0 and stability < 45.0:
        flags.append("unstable_neighbors")
        risk += 25.0
    if np.isfinite(pf_gap) and pf_gap > 1.0:
        flags.append("large_full_test_pf_gap")
        risk += min(pf_gap * 12.0, 25.0)
    if np.isfinite(wr_gap) and wr_gap > 20.0:
        flags.append("large_full_test_winrate_gap")
        risk += min(wr_gap * 0.8, 20.0)
    if np.isfinite(total_return) and np.isfinite(max_drawdown) and total_return > 100.0 and abs(max_drawdown) > 35.0:
        flags.append("high_return_bad_drawdown")
        risk += 15.0
    if np.isfinite(test_wr) and np.isfinite(test_pf) and test_wr >= 70.0 and test_pf < 1.4:
        flags.append("high_winrate_low_pf")
        risk += 15.0
    if np.isfinite(pf) and np.isfinite(test_pf) and test_pf + 0.5 < pf:
        flags.append("test_weaker_than_full")
        risk += 15.0

    return {
        "robustness_flags": ",".join(flags),
        "full_test_pf_gap": pf_gap,
        "full_test_winrate_gap": wr_gap,
        "overfit_risk_score": float(min(risk, 100.0)),
    }


def update_normal_score(row: dict[str, Any]) -> None:
    robustness = compute_robustness_fields(row)
    row.update(robustness)
    row["score"] = score_candidate(
        float(row["win_rate"]),
        float(row["total_return"]),
        float(row["profit_factor"]),
        float(row["expectancy"]),
        float(row["max_drawdown"]),
        int(row["trades"]),
        float(row["test_win_rate"]),
        float(row["test_total_return"]),
        float(row["test_profit_factor"]),
        float(row["test_expectancy"]),
        test_trades=int(row["test_trades"]),
        trades_per_day=float(row["trades_per_day"]),
        max_gap_days=float(row["max_gap_days"]),
        test_trades_per_day=float(row["test_trades_per_day"]),
        test_max_gap_days=float(row["test_max_gap_days"]),
        stability_score=float(row.get("stability_score", 0.0) or 0.0),
        full_test_pf_gap=float(row.get("full_test_pf_gap", 0.0) or 0.0),
        full_test_winrate_gap=float(row.get("full_test_winrate_gap", 0.0) or 0.0),
        overfit_risk_score=float(row.get("overfit_risk_score", 0.0) or 0.0),
    )


def batch_to_normal_rows(
    sl_arr: np.ndarray,
    tp_arr: np.ndarray,
    max_hold_arr: np.ndarray,
    trades_arr: np.ndarray,
    win_rate_arr: np.ndarray,
    total_return_arr: np.ndarray,
    profit_factor_arr: np.ndarray,
    expectancy_arr: np.ndarray,
    max_drawdown_arr: np.ndarray,
    avg_win_arr: np.ndarray,
    avg_loss_arr: np.ndarray,
    trades_per_day_arr: np.ndarray,
    max_gap_days_arr: np.ndarray,
    avg_bars_held_arr: np.ndarray,
    test_trades_arr: np.ndarray,
    test_win_rate_arr: np.ndarray,
    test_total_return_arr: np.ndarray,
    test_profit_factor_arr: np.ndarray,
    test_expectancy_arr: np.ndarray,
    test_trades_per_day_arr: np.ndarray,
    test_max_gap_days_arr: np.ndarray,
    test_avg_bars_held_arr: np.ndarray,
    ambiguous_trades_arr: np.ndarray,
    timeframe: str,
    strategy: str,
    params: str,
    side_mode: str,
    min_full_trades: int,
    min_test_trades: int,
    min_test_win_rate: float,
    min_profit_factor: float,
    min_test_profit_factor: float,
    equity_total_return_arr: np.ndarray | None = None,
    equity_max_drawdown_arr: np.ndarray | None = None,
    final_equity_arr: np.ndarray | None = None,
    liquidated_trades_arr: np.ndarray | None = None,
    include_rr_metrics: bool = True,
    include_ambiguity_metrics: bool = True,
    include_equity_metrics: bool = True,
    include_liquidation_metrics: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c in range(len(sl_arr)):
        trades = trades_arr[c]
        if trades < min_full_trades:
            continue

        total_ret = total_return_arr[c]
        pf = profit_factor_arr[c]
        exp = expectancy_arr[c]
        if total_ret <= 0 or pf < min_profit_factor or exp <= 0:
            continue

        test_trades = test_trades_arr[c]
        test_ret = test_total_return_arr[c]
        test_pf = test_profit_factor_arr[c]
        test_exp = test_expectancy_arr[c]
        test_wr = test_win_rate_arr[c]
        if (
            test_trades < min_test_trades
            or test_ret <= 0
            or test_pf < min_test_profit_factor
            or test_exp <= 0
            or test_wr < min_test_win_rate
        ):
            continue

        wr = win_rate_arr[c]
        mdd = max_drawdown_arr[c]
        aw = avg_win_arr[c]
        al = avg_loss_arr[c]
        sl_val = float(sl_arr[c])
        tp_val = float(tp_arr[c])
        ambiguous_trades = int(ambiguous_trades_arr[c])
        eq_tr = float(equity_total_return_arr[c]) if equity_total_return_arr is not None else float("nan")
        eq_mdd = float(equity_max_drawdown_arr[c]) if equity_max_drawdown_arr is not None else float("nan")
        fin_eq = float(final_equity_arr[c]) if final_equity_arr is not None else float("nan")
        liq_tr = int(liquidated_trades_arr[c]) if liquidated_trades_arr is not None else 0

        row = {
            "timeframe": timeframe,
            "strategy": strategy,
            "params": params,
            "side_mode": side_mode,
            "sl": sl_val,
            "tp": tp_val,
            "max_hold": int(max_hold_arr[c]),
            "trades": trades,
            "win_rate": wr,
            "total_return": total_ret,
            "profit_factor": pf,
            "expectancy": exp,
            "max_drawdown": mdd,
            "avg_win": aw,
            "avg_loss": al,
            "trades_per_day": float(trades_per_day_arr[c]),
            "max_gap_days": float(max_gap_days_arr[c]),
            "avg_bars_held": float(avg_bars_held_arr[c]),
            "test_trades": test_trades,
            "test_win_rate": test_wr,
            "test_total_return": test_ret,
            "test_profit_factor": test_pf,
            "test_expectancy": test_exp,
            "test_trades_per_day": float(test_trades_per_day_arr[c]),
            "test_max_gap_days": float(test_max_gap_days_arr[c]),
            "test_avg_bars_held": float(test_avg_bars_held_arr[c]),
            "stability_score": 0.0,
            "neighbor_count": 0,
            "neighbor_pass_count": 0,
            "neighbor_pass_rate": 0.0,
            "neighbor_avg_profit_factor": float("nan"),
            "neighbor_avg_test_profit_factor": float("nan"),
            "neighbor_avg_test_win_rate": float("nan"),
            "neighbor_avg_max_drawdown": float("nan"),
            "score": 0.0,
        }
        update_normal_score(row)
        if include_rr_metrics:
            row["rr"] = _compute_rr(tp_val, sl_val)
            row["realized_rr"] = _compute_realized_rr(aw, al)
        if include_ambiguity_metrics:
            row["ambiguous_trades"] = ambiguous_trades
            row["ambiguous_rate"] = _compute_ambiguous_rate(ambiguous_trades, trades)
        if include_equity_metrics:
            row["equity_total_return"] = eq_tr
            row["equity_max_drawdown"] = eq_mdd
            row["final_equity"] = fin_eq
        if include_liquidation_metrics:
            row["liquidated_trades"] = liq_tr
            row["liquidation_rate"] = _compute_liquidation_rate(liq_tr, trades)
        rows.append(row)
    return rows


def batch_to_dense_rows(
    sl_arr: np.ndarray,
    tp_arr: np.ndarray,
    max_hold_arr: np.ndarray,
    trades_arr: np.ndarray,
    win_rate_arr: np.ndarray,
    total_return_arr: np.ndarray,
    profit_factor_arr: np.ndarray,
    expectancy_arr: np.ndarray,
    max_drawdown_arr: np.ndarray,
    avg_win_arr: np.ndarray,
    avg_loss_arr: np.ndarray,
    trades_per_day_arr: np.ndarray,
    max_gap_days_arr: np.ndarray,
    avg_bars_held_arr: np.ndarray,
    test_trades_arr: np.ndarray,
    test_win_rate_arr: np.ndarray,
    test_total_return_arr: np.ndarray,
    test_profit_factor_arr: np.ndarray,
    test_expectancy_arr: np.ndarray,
    test_trades_per_day_arr: np.ndarray,
    test_max_gap_days_arr: np.ndarray,
    test_avg_bars_held_arr: np.ndarray,
    ambiguous_trades_arr: np.ndarray,
    timeframe: str,
    strategy: str,
    params: str,
    side_mode: str,
    min_trades: int,
    min_win_rate: float,
    min_test_trades: int,
    min_test_win_rate: float,
    equity_total_return_arr: np.ndarray | None = None,
    equity_max_drawdown_arr: np.ndarray | None = None,
    final_equity_arr: np.ndarray | None = None,
    liquidated_trades_arr: np.ndarray | None = None,
    include_rr_metrics: bool = True,
    include_ambiguity_metrics: bool = True,
    include_equity_metrics: bool = True,
    include_liquidation_metrics: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c in range(len(sl_arr)):
        trades = trades_arr[c]
        wr = win_rate_arr[c]
        total_ret = total_return_arr[c]
        pf = profit_factor_arr[c]
        exp = expectancy_arr[c]
        if (
            trades < min_trades
            or wr < min_win_rate
            or total_ret <= 0
            or pf < 1.0
            or exp <= 0
        ):
            continue

        test_trades = test_trades_arr[c]
        test_wr = test_win_rate_arr[c]
        test_ret = test_total_return_arr[c]
        test_pf = test_profit_factor_arr[c]
        test_exp = test_expectancy_arr[c]
        if (
            test_trades < min_test_trades
            or test_wr < min_test_win_rate
            or test_ret <= 0
            or test_pf < 1.0
            or test_exp <= 0
        ):
            continue

        mdd = max_drawdown_arr[c]
        tpd = trades_per_day_arr[c]
        test_tpd = test_trades_per_day_arr[c]

        score_row = {
            "win_rate": wr,
            "profit_factor": pf,
            "expectancy": exp,
            "test_win_rate": test_wr,
            "test_total_return": test_ret,
            "test_profit_factor": test_pf,
            "test_expectancy": test_exp,
            "max_drawdown": mdd,
            "test_trades_per_day": test_tpd,
        }
        score = score_dense_candidate(score_row)
        sl_val = float(sl_arr[c])
        tp_val = float(tp_arr[c])
        aw = avg_win_arr[c]
        al = avg_loss_arr[c]
        ambiguous_trades = int(ambiguous_trades_arr[c])
        eq_tr = float(equity_total_return_arr[c]) if equity_total_return_arr is not None else float("nan")
        eq_mdd = float(equity_max_drawdown_arr[c]) if equity_max_drawdown_arr is not None else float("nan")
        fin_eq = float(final_equity_arr[c]) if final_equity_arr is not None else float("nan")
        liq_tr = int(liquidated_trades_arr[c]) if liquidated_trades_arr is not None else 0

        row = {
            "timeframe": timeframe,
            "strategy": strategy,
            "params": params,
            "side_mode": side_mode,
            "sl": sl_val,
            "tp": tp_val,
            "max_hold": int(max_hold_arr[c]),
            "trades": trades,
            "win_rate": wr,
            "total_return": total_ret,
            "profit_factor": pf,
            "expectancy": exp,
            "max_drawdown": mdd,
            "avg_win": aw,
            "avg_loss": al,
            "trades_per_day": tpd,
            "max_gap_days": float(max_gap_days_arr[c]),
            "avg_bars_held": float(avg_bars_held_arr[c]),
            "test_trades": test_trades,
            "test_win_rate": test_wr,
            "test_total_return": test_ret,
            "test_profit_factor": test_pf,
            "test_expectancy": test_exp,
            "test_trades_per_day": test_tpd,
            "test_max_gap_days": float(test_max_gap_days_arr[c]),
            "test_avg_bars_held": float(test_avg_bars_held_arr[c]),
            "score": score,
        }
        if include_rr_metrics:
            row["rr"] = _compute_rr(tp_val, sl_val)
            row["realized_rr"] = _compute_realized_rr(aw, al)
        if include_ambiguity_metrics:
            row["ambiguous_trades"] = ambiguous_trades
            row["ambiguous_rate"] = _compute_ambiguous_rate(ambiguous_trades, trades)
        if include_equity_metrics:
            row["equity_total_return"] = eq_tr
            row["equity_max_drawdown"] = eq_mdd
            row["final_equity"] = fin_eq
        if include_liquidation_metrics:
            row["liquidated_trades"] = liq_tr
            row["liquidation_rate"] = _compute_liquidation_rate(liq_tr, trades)
        rows.append(row)
    return rows
