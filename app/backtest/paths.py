from __future__ import annotations

from pathlib import Path


def resolve_paths(script_path: Path | None = None) -> tuple[Path, Path, Path]:
    if script_path is None:
        script_path = Path(__file__).resolve()

    roots = []
    for index in range(1, len(script_path.parents)):
        root = script_path.parents[index]
        if root not in roots:
            roots.append(root)

    for root in roots:
        data_root = root / "flect_mt5" / "cache" / "btc"
        if data_root.exists():
            return root, data_root, root / "result" / "btc_strategy_search"

        data_root = root / "my-data" / "flect_mt5" / "cache" / "btc"
        if data_root.exists():
            return root, data_root, root / "my-data" / "flect_mt5" / "result" / "btc_strategy_search"

    raise FileNotFoundError("Could not find flect_mt5/cache/btc data root")


ROOT, DATA_ROOT, OUT_DIR = resolve_paths()
