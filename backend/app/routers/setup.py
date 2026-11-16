"""Owner-only endpoints backing the first-run / re-runnable setup wizard.

The wizard edits config through the normal `/api/settings` write and validates each step with
the existing per-integration *test* endpoints; this router only exposes the cheap per-section
readiness the wizard renders as its section map.
"""

import asyncio

import structlog
from fastapi import APIRouter, Depends

from app.auth import AuthContext, require_owner
from app.config import settings
from app.services.classifier_service import get_classifier
from app.services.model_manager import model_manager
from app.services.service_connections import collect_service_connections
from app.services.setup_state_service import SetupState, compute_setup_state

router = APIRouter(prefix="/setup", tags=["setup"])
log = structlog.get_logger()


async def _active_model_installed() -> bool | None:
    """Whether the classifier finds its model on disk, or None when it could not say."""
    try:
        status = await asyncio.to_thread(get_classifier().get_status)
    except Exception as error:
        log.warning("setup_state_model_reading_failed", error=type(error).__name__)
        return None
    installed = status.get("active_model_installed")
    return installed if isinstance(installed, bool) else None


@router.get("/state", response_model=SetupState)
async def get_setup_state(_auth: AuthContext = Depends(require_owner)) -> SetupState:
    """Per-section setup readiness for the wizard's section map.

    Owner-gated, but open during first run (auth is not yet enabled), so the wizard can render
    before a password exists.
    """
    return compute_setup_state(
        settings,
        active_model_id=model_manager.active_model_id,
        model_installed=await _active_model_installed(),
        connections=await collect_service_connections(refresh_frigate=True),
    )
