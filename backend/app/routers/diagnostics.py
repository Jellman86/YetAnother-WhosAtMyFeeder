from fastapi import APIRouter, Depends, Query

from app.auth import AuthContext, require_owner
from app.services.error_diagnostics import error_diagnostics_history

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


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
