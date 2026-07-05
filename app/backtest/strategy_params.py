from __future__ import annotations

STRATEGY_PARAM_SCHEMAS: dict[str, dict] = {
    "EMA_PULLBACK": {
        "fast": {"type": "select", "default": ["34", "50"], "options": ["34", "50"]},
        "trend": {"type": "select", "default": ["ema200"], "options": ["none", "ema200"]},
        "rsi_lo": {"type": "range", "default": [40, 45], "min": 20, "max": 50, "step": 5},
        "rsi_hi": {"type": "range", "default": [55, 60], "min": 50, "max": 80, "step": 5},
        "adx_min": {"type": "range", "default": [12, 18], "min": 5, "max": 40, "step": 1},
        "atr_mult": {"type": "range", "default": [0.60, 0.90], "min": 0.1, "max": 2.0, "step": 0.05},
        "use_vol": {"type": "select", "default": ["false"], "options": ["true", "false"]},
    },
    "DONCHIAN_BREAKOUT": {
        "window": {"type": "select", "default": ["40", "80"], "options": ["40", "80"]},
        "trend": {"type": "select", "default": ["ema200"], "options": ["none", "ema200"]},
        "adx_min": {"type": "range", "default": [18, 24], "min": 5, "max": 40, "step": 1},
        "use_vol": {"type": "select", "default": ["false"], "options": ["true", "false"]},
    },
    "BB_RSI_REVERT": {
        "window": {"type": "select", "default": ["20", "40"], "options": ["20", "40"]},
        "z": {"type": "select", "default": ["2.0", "2.4"], "options": ["2.0", "2.4"]},
        "rsi_lo": {"type": "range", "default": [25, 30], "min": 10, "max": 50, "step": 5},
        "rsi_hi": {"type": "range", "default": [70, 75], "min": 50, "max": 90, "step": 5},
        "trend_mode": {"type": "select", "default": ["trend", "range"], "options": ["trend", "counter", "range"]},
        "adx_max": {"type": "select", "default": ["none", "24"], "options": ["none", "24"]},
    },
    "IBS_REVERT": {
        "ibs_lo": {"type": "select", "default": ["0.05", "0.10", "0.20"], "options": ["0.05", "0.10", "0.20"]},
        "ibs_hi": {"type": "select", "default": ["0.80", "0.90", "0.95"], "options": ["0.80", "0.90", "0.95"]},
        "trend_mode": {"type": "select", "default": ["trend", "range"], "options": ["trend", "counter", "range"]},
        "adx_max": {"type": "select", "default": ["none", "24"], "options": ["none", "24"]},
    },
    "VOL_EXPANSION_CONT": {
        "range_mult": {"type": "range", "default": [0.8, 2.0], "min": 0.5, "max": 3.0, "step": 0.1},
        "trend": {"type": "select", "default": ["none", "ema100", "ema200"], "options": ["auto", "none", "ema20", "ema50", "ema100", "ema200", "ema300"]},
        "adx_min": {"type": "range", "default": [8, 24], "min": 5, "max": 40, "step": 1},
        "close_extreme": {"type": "range", "default": [0.60, 0.85], "min": 0.5, "max": 1.0, "step": 0.05},
        "body_min": {"type": "range", "default": [0.45, 0.55], "min": 0.3, "max": 0.7, "step": 0.05},
    },
    "SUPERTREND": {
        "period": {"type": "select", "default": ["10", "14", "20"], "options": ["10", "14", "20"]},
        "mult": {"type": "select", "default": ["2.0", "3.0", "4.0"], "options": ["2.0", "3.0", "4.0"]},
        "trend": {"type": "select", "default": ["none", "ema200"], "options": ["none", "ema200"]},
    },
    "MACD_CROSS": {
        "preset": {"type": "select", "default": ["8/21/5", "12/26/9", "5/34/5"], "options": ["8/21/5", "12/26/9", "5/34/5"]},
        "trend": {"type": "select", "default": ["none", "ema200"], "options": ["none", "ema200"]},
        "adx_min": {"type": "range", "default": [12, 18], "min": 5, "max": 40, "step": 1},
    },
    "WAVETREND": {
        "preset": {"type": "select", "default": ["10/21", "10/11", "14/21"], "options": ["10/21", "10/11", "14/21"]},
        "ob_os": {"type": "select", "default": ["53/-53", "60/-60"], "options": ["53/-53", "60/-60"]},
        "trend_mode": {"type": "select", "default": ["trend", "range"], "options": ["trend", "counter", "range"]},
    },
    "SQUEEZE_MOM": {
        "length": {"type": "select", "default": ["20", "30"], "options": ["20", "30"]},
        "bb_mult": {"type": "select", "default": ["2.0"], "options": ["2.0"]},
        "kc_mult": {"type": "select", "default": ["1.5", "2.0"], "options": ["1.5", "2.0"]},
        "trend": {"type": "select", "default": ["none", "ema200"], "options": ["none", "ema200"]},
    },
    "WILLIAMS_VIX_FIX": {
        "pd_len": {"type": "select", "default": ["22", "30"], "options": ["22", "30"]},
        "bbl": {"type": "select", "default": ["20"], "options": ["20"]},
        "ph": {"type": "select", "default": ["0.85", "0.90"], "options": ["0.85", "0.90"]},
        "trend_mode": {"type": "select", "default": ["trend", "range"], "options": ["trend", "counter", "range"]},
    },
}

GRID_PARAM_SCHEMA: dict[str, dict] = {
    "sl_values": {"type": "csv", "default": [0.02, 0.03, 0.04, 0.06, 0.08]},
    "tp_values": {"type": "csv", "default": [0.005, 0.0075, 0.01, 0.015, 0.02, 0.03]},
    "max_holds": {"type": "csv", "default": [16, 32, 64, 96]},
    "min_trades_per_day": {"type": "number", "default": 0.33, "min": 0.1, "max": 5.0},
    "min_test_trades_per_day": {"type": "number", "default": 0.33, "min": 0.1, "max": 5.0},
}


def get_default_params(strategy_name: str) -> dict[str, list]:
    schema = STRATEGY_PARAM_SCHEMAS.get(strategy_name, {})
    return {k: list(v["default"]) for k, v in schema.items()}
