from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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


@router.get("/saved-runs/{run_id}/export.csv")
def api_export_csv(run_id: str):
    data = load_run(run_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Saved run not found")

    columns = data.get("columns", [])
    rows = data.get("rows", [])
    ratings = data.get("ratings", {})
    selected_rows = data.get("selectedRows", {})
    row_notes = data.get("rowNotes", {})

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    review_cols = ["selected", "rating", "note"]
    writer.writerow(columns + review_cols)

    for i, row in enumerate(rows):
        data_row = [row.get(col, "") for col in columns]
        sel = "yes" if str(i) in selected_rows and selected_rows[str(i)] else ""
        rating = ratings.get(str(i), "")
        note = row_notes.get(str(i), "")
        writer.writerow(data_row + [sel, rating, note])

    csv_bytes = output.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{run_id}.csv"',
            "Content-Length": str(len(csv_bytes)),
        },
    )
