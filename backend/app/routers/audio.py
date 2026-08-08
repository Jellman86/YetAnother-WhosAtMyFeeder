from fastapi import APIRouter, Depends, Request, Query, HTTPException, Path as ApiPath
from fastapi.responses import Response
import httpx
from datetime import date, datetime, timedelta, timezone
import json
import structlog
from pydantic import BaseModel
from typing import Literal
from app.services.audio.audio_service import audio_service
from app.config import settings
from app.auth import AuthContext
from app.auth import get_auth_context_with_legacy
from app.ratelimit import guest_rate_limit
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository, match_audio_history_visual_events
from app.utils.language import get_user_language
from app.utils.audio_localization import localize_audio_detections
from app.utils.canonical_species import should_hide_species_label
from app.utils.api_datetime import serialize_api_datetime
from app.utils.public_access import effective_public_events_days

router = APIRouter(prefix="/audio", tags=["audio"])
log = structlog.get_logger()
AUDIO_SUPPRESSED_BY_MAPPING_HEADER = "X-YAWAMF-Audio-Suppressed-By-Mapping"
AUDIO_CONTEXT_RESPONSE_METADATA = {
    200: {
        "headers": {
            AUDIO_SUPPRESSED_BY_MAPPING_HEADER: {
                "description": "Audio detections in the window excluded by the camera mapping.",
                "schema": {"type": "integer", "minimum": 0},
            }
        }
    }
}


class AudioSourceResponse(BaseModel):
    source_name: str
    mapping_value: str
    last_seen: str
    sample_source_id: str | None = None
    seen_count: int = 1


class AudioDetectionResponse(BaseModel):
    timestamp: str
    species: str
    confidence: float
    sensor_id: str | None = None
    source_name: str | None = None
    birdnet_id: int | None = None


class AudioHistoryDetectionResponse(AudioDetectionResponse):
    id: int
    matched_visual_event_id: str | None = None


class AudioHistoryResponse(BaseModel):
    items: list[AudioHistoryDetectionResponse]
    total: int
    limit: int
    offset: int


class AudioSpeciesSummaryResponse(BaseModel):
    species: str
    count: int
    avg_confidence: float
    max_confidence: float
    first_heard: str | None = None
    last_heard: str | None = None


class AudioDailyCountResponse(BaseModel):
    date: str
    count: int


class AudioHourlyCountResponse(BaseModel):
    hour: int
    count: int


class AudioSourceSummaryResponse(BaseModel):
    source_name: str
    count: int
    last_heard: str


class AudioSummaryResponse(BaseModel):
    total: int
    species_count: int
    source_count: int
    top_species: list[AudioSpeciesSummaryResponse]
    daily_counts: list[AudioDailyCountResponse]
    hourly_counts: list[AudioHourlyCountResponse]
    sources: list[AudioSourceSummaryResponse]


class AudioSpeciesLeaderboardItemResponse(BaseModel):
    species: str
    scientific_name: str | None = None
    heard_count: int
    heard_prev_count: int
    heard_delta: int
    heard_percent: float
    avg_confidence: float
    last_heard: str | None = None


class AudioSpeciesLeaderboardResponse(BaseModel):
    span: Literal["day", "week", "month", "all"]
    window_start: str
    window_end: str
    species: list[AudioSpeciesLeaderboardItemResponse]


class AudioContextDetectionResponse(AudioDetectionResponse):
    offset_seconds: int


class AudioHistoryQuery(BaseModel):
    start_date: datetime | None
    end_date: datetime | None


def _history_window(days: int, start_date: datetime | None, end_date: datetime | None) -> AudioHistoryQuery:
    resolved_end = end_date
    if resolved_end is None:
        resolved_end = datetime.now(timezone.utc)
    elif resolved_end.tzinfo is None:
        resolved_end = resolved_end.replace(tzinfo=timezone.utc)

    resolved_start = start_date
    if resolved_start is None:
        resolved_start = resolved_end - timedelta(days=days)
    elif resolved_start.tzinfo is None:
        resolved_start = resolved_start.replace(tzinfo=timezone.utc)

    return AudioHistoryQuery(start_date=resolved_start, end_date=resolved_end)


