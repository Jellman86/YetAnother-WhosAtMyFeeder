import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.auth import AuthContext, require_owner
from app.services.error_diagnostics import error_diagnostics_history

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

WORKSPACE_SCHEMA_VERSION = "2026-03-12.owner-incident-workspace.v1"
BUNDLE_SCHEMA_VERSION = "2026-04-09.owner-diagnostics-bundle.v1"

_BACKFILL_STALE_JOB_SECONDS = 600.0

_VIDEO_DIAGNOSTIC_COMPONENTS = {"auto_video_classifier", "video_classifier"}
_VIDEO_BREAKER_REASON_CODES = {"video_circuit_open", "video_circuit_opened", "circuit_open"}


def _is_video_diagnostic_event(event: dict[str, Any]) -> bool:
    component = str(event.get("component") or "").strip().lower()
    worker_pool = str(event.get("worker_pool") or "").strip().lower()
    return component in _VIDEO_DIAGNOSTIC_COMPONENTS or worker_pool == "video"


def _copy_event(event: dict[str, Any] | None) -> dict[str, Any] | None:
    return dict(event) if isinstance(event, dict) else None


def _build_video_classifier_focus(
    backend_snapshot: dict[str, Any],
    health: dict[str, Any],
) -> dict[str, Any]:
    events = backend_snapshot.get("events") if isinstance(backend_snapshot, dict) else []
    health_video = health.get("video_classifier") if isinstance(health, dict) else {}
    health_video = health_video if isinstance(health_video, dict) else {}

    recent_events = [
        _copy_event(event)
        for event in events
        if isinstance(event, dict) and _is_video_diagnostic_event(event)
    ][:8]
    recent_events = [event for event in recent_events if event is not None]

    latest_circuit_opened = next(
        (
            _copy_event(event)
            for event in recent_events
            if str(event.get("reason_code") or "").strip().lower() == "video_circuit_opened"
        ),
        None,
    )
    candidate_failure_events = [
        event
        for event in recent_events
        if str(event.get("reason_code") or "").strip().lower() not in _VIDEO_BREAKER_REASON_CODES
    ][:5]

    likely_last_error = None
    if latest_circuit_opened and isinstance(latest_circuit_opened.get("context"), dict):
        last_error = latest_circuit_opened["context"].get("last_error")
        if isinstance(last_error, str) and last_error.strip():
            likely_last_error = last_error.strip()
    if likely_last_error is None and candidate_failure_events:
        candidate_reason = candidate_failure_events[0].get("reason_code")
        if isinstance(candidate_reason, str) and candidate_reason.strip():
            likely_last_error = candidate_reason.strip()

    return {
        "circuit_open": bool(health_video.get("circuit_open")),
        "open_until": health_video.get("open_until") or None,
        "failure_count": int(health_video.get("failure_count") or 0),
        "pending": int(health_video.get("pending") or 0),
        "active": int(health_video.get("active") or 0),
        "latest_circuit_opened": latest_circuit_opened,
        "likely_last_error": likely_last_error,
        "candidate_failure_events": candidate_failure_events,
        "recent_events": recent_events,
    }


def _build_backfill_focus(backend_snapshot: dict[str, Any]) -> dict[str, Any]:
    from app.routers.backfill import _JOB_STORE

    now_iso = datetime.now(timezone.utc).isoformat()
    now_monotonic = time.monotonic()

    jobs: list[dict[str, Any]] = []
    stale_jobs: list[dict[str, Any]] = []

    for job in _JOB_STORE.values():
        job_dict = job.model_dump()
        started_at_str = job_dict.get("started_at")
        age_seconds: float | None = None
        if started_at_str and job_dict.get("status") == "running":
            try:
                started_dt = datetime.fromisoformat(started_at_str)
                age_seconds = (datetime.now(timezone.utc) - started_dt).total_seconds()
                job_dict["age_seconds"] = round(age_seconds, 1)
            except (ValueError, TypeError):
                pass
        jobs.append(job_dict)
        if job_dict.get("status") == "running" and isinstance(age_seconds, float) and age_seconds >= _BACKFILL_STALE_JOB_SECONDS:
            stale_jobs.append(job_dict)

    running_jobs = [j for j in jobs if j.get("status") == "running"]
    failed_jobs = [j for j in jobs if j.get("status") == "failed"]

    events = backend_snapshot.get("events") if isinstance(backend_snapshot, dict) else []
    recent_errors = [
        _copy_event(ev)
        for ev in events
        if isinstance(ev, dict) and str(ev.get("source") or "").lower() == "backfill"
    ][:8]
    recent_errors = [ev for ev in recent_errors if ev is not None]

    return {
        "jobs": jobs,
        "running_jobs": running_jobs,
        "failed_jobs": failed_jobs,
        "stale_jobs": stale_jobs,
        "has_stale_running_job": len(stale_jobs) > 0,
        "recent_errors": recent_errors,
        "snapshot_at": now_iso,
    }


