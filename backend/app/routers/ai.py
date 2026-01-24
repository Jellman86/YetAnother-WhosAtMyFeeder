from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
import structlog
from app.services.ai_service import ai_service
from app.services.frigate_client import frigate_client
from app.repositories.detection_repository import DetectionRepository
from app.database import get_db
from app.services.i18n_service import i18n_service
from app.utils.language import get_user_language
from app.auth import AuthContext
from app.auth_legacy import get_auth_context_with_legacy
from app.config import settings

router = APIRouter()
log = structlog.get_logger()

class AIAnalysisResponse(BaseModel):
    analysis: str

@router.post("/events/{event_id}/analyze", response_model=AIAnalysisResponse)
async def analyze_event(
    event_id: str,
    request: Request,
    force: bool = False,
    use_clip: bool = True,
    frame_count: int = 5,
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Run AI analysis on a specific detection.

    Args:
        event_id: The Frigate event ID
        force: If True, regenerate analysis even if it already exists
    """
    lang = get_user_language(request)
    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event(event_id)

        if not detection:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.detection_not_found", lang)
            )

        # Check if analysis already exists and force is not set
        if detection.ai_analysis and not force:
            log.info("returning_cached_analysis", event_id=event_id)
            return AIAnalysisResponse(analysis=detection.ai_analysis)

        if not auth.is_owner:
            raise HTTPException(
                status_code=403,
                detail="Owner access required to generate AI analysis."
            )

        frames: list[bytes] = []
        frame_count = max(1, min(frame_count, 10))
        if use_clip and settings.frigate.clips_enabled:
            clip_bytes, clip_error = await frigate_client.get_clip_with_error(event_id)
            if clip_bytes:
                frames = ai_service.extract_frames_from_clip(clip_bytes, frame_count=frame_count)
                if not frames:
                    log.warning("clip_frame_extraction_failed", event_id=event_id)
            else:
                log.info("clip_fetch_skipped", event_id=event_id, reason=clip_error)

        image_data = None
        if not frames:
            image_data = await frigate_client.get_snapshot(event_id, crop=True, quality=90)
            if not image_data:
                raise HTTPException(
                    status_code=502,
                    detail=i18n_service.translate("errors.ai.image_fetch_failed", lang)
                )

        # Metadata for prompt
        metadata = {
            "temperature": detection.temperature,
            "weather_condition": detection.weather_condition,
            "time": detection.detection_time.strftime("%H:%M")
        }
        if frames:
            metadata["frame_count"] = len(frames)

        # Generate new analysis
        log.info("generating_new_analysis", event_id=event_id, force=force)
        analysis = await ai_service.analyze_detection(
            species=detection.display_name,
            image_data=image_data,
            metadata=metadata,
            image_list=frames if frames else None
        )

        # Save analysis to database
        await repo.update_ai_analysis(event_id, analysis)

        return AIAnalysisResponse(analysis=analysis)
