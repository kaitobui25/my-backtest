from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import tomllib


@dataclass(frozen=True)
class BacktestConfig:
    path: Path
    base_dir: Path
    raw: dict[str, Any]

    @property
    def market(self) -> dict[str, Any]:
        return self.raw["market"]

    @property
    def costs(self) -> dict[str, Any]:
        return self.raw["costs"]

    @property
    def execution(self) -> dict[str, Any]:
        return self.raw["execution"]

    @property
    def validation(self) -> dict[str, Any]:
        return self.raw["validation"]

    @property
    def targets(self) -> dict[str, Any]:
        return self.raw["targets"]

    @property
    def target_achievement(self) -> dict[str, Any]:
        nested = self.targets.get("achievement")
        if isinstance(nested, dict) and nested:
            return nested
        standalone = self.raw.get("target_achievement")
        if isinstance(standalone, dict) and standalone:
            return standalone
        return {
            "full_avg_monthly_return_min": self.targets["monthly_return_min"],
            "oos_avg_monthly_return_min": self.targets["monthly_return_min"],
            "full_avg_monthly_return_max": self.targets["monthly_return_max"],
        }

    @property
    def target_label(self) -> str:
        configured = self.targets.get("description") or self.targets.get("target_label")
        if configured:
            return str(configured)
        low = format_pct(self.targets["monthly_return_min"])
        high = format_pct(self.targets["monthly_return_max"])
        return f"raw monthly return {low} den {high}/month"

    @property
    def filters(self) -> dict[str, Any]:
        return self.raw["filters"]

    @property
    def hard_filters(self) -> dict[str, Any]:
        return self.raw.get("hard_filters", {})

    @property
    def data_quality(self) -> dict[str, Any]:
        return self.raw.get("data_quality", {})

    @property
    def indicators(self) -> dict[str, Any]:
        return self.raw.get("indicators", {})

    @property
    def reporting(self) -> dict[str, Any]:
        return self.raw.get("reporting", {})

    @property
    def scoring_weights(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.raw.get("scoring", {}).get("weights", {}).items()}

    @property
    def scoring_params(self) -> dict[str, Any]:
        return self.raw.get("scoring", {}).get("params", {})

    @property
    def warning_thresholds(self) -> dict[str, Any]:
        return self.raw.get("warning_thresholds", {})

    @property
    def risk_thresholds(self) -> dict[str, Any]:
        return self.raw.get("risk", {})

    @property
    def symbol(self) -> str:
        return str(self.market["symbol"])

    @property
    def timeframes(self) -> list[str]:
        return [str(x).upper() for x in self.market["timeframes"]]

    @property
    def preferred_timeframes(self) -> set[str]:
        return {str(x).upper() for x in self.market.get("preferred_timeframes", self.timeframes)}

    @property
    def initial_equity(self) -> float:
        return float(self.execution["initial_equity"])

    @property
    def position_size_pct(self) -> float:
        return float(self.execution["position_size_pct"])

    @property
    def fee_per_side(self) -> float:
        return float(self.costs["fee_per_side"])

    @property
    def slippage_per_side(self) -> float:
        return float(self.costs["slippage_per_side"])

    @property
    def start(self) -> pd.Timestamp | None:
        return parse_timestamp(self.market.get("start"))

    @property
    def end(self) -> pd.Timestamp | None:
        return parse_timestamp(self.market.get("end"))

    @property
    def train_end(self) -> pd.Timestamp:
        ts = parse_timestamp(self.validation.get("train_end"))
        if ts is None:
            raise ValueError("validation.train_end is required")
        return ts

    @property
    def oos_start(self) -> pd.Timestamp:
        ts = parse_timestamp(self.validation.get("oos_start"))
        if ts is None:
            raise ValueError("validation.oos_start is required")
        return ts

    @property
    def data_path(self) -> Path:
        return resolve_path(self.base_dir, str(self.market["data_path"]))

    @property
    def raw_pine_dir(self) -> Path | None:
        ref = self.raw.get("tradingview_reference", {}).get("raw_pine_dir")
        return resolve_path(self.base_dir, str(ref)) if ref else None

    def grid_for_timeframe(self, timeframe: str) -> dict[str, list[Any]]:
        optimization = self.raw["optimization"]
        grid = {k: list(v) for k, v in optimization["default_grid"].items()}
        tf_grid = optimization.get("timeframe_grids", {}).get(timeframe.upper())
        if tf_grid:
            grid.update({k: list(v) for k, v in tf_grid.items()})
        return grid


def parse_timestamp(value: Any) -> pd.Timestamp | None:
    if value in (None, ""):
        return None
    return pd.Timestamp(value)


def format_pct(value: Any) -> str:
    return f"{float(value) * 100:.2f}%"


def resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def load_config(path: str | Path) -> BacktestConfig:
    config_path = Path(path).resolve()
    with config_path.open("rb") as f:
        raw = tomllib.load(f)
    validate_config(raw)
    return BacktestConfig(path=config_path, base_dir=config_path.parent, raw=raw)


def validate_config(raw: dict[str, Any]) -> None:
    required_sections = ["market", "costs", "execution", "validation", "targets", "filters", "optimization"]
    missing = [name for name in required_sections if name not in raw]
    if missing:
        raise ValueError(f"Missing config sections: {', '.join(missing)}")
    if int(raw["execution"].get("entry_lag_bars", 1)) < 1:
        raise ValueError("execution.entry_lag_bars must be >= 1 to avoid same-candle lookahead")
    if str(raw["execution"].get("same_bar_exit_priority", "sl")).lower() not in {"sl", "tp"}:
        raise ValueError("execution.same_bar_exit_priority must be 'sl' or 'tp'")
    if str(raw["execution"].get("signal_conflict", "skip")).lower() not in {"skip", "long", "short"}:
        raise ValueError("execution.signal_conflict must be 'skip', 'long', or 'short'")
    if float(raw["execution"].get("position_size_pct", 1.0)) <= 0:
        raise ValueError("execution.position_size_pct must be > 0")
    grid = raw["optimization"].get("default_grid", {})
    for key in ("stop_loss_pct", "take_profit_pct", "max_hold_bars", "side_modes"):
        if key not in grid or not grid[key]:
            raise ValueError(f"optimization.default_grid.{key} is required")
