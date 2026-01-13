from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog
from app.services.ai_service import ai_service
from app.services.frigate_client import frigate_client
from app.repositories.detection_repository import DetectionRepository
from app.database import get_db

router = APIRouter()
log = structlog.get_logger()

class AIAnalysisResponse(BaseModel):
    analysis: str

@router.post("/events/{event_id}/analyze", response_model=AIAnalysisResponse)
async def analyze_event(event_id: str, force: bool = False):
    """Run AI analysis on a specific detection.

    Args:
        event_id: The Frigate event ID
        force: If True, regenerate analysis even if it already exists
    """
    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event(event_id)

        if not detection:
            raise HTTPException(status_code=404, detail="Detection not found")

        # Check if analysis already exists and force is not set
        if detection.ai_analysis and not force:
            log.info("returning_cached_analysis", event_id=event_id)
            return AIAnalysisResponse(analysis=detection.ai_analysis)

        # Fetch snapshot
        image_data = await frigate_client.get_snapshot(event_id, crop=True, quality=90)
        if not image_data:
            raise HTTPException(status_code=502, detail="Failed to fetch image from Frigate")

        # Metadata for prompt
        metadata = {
            "temperature": detection.temperature,
            "weather_condition": detection.weather_condition,
            "time": detection.detection_time.strftime("%H:%M")
        }

        # Generate new analysis
        log.info("generating_new_analysis", event_id=event_id, force=force)
        analysis = await ai_service.analyze_detection(
            species=detection.display_name,
            image_data=image_data,
            metadata=metadata
        )

        # Save analysis to database
        await repo.update_ai_analysis(event_id, analysis)

        return AIAnalysisResponse(analysis=analysis)
