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
) -> float:
    if np.isnan(win_rate) or np.isnan(test_win_rate) or np.isnan(expectancy) or np.isnan(test_expectancy):
        return -np.inf
    return (
        0.55 * win_rate
        + 0.75 * test_win_rate
        + 10.0 * min(profit_factor, 4.0)
        + 14.0 * min(test_profit_factor, 4.0)
        + 0.10 * total_return
        + 0.18 * test_total_return
        + 50.0 * max(expectancy, -0.5)
        + 65.0 * max(test_expectancy, -0.5)
        - 0.45 * abs(max_drawdown)
        + min(trades, 800) / 100.0
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
