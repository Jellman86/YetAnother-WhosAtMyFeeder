from fastapi import APIRouter, Depends, Request, Query
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

router = APIRouter(prefix="/audio", tags=["audio"])
log = structlog.get_logger()


class AudioSourceResponse(BaseModel):
    source_name: str
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

                for candidate in (payload.get("nm"), source.get("displayName"), stored_sensor_id):
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

async def _localize_audio_species(
    detections: list[dict],
    lang: str,
    db: aiosqlite.Connection,
) -> None:
    """In-place: override locale-dependent `species` with the canonical English name
    (or localized translation for non-English) resolved via `taxonomy_cache`.

    BirdNET-Go publishes `comName` in whichever language it is configured for, which
    then flows into `species`. For YA-WAMF's display locale we want the name the user
    expects — mirroring the response-time transform already applied to species and
    leaderboard endpoints in fix for issue #46.
    """
    taxa_id_cache: dict[str, int | None] = {}
    for d in detections:
        scientific = (d.get("scientific_name") or "").strip()
        if not scientific:
            continue

        if scientific in taxa_id_cache:
            taxa_id = taxa_id_cache[scientific]
        else:
            try:
                taxonomy = await taxonomy_service._query_cache(db, scientific)
                taxa_id = taxonomy.get("taxa_id") if taxonomy else None
            except Exception as exc:
                log.warning("Audio taxonomy cache lookup failed", scientific=scientific, error=str(exc))
                taxa_id = None
            taxa_id_cache[scientific] = taxa_id

        if not taxa_id:
            continue

        try:
            if lang != "en":
                resolved = await taxonomy_service.get_localized_common_name(int(taxa_id), lang, db=db)
            else:
                resolved = await taxonomy_service.get_canonical_english_name(int(taxa_id), db=db)
        except Exception as exc:
            log.warning("Audio name localization failed", scientific=scientific, lang=lang, error=str(exc))
            resolved = None

        if resolved:
            d["species"] = resolved


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
        await _localize_audio_species(detections, lang, db)
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
        await _localize_audio_species(detections, lang, db)
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
                last_seen=str(row.get("timestamp")),
                sample_source_id=sample_source_id,
                seen_count=1,
            )

    result = [sources[key] for key in ordered_keys[:limit]]
    if hide_sensor:
        return []
    return result
