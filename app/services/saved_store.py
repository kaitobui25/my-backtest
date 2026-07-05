from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


DATA_DIR = Path("data/saved_runs")


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _safe_path(run_id: str) -> Path | None:
    try:
        candidate = (DATA_DIR / f"{run_id}.json").resolve()
        candidate.relative_to(DATA_DIR.resolve())
        return candidate
    except (ValueError, OSError):
        return None


def save_run(
    columns: list,
    rows: list,
    ratings: dict,
    selected_rows: dict,
    row_notes: dict,
    metadata: dict,
) -> dict:
    _ensure_dir()
    run_id = str(uuid4())
    file_path = DATA_DIR / f"{run_id}.json"

    metadata.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    metadata["run_id"] = run_id

    data = {
        "metadata": metadata,
        "columns": columns,
        "rows": rows,
        "ratings": ratings,
        "selectedRows": selected_rows,
        "rowNotes": row_notes,
    }

    file_path.write_text(json.dumps(data, default=str), encoding="utf-8")
    return {"run_id": run_id, "file_path": str(file_path)}


def list_saved_runs() -> list[dict]:
    _ensure_dir()
    if not DATA_DIR.exists():
        return []

    items = []
    for f in sorted(DATA_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.suffix != ".json":
            continue
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            meta = raw.get("metadata", {})
            meta["run_id"] = f.stem
            items.append(meta)
        except (json.JSONDecodeError, OSError):
            continue

    return items


def load_run(run_id: str) -> dict | None:
    path = _safe_path(run_id)
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def delete_run(run_id: str) -> bool:
    path = _safe_path(run_id)
    if path is None or not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False
