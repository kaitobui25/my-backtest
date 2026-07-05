from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ResultFilter(BaseModel):
    field: str
    op: str
    value: str | int | float


class BacktestRequest(BaseModel):
    symbol: str = "BTCUSD"
    timeframes: list[str] = Field(default_factory=lambda: ["M15"])
    mode: str = "normal"
    strategies: list[str] | None = None
    search_params: dict[str, Any] | None = None
    filters: list[ResultFilter] = Field(default_factory=list)
    limit: int = 500


class TimingInfo(BaseModel):
    started_at: str
    finished_at: str
    duration_sec: float


class BacktestResponse(BaseModel):
    run_temp_id: str
    row_count: int
    columns: list[str]
    rows: list[dict[str, Any]]
    timing: TimingInfo | None = None
