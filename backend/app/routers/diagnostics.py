from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.auth import AuthContext, require_owner
from app.services.error_diagnostics import error_diagnostics_history

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

WORKSPACE_SCHEMA_VERSION = "2026-03-12.owner-incident-workspace.v1"
BUNDLE_SCHEMA_VERSION = "2026-04-09.owner-diagnostics-bundle.v1"

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


async def _collect_workspace_payload(limit: int) -> dict[str, Any]:
    from app.main import health_check
    from app.routers.classifier import classifier_service

    health = await health_check()
    backend_diagnostics = error_diagnostics_history.snapshot(limit=limit)
    return {
        "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
        "backend_diagnostics": backend_diagnostics,
        "focused_diagnostics": {
            "video_classifier": _build_video_classifier_focus(backend_diagnostics, health),
        },
        "health": health,
        "classifier": classifier_service.get_status(),
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
    startup_warnings = workspace.get("startup_warnings") if isinstance(workspace, dict) else []
    startup_warnings = startup_warnings if isinstance(startup_warnings, list) else []

    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "health_status": health.get("status") or "unknown",
            "diagnostic_events": int(backend_diagnostics.get("returned_events") or 0),
            "startup_warning_count": len(startup_warnings),
        },
        "server": {
            "service": health.get("service") or "unknown",
            "version": health.get("version") or "unknown",
            "startup_instance_id": health.get("startup_instance_id") or "unknown",
        },
        "workspace": workspace,
        "health": health,
        "classifier": classifier,
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