def _parse_audio_source_fields(raw_data: str | None, stored_sensor_id: str | None) -> tuple[str | None, str | None]:
    source_name = None
    sample_source_id = None

    if raw_data:
        try:
            payload = json.loads(raw_data)
            if isinstance(payload, dict):
                source = payload.get("Source")
                source = source if isinstance(source, dict) else {}

                for candidate in (
                    payload.get("nm"),
                    payload.get("sourceName"),
                    source.get("displayName"),
                    stored_sensor_id,
                ):
                    if isinstance(candidate, str) and candidate.strip():
                        source_name = candidate.strip()
                        break

                for candidate in (payload.get("src"), payload.get("sourceId"), source.get("id")):
                    if isinstance(candidate, str) and candidate.strip():
                        sample_source_id = candidate.strip()
                        break
        except Exception:
            # Ignore malformed raw_data and fall back to stored value.
            pass

    if not source_name and isinstance(stored_sensor_id, str) and stored_sensor_id.strip():
        source_name = stored_sensor_id.strip()

    if not source_name and sample_source_id:
        source_name = sample_source_id

    return source_name, sample_source_id


@router.get("/recent", response_model=list[AudioDetectionResponse])
@guest_rate_limit()
async def get_recent_audio(
    request: Request, limit: int = 10, auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Get the most recent audio detections from the memory buffer."""
    detections = await audio_service.get_recent_detections(limit=limit)
    lang = get_user_language(request) or "en"
    async with get_db() as db:
        await localize_audio_detections(detections, lang, db)
    # Drop scientific_name from the response — it is an internal hook for localization
    # and is not part of the public Recent Audio contract.
    for detection in detections:
        detection.pop("scientific_name", None)
    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names
    if hide_sensor:
        for detection in detections:
            detection["sensor_id"] = None
    return detections


@router.get("/history", response_model=AudioHistoryResponse)
@guest_rate_limit()
async def get_audio_history(
    request: Request,
    days: int = Query(default=30, ge=1, le=3650),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    species: str | None = Query(default=None, max_length=120),
    source: str | None = Query(default=None, max_length=120),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
):
    """Browse persisted BirdNET-Go detections separately from visual detections."""
    window = _history_window(days, start_date, end_date)
    lang = get_user_language(request) or "en"
    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names

    async with get_db() as db:
        repo = DetectionRepository(db)
        result = await repo.get_audio_history(
            start_date=window.start_date,
            end_date=window.end_date,
            species=species,
            source=source,
            min_confidence=min_confidence,
            limit=limit,
            offset=offset,
        )
        if result["items"]:
            correlation_window = max(0, int(settings.frigate.audio_correlation_window_seconds))
            item_times: list[datetime] = []
            for item in result["items"]:
                item_time = datetime.fromisoformat(item["timestamp"])
                item_times.append(
                    item_time.replace(tzinfo=timezone.utc)
                    if item_time.tzinfo is None
                    else item_time.astimezone(timezone.utc)
                )
            candidate_start = min(item_times) - timedelta(seconds=correlation_window)
            candidate_end = max(item_times) + timedelta(seconds=correlation_window)
            if not auth.is_owner and settings.public_access.enabled:
                public_days = effective_public_events_days()
                cutoff_date = date.today() - timedelta(days=public_days) if public_days > 0 else date.today()
                public_cutoff = datetime.combine(cutoff_date, datetime.min.time(), tzinfo=timezone.utc)
                candidate_start = max(candidate_start, public_cutoff)
            candidates = await repo.get_audio_visual_match_candidates(
                start_date=candidate_start,
                end_date=candidate_end,
                scientific_names={item["scientific_name"] for item in result["items"] if item.get("scientific_name")},
            )
            matches = match_audio_history_visual_events(
                result["items"],
                candidates,
                window_seconds=correlation_window,
                camera_audio_mapping=settings.frigate.camera_audio_mapping,
            )
            for item in result["items"]:
                item["matched_visual_event_id"] = matches.get(item["id"])
        await localize_audio_detections(result["items"], lang, db)

    for detection in result["items"]:
        detection.pop("scientific_name", None)
        detection.pop("_mapping_keys", None)
        if hide_sensor:
            detection["sensor_id"] = None
            detection["source_name"] = None

    return result


@router.get("/summary", response_model=AudioSummaryResponse)
@guest_rate_limit()
async def get_audio_summary(
    request: Request,
    days: int = Query(default=30, ge=1, le=3650),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    species: str | None = Query(default=None, max_length=120),
    source: str | None = Query(default=None, max_length=120),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
):
    """Summarise persisted BirdNET-Go detection history."""
    window = _history_window(days, start_date, end_date)
    lang = get_user_language(request) or "en"
    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names

    async with get_db() as db:
        repo = DetectionRepository(db)
        result = await repo.get_audio_history_summary(
            start_date=window.start_date,
            end_date=window.end_date,
            species=species,
            source=source,
            min_confidence=min_confidence,
        )
        await localize_audio_detections(result["top_species"], lang, db)

    for item in result["top_species"]:
        item.pop("scientific_name", None)
    if hide_sensor:
        result["sources"] = []
        result["source_count"] = 0

    return result


def _leaderboard_window(span: str) -> tuple[datetime, datetime, datetime, datetime]:
    """Rolling window + prior window for the audio leaderboard, aligned to the
    visual leaderboard spans in ``routers/species.py`` (day=24h, week=7d,
    month=30d). ``all`` collapses the lower bound to the epoch so every stored
    detection counts and the prior window contributes nothing."""
    now = datetime.now(timezone.utc)
    if span == "all":
        window_start = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return window_start, now, window_start, window_start
    if span == "day":
        window = timedelta(hours=24)
    elif span == "week":
        window = timedelta(days=7)
    else:
        window = timedelta(days=30)
    window_start = now - window
    return window_start, now, window_start - window, window_start


@router.get("/species", response_model=AudioSpeciesLeaderboardResponse)
@guest_rate_limit()
async def get_audio_species_leaderboard(
    request: Request,
    span: Literal["day", "week", "month", "all"] = Query(default="week"),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
):
    """Heard-count leaderboard over persisted BirdNET-Go detections.

    Returns one row per species (grouped by scientific name where available) with the
    current-window heard count plus the prior window for trend, so the Species page can
    merge these onto the camera "seen" leaderboard. Species names are localized through
    the same taxonomy path as the visual leaderboard so client-side matching lines up.
    """
    window_start, window_end, prev_start, prev_end = _leaderboard_window(span)
    lang = get_user_language(request) or "en"
    unknown_labels = getattr(settings.classification, "unknown_bird_labels", None) or []

    async with get_db() as db:
        repo = DetectionRepository(db)
        rows = await repo.get_audio_species_counts(
            window_start=window_start,
            window_end=window_end,
            prev_start=prev_start,
            prev_end=prev_end,
        )
        await localize_audio_detections(rows, lang, db)

    species: list[dict] = []
    for row in rows:
        name = row.get("species")
        if not name or name in unknown_labels or should_hide_species_label(name):
            continue
        if row["window_count"] <= 0:
            continue
        prev_count = row["prev_count"]
        delta = row["window_count"] - prev_count
        percent = (delta / prev_count) * 100.0 if prev_count > 0 else 0.0
        species.append(
            {
                "species": name,
                "scientific_name": row.get("scientific_name"),
                "heard_count": row["window_count"],
                "heard_prev_count": prev_count,
                "heard_delta": delta,
                "heard_percent": percent,
                "avg_confidence": row.get("window_avg_confidence", 0.0),
                "last_heard": serialize_api_datetime(row.get("window_last_heard")),
            }
        )

    species.sort(key=lambda x: int(x.get("heard_count") or 0), reverse=True)

    return {
        "span": span,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "species": species,
    }


@router.get("/spectrogram/{birdnet_id}", response_class=Response)
async def get_audio_spectrogram(
    birdnet_id: int,
    width: int = Query(default=400, ge=64, le=1600),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
):
    """Proxy a BirdNET-Go spectrogram PNG so the browser does not need a
    direct route to the BirdNET-Go host.

    Cached for a day client-side. BirdNET-Go itself returns the image with
    a 30-day immutable cache header — we keep ours shorter so YA-WAMF can
    invalidate by changing birdnet_url without long-lived stale URLs.
    """
    base_url = (settings.frigate.birdnet_url or "").rstrip("/")
    if not base_url:
        raise HTTPException(status_code=503, detail="BirdNET-Go URL not configured")
    if birdnet_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid detection id")
    target = f"{base_url}/api/v2/spectrogram/{birdnet_id}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(target, params={"width": width})
    except httpx.HTTPError as exc:
        log.warning("birdnet_spectrogram_proxy_failed", id=birdnet_id, error=str(exc))
        raise HTTPException(status_code=502, detail="BirdNET-Go unreachable")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Spectrogram not found")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"BirdNET-Go returned {response.status_code}")
    media_type = response.headers.get("content-type", "image/png")
    return Response(
        content=response.content,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.get("/clip/{birdnet_id}", response_class=Response)
async def get_audio_clip(
    birdnet_id: int,
    request: Request,
    auth: AuthContext = Depends(get_auth_context_with_legacy),
):
    """Proxy a BirdNET-Go audio clip so the browser can play the matched
    audio inline in the detection modal.

    Forwards the client's Range header so HTML5 ``<audio controls>`` can
    scrub. Clips are typically ~250 KB AAC/m4a; buffered in memory rather
    than streamed because the size is bounded and the existing Frigate
    proxy uses the same shape.
    """
    base_url = (settings.frigate.birdnet_url or "").rstrip("/")
    if not base_url:
        raise HTTPException(status_code=503, detail="BirdNET-Go URL not configured")
    if birdnet_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid detection id")
    target = f"{base_url}/api/v2/audio/{birdnet_id}"
    forward_headers: dict[str, str] = {}
    if range_header := request.headers.get("range"):
        forward_headers["Range"] = range_header
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(target, headers=forward_headers)
    except httpx.HTTPError as exc:
        log.warning("birdnet_clip_proxy_failed", id=birdnet_id, error=str(exc))
        raise HTTPException(status_code=502, detail="BirdNET-Go unreachable")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Audio clip not found")
    if response.status_code >= 400 and response.status_code != 206:
        raise HTTPException(status_code=502, detail=f"BirdNET-Go returned {response.status_code}")
    # Pass through everything an audio element needs to scrub: status code
    # (200 vs 206), Content-Type, Content-Length, Accept-Ranges, Content-Range.
    media_type = response.headers.get("content-type", "audio/mp4")
    pass_through = {}
    for h in ("accept-ranges", "content-range", "content-length", "content-disposition"):
        if h in response.headers:
            pass_through[h.title()] = response.headers[h]
    pass_through["Cache-Control"] = "private, max-age=86400"
    return Response(
        content=response.content,
        media_type=media_type,
        status_code=response.status_code,
        headers=pass_through,
    )


@router.get(
    "/context",
    response_model=list[AudioContextDetectionResponse],
    responses=AUDIO_CONTEXT_RESPONSE_METADATA,
)
@guest_rate_limit()
async def get_audio_context(
    request: Request,
    response: Response,
    timestamp: datetime = Query(..., description="ISO timestamp for the visual detection"),
    camera: str | None = Query(default=None, description="Camera name for sensor mapping"),
    window_seconds: int = Query(default=300, ge=5, le=3600),
    limit: int = Query(default=5, ge=1, le=20),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
):
    """Get audio detections near a specific detection time."""
    target_time = timestamp
    if target_time.tzinfo is None:
        target_time = target_time.replace(tzinfo=timezone.utc)

    mapping_value = None
    if camera and settings.frigate.camera_audio_mapping:
        mapping_value = settings.frigate.camera_audio_mapping.get(camera)

    lang = get_user_language(request) or "en"
    async with get_db() as db:
        repo = DetectionRepository(db)
        detections, suppressed_by_mapping = await repo.get_audio_context(
            target_time=target_time, window_seconds=window_seconds, mapping_value=mapping_value, limit=limit
        )
        await localize_audio_detections(detections, lang, db)
    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names
    if hide_sensor:
        for detection in detections:
            detection["sensor_id"] = None
    response.headers[AUDIO_SUPPRESSED_BY_MAPPING_HEADER] = str(suppressed_by_mapping)
    return detections


@router.get(
    "/context/event/{event_id}",
    response_model=list[AudioContextDetectionResponse],
    responses=AUDIO_CONTEXT_RESPONSE_METADATA,
)
@guest_rate_limit()
async def get_event_audio_context(
    request: Request,
    response: Response,
    event_id: str = ApiPath(..., min_length=1, max_length=255),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
):
    """Get BirdNET-Go detections near a persisted visual event.

    Event-scoped lookup ensures the server's current source mapping and
    correlation window are applied even when audio arrived after the visual
    event's ingest-time correlation attempt.
    """
    lang = get_user_language(request) or "en"
    async with get_db() as db:
        repo = DetectionRepository(db)
        event = await repo.get_by_frigate_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Detection not found")

        if not auth.is_owner and settings.public_access.enabled:
            event_date = event.detection_time.date()
            public_days = effective_public_events_days()
            cutoff_date = date.today() - timedelta(days=public_days)
            outside_public_history = event_date < cutoff_date if public_days > 0 else event_date != date.today()
            if event.is_hidden or outside_public_history:
                raise HTTPException(status_code=404, detail="Detection not found")

        mapping_value = None
        if settings.frigate.camera_audio_mapping:
            mapping_value = settings.frigate.camera_audio_mapping.get(event.camera_name)

        detections, suppressed_by_mapping = await repo.get_audio_context(
            target_time=event.detection_time,
            window_seconds=settings.frigate.audio_correlation_window_seconds,
            mapping_value=mapping_value,
            limit=8,
        )
        await localize_audio_detections(detections, lang, db)

    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names
    if hide_sensor:
        for detection in detections:
            detection["sensor_id"] = None
    response.headers[AUDIO_SUPPRESSED_BY_MAPPING_HEADER] = str(suppressed_by_mapping)
    return detections


@router.get("/sources", response_model=list[AudioSourceResponse])
@guest_rate_limit()
async def get_audio_sources(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
):
    """Get recently observed BirdNET source names for camera mapping."""
    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names

    async with get_db() as db:
        repo = DetectionRepository(db)
        # Fetch more rows than requested to support deduplication by source_name.
        rows = await repo.get_recent_audio_source_observations(limit=max(limit * 10, 50))

    sources: dict[str, AudioSourceResponse] = {}
    ordered_keys: list[str] = []
    for row in rows:
        source_name, sample_source_id = _parse_audio_source_fields(row.get("raw_data"), row.get("sensor_id"))
        if not source_name:
            continue
        if source_name in sources:
            sources[source_name].seen_count += 1
            if not sources[source_name].sample_source_id and sample_source_id:
                sources[source_name].sample_source_id = sample_source_id
            continue

        if len(ordered_keys) >= limit:
            continue

        if source_name not in sources:
            ordered_keys.append(source_name)
            sources[source_name] = AudioSourceResponse(
                source_name=source_name,
                mapping_value=source_name,
                last_seen=str(row.get("timestamp")),
                sample_source_id=sample_source_id,
                seen_count=1,
            )

    result = [sources[key] for key in ordered_keys[:limit]]
    if hide_sensor:
        return []
    return result
