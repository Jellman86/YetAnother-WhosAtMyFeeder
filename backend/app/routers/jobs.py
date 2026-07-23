"""Canonical owner view of background work across detection pipelines."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.auth import AuthContext, require_owner
from app.services.auto_video_classifier_service import auto_video_classifier
from app.services.full_visit_clip_service import full_visit_clip_service
from app.services.high_quality_snapshot_service import high_quality_snapshot_service


router = APIRouter(prefix="/jobs", tags=["jobs"])


JobStatus = Literal["queued", "running", "completed", "failed", "stale", "retrying"]
JobVisibility = Literal["prominent", "routine"]


class JobSnapshotItem(BaseModel):
    id: str
    event_id: str | None = None
    kind: str
    source: str
    status: JobStatus
    phase: str
    current: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    unit: str = "items"
    route: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    visibility: JobVisibility = "prominent"


class JobLaneSnapshot(BaseModel):
    kind: str
    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    capacity: int | None = None
    max_concurrent_configured: int | None = None
    max_concurrent_effective: int | None = None
    state: str = "idle"
    blocker: str | None = None


class JobsSnapshotResponse(BaseModel):
    captured_at: str
    items: list[JobSnapshotItem]
    lanes: list[JobLaneSnapshot]


def _backfill_job_snapshots() -> list[dict[str, object]]:
    # Imported lazily to avoid binding the router module's mutable job store at
    # application import time.
    from app.routers.backfill import _JOB_STORE

    snapshots: list[dict[str, object]] = []
    for job in _JOB_STORE.values():
        status = str(job.status or "running").lower()
        if status not in {"running", "completed", "failed", "stale"}:
            status = "running"
        snapshots.append(
            {
                "id": job.id,
                "event_id": None,
                "kind": job.kind,
                "source": "owner",
                "status": status,
                "phase": "processing" if status == "running" else status,
                "current": max(0, int(job.processed or 0)),
                "total": max(0, int(job.total or 0)),
                "unit": "detections",
                "route": "/settings/data",
                "created_at": job.started_at,
                "updated_at": job.last_progress_at,
                "finished_at": job.finished_at,
                "error": job.message if status == "failed" else None,
                "visibility": "prominent",
            }
        )
    return snapshots


def _build_lanes(items: list[JobSnapshotItem]) -> list[JobLaneSnapshot]:
    counts: dict[str, Counter[str]] = {}
    for item in items:
        counts.setdefault(item.kind, Counter())[item.status] += 1

    video_status = auto_video_classifier.get_status()
    hq_status = high_quality_snapshot_service.get_status()
    full_visit_status = full_visit_clip_service.get_status()
    capacities = {
        "auto_video": int(video_status.get("pending_capacity") or 0),
        "video_analysis": int(video_status.get("pending_capacity") or 0),
        "high_quality_snapshot": int(
            high_quality_snapshot_service.MAX_PENDING_QUEUE + high_quality_snapshot_service.MAX_DEFERRED_EVENTS
        ),
        "full_visit": int(full_visit_status.get("queue_capacity") or 0),
    }
    concurrency = {
        "auto_video": (
            int(video_status.get("max_concurrent_configured") or 1),
            int(video_status.get("max_concurrent_effective") or 0),
        ),
        "video_analysis": (
            int(video_status.get("max_concurrent_configured") or 1),
            int(video_status.get("max_concurrent_effective") or 0),
        ),
        "high_quality_snapshot": (
            int(high_quality_snapshot_service.MAX_CONCURRENT_TASKS),
            int(high_quality_snapshot_service.MAX_CONCURRENT_TASKS),
        ),
        "full_visit": (
            int(full_visit_status.get("workers") or 0),
            int(full_visit_status.get("workers") or 0),
        ),
    }
    blockers = {
        "auto_video": "paused_after_failures" if video_status.get("circuit_open") else None,
        "video_analysis": (
            "paused_after_failures"
            if video_status.get("maintenance_circuit_open")
            else "waiting_for_live_detections"
            if video_status.get("throttled_for_live_pressure")
            else None
        ),
        "high_quality_snapshot": "waiting_for_capacity" if int(hq_status.get("deferred") or 0) > 0 else None,
        "full_visit": (
            "waiting_for_capacity"
            if int(full_visit_status.get("queued") or 0) >= int(full_visit_status.get("queue_capacity") or 1)
            else None
        ),
    }

    lanes: list[JobLaneSnapshot] = []
    for kind in sorted(counts):
        kind_counts = counts[kind]
        queued = kind_counts["queued"] + kind_counts["retrying"]
        running = kind_counts["running"] + kind_counts["stale"]
        blocker = blockers.get(kind)
        configured, effective = concurrency.get(kind, (None, None))
        state = (
            "paused" if blocker == "paused_after_failures" else "running" if running else "queued" if queued else "idle"
        )
        lanes.append(
            JobLaneSnapshot(
                kind=kind,
                queued=queued,
                running=running,
                completed=kind_counts["completed"],
                failed=kind_counts["failed"],
                capacity=capacities.get(kind) or None,
                max_concurrent_configured=configured,
                max_concurrent_effective=effective,
                state=state,
                blocker=blocker,
            )
        )
    return lanes


def _job_sort_timestamp(item: JobSnapshotItem) -> float:
    """Return a stable UTC timestamp so limits keep the newest relevant work."""
    value = item.updated_at or item.finished_at or item.created_at
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0


@router.get("", response_model=JobsSnapshotResponse)
async def get_jobs_snapshot(
    include_routine: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=500),
    _auth: AuthContext = Depends(require_owner),
) -> JobsSnapshotResponse:
    raw_items = [
        *auto_video_classifier.get_jobs_snapshot(),
        *high_quality_snapshot_service.get_jobs_snapshot(),
        *full_visit_clip_service.get_jobs_snapshot(),
        *_backfill_job_snapshots(),
    ]
    items: list[JobSnapshotItem] = []
    for raw in raw_items:
        visibility: JobVisibility = (
            "routine"
            if str(raw.get("kind") or "") in {"auto_video", "high_quality_snapshot", "full_visit"}
            else "prominent"
        )
        item = JobSnapshotItem.model_validate({**raw, "visibility": visibility})
        if include_routine or item.visibility == "prominent":
            items.append(item)
    items.sort(
        key=lambda item: (
            0 if item.status in {"running", "stale"} else 1 if item.status in {"queued", "retrying"} else 2,
            -_job_sort_timestamp(item),
            item.id,
        )
    )
    lanes = _build_lanes(items)
    items = items[:limit]
    return JobsSnapshotResponse(
        captured_at=datetime.now(timezone.utc).isoformat(),
        items=items,
        lanes=lanes,
    )
