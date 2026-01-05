from fastapi import APIRouter
import structlog
from app.services.audio.audio_service import audio_service

router = APIRouter(prefix="/audio", tags=["audio"])
log = structlog.get_logger()

@router.get("/recent")
async def get_recent_audio(limit: int = 10):
    """Get the most recent audio detections from the memory buffer."""
    return await audio_service.get_recent_detections(limit=limit)
