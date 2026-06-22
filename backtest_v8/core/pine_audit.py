from __future__ import annotations

from typing import Any

import pandas as pd

from .config import BacktestConfig


KNOWN_SOURCE_MAP = {
    "WaveTrend Oscillator.pine": ("wavetrend_cross", "manual_python_conversion"),
    "CM_Williams_Vix_Fix.pine": ("williams_vix_fix", "manual_python_conversion"),
    "Squeeze Momentum Indicator [LazyBear].pine": ("squeeze_momentum", "manual_python_conversion"),
    "SuperTrend by KivancOzbilgic.pine": ("supertrend_flip", "manual_python_conversion"),
    "MacD Custom.pine": ("macd_cross", "manual_current_timeframe_conversion_original_uses_security"),
    "adx_ema_combined.pine": ("adx_ema_trend", "manual_python_conversion_no_security_no_pivot"),
    "Signal Forge [LuxAlgo] by LuxAlgo.pine": ("signal_forge_lite", "partial_manual_conversion_available_disabled_pending_tv_parity_test"),
    "bb.pine": ("bb_rsi_reversion", "formula_reference"),
    "rsi.pine": ("bb_rsi_reversion", "formula_reference"),
    "adx.pine": ("donchian_breakout,ema_reject_pullback,ibs_reversion", "formula_reference"),
    "ema.pine": ("donchian_breakout,ema_reject_pullback,ibs_reversion,macd_cross", "formula_reference"),
    "atr.pine": ("ema_reject_pullback,supertrend_flip", "formula_reference"),
}

KNOWN_SKIP_NOTES = {
    "Predictive Breakout Channels.pine": "Not used. Complex TradingView script; needs manual review for stateful pivots/repaint behavior before Python use.",
    "Predictive Breakout ChannelsGainzAlgo.pine": "Not used. Complex script; manual conversion and repaint/lookahead audit required.",
    "PrecSniper.pine": "Not used. Large script; manual conversion and repaint/lookahead audit required.",
    "SMC.pipe": "Not used. Smart-money style scripts often rely on pivots/structure; manual repaint audit required.",
    "smi.pipe": "Duplicate of Squeeze Momentum source shape; main .pine conversion is used instead.",
}


def audit_pine_sources(config: BacktestConfig, enabled_indicators: set[str]) -> pd.DataFrame:
    raw_dir = config.raw_pine_dir
    rows: list[dict[str, Any]] = []
    if raw_dir is None:
        return pd.DataFrame(rows)
    if not raw_dir.exists():
        return pd.DataFrame([{"file": str(raw_dir), "status": "missing_raw_pine_dir", "notes": "Directory not found"}])
    for path in sorted(list(raw_dir.glob("*.pine")) + list(raw_dir.glob("*.pipe"))):
        indicator_names, status = KNOWN_SOURCE_MAP.get(path.name, ("", "raw_reference_only"))
        mapped = [name.strip() for name in indicator_names.split(",") if name.strip()]
        if mapped:
            used = any(name in enabled_indicators for name in mapped)
            row_status = "converted_enabled" if used else "converted_available_disabled"
            notes = status
        else:
            row_status = "not_converted_not_used"
            notes = KNOWN_SKIP_NOTES.get(path.name, "Not used. Raw Pine is reference only until manually converted to the Python interface.")
        rows.append(
            {
                "file": path.name,
                "path": str(path),
                "mapped_indicators": ", ".join(mapped),
                "status": row_status,
                "notes": notes,
            }
        )
    return pd.DataFrame(rows)
