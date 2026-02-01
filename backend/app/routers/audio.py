from fastapi import APIRouter, Depends, Request, Query
from datetime import datetime, timezone
import structlog
from app.services.audio.audio_service import audio_service
from app.config import settings
from app.auth import AuthContext
from app.auth_legacy import get_auth_context_with_legacy
from app.ratelimit import guest_rate_limit
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository

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

@router.get("/context")
@guest_rate_limit()
async def get_audio_context(
    request: Request,
    timestamp: datetime = Query(..., description="ISO timestamp for the visual detection"),
    camera: str | None = Query(default=None, description="Camera name for sensor mapping"),
    window_seconds: int = Query(default=300, ge=5, le=3600),
    limit: int = Query(default=5, ge=1, le=20),
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Get audio detections near a specific detection time."""
    target_time = timestamp
    if target_time.tzinfo is None:
        target_time = target_time.replace(tzinfo=timezone.utc)

    expected_sensor_id = None
    if camera and settings.frigate.camera_audio_mapping:
        expected_sensor_id = settings.frigate.camera_audio_mapping.get(camera)
        if expected_sensor_id == "*":
            expected_sensor_id = None

    async with get_db() as db:
        repo = DetectionRepository(db)
        detections = await repo.get_audio_context(
            target_time=target_time,
            window_seconds=window_seconds,
            sensor_id=expected_sensor_id,
            limit=limit
        )
    hide_sensor = (
        not auth.is_owner
        and settings.public_access.enabled
        and not settings.public_access.show_camera_names
    )
    if hide_sensor:
        for detection in detections:
            detection["sensor_id"] = None
    return detections
