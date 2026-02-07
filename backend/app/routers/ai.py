from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from datetime import datetime, timezone
import base64
import hashlib
import json
import structlog
from app.services.ai_service import ai_service
from app.services.frigate_client import frigate_client
from app.repositories.detection_repository import DetectionRepository
from app.repositories.leaderboard_analysis_repository import LeaderboardAnalysisRepository
from app.repositories.ai_conversation_repository import AIConversationRepository
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

class LeaderboardAnalysisRequest(BaseModel):
    config: dict
    image_base64: str
    force: bool = False
    config_key: str | None = None

class LeaderboardAnalysisResponse(BaseModel):
    analysis: str
    analysis_timestamp: str


class ConversationTurnResponse(BaseModel):
    role: str
    content: str
    created_at: str


class ConversationRequest(BaseModel):
    message: str

def _compute_config_key(config: dict) -> str:
    payload = json.dumps(config, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

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

        # If regenerating analysis, clear any existing AI chat thread so the new
        # analysis starts with a fresh conversation context.
        if force:
            convo_repo = AIConversationRepository(db)
            await convo_repo.delete_turns(event_id)

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
            image_list=frames if frames else None,
            language=lang,
            mime_type="image/jpeg"
        )

        # Save analysis to database
        await repo.update_ai_analysis(event_id, analysis)

        return AIAnalysisResponse(analysis=analysis)

@router.get("/leaderboard/analysis", response_model=LeaderboardAnalysisResponse)
async def get_leaderboard_analysis(
    request: Request,
    config_key: str,
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required.")
    async with get_db() as db:
        repo = LeaderboardAnalysisRepository(db)
        entry = await repo.get_by_config_key(config_key)
        if not entry:
            raise HTTPException(status_code=404, detail="Analysis not found.")
        return LeaderboardAnalysisResponse(
            analysis=entry.analysis,
            analysis_timestamp=entry.analysis_timestamp.isoformat()
        )

@router.post("/leaderboard/analyze", response_model=LeaderboardAnalysisResponse)
async def analyze_leaderboard(
    request: Request,
    body: LeaderboardAnalysisRequest,
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required.")

    config_key = body.config_key or _compute_config_key(body.config)
    lang = get_user_language(request)

    async with get_db() as db:
        repo = LeaderboardAnalysisRepository(db)
        existing = await repo.get_by_config_key(config_key)
        if existing and not body.force:
            return LeaderboardAnalysisResponse(
                analysis=existing.analysis,
                analysis_timestamp=existing.analysis_timestamp.isoformat()
            )

        try:
            raw = body.image_base64
            mime_type = "image/png"
            if raw.startswith("data:image"):
                header, raw = raw.split(",", 1)
                header_parts = header.split(";")[0].split(":")
                if len(header_parts) == 2:
                    mime_type = header_parts[1]
            image_bytes = base64.b64decode(raw)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid image payload.")

        analysis = await ai_service.analyze_chart(image_bytes, body.config, language=lang, mime_type=mime_type)
        if not analysis:
            raise HTTPException(status_code=502, detail="AI analysis failed.")

        now = datetime.now(timezone.utc)
        await repo.upsert_analysis(config_key, body.config, analysis, now)

        return LeaderboardAnalysisResponse(
            analysis=analysis,
            analysis_timestamp=now.isoformat()
        )


@router.get("/events/{event_id}/conversation", response_model=list[ConversationTurnResponse])
async def get_event_conversation(
    event_id: str,
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required to view AI conversation.")
    async with get_db() as db:
        repo = AIConversationRepository(db)
        turns = await repo.list_turns(event_id)
    return [
        ConversationTurnResponse(
            role=turn.role,
            content=turn.content,
            created_at=turn.created_at.isoformat()
        )
        for turn in turns
    ]


@router.post("/events/{event_id}/conversation", response_model=list[ConversationTurnResponse])
async def post_event_conversation(
    event_id: str,
    request: Request,
    body: ConversationRequest,
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    if not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner access required to chat with AI.")

    lang = get_user_language(request)
    async with get_db() as db:
        detection_repo = DetectionRepository(db)
        detection = await detection_repo.get_by_frigate_event(event_id)
        if not detection:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.detection_not_found", lang)
            )

        convo_repo = AIConversationRepository(db)
        history = await convo_repo.list_turns(event_id)

        await convo_repo.add_turn(event_id, "user", body.message)

        prompt = ai_service.build_conversation_prompt(
            species=detection.display_name,
            analysis=detection.ai_analysis,
            history=[{"role": t.role, "content": t.content} for t in history],
            question=body.message,
            language=lang
        )
        reply = await ai_service.chat_detection(prompt)
        if reply:
            await convo_repo.add_turn(event_id, "assistant", reply)

        turns = await convo_repo.list_turns(event_id)
        return [
            ConversationTurnResponse(
                role=turn.role,
                content=turn.content,
                created_at=turn.created_at.isoformat()
            )
            for turn in turns
        ]
