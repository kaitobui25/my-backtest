from __future__ import annotations

from fastapi import APIRouter


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
    "win_rate",
    "total_return",
    "profit_factor",
    "expectancy",
    "max_drawdown",
    "test_win_rate",
    "test_total_return",
    "test_profit_factor",
    "score",
    "trades_per_day",
    "test_trades_per_day",
]
OPERATORS = [">", ">=", "<", "<=", "=", "~"]


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/options")
def options() -> dict[str, list[str]]:
    return {
        "symbols": ["BTCUSD"],
        "timeframes": TIMEFRAMES,
        "modes": MODES,
        "indicators": INDICATORS,
        "filter_fields": FILTER_FIELDS,
        "operators": OPERATORS,
    }
