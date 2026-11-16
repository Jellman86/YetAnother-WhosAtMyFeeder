"""The owner's status snapshot over HTTP, for a first paint and for a client without the live stream."""

from fastapi import APIRouter, Depends, Response

from app.auth import AuthContext, require_owner
from app.models.system_status import SystemStatusSnapshot
from app.services.system_status_runtime import system_status_service

router = APIRouter(tags=["status"])


@router.get("/status", response_model=SystemStatusSnapshot)
async def get_system_status(
    response: Response,
    _auth: AuthContext = Depends(require_owner),
) -> SystemStatusSnapshot:
    """The same snapshot the live stream pushes as a `status` event. Owner only."""
    response.headers["Cache-Control"] = "no-store"
    return await system_status_service.current()
