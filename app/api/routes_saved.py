from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.saved_store import delete_run, list_saved_runs, load_run, save_run


router = APIRouter(prefix="/api", tags=["saved"])


class SaveRequest(BaseModel):
    columns: list
    rows: list
    ratings: dict
    selectedRows: dict
    rowNotes: dict
    metadata: dict


@router.post("/saved-runs")
def api_save_run(req: SaveRequest) -> dict:
    if not req.columns or not req.rows:
        raise HTTPException(status_code=400, detail="No results to save")

    result = save_run(
        columns=req.columns,
        rows=req.rows,
        ratings=req.ratings,
        selected_rows=req.selectedRows,
        row_notes=req.rowNotes,
        metadata=req.metadata,
    )

    return {
        "run_id": result["run_id"],
        "message": "Saved",
        "saved_path": result["file_path"],
    }


@router.get("/saved-runs")
def api_list_saved_runs() -> list[dict]:
    return list_saved_runs()


@router.get("/saved-runs/{run_id}")
def api_load_saved_run(run_id: str) -> dict:
    data = load_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Saved run not found")
    return data


@router.delete("/saved-runs/{run_id}")
def api_delete_saved_run(run_id: str) -> dict:
    ok = delete_run(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Saved run not found")
    return {"message": "Deleted saved run"}
