"""Owner-only HTTP endpoints for the model evaluation harness."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.auth import AuthContext, require_owner
from app.services.model_eval_service import (
    CONFUSIONS_FILENAME,
    ModelEvalAlreadyRunning,
    RESULTS_FILENAME,
    RUNTIME_FILENAME,
    SUMMARY_FILENAME,
    model_eval_runner,
)

router = APIRouter(prefix="/diagnostics/model-eval", tags=["diagnostics"])


class StartRunRequest(BaseModel):
    include_per_image: bool = False
    region_override: Optional[str] = None


class StartRunResponse(BaseModel):
    run_id: str


@router.post("/runs", response_model=StartRunResponse)
async def start_run(
    body: StartRunRequest = StartRunRequest(),
    _auth: AuthContext = Depends(require_owner),
) -> StartRunResponse:
    try:
        run_id = await model_eval_runner.start(
            include_per_image=body.include_per_image,
            region_override=body.region_override,
        )
    except ModelEvalAlreadyRunning as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return StartRunResponse(run_id=run_id)


@router.get("/runs")
async def list_runs(_auth: AuthContext = Depends(require_owner)) -> dict:
    return {
        "active": model_eval_runner.active_status() if model_eval_runner.is_running() else None,
        "runs": model_eval_runner.list_runs(),
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: str, _auth: AuthContext = Depends(require_owner)) -> dict:
    payload = model_eval_runner.get_run(run_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="run not found")
    return payload


@router.get("/runs/{run_id}/{artifact}")
async def get_artifact(
    run_id: str,
    artifact: str,
    _auth: AuthContext = Depends(require_owner),
):
    if artifact not in {SUMMARY_FILENAME, RUNTIME_FILENAME, RESULTS_FILENAME, CONFUSIONS_FILENAME}:
        raise HTTPException(status_code=400, detail="unknown artifact")
    path = model_eval_runner.artifact_path(run_id, artifact)
    if path is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    media_type = (
        "application/json" if artifact.endswith(".json")
        else "application/x-ndjson" if artifact.endswith(".jsonl")
        else "text/csv"
    )
    return FileResponse(path, media_type=media_type, filename=artifact)


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str, _auth: AuthContext = Depends(require_owner)) -> dict:
    ok = model_eval_runner.delete_run(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="run not found or in progress")
    return {"deleted": run_id}
