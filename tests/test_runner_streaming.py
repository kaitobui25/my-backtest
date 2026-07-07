from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.api.routes_options import BACKTEST_MODES, MODES, options
from app.backtest.config import ROBUSTNESS_COLUMNS, STABILITY_COLUMNS, result_columns_for_params
from app.backtest.metrics import score_candidate
from app.backtest.result_builder import compute_stability_score
from app.backtest import signals
from app.backtest.runner import (
    _neighbor_holds,
    _neighbor_values,
    _nearby_strategy_variants,
    _normal_core_kernel_enabled,
    run_search,
    run_search_limited,
    run_search_limited_with_diagnostics,
)


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
        "normal_candidates_scanned",
        "top_candidates_selected",
        "verified_candidates",
        "stability_candidates_checked",
        "stability_neighbors_simulated",
        "verification_sec",
        "stability_sec",
        "ranking_sec",
        "rows_before_pre_filter",
        "rows_after_pre_filter",
        "rows_before_post_filter",
        "rows_after_post_filter",
    }
    assert set(diagnostics) == expected_keys
    assert diagnostics["kernel_used"] == "normal_core"
    assert diagnostics["side_modes_scanned"] <= diagnostics["variants_generated"]
    assert diagnostics["rows_kept"] == len(df)
    assert diagnostics["top_candidates_selected"] >= diagnostics["verified_candidates"]
    assert diagnostics["stability_neighbors_simulated"] >= diagnostics["stability_candidates_checked"]
    assert diagnostics["rows_before_pre_filter"] >= diagnostics["rows_after_pre_filter"]
    assert diagnostics["rows_before_post_filter"] >= diagnostics["rows_after_post_filter"]
    assert "load_data_sec" not in df.columns
    for col in [*STABILITY_COLUMNS, *ROBUSTNESS_COLUMNS]:
        assert col in df.columns


def _post_filter_params():
    return {
        "max_signal_variants": 1,
        "grid_profile": "normal",
        "verify_top_n": 10,
        "stability_top_n": 10,
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


def test_normal_post_filters_apply_after_enrichment():
    params = _post_filter_params()
    base = run_search_limited(
        ["M15"],
        "normal",
        ["VOL_EXPANSION_CONT"],
        params,
        result_filters=[{"field": "win_rate", "op": ">=", "value": 0}],
        limit=20,
    )
    assert not base.empty

    score_threshold = float(base["score"].max()) - 0.001
    stability_threshold = float(base["stability_score"].max()) - 0.001
    overfit_threshold = float(base["overfit_risk_score"].min())

    by_score = run_search_limited(
        ["M15"],
        "normal",
        ["VOL_EXPANSION_CONT"],
        params,
        result_filters=[{"field": "score", "op": ">=", "value": score_threshold}],
        limit=20,
    )
    assert not by_score.empty
    assert (by_score["score"] >= score_threshold).all()

    by_stability = run_search_limited(
        ["M15"],
        "normal",
        ["VOL_EXPANSION_CONT"],
        params,
        result_filters=[{"field": "stability_score", "op": ">=", "value": stability_threshold}],
        limit=20,
    )
    assert not by_stability.empty
    assert (by_stability["stability_score"] >= stability_threshold).all()

    by_overfit = run_search_limited(
        ["M15"],
        "normal",
        ["VOL_EXPANSION_CONT"],
        params,
        result_filters=[{"field": "overfit_risk_score", "op": "<=", "value": overfit_threshold}],
        limit=20,
    )
    assert not by_overfit.empty
    assert (by_overfit["overfit_risk_score"] <= overfit_threshold).all()


def test_existing_core_filters_still_apply_before_enrichment():
    params = _post_filter_params()
    rows = run_search_limited(
        ["M15"],
        "normal",
        ["VOL_EXPANSION_CONT"],
        params,
        result_filters=[{"field": "win_rate", "op": ">=", "value": 50}],
        limit=20,
    )
    assert not rows.empty
    assert (rows["win_rate"] >= 50).all()


def test_frontend_enabled_filter_fields_include_stability_and_robustness():
    source = Path("frontend/src/main.js").read_text(encoding="utf-8")
    assert "groups.stability" in source
    assert "groups.robustness" in source


def test_stability_neighbor_generation():
    assert _neighbor_values([0.01, 0.02, 0.04, 0.06], 0.04) == [0.02, 0.04, 0.06]
    assert _neighbor_values([0.01, 0.02, 0.04, 0.06], 0.03) == [0.02, 0.03, 0.04]
    assert _neighbor_holds([0, 48, 96], 48) == [0, 48, 96]
    row = {"params": "range_mult=0.8,trend=none,adx_min=8,body_min=0.45"}
    variants = [
        SimpleNamespace(params="range_mult=0.8,trend=none,adx_min=8,body_min=0.45"),
        SimpleNamespace(params="range_mult=1.2,trend=none,adx_min=8,body_min=0.45"),
        SimpleNamespace(params="range_mult=1.2,trend=ema200,adx_min=8,body_min=0.45"),
    ]
    neighbors = _nearby_strategy_variants(row, variants)
    assert [item.params for item in neighbors] == ["range_mult=1.2,trend=none,adx_min=8,body_min=0.45"]


def test_stability_score_rewards_robust_neighbors():
    robust = compute_stability_score(12, 10, 1.8, 62.0, -8.0)
    one_point = compute_stability_score(12, 1, 1.1, 51.0, -30.0)
    assert robust > one_point
    assert robust > 70.0
    assert one_point < 30.0


def _normal_score(**overrides):
    row = {
        "win_rate": 58.0,
        "total_return": 80.0,
        "profit_factor": 1.8,
        "expectancy": 0.25,
        "max_drawdown": -10.0,
        "trades": 120,
        "test_win_rate": 58.0,
        "test_total_return": 35.0,
        "test_profit_factor": 1.7,
        "test_expectancy": 0.18,
        "test_trades": 35,
        "trades_per_day": 0.5,
        "max_gap_days": 6.0,
        "test_trades_per_day": 0.4,
        "test_max_gap_days": 8.0,
        "stability_score": 80.0,
        "full_test_pf_gap": 0.1,
        "full_test_winrate_gap": 2.0,
        "overfit_risk_score": 5.0,
    }
    row.update(overrides)
    return score_candidate(**row)


def test_new_score_ranks_tradeable_robust_setup_higher():
    robust = _normal_score()
    one_point = _normal_score(stability_score=5.0, full_test_pf_gap=1.8, overfit_risk_score=65.0)
    low_trades = _normal_score(test_trades=3, test_trades_per_day=0.02)
    high_gap = _normal_score(max_gap_days=60.0, test_max_gap_days=80.0)
    weak_oos = _normal_score(test_profit_factor=1.05, test_win_rate=48.0, test_total_return=2.0, test_expectancy=0.01)

    assert robust > one_point
    assert robust > low_trades
    assert robust > high_gap
    assert robust > weak_oos


def test_user_facing_options_are_normal_only_dense_backend_still_known():
    data = options()
    assert data["modes"] == ["normal"]
    assert MODES == ["normal"]
    assert "dense_high_winrate" in BACKTEST_MODES


def test_robustness_columns_are_normal_only():
    normal_cols = result_columns_for_params({"_mode": "normal"})
    dense_cols = result_columns_for_params({"_mode": "dense_high_winrate"})
    for col in [*STABILITY_COLUMNS, *ROBUSTNESS_COLUMNS]:
        assert col in normal_cols
        assert col not in dense_cols
