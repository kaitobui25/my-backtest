from __future__ import annotations

import numpy as np
import pandas as pd

from app.backtest import signals
from app.backtest.runner import _normal_core_kernel_enabled, run_search, run_search_limited, run_search_limited_with_diagnostics


def _small_ohlc(n: int = 120) -> pd.DataFrame:
    close = 100.0 + np.sin(np.arange(n) / 5.0)
    high = close + 1.0
    low = close - 1.0
    open_ = close.copy()
    volume = np.full(n, 1000.0)
    idx = pd.date_range("2020-01-01", periods=n, freq="h")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)


def test_iter_signal_variants_applies_max_before_full_vol_materialization(monkeypatch):
    built = 0
    original = signals._iter_vol_expansion_signals

    def wrapped(*args, **kwargs):
        nonlocal built
        for item in original(*args, **kwargs):
            built += 1
            yield item

    monkeypatch.setattr(signals, "_iter_vol_expansion_signals", wrapped)
    variants = list(
        signals.iter_signal_variants(
            _small_ohlc(),
            "H1",
            "normal",
            strategies=["VOL_EXPANSION_CONT"],
            max_signal_variants=1,
        )
    )
    assert len(variants) == 1
    assert built == 1


def test_limited_runner_matches_full_runner_for_small_request():
    params = {"max_signal_variants": 2, "grid_profile": "normal"}
    filters = [{"field": "win_rate", "op": ">=", "value": 0}]
    full = run_search(["M15"], "normal", ["VOL_EXPANSION_CONT"], params)
    expected = full[full["win_rate"] >= 0].head(5).reset_index(drop=True)

    limited = run_search_limited(
        ["M15"],
        "normal",
        ["VOL_EXPANSION_CONT"],
        params,
        result_filters=filters,
        limit=5,
    ).reset_index(drop=True)

    cols = ["strategy", "params", "side_mode", "sl", "tp", "max_hold", "score"]
    assert expected[cols].equals(limited[cols])


def test_normal_core_kernel_selection():
    assert _normal_core_kernel_enabled("normal", {})
    assert _normal_core_kernel_enabled("normal", {"entry_mode": "same_open"})
    assert not _normal_core_kernel_enabled("dense_high_winrate", {})
    assert not _normal_core_kernel_enabled("normal", {"entry_mode": "next_open"})
    assert not _normal_core_kernel_enabled("normal", {"use_spread_slippage": True})
    assert not _normal_core_kernel_enabled("normal", {"use_position_sizing": True})
    assert not _normal_core_kernel_enabled("normal", {"use_leverage": True})
    assert not _normal_core_kernel_enabled("normal", {"use_liquidation": True})
    assert not _normal_core_kernel_enabled("normal", {"compute_ambiguity_metrics": True})


def test_limited_runner_diagnostics_are_separate():
    params = {
        "max_signal_variants": 1,
        "grid_profile": "normal",
        "strategy_params": {
            "VOL_EXPANSION_CONT": {
                "range_mult": [0.8],
                "trend": ["none"],
                "adx_min": [8],
                "close_extreme": [0.6],
                "body_min": [0.45],
            }
        },
    }
    df, diagnostics = run_search_limited_with_diagnostics(
        ["M15"],
        "normal",
        ["VOL_EXPANSION_CONT"],
        params,
        result_filters=[{"field": "side_mode", "op": "=", "value": "both"}],
        limit=5,
    )

    expected_keys = {
        "load_data_sec",
        "indicator_sec",
        "signal_build_sec",
        "simulate_sec",
        "row_build_sec",
        "total_runtime_sec",
        "variants_generated",
        "variants_skipped_low_signal",
        "side_modes_scanned",
        "kernel_calls",
        "configs_tested",
        "rows_kept",
        "kernel_used",
    }
    assert set(diagnostics) == expected_keys
    assert diagnostics["kernel_used"] == "normal_core"
    assert diagnostics["side_modes_scanned"] <= diagnostics["variants_generated"]
    assert diagnostics["rows_kept"] == len(df)
    assert "load_data_sec" not in df.columns
