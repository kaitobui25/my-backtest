from __future__ import annotations

import pandas as pd


SYMBOL = "BTCUSD"
TEST_START = pd.Timestamp("2025-01-01")

# Current BTCUSD MT5 spread observed near 48 USD on 73,600 USD BTC, roughly 0.065% round trip.
# Use a slightly rounded conservative cost model. Change this before running if broker terms differ.
FEE_PER_SIDE = 0.00035

NORMAL_TIMEFRAMES = ["M15", "M30", "H1", "H4", "D1"]
DENSE_TIMEFRAMES = ["M15", "M30", "H1", "H2", "H4"]

MIN_FULL_TRADES = {
    "M15": 80,
    "M30": 70,
    "H1": 55,
    "H2": 40,
    "H4": 28,
    "D1": 12,
}

MIN_TEST_TRADES = {
    "M15": 20,
    "M30": 18,
    "H1": 14,
    "H2": 10,
    "H4": 7,
    "D1": 4,
}

DENSE_MIN_WIN_RATE = 75.0
DENSE_MIN_TEST_WIN_RATE = 75.0
DENSE_MIN_TRADES_PER_DAY = 0.33
DENSE_MIN_TEST_TRADES_PER_DAY = 0.33

REQUIRED_COLUMNS = [
    "timeframe",
    "strategy",
    "params",
    "side_mode",
    "sl",
    "tp",
    "max_hold",
    "trades",
    "win_rate",
    "total_return",
    "profit_factor",
    "expectancy",
    "max_drawdown",
    "avg_win",
    "avg_loss",
    "rr",
    "realized_rr",
    "test_trades",
    "test_win_rate",
    "test_total_return",
    "test_profit_factor",
    "test_expectancy",
    "trades_per_day",
    "max_gap_days",
    "avg_bars_held",
    "test_trades_per_day",
    "test_max_gap_days",
    "test_avg_bars_held",
    "ambiguous_trades",
    "ambiguous_rate",
    "equity_total_return",
    "equity_max_drawdown",
    "final_equity",
    "liquidated_trades",
    "score",
]


def normal_grid_for_timeframe(timeframe: str) -> tuple[list[float], list[float], list[int]]:
    if timeframe in {"M15", "M30"}:
        return (
            [0.010, 0.020, 0.040, 0.060],
            [0.005, 0.010, 0.020, 0.030],
            [48, 96, 0],
        )
    if timeframe == "H1":
        return (
            [0.015, 0.030, 0.060, 0.100],
            [0.0075, 0.015, 0.030, 0.050],
            [24, 72, 0],
        )
    if timeframe == "H4":
        return (
            [0.020, 0.040, 0.080, 0.140],
            [0.010, 0.020, 0.050, 0.100],
            [6, 18, 0],
        )
    return (
        [0.030, 0.060, 0.120, 0.180],
        [0.015, 0.030, 0.080, 0.120],
        [5, 10, 0],
    )


def dense_grid_for_timeframe(timeframe: str) -> tuple[list[float], list[float], list[int]]:
    if timeframe == "M15":
        return (
            [0.020, 0.030, 0.040, 0.060, 0.080],
            [0.0050, 0.0075, 0.0100, 0.0150, 0.0200, 0.0300],
            [16, 32, 64, 96],
        )
    if timeframe == "M30":
        return (
            [0.020, 0.030, 0.040, 0.060, 0.080],
            [0.0050, 0.0075, 0.0100, 0.0150, 0.0200, 0.0300],
            [8, 16, 32, 48],
        )
    return (
        [0.020, 0.030, 0.040, 0.060, 0.080, 0.100],
        [0.0050, 0.0075, 0.0100, 0.0150, 0.0200, 0.0300],
        [4, 8, 12, 24],
    )
