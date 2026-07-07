from __future__ import annotations

import math
import time
from datetime import date, datetime, timezone
from uuid import uuid4

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder

from app.api.routes_options import BACKTEST_MODES, FILTER_FIELDS, INDICATORS, OPERATORS, TIMEFRAMES
from app.api.schemas import BacktestRequest, BacktestResponse, ResultFilter, TimingInfo
from app.backtest.config import SYMBOL, result_columns_for_params
from app.backtest.runner import run_search_limited, run_search_limited_with_diagnostics


router = APIRouter(prefix="/api", tags=["backtest"])


def validate_request(request: BacktestRequest) -> None:
    if request.symbol != SYMBOL:
        raise HTTPException(status_code=400, detail=f"Unsupported symbol: {request.symbol}")
    if request.mode not in BACKTEST_MODES:
        raise HTTPException(status_code=400, detail=f"Unsupported mode: {request.mode}")

    invalid_timeframes = [timeframe for timeframe in request.timeframes if timeframe not in TIMEFRAMES]
    if invalid_timeframes:
        raise HTTPException(status_code=400, detail=f"Invalid timeframes: {invalid_timeframes}")

    if request.strategies is not None:
        invalid_strategies = [strategy for strategy in request.strategies if strategy not in INDICATORS]
        if invalid_strategies:
            raise HTTPException(status_code=400, detail=f"Invalid strategies: {invalid_strategies}")

    invalid_filters = [
        {"field": item.field, "op": item.op}
        for item in request.filters
        if item.field not in FILTER_FIELDS or item.op not in OPERATORS
    ]
    if invalid_filters:
        raise HTTPException(status_code=400, detail=f"Invalid filters: {invalid_filters}")

    enabled_params = dict(request.search_params or {})
    enabled_params["_mode"] = request.mode
    enabled_fields = set(result_columns_for_params(enabled_params))
    disabled_filters = [
        item.field
        for item in request.filters
        if item.field in FILTER_FIELDS and item.field not in enabled_fields
    ]
    if disabled_filters:
        raise HTTPException(
            status_code=400,
            detail=f"Filter fields require enabling their metric options first: {disabled_filters}",
        )

    if request.limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")


def apply_result_filter(df: pd.DataFrame, item: ResultFilter) -> pd.DataFrame:
    if item.field not in df.columns:
        raise HTTPException(
            status_code=400,
            detail=f"Filter field '{item.field}' not found in results. Available: {list(df.columns)}",
        )

    if item.op == "~":
        return df[df[item.field].astype(str).str.contains(str(item.value), case=False, na=False)]

    series = pd.to_numeric(df[item.field], errors="coerce")
    value = float(item.value)
    if item.op == ">":
        return df[series > value]
    if item.op == ">=":
        return df[series >= value]
    if item.op == "<":
        return df[series < value]
    if item.op == "<=":
        return df[series <= value]
    if item.op == "=":
        return df[series == value]
    raise HTTPException(status_code=400, detail=f"Invalid operator: {item.op}")


def apply_filters(df: pd.DataFrame, request: BacktestRequest) -> pd.DataFrame:
    if request.strategies:
        df = df[df["strategy"].isin(request.strategies)]

    for item in request.filters:
        df = apply_result_filter(df, item)

    return df.head(request.limit)


def clean_value(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def dataframe_to_rows(df: pd.DataFrame) -> list[dict]:
    records = df.to_dict(orient="records")
    rows = [{key: clean_value(value) for key, value in row.items()} for row in records]
    return jsonable_encoder(rows)


@router.post("/backtest", response_model=BacktestResponse)
def run_backtest(request: BacktestRequest) -> BacktestResponse:
    validate_request(request)

    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    diagnostics = None
    if request.mode == "normal":
        df, diagnostics = run_search_limited_with_diagnostics(
            timeframes=request.timeframes,
            mode=request.mode,
            strategies=request.strategies,
            search_params=request.search_params,
            result_filters=request.filters,
            limit=request.limit,
        )
    else:
        df = run_search_limited(
            timeframes=request.timeframes,
            mode=request.mode,
            strategies=request.strategies,
            search_params=request.search_params,
            result_filters=request.filters,
            limit=request.limit,
        )

    finished_at = datetime.now(timezone.utc)
    duration_sec = round(time.perf_counter() - t0, 4)

    return BacktestResponse(
        run_temp_id=str(uuid4()),
        row_count=len(df),
        columns=list(df.columns),
        rows=dataframe_to_rows(df),
        timing=TimingInfo(
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            duration_sec=duration_sec,
        ),
        diagnostics=diagnostics,
    )
