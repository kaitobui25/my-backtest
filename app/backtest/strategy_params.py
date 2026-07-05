from __future__ import annotations

STRATEGY_PARAM_SCHEMAS: dict[str, dict] = {
    "VOL_EXPANSION_CONT": {
        "range_mult": {"type": "range", "default": [0.8, 2.0], "min": 0.5, "max": 3.0, "step": 0.1},
        "trend": {"type": "select", "default": ["none", "ema100", "ema200"], "options": ["none", "ema100", "ema200"]},
        "adx_min": {"type": "range", "default": [8, 24], "min": 5, "max": 40, "step": 1},
        "close_extreme": {"type": "range", "default": [0.60, 0.85], "min": 0.5, "max": 1.0, "step": 0.05},
        "body_min": {"type": "range", "default": [0.45, 0.55], "min": 0.3, "max": 0.7, "step": 0.05},
    },
}

VOL_EXPANSION_CONT_DEFAULTS: dict[str, list] = {
    "range_mult": [0.8, 2.0],
    "trend": ["none", "ema100", "ema200"],
    "adx_min": [8, 24],
    "close_extreme": [0.60, 0.85],
    "body_min": [0.45, 0.55],
}

GRID_PARAM_SCHEMA: dict[str, dict] = {
    "sl_values": {"type": "csv", "default": [0.02, 0.03, 0.04, 0.06, 0.08]},
    "tp_values": {"type": "csv", "default": [0.005, 0.0075, 0.01, 0.015, 0.02, 0.03]},
    "max_holds": {"type": "csv", "default": [16, 32, 64, 96]},
    "min_trades_per_day": {"type": "number", "default": 0.33, "min": 0.1, "max": 5.0},
    "min_test_trades_per_day": {"type": "number", "default": 0.33, "min": 0.1, "max": 5.0},
}
