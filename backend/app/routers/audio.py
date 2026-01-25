from fastapi import APIRouter, Depends, Request
import structlog
from app.services.audio.audio_service import audio_service
from app.config import settings
from app.auth import AuthContext
from app.auth_legacy import get_auth_context_with_legacy
from app.ratelimit import guest_rate_limit

router = APIRouter(prefix="/audio", tags=["audio"])
log = structlog.get_logger()

@router.get("/recent")
@guest_rate_limit()
async def get_recent_audio(
    request: Request,
    limit: int = 10,
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Get the most recent audio detections from the memory buffer."""
    detections = await audio_service.get_recent_detections(limit=limit)
    hide_sensor = (
        not auth.is_owner
        and settings.public_access.enabled
        and not settings.public_access.show_camera_names
    )
    if hide_sensor:
        for detection in detections:
            detection["sensor_id"] = None
    return detections
