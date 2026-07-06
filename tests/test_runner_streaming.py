from __future__ import annotations

import numpy as np
import pandas as pd

from app.backtest import signals
from app.backtest.runner import run_search, run_search_limited


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
