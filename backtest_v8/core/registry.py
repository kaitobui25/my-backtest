from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path
from typing import Any

from indicators.base import Indicator


LOGGER = logging.getLogger(__name__)


def discover_indicators(indicator_package: str = "indicators") -> dict[str, Indicator]:
    package = importlib.import_module(indicator_package)
    package_paths = [Path(p) for p in package.__path__]
    registry: dict[str, Indicator] = {}
    for package_path in package_paths:
        for module_info in pkgutil.iter_modules([str(package_path)]):
            name = module_info.name
            if name.startswith("_") or name == "base":
                continue
            module_name = f"{indicator_package}.{name}"
            try:
                module = importlib.import_module(module_name)
            except Exception:
                LOGGER.exception("Could not import indicator module %s", module_name)
                continue
            for indicator in _indicators_from_module(module):
                meta = indicator.metadata
                if meta.name in registry:
                    raise ValueError(f"Duplicate indicator name: {meta.name}")
                registry[meta.name] = indicator
    return registry


def _indicators_from_module(module: Any) -> list[Indicator]:
    if hasattr(module, "INDICATORS"):
        return list(module.INDICATORS)
    indicators: list[Indicator] = []
    for _, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and hasattr(obj, "metadata") and hasattr(obj, "generate"):
            try:
                indicators.append(obj())
            except TypeError:
                continue
    return indicators

