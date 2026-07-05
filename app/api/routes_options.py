from __future__ import annotations

from fastapi import APIRouter

from app.backtest.strategy_params import GRID_PARAM_SCHEMA, STRATEGY_PARAM_SCHEMAS


router = APIRouter(prefix="/api", tags=["options"])

TIMEFRAMES = ["M15", "M30", "H1", "H2", "H4", "D1"]
MODES = ["normal", "dense_high_winrate"]
INDICATORS = [
    "EMA_PULLBACK",
    "DONCHIAN_BREAKOUT",
    "BB_RSI_REVERT",
    "IBS_REVERT",
    "VOL_EXPANSION_CONT",
    "SUPERTREND",
    "MACD_CROSS",
    "WAVETREND",
    "SQUEEZE_MOM",
    "WILLIAMS_VIX_FIX",
]
FILTER_FIELDS = [
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
OPERATORS = [">", ">=", "<", "<=", "=", "~"]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/options")
def options() -> dict:
    return {
        "symbols": ["BTCUSD"],
        "timeframes": TIMEFRAMES,
        "modes": MODES,
        "indicators": INDICATORS,
        "filter_fields": FILTER_FIELDS,
        "operators": OPERATORS,
        "strategy_param_schemas": STRATEGY_PARAM_SCHEMAS,
        "grid_param_schema": GRID_PARAM_SCHEMA,
    }
