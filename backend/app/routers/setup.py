"""Owner-only endpoints backing the first-run / re-runnable setup wizard.

The wizard edits config through the normal `/api/settings` write and validates each step with
the existing per-integration *test* endpoints; this router only exposes the cheap per-section
readiness the wizard renders as its section map.
"""

from fastapi import APIRouter, Depends

from app.auth import AuthContext, require_owner
from app.config import settings
from app.services.setup_state_service import SetupState, compute_setup_state

router = APIRouter(prefix="/setup", tags=["setup"])


@router.get("/state", response_model=SetupState)
async def get_setup_state(_auth: AuthContext = Depends(require_owner)) -> SetupState:
    """Per-section setup readiness for the wizard's section map.

    Owner-gated, but open during first run (auth is not yet enabled), so the wizard can render
    before a password exists.
    """
    return compute_setup_state(settings)
