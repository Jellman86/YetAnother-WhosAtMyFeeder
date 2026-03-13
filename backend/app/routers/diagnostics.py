from fastapi import APIRouter, Depends, Query

from app.auth import AuthContext, require_owner
from app.services.error_diagnostics import error_diagnostics_history

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

WORKSPACE_SCHEMA_VERSION = "2026-03-12.owner-incident-workspace.v1"


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
    from app.main import health_check
    from app.routers.classifier import classifier_service

    health = await health_check()
    return {
        "workspace_schema_version": WORKSPACE_SCHEMA_VERSION,
        "backend_diagnostics": error_diagnostics_history.snapshot(limit=limit),
        "health": health,
        "classifier": classifier_service.get_status(),
        "startup_warnings": health.get("startup_warnings") or [],
    }


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
