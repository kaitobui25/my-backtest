from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.backtest.strategy_params import STRATEGY_PARAM_SCHEMAS, get_default_params
from app.backtest.signals import (
    _expand_range,
    _params_for,
    _resolve_trend_selection,
    build_signals,
    build_signal_variants,
    _build_vol_expansion_dense_signals,
)


ALL_STRATEGIES = [
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

VOL_SMALL_PARAMS = {
    "VOL_EXPANSION_CONT": {
        "range_mult": [0.8],
        "trend": ["none"],
        "adx_min": [8],
        "close_extreme": [0.6],
        "body_min": [0.45],
    }
}


def test_all_strategies_have_schemas():
    for name in ALL_STRATEGIES:
        assert name in STRATEGY_PARAM_SCHEMAS, f"Missing schema for {name}"


def test_schema_defaults_are_valid_lists():
    for name, schema in STRATEGY_PARAM_SCHEMAS.items():
        for param, meta in schema.items():
            default = meta["default"]
            assert isinstance(default, list), f"{name}.{param} default must be a list"
            assert len(default) > 0, f"{name}.{param} default must not be empty"
            if meta["type"] == "range":
                assert len(default) == 2, f"{name}.{param} range default must have 2 elements"
                assert meta["min"] <= default[0] <= meta["max"], f"{name}.{param} default[0] out of range"
                assert meta["min"] <= default[1] <= meta["max"], f"{name}.{param} default[1] out of range"


def test_get_default_params():
    for name in ALL_STRATEGIES:
        defaults = get_default_params(name)
        schema = STRATEGY_PARAM_SCHEMAS[name]
        assert set(defaults.keys()) == set(schema.keys())


def test_params_for_returns_defaults_when_none():
    for name in ALL_STRATEGIES:
        p = _params_for(name, None)
        schema = STRATEGY_PARAM_SCHEMAS[name]
        assert set(p.keys()) == set(schema.keys())


def test_params_for_unknown_params_ignored():
    extra = {"VOL_EXPANSION_CONT": {"range_mult": [0.5, 1.5], "unknown_param": [1, 2, 3]}}
    p = _params_for("VOL_EXPANSION_CONT", extra)
    assert "range_mult" in p
    assert "unknown_param" not in p


def test_params_for_range_expands():
    user = {"EMA_PULLBACK": {"rsi_lo": [30, 40]}}
    p = _params_for("EMA_PULLBACK", user)
    assert p["rsi_lo"] == [30, 35, 40]


def test_params_for_select_preserves():
    user = {"VOL_EXPANSION_CONT": {"trend": ["none", "ema200"]}}
    p = _params_for("VOL_EXPANSION_CONT", user)
    assert p["trend"] == ["none", "ema200"]


def test_expand_range_two_values():
    result = _expand_range([40, 45], 5)
    assert result == [40, 45]


def test_expand_range_many_values():
    result = _expand_range([0.6, 0.9], 0.05)
    assert len(result) == 7
    assert result[0] == 0.6
    assert result[-1] == 0.9


def test_expand_range_single_value():
    result = _expand_range(5, None)
    assert result == [5]


class TestTrendSelection:
    def test_auto_expands_to_all(self):
        result = _resolve_trend_selection(["auto"])
        assert "auto" not in result
        assert "none" in result
        assert "ema20" in result
        assert "ema50" in result
        assert "ema100" in result
        assert "ema200" in result
        assert "ema300" in result

    def test_auto_with_others_merges_deduped(self):
        result = _resolve_trend_selection(["auto", "ema100"])
        assert result.count("ema100") == 1
        assert "none" in result
        assert "ema20" in result
        assert "ema200" in result

    def test_no_auto_keeps_as_is(self):
        result = _resolve_trend_selection(["none", "ema200"])
        assert result == ["none", "ema200"]

    def test_single_trend(self):
        result = _resolve_trend_selection(["ema200"])
        assert result == ["ema200"]


class TestBuildSignals:
    @pytest.fixture
    def df(self):
        n = 300
        np.random.seed(42)
        close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
        close = np.maximum(close, 10.0)
        high = close + np.abs(np.random.randn(n)) * 0.3
        low = close - np.abs(np.random.randn(n)) * 0.3
        open_ = low + np.random.rand(n) * (high - low)
        volume = np.random.randint(1000, 10000, n).astype(float)
        idx = pd.date_range("2020-01-01", periods=n, freq="h")
        return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)

    def test_build_signals_no_strategy_params(self, df):
        for name in ALL_STRATEGIES:
            params = VOL_SMALL_PARAMS if name == "VOL_EXPANSION_CONT" else None
            signals = build_signals(df, "H1", strategy_params=params, strategies={name})
            strategies = set(s for s, _, _, _, _ in signals)
            assert name in strategies, f"Missing {name} in signals"

    def test_build_signals_with_empty_strategy_params(self, df):
        signals = build_signals(df, "H1", strategy_params={}, strategies={"MACD_CROSS"})
        assert len(signals) > 0

    def test_build_signals_with_unknown_strategy_params(self, df):
        signals = build_signals(df, "H1", strategy_params={"UNKNOWN_STRATEGY": {}}, strategies={"MACD_CROSS"})
        assert len(signals) > 0

    def test_build_signals_vol_trend_auto(self, df):
        params = {"VOL_EXPANSION_CONT": {**VOL_SMALL_PARAMS["VOL_EXPANSION_CONT"], "trend": ["auto"]}}
        signals = build_signals(df, "H1", strategy_params=params, strategies={"VOL_EXPANSION_CONT"})
        vol_signals = [s for s in signals if s[0] == "VOL_EXPANSION_CONT"]
        trend_values = set()
        for _, param_str, _, _, _ in vol_signals:
            for part in param_str.split(","):
                if part.startswith("trend="):
                    trend_values.add(part.split("=")[1])
        assert "none" in trend_values
        assert "ema20" in trend_values
        assert "ema200" in trend_values
        assert "ema300" in trend_values

    def test_build_signals_vol_trend_single(self, df):
        params = {"VOL_EXPANSION_CONT": {**VOL_SMALL_PARAMS["VOL_EXPANSION_CONT"], "trend": ["ema200"]}}
        signals = build_signals(df, "H1", strategy_params=params, strategies={"VOL_EXPANSION_CONT"})
        vol_signals = [s for s in signals if s[0] == "VOL_EXPANSION_CONT"]
        trend_values = set()
        for _, param_str, _, _, _ in vol_signals:
            for part in param_str.split(","):
                if part.startswith("trend="):
                    trend_values.add(part.split("=")[1])
        assert trend_values == {"ema200"}

    def test_build_signals_ema_pullback_custom_rsi(self, df):
        params = {"EMA_PULLBACK": {"rsi_lo": [35, 40]}}
        signals = build_signals(df, "H1", strategy_params=params)
        ep_signals = [s for s in signals if s[0] == "EMA_PULLBACK"]
        assert len(ep_signals) > 0

    def test_build_signal_variants_normal_filters_strategies(self, df):
        variants = build_signal_variants(
            df,
            "H1",
            mode="normal",
            strategies=["VOL_EXPANSION_CONT"],
            strategy_params=VOL_SMALL_PARAMS,
        )
        assert all(v.strategy == "VOL_EXPANSION_CONT" for v in variants)

    def test_build_signal_variants_dense_vol(self, df):
        variants = build_signal_variants(
            df,
            "H1",
            mode="dense_high_winrate",
            strategies=["VOL_EXPANSION_CONT"],
            strategy_params=VOL_SMALL_PARAMS,
        )
        assert len(variants) > 0
        assert all(v.strategy == "VOL_EXPANSION_CONT" for v in variants)

    def test_dense_vol_accepts_strategy_params(self, df):
        params = {"VOL_EXPANSION_CONT": {**VOL_SMALL_PARAMS["VOL_EXPANSION_CONT"], "trend": ["auto"]}}
        dense_signals = _build_vol_expansion_dense_signals(df, strategy_params=params)
        assert len(dense_signals) > 0

    def test_dense_vol_trend_auto_has_multiple_trends(self, df):
        params = {"VOL_EXPANSION_CONT": {**VOL_SMALL_PARAMS["VOL_EXPANSION_CONT"], "trend": ["auto"]}}
        dense_signals = _build_vol_expansion_dense_signals(df, strategy_params=params)
        trend_values = set()
        for param_str, _, _, _ in dense_signals:
            for part in param_str.split(","):
                if part.startswith("trend="):
                    trend_values.add(part.split("=")[1])
        assert "none" in trend_values
        assert "ema20" in trend_values
        assert "ema100" in trend_values
        assert "ema200" in trend_values
        assert "ema300" in trend_values

    def test_dense_vol_trend_single_variant(self, df):
        params = {"VOL_EXPANSION_CONT": {**VOL_SMALL_PARAMS["VOL_EXPANSION_CONT"], "trend": ["ema200"]}}
        dense_signals = _build_vol_expansion_dense_signals(df, strategy_params=params)
        trend_values = set()
        for param_str, _, _, _ in dense_signals:
            for part in param_str.split(","):
                if part.startswith("trend="):
                    trend_values.add(part.split("=")[1])
        assert trend_values == {"ema200"}
