from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.saved_store import DATA_DIR, _safe_path, delete_run, list_saved_runs, load_run, save_run


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_data_dir():
    """Ensure a clean DATA_DIR before and after each test."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for f in DATA_DIR.iterdir():
        if f.is_file():
            f.unlink()
    yield
    for f in DATA_DIR.iterdir():
        if f.is_file():
            f.unlink()


SAMPLE_PAYLOAD = {
    "columns": ["col1", "col2"],
    "rows": [{"col1": 1, "col2": "a"}, {"col1": 2, "col2": "b"}],
    "ratings": {"0": 5},
    "selectedRows": {"1": True},
    "rowNotes": {"0": "hello"},
    "metadata": {
        "symbol": "BTCUSD",
        "timeframes": ["M15"],
        "mode": "normal",
        "strategies": ["EMA_PULLBACK"],
        "filters": [{"field": "win_rate", "op": ">=", "value": "65"}],
        "row_count": 2,
        "note": "",
    },
}


# ---------------------------------------------------------------------------
# _safe_path
# ---------------------------------------------------------------------------

class TestSafePath:
    def test_valid_uuid(self):
        path = _safe_path("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        assert path is not None
        assert path.suffix == ".json"
        assert path.parent == DATA_DIR.resolve()

    def test_path_traversal_rejected(self):
        assert _safe_path("../../etc/passwd") is None
        assert _safe_path("..\\..\\windows\\system32") is None
        assert _safe_path("../other.json") is None

    def test_non_uuid_still_valid(self):
        """Any filename that does not escape the directory is valid."""
        path = _safe_path("my-run")
        assert path is not None
        assert path.name == "my-run.json"

    def test_empty_run_id(self):
        path = _safe_path("")
        resolved = DATA_DIR.resolve()
        assert path is not None
        # resolved / ".json" -> this file path; shouldn't traverse
        assert path.parent == resolved


# ---------------------------------------------------------------------------
# save_run
# ---------------------------------------------------------------------------

class TestSaveRun:
    def test_save_returns_run_id_and_path(self):
        result = save_run(
            columns=SAMPLE_PAYLOAD["columns"],
            rows=SAMPLE_PAYLOAD["rows"],
            ratings=SAMPLE_PAYLOAD["ratings"],
            selected_rows=SAMPLE_PAYLOAD["selectedRows"],
            row_notes=SAMPLE_PAYLOAD["rowNotes"],
            metadata=SAMPLE_PAYLOAD["metadata"],
        )
        assert "run_id" in result
        assert "file_path" in result
        assert result["file_path"].endswith(".json")
        assert Path(result["file_path"]).exists()

    def test_save_writes_valid_json(self):
        result = save_run(
            columns=SAMPLE_PAYLOAD["columns"],
            rows=SAMPLE_PAYLOAD["rows"],
            ratings=SAMPLE_PAYLOAD["ratings"],
            selected_rows=SAMPLE_PAYLOAD["selectedRows"],
            row_notes=SAMPLE_PAYLOAD["rowNotes"],
            metadata=SAMPLE_PAYLOAD["metadata"],
        )
        with open(result["file_path"], encoding="utf-8") as f:
            data = json.load(f)
        assert data["columns"] == ["col1", "col2"]
        assert len(data["rows"]) == 2
        assert data["ratings"] == {"0": 5}
        assert data["rowNotes"] == {"0": "hello"}
        assert data["metadata"]["symbol"] == "BTCUSD"

    def test_save_adds_created_at_and_run_id_to_metadata(self):
        result = save_run(
            columns=SAMPLE_PAYLOAD["columns"],
            rows=SAMPLE_PAYLOAD["rows"],
            ratings={},
            selected_rows={},
            row_notes={},
            metadata=SAMPLE_PAYLOAD["metadata"],
        )
        with open(result["file_path"], encoding="utf-8") as f:
            data = json.load(f)
        assert data["metadata"]["run_id"] == result["run_id"]
        assert "created_at" in data["metadata"]


# ---------------------------------------------------------------------------
# list_saved_runs
# ---------------------------------------------------------------------------

class TestListSavedRuns:
    def test_empty_dir(self):
        assert list_saved_runs() == []

    def test_lists_metadata_only(self):
        save_run(
            columns=SAMPLE_PAYLOAD["columns"],
            rows=SAMPLE_PAYLOAD["rows"],
            ratings=SAMPLE_PAYLOAD["ratings"],
            selected_rows=SAMPLE_PAYLOAD["selectedRows"],
            row_notes=SAMPLE_PAYLOAD["rowNotes"],
            metadata=SAMPLE_PAYLOAD["metadata"],
        )
        items = list_saved_runs()
        assert len(items) == 1
        item = items[0]
        assert item["symbol"] == "BTCUSD"
        assert item["timeframes"] == ["M15"]
        assert item["row_count"] == 2
        assert "run_id" in item
        # Should not contain full rows/columns
        assert "rows" not in item
        assert "columns" not in item

    def test_newest_first(self):
        r1 = save_run(columns=["c"], rows=[{"c": 1}], ratings={}, selected_rows={}, row_notes={}, metadata={})
        r2 = save_run(columns=["c"], rows=[{"c": 2}], ratings={}, selected_rows={}, row_notes={}, metadata={})
        items = list_saved_runs()
        assert len(items) == 2
        assert items[0]["run_id"] == r2["run_id"]
        assert items[1]["run_id"] == r1["run_id"]

    def test_skips_corrupt_json(self):
        (DATA_DIR / "corrupt.json").write_text("not json", encoding="utf-8")
        save_run(columns=["c"], rows=[{"c": 1}], ratings={}, selected_rows={}, row_notes={}, metadata={})
        items = list_saved_runs()
        assert len(items) == 1

    def test_skips_non_json_suffix(self):
        (DATA_DIR / "readme.md").write_text("hello", encoding="utf-8")
        assert list_saved_runs() == []


# ---------------------------------------------------------------------------
# load_run
# ---------------------------------------------------------------------------

class TestLoadRun:
    def test_load_returns_full_data(self):
        result = save_run(
            columns=SAMPLE_PAYLOAD["columns"],
            rows=SAMPLE_PAYLOAD["rows"],
            ratings=SAMPLE_PAYLOAD["ratings"],
            selected_rows=SAMPLE_PAYLOAD["selectedRows"],
            row_notes=SAMPLE_PAYLOAD["rowNotes"],
            metadata=SAMPLE_PAYLOAD["metadata"],
        )
        data = load_run(result["run_id"])
        assert data is not None
        assert data["columns"] == ["col1", "col2"]
        assert len(data["rows"]) == 2
        assert data["ratings"] == {"0": 5}
        assert data["rowNotes"] == {"0": "hello"}

    def test_load_missing_returns_none(self):
        assert load_run("nonexistent-run-id") is None

    def test_load_corrupt_returns_none(self):
        (DATA_DIR / "corrupt.json").write_text("not json", encoding="utf-8")
        assert load_run("corrupt") is None

    def test_load_path_traversal_returns_none(self):
        assert load_run("../../etc/passwd") is None

    def test_load_outside_dir_returns_none(self):
        assert load_run("..\\somefile") is None


# ---------------------------------------------------------------------------
# delete_run
# ---------------------------------------------------------------------------

class TestDeleteRun:
    def test_delete_success(self):
        result = save_run(columns=["c"], rows=[{"c": 1}], ratings={}, selected_rows={}, row_notes={}, metadata={})
        assert delete_run(result["run_id"]) is True
        assert not Path(result["file_path"]).exists()

    def test_delete_missing_returns_false(self):
        assert delete_run("nonexistent") is False

    def test_delete_path_traversal_returns_false(self):
        assert delete_run("../../etc/passwd") is False


# ---------------------------------------------------------------------------
# API endpoints via TestClient
# ---------------------------------------------------------------------------

class TestAPI:
    client = TestClient(app)

    def _create_run(self) -> str:
        r = self.client.post("/api/saved-runs", json=SAMPLE_PAYLOAD)
        assert r.status_code == 200
        return r.json()["run_id"]

    def test_save_empty_rejected(self):
        r = self.client.post("/api/saved-runs", json={
            "columns": [],
            "rows": [],
            "ratings": {},
            "selectedRows": {},
            "rowNotes": {},
            "metadata": {},
        })
        assert r.status_code == 400
        assert "No results to save" in r.json()["detail"]

    def test_save_valid(self):
        r = self.client.post("/api/saved-runs", json=SAMPLE_PAYLOAD)
        assert r.status_code == 200
        body = r.json()
        assert body["message"] == "Saved"
        assert "run_id" in body

    def test_list(self):
        run_id = self._create_run()
        r = self.client.get("/api/saved-runs")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["run_id"] == run_id

    def test_load(self):
        run_id = self._create_run()
        r = self.client.get(f"/api/saved-runs/{run_id}")
        assert r.status_code == 200
        assert r.json()["columns"] == ["col1", "col2"]

    def test_load_missing(self):
        r = self.client.get("/api/saved-runs/does-not-exist")
        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_load_path_traversal(self):
        r = self.client.get("/api/saved-runs/../../etc/passwd")
        assert r.status_code == 404

    def test_delete(self):
        run_id = self._create_run()
        r = self.client.delete(f"/api/saved-runs/{run_id}")
        assert r.status_code == 200
        assert "Deleted" in r.json()["message"]

    def test_delete_missing(self):
        r = self.client.delete("/api/saved-runs/does-not-exist")
        assert r.status_code == 404

    def test_delete_path_traversal(self):
        r = self.client.delete("/api/saved-runs/../../etc/passwd")
        assert r.status_code == 404

    def test_corrupt_does_not_crash_list(self):
        (DATA_DIR / "corrupt.json").write_text("not json", encoding="utf-8")
        r = self.client.get("/api/saved-runs")
        assert r.status_code == 200

    def test_corrupt_does_not_crash_load(self):
        (DATA_DIR / "corrupt.json").write_text("not json", encoding="utf-8")
        r = self.client.get("/api/saved-runs/corrupt")
        assert r.status_code == 404
