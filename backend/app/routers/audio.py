from fastapi import APIRouter, Depends, Request, Query, HTTPException
from fastapi.responses import Response
import httpx
from datetime import datetime, timezone
import json
import structlog
from pydantic import BaseModel
import aiosqlite
from app.services.audio.audio_service import audio_service
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.config import settings
from app.auth import AuthContext
from app.auth import get_auth_context_with_legacy
from app.ratelimit import guest_rate_limit
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.utils.language import get_user_language
from app.utils.audio_localization import localize_audio_detections

router = APIRouter(prefix="/audio", tags=["audio"])
log = structlog.get_logger()


class AudioSourceResponse(BaseModel):
    source_name: str
    mapping_value: str
    last_seen: str
    sample_source_id: str | None = None
    seen_count: int = 1


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


@router.get("/recent")
@guest_rate_limit()
async def get_recent_audio(
    request: Request,
    limit: int = 10,
    auth: AuthContext = Depends(get_auth_context_with_legacy)
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
    hide_sensor = (
        not auth.is_owner
        and settings.public_access.enabled
        and not settings.public_access.show_camera_names
    )
    if hide_sensor:
        for detection in detections:
            detection["sensor_id"] = None
    return detections

@router.get("/spectrogram/{birdnet_id}")
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


@router.get("/clip/{birdnet_id}")
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
    if (range_header := request.headers.get("range")):
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

    mapping_value = None
    if camera and settings.frigate.camera_audio_mapping:
        mapping_value = settings.frigate.camera_audio_mapping.get(camera)

    lang = get_user_language(request) or "en"
    async with get_db() as db:
        repo = DetectionRepository(db)
        detections = await repo.get_audio_context(
            target_time=target_time,
            window_seconds=window_seconds,
            mapping_value=mapping_value,
            limit=limit
        )
        await localize_audio_detections(detections, lang, db)
    hide_sensor = (
        not auth.is_owner
        and settings.public_access.enabled
        and not settings.public_access.show_camera_names
    )
    if hide_sensor:
        for detection in detections:
            detection["sensor_id"] = None
    return detections


@router.get("/sources", response_model=list[AudioSourceResponse])
@guest_rate_limit()
async def get_audio_sources(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
):
    """Get recently observed BirdNET source names for camera mapping."""
    hide_sensor = (
        not auth.is_owner
        and settings.public_access.enabled
        and not settings.public_access.show_camera_names
    )

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
