"""Canonical owner view of background work across detection pipelines."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth import AuthContext, require_owner
from app.services.jobs_snapshot import JobsSnapshotResponse, build_jobs_snapshot

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobsSnapshotResponse)
async def get_jobs_snapshot(
    include_routine: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=500),
    _auth: AuthContext = Depends(require_owner),
) -> JobsSnapshotResponse:
    return await build_jobs_snapshot(include_routine=include_routine, limit=limit)
