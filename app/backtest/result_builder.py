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
        score = score_candidate(wr, total_ret, pf, exp, mdd, trades, test_wr, test_ret, test_pf, test_exp)
        sl_val = float(sl_arr[c])
        tp_val = float(tp_arr[c])
        ambiguous_trades = int(ambiguous_trades_arr[c])
        eq_tr = float(equity_total_return_arr[c]) if equity_total_return_arr is not None else float("nan")
        eq_mdd = float(equity_max_drawdown_arr[c]) if equity_max_drawdown_arr is not None else float("nan")
        fin_eq = float(final_equity_arr[c]) if final_equity_arr is not None else float("nan")
        liq_tr = int(liquidated_trades_arr[c]) if liquidated_trades_arr is not None else 0

        rows.append(
            {
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
                "rr": _compute_rr(tp_val, sl_val),
                "realized_rr": _compute_realized_rr(aw, al),
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
                "ambiguous_trades": ambiguous_trades,
                "ambiguous_rate": _compute_ambiguous_rate(ambiguous_trades, trades),
                "equity_total_return": eq_tr,
                "equity_max_drawdown": eq_mdd,
                "final_equity": fin_eq,
                "liquidated_trades": liq_tr,
                "liquidation_rate": _compute_liquidation_rate(liq_tr, trades),
                "score": score,
            }
        )
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

        rows.append(
            {
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
                "rr": _compute_rr(tp_val, sl_val),
                "realized_rr": _compute_realized_rr(aw, al),
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
                "ambiguous_trades": ambiguous_trades,
                "ambiguous_rate": _compute_ambiguous_rate(ambiguous_trades, trades),
                "equity_total_return": eq_tr,
                "equity_max_drawdown": eq_mdd,
                "final_equity": fin_eq,
                "liquidated_trades": liq_tr,
                "liquidation_rate": _compute_liquidation_rate(liq_tr, trades),
                "score": score,
            }
        )
    return rows