async def _collect_workspace_payload(limit: int) -> dict[str, Any]:
    from app.main import health_check
    from app.routers.classifier import classifier_service
    from app.routers.settings import canonical_identity_repair_service
    from app.services.maintenance_coordinator import maintenance_coordinator

    health = await health_check()
    backend_diagnostics = error_diagnostics_history.snapshot(limit=limit)
    taxonomy_repair = canonical_identity_repair_service.get_status()
    maintenance_status = await maintenance_coordinator.get_status()
    return {
        "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
        "backend_diagnostics": backend_diagnostics,
        "focused_diagnostics": {
            "video_classifier": _build_video_classifier_focus(backend_diagnostics, health),
            "backfill": _build_backfill_focus(backend_diagnostics),
        },
        "health": health,
        "classifier": classifier_service.get_status(),
        "taxonomy_repair": taxonomy_repair,
        "maintenance_coordinator": maintenance_status,
        "startup_warnings": health.get("startup_warnings") or [],
    }


async def _collect_bundle_payload(limit: int) -> dict[str, Any]:
    workspace = await _collect_workspace_payload(limit)
    health = workspace.get("health") if isinstance(workspace, dict) else {}
    health = health if isinstance(health, dict) else {}
    backend_diagnostics = workspace.get("backend_diagnostics") if isinstance(workspace, dict) else {}
    backend_diagnostics = backend_diagnostics if isinstance(backend_diagnostics, dict) else {}
    classifier = workspace.get("classifier") if isinstance(workspace, dict) else {}
    classifier = classifier if isinstance(classifier, dict) else {}
    taxonomy_repair = workspace.get("taxonomy_repair") if isinstance(workspace, dict) else {}
    taxonomy_repair = taxonomy_repair if isinstance(taxonomy_repair, dict) else {}
    maintenance_status = workspace.get("maintenance_coordinator") if isinstance(workspace, dict) else {}
    maintenance_status = maintenance_status if isinstance(maintenance_status, dict) else {}
    startup_warnings = workspace.get("startup_warnings") if isinstance(workspace, dict) else []
    startup_warnings = startup_warnings if isinstance(startup_warnings, list) else []

    focused = workspace.get("focused_diagnostics") or {}
    backfill_focus = focused.get("backfill") if isinstance(focused, dict) else {}
    backfill_focus = backfill_focus if isinstance(backfill_focus, dict) else {}

    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "health_status": health.get("status") or "unknown",
            "diagnostic_events": int(backend_diagnostics.get("returned_events") or 0),
            "startup_warning_count": len(startup_warnings),
            "backfill_stale_jobs": len(backfill_focus.get("stale_jobs") or []),
            "backfill_running_jobs": len(backfill_focus.get("running_jobs") or []),
            "backfill_failed_jobs": len(backfill_focus.get("failed_jobs") or []),
        },
        "server": {
            "service": health.get("service") or "unknown",
            "version": health.get("version") or "unknown",
            "startup_instance_id": health.get("startup_instance_id") or "unknown",
        },
        "workspace": workspace,
        "health": health,
        "classifier": classifier,
        "taxonomy_repair": taxonomy_repair,
        "maintenance_coordinator": maintenance_status,
        "startup_warnings": startup_warnings,
        "backend_diagnostics": backend_diagnostics,
        "focused_diagnostics": workspace.get("focused_diagnostics") or {},
    }


@router.get("/errors")
async def get_error_diagnostics_history(
    limit: int = Query(default=200, ge=1, le=1000),
    source: str | None = Query(default=None),
    component: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    _auth: AuthContext = Depends(require_owner),
):
    """Return recent backend diagnostics events for operator troubleshooting."""
    return error_diagnostics_history.snapshot(
        limit=limit,
        source=source,
        component=component,
        severity=severity,
    )


@router.get("/workspace")
async def get_owner_workspace_diagnostics(
    limit: int = Query(default=200, ge=1, le=1000),
    _auth: AuthContext = Depends(require_owner),
):
    """Return bounded diagnostics evidence for the owner incident workspace."""
    return await _collect_workspace_payload(limit)


@router.get("/bundle")
async def get_owner_diagnostics_bundle(
    limit: int = Query(default=200, ge=1, le=1000),
    _auth: AuthContext = Depends(require_owner),
):
    """Return the full owner diagnostics bundle as one exportable JSON payload."""
    return await _collect_bundle_payload(limit)


@router.post("/clear")
async def clear_owner_workspace_diagnostics(
    _auth: AuthContext = Depends(require_owner),
):
    """Clear bounded backend diagnostics history for the owner workspace."""
    cleared_events = error_diagnostics_history.clear()
    return {
        "cleared_events": cleared_events,
        "remaining_events": 0,
    }
