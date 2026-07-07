from __future__ import annotations

import numpy as np


def metrics(returns: np.ndarray) -> tuple[int, float, float, float, float, float, float, float]:
    if returns.size == 0:
        return 0, np.nan, 0.0, np.nan, np.nan, np.nan, np.nan, np.nan
    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    equity = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(equity)
    drawdown = np.where(peak > 0, equity / peak - 1, 0)
    gross_profit = wins.sum()
    gross_loss = -losses.sum()
    pf = gross_profit / gross_loss if gross_loss > 0 else np.inf
    return (
        returns.size,
        wins.size / returns.size * 100,
        (equity[-1] - 1) * 100,
        pf,
        returns.mean() * 100,
        drawdown.min() * 100,
        wins.mean() * 100 if wins.size else np.nan,
        losses.mean() * 100 if losses.size else np.nan,
    )


def score_candidate(
    win_rate: float,
    total_return: float,
    profit_factor: float,
    expectancy: float,
    max_drawdown: float,
    trades: int,
    test_win_rate: float,
    test_total_return: float,
    test_profit_factor: float,
    test_expectancy: float,
    test_trades: int = 0,
    trades_per_day: float = 0.0,
    max_gap_days: float = np.inf,
    test_trades_per_day: float = 0.0,
    test_max_gap_days: float = np.inf,
    stability_score: float = 0.0,
    full_test_pf_gap: float = 0.0,
    full_test_winrate_gap: float = 0.0,
    overfit_risk_score: float = 0.0,
) -> float:
    if np.isnan(win_rate) or np.isnan(test_win_rate) or np.isnan(expectancy) or np.isnan(test_expectancy):
        return -np.inf
    pf = min(profit_factor if np.isfinite(profit_factor) else 5.0, 5.0)
    test_pf = min(test_profit_factor if np.isfinite(test_profit_factor) else 5.0, 5.0)
    safe_stability = 0.0 if np.isnan(stability_score) else max(0.0, min(stability_score, 100.0))
    gap_days = max_gap_days if np.isfinite(max_gap_days) else 365.0
    test_gap_days = test_max_gap_days if np.isfinite(test_max_gap_days) else 365.0
    trade_count_quality = min(max(test_trades, 0), 80) / 80.0 * 100.0
    frequency_quality = min(max(test_trades_per_day, trades_per_day, 0.0), 1.0) * 100.0
    capped_total_return = min(max(total_return, -100.0), 300.0)
    capped_test_total_return = min(max(test_total_return, -100.0), 200.0)

    return (
        35.0 * min(test_pf, 3.0)
        + 18.0 * min(pf, 3.0)
        + 0.75 * test_win_rate
        + 0.25 * win_rate
        + 0.12 * capped_test_total_return
        + 0.04 * capped_total_return
        + 45.0 * max(test_expectancy, -0.25)
        + 20.0 * max(expectancy, -0.25)
        + 0.35 * trade_count_quality
        + 0.18 * frequency_quality
        + 0.60 * safe_stability
        - 0.55 * abs(max_drawdown)
        - 1.10 * min(test_gap_days, 90.0)
        - 0.45 * min(gap_days, 90.0)
        - 16.0 * max(full_test_pf_gap, 0.0)
        - 0.70 * max(full_test_winrate_gap, 0.0)
        - 0.85 * max(overfit_risk_score, 0.0)
    )


def score_dense_candidate(row: dict[str, float]) -> float:
    return (
        0.35 * row["win_rate"]
        + 0.65 * row["test_win_rate"]
        + 18.0 * min(row["profit_factor"], 2.0)
        + 28.0 * min(row["test_profit_factor"], 2.0)
        + 45.0 * max(row["expectancy"], -0.1)
        + 75.0 * max(row["test_expectancy"], -0.1)
        + 0.04 * row["test_total_return"]
        - 0.20 * abs(row["max_drawdown"])
        + 2.0 * min(row["test_trades_per_day"], 3.0)
    )
