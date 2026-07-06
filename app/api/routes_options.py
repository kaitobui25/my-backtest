from __future__ import annotations

from fastapi import APIRouter

from app.backtest.config import (
    AMBIGUITY_COLUMNS,
    CORE_COLUMNS,
    EQUITY_COLUMNS,
    LIQUIDATION_COLUMNS,
    RR_COLUMNS,
)
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
FILTER_FIELD_GROUPS = {
    "core": CORE_COLUMNS,
    "rr": RR_COLUMNS,
    "ambiguity": AMBIGUITY_COLUMNS,
    "equity": EQUITY_COLUMNS,
    "liquidation": LIQUIDATION_COLUMNS,
}
FILTER_FIELDS = [
    *CORE_COLUMNS[:-1],
    *RR_COLUMNS,
    *AMBIGUITY_COLUMNS,
    *EQUITY_COLUMNS,
    *LIQUIDATION_COLUMNS,
    *CORE_COLUMNS[-1:],
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
        "filter_field_groups": FILTER_FIELD_GROUPS,
        "operators": OPERATORS,
        "strategy_param_schemas": STRATEGY_PARAM_SCHEMAS,
        "grid_param_schema": GRID_PARAM_SCHEMA,
    }
