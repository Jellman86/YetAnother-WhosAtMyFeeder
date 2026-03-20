import asyncio
import time
import unicodedata
from fastapi import APIRouter, HTTPException, Query, Request, Depends
from typing import List, Optional, Literal
from datetime import datetime, date, timedelta
from io import BytesIO
from pydantic import BaseModel, Field
import structlog
from PIL import Image

from app.database import get_db
from app.models import DetectionResponse
from app.repositories.detection_repository import DetectionRepository
from app.config import settings
from app.services.classifier_service import get_classifier
from app.services.frigate_client import frigate_client
from app.services.high_quality_snapshot_service import high_quality_snapshot_service
from app.services.broadcaster import broadcaster
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.services.audio.audio_service import audio_service
from app.services.i18n_service import i18n_service
from app.utils.language import get_user_language
from app.auth import require_owner, AuthContext
from app.auth import get_auth_context_with_legacy
from app.ratelimit import guest_rate_limit
from app.utils.public_access import effective_public_events_days

router = APIRouter()
log = structlog.get_logger()


CLIP_CHECK_CONCURRENCY = 10
LOCALIZED_NAME_CONCURRENCY = 5
EVENT_FILTERS_CACHE_TTL_SECONDS = 60
UNKNOWN_BIRD_FILTER_ALIAS = "alias:unknown_bird"
UNKNOWN_BIRD_DISPLAY_LABEL = "Unknown Bird"


def parse_species_filter(species: Optional[str]) -> tuple[Optional[str], Optional[int]]:
    """Parse species filter into display_name or taxa_id."""
    if not species:
        return None, None
    if species.startswith("taxa:"):
        try:
            return None, int(species.split(":", 1)[1])
        except ValueError:
            return species, None
    return species, None


def resolve_species_display_filter_aliases(
    species_name: Optional[str],
    taxa_id: Optional[int],
) -> tuple[Optional[str], Optional[list[str]]]:
    """Map UI display aliases (e.g. 'Unknown Bird') to underlying stored labels."""
    if taxa_id is not None or not species_name:
        return species_name, None
    normalized_species = _normalize_species_name(species_name)
    if (
        species_name != UNKNOWN_BIRD_FILTER_ALIAS
        and normalized_species != _normalize_species_name(UNKNOWN_BIRD_DISPLAY_LABEL)
    ):
        return species_name, None

    aliases: list[str] = []
    seen: set[str] = set()
    for candidate in [UNKNOWN_BIRD_DISPLAY_LABEL, *(settings.classification.unknown_bird_labels or [])]:
        value = str(candidate or "").strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(value)

    if not aliases:
        aliases = [UNKNOWN_BIRD_DISPLAY_LABEL]
    return None, aliases


def _normalize_species_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKD", str(value)).casefold()
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = " ".join(normalized.split())
    return normalized or None


def _manual_update_is_alias_noop(detection, requested_species: str, resolved_aliases: dict) -> bool:
    """Return True when manual tag request is only a label-style/localization alias."""
    requested_norm = _normalize_species_name(requested_species)
    existing_names = {
        _normalize_species_name(getattr(detection, "display_name", None)),
        _normalize_species_name(getattr(detection, "category_name", None)),
        _normalize_species_name(getattr(detection, "scientific_name", None)),
        _normalize_species_name(getattr(detection, "common_name", None)),
    }
    existing_names.discard(None)

    if requested_norm and requested_norm in existing_names:
        return True

    existing_taxa_id = getattr(detection, "taxa_id", None)
    resolved_taxa_id = resolved_aliases.get("taxa_id")
    if existing_taxa_id is not None and resolved_taxa_id is not None and existing_taxa_id == resolved_taxa_id:
        return True

    resolved_scientific = _normalize_species_name(resolved_aliases.get("scientific_name"))
    existing_scientific = _normalize_species_name(getattr(detection, "scientific_name", None))
    if resolved_scientific and existing_scientific and resolved_scientific == existing_scientific:
        return True

    alias_match_names = {
        _normalize_species_name(name)
        for name in (resolved_aliases.get("match_names") or [])
    }
    alias_match_names.discard(None)
    if (
        alias_match_names
        and alias_match_names.intersection(existing_names)
        and existing_taxa_id is None
        and resolved_taxa_id is None
        and not existing_scientific
        and not resolved_scientific
    ):
        return True

    return False

def _get_active_model_id_for_feedback() -> str:
    try:
        from app.services.model_manager import model_manager

        active_model_id = str(getattr(model_manager, "active_model_id", "") or "").strip()
        if active_model_id:
            return active_model_id
    except Exception:
        pass

    configured_model = str(getattr(settings.classification, "model", "") or "").strip()
    return configured_model or "unknown"


def _video_classification_model_name(model_id: str | None) -> str | None:
    normalized = str(model_id or "").strip()
    if not normalized:
        return None
    try:
        from app.services.model_manager import REMOTE_REGISTRY

        model_meta = next((m for m in REMOTE_REGISTRY if m["id"] == normalized), None)
    except Exception:
        model_meta = None
    if not model_meta:
        return None
    name = str(model_meta.get("name") or "").strip()
    return name or None


async def batch_check_clips(event_ids: list[str]) -> dict[str, dict[str, bool]]:
    """
    Check Frigate event/media availability for multiple events.
    Returns a dict mapping event_id -> availability flags.
    """
    if not event_ids:
        return {}

    semaphore = asyncio.Semaphore(CLIP_CHECK_CONCURRENCY)

    async def check(event_id: str) -> tuple[str, dict[str, bool]]:
        async with semaphore:
            try:
                event_data = await frigate_client.get_event(event_id)
                if not event_data:
                    return event_id, {
                        "has_frigate_event": False,
                        "has_clip": False,
                        "has_snapshot": False,
                    }
                return event_id, {
                    "has_frigate_event": True,
                    "has_clip": bool(event_data.get("has_clip", False)),
                    "has_snapshot": bool(event_data.get("has_snapshot", True)),
                }
            except Exception:
                return event_id, {
                    "has_frigate_event": False,
                    "has_clip": False,
                    "has_snapshot": False,
                }

    results = await asyncio.gather(*(check(event_id) for event_id in event_ids))
    return dict(results)


def _detection_updated_payload(detection, overrides: dict | None = None) -> dict:
    payload = {
        "frigate_event": detection.frigate_event,
        "display_name": detection.display_name,
        "score": detection.score,
        "timestamp": detection.detection_time.isoformat(),
        "camera": detection.camera_name,
        "is_hidden": detection.is_hidden,
        "is_favorite": detection.is_favorite,
        "frigate_score": detection.frigate_score,
        "sub_label": detection.sub_label,
        "manual_tagged": detection.manual_tagged,
        "audio_confirmed": detection.audio_confirmed,
        "audio_species": detection.audio_species,
        "audio_score": detection.audio_score,
        "temperature": detection.temperature,
        "weather_condition": detection.weather_condition,
        "weather_cloud_cover": detection.weather_cloud_cover,
        "weather_wind_speed": detection.weather_wind_speed,
        "weather_wind_direction": detection.weather_wind_direction,
        "weather_precipitation": detection.weather_precipitation,
        "weather_rain": detection.weather_rain,
        "weather_snowfall": detection.weather_snowfall,
        "scientific_name": detection.scientific_name,
        "common_name": detection.common_name,
        "taxa_id": detection.taxa_id,
        "video_classification_score": detection.video_classification_score,
        "video_classification_label": detection.video_classification_label,
        "video_classification_status": detection.video_classification_status,
        "video_classification_error": detection.video_classification_error,
        "video_classification_provider": detection.video_classification_provider,
        "video_classification_backend": detection.video_classification_backend,
        "video_classification_model_id": detection.video_classification_model_id,
        "video_classification_model_name": _video_classification_model_name(detection.video_classification_model_id),
        "video_classification_timestamp": detection.video_classification_timestamp.isoformat() if detection.video_classification_timestamp else None,
    }
    if overrides:
        payload.update(overrides)
    return payload

# get_classifier is now imported from classifier_service


class EventFilterSpecies(BaseModel):
    """Species filter option with taxonomy data."""
    value: str
    display_name: str
    scientific_name: Optional[str] = None
    common_name: Optional[str] = None
    taxa_id: Optional[int] = None


class EventFilters(BaseModel):
    """Available filter options for events."""
    species: List[EventFilterSpecies]
    cameras: List[str]


_event_filters_cache: dict[tuple[str, bool], tuple[float, EventFilters]] = {}


class EventsCountResponse(BaseModel):
    """Response for events count endpoint."""
    count: int
    filtered: bool


@router.get("/events/filters", response_model=EventFilters)
@guest_rate_limit()
async def get_event_filters(
    request: Request,
    force_refresh: bool = Query(
        default=False,
        description="Bypass short-lived filter cache and fetch fresh species/camera options"
    ),
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Get available filter options (species and cameras) from the database."""
    hide_camera_names = (
        not auth.is_owner
        and settings.public_access.enabled
        and not settings.public_access.show_camera_names
    )
    lang = get_user_language(request)
    cache_key = (lang, hide_camera_names)
    now = time.monotonic()
    if not force_refresh:
        cached = _event_filters_cache.get(cache_key)
        if cached and (now - cached[0]) < EVENT_FILTERS_CACHE_TTL_SECONDS:
            return cached[1]
    async with get_db() as db:
        repo = DetectionRepository(db)
        species_rows = await repo.get_unique_species_with_taxonomy()
        cameras = [] if hide_camera_names else await repo.get_unique_cameras()
        unknown_label_keys = {
            key
            for key in (
                _normalize_species_name(UNKNOWN_BIRD_DISPLAY_LABEL),
                *(_normalize_species_name(v) for v in (settings.classification.unknown_bird_labels or [])),
            )
            if key
        }

        semaphore = asyncio.Semaphore(LOCALIZED_NAME_CONCURRENCY)
        species_options: list[EventFilterSpecies] = []

        async def resolve_species(row: tuple[str, Optional[str], Optional[str], Optional[int]]) -> EventFilterSpecies:
            display_name, scientific_name, common_name, taxa_id = row
            if _normalize_species_name(display_name) in unknown_label_keys:
                return EventFilterSpecies(
                    value=UNKNOWN_BIRD_FILTER_ALIAS,
                    display_name=UNKNOWN_BIRD_DISPLAY_LABEL,
                    scientific_name=None,
                    common_name=None,
                    taxa_id=None,
                )
            async with semaphore:
                taxonomy = await taxonomy_service.get_names(display_name)
                sci_name = scientific_name or taxonomy.get("scientific_name") or display_name
                com_name = common_name or taxonomy.get("common_name")
                t_id = taxa_id or taxonomy.get("taxa_id")
                if lang != "en" and t_id:
                    localized = await taxonomy_service.get_localized_common_name(t_id, lang, db=db)
                    if localized:
                        com_name = localized
                value = f"taxa:{t_id}" if t_id else display_name
                return EventFilterSpecies(
                    value=value,
                    display_name=sci_name or display_name,
                    scientific_name=sci_name,
                    common_name=com_name,
                    taxa_id=t_id
                )

        if species_rows:
            resolved = await asyncio.gather(*(resolve_species(row) for row in species_rows))
        else:
            resolved = []

        # Deduplicate by taxa_id when available; fallback to display_name
        seen: set[str] = set()
        for item in resolved:
            key = f"taxa:{item.taxa_id}" if item.taxa_id else item.value.lower()
            if key in seen:
                continue
            seen.add(key)
            species_options.append(item)

        result = EventFilters(species=species_options, cameras=cameras)
        _event_filters_cache[cache_key] = (now, result)
        return result


@router.get("/events", response_model=List[DetectionResponse])
@guest_rate_limit()
async def get_events(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500, description="Number of events to return"),
    offset: int = Query(default=0, ge=0, description="Number of events to skip"),
    start_date: Optional[date] = Query(default=None, description="Filter events from this date (inclusive)"),
    end_date: Optional[date] = Query(default=None, description="Filter events until this date (inclusive)"),
    species: Optional[str] = Query(default=None, description="Filter by species name"),
    camera: Optional[str] = Query(default=None, description="Filter by camera name"),
    favorites: bool = Query(default=False, description="Only return favorited detections"),
    audio_confirmed_only: bool = Query(default=False, description="Only return detections with audio confirmation"),
    sort: Literal["newest", "oldest", "confidence"] = Query(default="newest", description="Sort order"),
    include_hidden: bool = Query(default=False, description="Include hidden/ignored detections"),
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Get paginated events with optional filters.

    Public users see limited historical data based on settings.
    """
    lang = get_user_language(request)
    hide_camera_names = (
        not auth.is_owner
        and settings.public_access.enabled
        and not settings.public_access.show_camera_names
    )

    # Apply public access restrictions
    if not auth.is_owner and settings.public_access.enabled:
        # Restrict historical data for guests
        max_days = effective_public_events_days()
        if max_days > 0:
            cutoff_date = date.today() - timedelta(days=max_days)
            if start_date is None or start_date < cutoff_date:
                start_date = cutoff_date
        else:
            # Only show today's data
            start_date = date.today()
            end_date = date.today()

        # Limit result count for guests
        limit = min(limit, 50)

        # Never show hidden detections to guests
        include_hidden = False

        # Prevent camera-based filtering if camera names are hidden
        if hide_camera_names:
            camera = None

    async with get_db() as db:
        repo = DetectionRepository(db)

        # Convert dates to datetime for filtering
        start_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
        end_datetime = datetime.combine(end_date, datetime.max.time()) if end_date else None

        species_name, taxa_id = parse_species_filter(species)
        species_name, species_aliases = resolve_species_display_filter_aliases(species_name, taxa_id)
        events = await repo.get_all(
            limit=limit,
            offset=offset,
            start_date=start_datetime,
            end_date=end_datetime,
            species=species_name,
            species_any=species_aliases,
            taxa_id=taxa_id,
            camera=camera,
            sort=sort,
            include_hidden=include_hidden,
            favorite_only=favorites,
            audio_confirmed_only=audio_confirmed_only
        )

        # Batch fetch clip availability from Frigate (eliminates N individual HEAD requests)
        event_ids = [e.frigate_event for e in events]
        clip_availability = await batch_check_clips(event_ids)

        # Get labels that should be displayed as "Unknown Bird"
        unknown_labels = settings.classification.unknown_bird_labels

        # Preload localized names for this page to avoid per-row network calls.
        localized_names: dict[int, str] = {}
        if lang != 'en':
            taxa_ids = {event.taxa_id for event in events if event.taxa_id}
            if taxa_ids:
                semaphore = asyncio.Semaphore(LOCALIZED_NAME_CONCURRENCY)

                async def lookup(taxa_id: int) -> tuple[int, str | None]:
                    async with semaphore:
                        name = await taxonomy_service.get_localized_common_name(taxa_id, lang, db=db)
                        return taxa_id, name

                results = await asyncio.gather(*(lookup(taxa_id) for taxa_id in taxa_ids))
                localized_names = {taxa_id: name for taxa_id, name in results if name}

        audio_context_species_by_event: dict[str, list[str]] = {}
        for event in events:
            if event.audio_confirmed or not event.audio_species:
                continue

            mapping_value = None
            if settings.frigate.camera_audio_mapping:
                mapping_value = settings.frigate.camera_audio_mapping.get(event.camera_name)

            nearby_audio = await repo.get_audio_context(
                target_time=event.detection_time,
                window_seconds=settings.frigate.audio_correlation_window_seconds,
                mapping_value=mapping_value,
                limit=8,
            )

            seen_species: set[str] = set()
            ordered_species: list[str] = []

            primary_heard = str(event.audio_species or "").strip()
            if primary_heard:
                ordered_species.append(primary_heard)
                seen_species.add(primary_heard.casefold())

            for item in nearby_audio:
                species_name = str(item.get("species") or "").strip()
                if not species_name:
                    continue
                species_key = species_name.casefold()
                if species_key in seen_species:
                    continue
                seen_species.add(species_key)
                ordered_species.append(species_name)
                if len(ordered_species) >= 4:
                    break

            if ordered_species:
                audio_context_species_by_event[event.frigate_event] = ordered_species

        # Convert to response models with clip info
        response_events = []
        for event in events:
            # Transform unknown bird labels for display
            display_name = event.display_name
            if display_name in unknown_labels:
                display_name = UNKNOWN_BIRD_DISPLAY_LABEL

            common_name = event.common_name
            # Fetch localized common name if not in English and we have a taxa_id
            if lang != 'en' and event.taxa_id:
                localized_name = localized_names.get(event.taxa_id)
                if localized_name:
                    common_name = localized_name

            response_event = DetectionResponse(
                id=event.id,
                detection_time=event.detection_time,
                detection_index=event.detection_index,
                score=event.score,
                display_name=display_name,
                category_name=event.category_name,
                frigate_event=event.frigate_event,
                camera_name="Hidden" if hide_camera_names else event.camera_name,
                has_clip=clip_availability.get(event.frigate_event, {}).get("has_clip", False),
                has_snapshot=clip_availability.get(event.frigate_event, {}).get("has_snapshot", False),
                has_frigate_event=clip_availability.get(event.frigate_event, {}).get("has_frigate_event", False),
                is_hidden=event.is_hidden,
                is_favorite=event.is_favorite,
                frigate_score=event.frigate_score,
                sub_label=event.sub_label,
                manual_tagged=event.manual_tagged,
                audio_confirmed=event.audio_confirmed,
                audio_species=event.audio_species,
                audio_score=event.audio_score,
                audio_context_species=audio_context_species_by_event.get(event.frigate_event),
                temperature=event.temperature,
                weather_condition=event.weather_condition,
                weather_cloud_cover=event.weather_cloud_cover,
                weather_wind_speed=event.weather_wind_speed,
                weather_wind_direction=event.weather_wind_direction,
                weather_precipitation=event.weather_precipitation,
                weather_rain=event.weather_rain,
                weather_snowfall=event.weather_snowfall,
                scientific_name=event.scientific_name,
                common_name=common_name,
                taxa_id=event.taxa_id,
                video_classification_score=event.video_classification_score,
                video_classification_label=event.video_classification_label,
                video_classification_timestamp=event.video_classification_timestamp,
                video_classification_status=event.video_classification_status,
                video_classification_error=event.video_classification_error,
                video_classification_provider=event.video_classification_provider,
                video_classification_backend=event.video_classification_backend,
                video_classification_model_id=event.video_classification_model_id,
                video_classification_model_name=_video_classification_model_name(event.video_classification_model_id),
                ai_analysis=event.ai_analysis,
                ai_analysis_timestamp=event.ai_analysis_timestamp
            )
            response_events.append(response_event)

        return response_events


class HiddenCountResponse(BaseModel):
    """Response for hidden count endpoint."""
    hidden_count: int


@router.get("/events/hidden-count", response_model=HiddenCountResponse)
async def get_hidden_count(auth: AuthContext = Depends(require_owner)):
    """Get count of hidden detections. Owner only."""
    async with get_db() as db:
        repo = DetectionRepository(db)
        count = await repo.get_hidden_count()
        return HiddenCountResponse(hidden_count=count)


@router.get("/events/count", response_model=EventsCountResponse)
@guest_rate_limit()
async def get_events_count(
    request: Request,
    start_date: Optional[date] = Query(default=None, description="Filter events from this date (inclusive)"),
    end_date: Optional[date] = Query(default=None, description="Filter events until this date (inclusive)"),
    species: Optional[str] = Query(default=None, description="Filter by species name"),
    camera: Optional[str] = Query(default=None, description="Filter by camera name"),
    favorites: bool = Query(default=False, description="Only count favorited detections"),
    audio_confirmed_only: bool = Query(default=False, description="Only count detections with audio confirmation"),
    include_hidden: bool = Query(default=False, description="Include hidden/ignored detections"),
    auth: AuthContext = Depends(get_auth_context_with_legacy)
):
    """Get total count of events (optionally filtered). Public users see limited historical data."""
    hide_camera_names = (
        not auth.is_owner
        and settings.public_access.enabled
        and not settings.public_access.show_camera_names
    )
    # Apply public access restrictions
    if not auth.is_owner and settings.public_access.enabled:
        max_days = effective_public_events_days()
        if max_days > 0:
            cutoff_date = date.today() - timedelta(days=max_days)
            if start_date is None or start_date < cutoff_date:
                start_date = cutoff_date
        else:
            start_date = date.today()
            end_date = date.today()
        include_hidden = False
        if hide_camera_names:
            camera = None

    async with get_db() as db:
        repo = DetectionRepository(db)

        start_datetime = datetime.combine(start_date, datetime.min.time()) if start_date else None
        end_datetime = datetime.combine(end_date, datetime.max.time()) if end_date else None
        species_name, taxa_id = parse_species_filter(species)
        species_name, species_aliases = resolve_species_display_filter_aliases(species_name, taxa_id)

        count = await repo.get_count(
            start_date=start_datetime,
            end_date=end_datetime,
            species=species_name,
            species_any=species_aliases,
            taxa_id=taxa_id,
            camera=camera,
            include_hidden=include_hidden,
            favorite_only=favorites,
            audio_confirmed_only=audio_confirmed_only
        )

        # Determine if any filters are applied
        filtered = any([start_date, end_date, species, camera, favorites, audio_confirmed_only])

        return EventsCountResponse(count=count, filtered=filtered)

@router.delete("/events/{event_id}")
async def delete_event(
    event_id: str,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """Delete a detection by its Frigate event ID. Owner only."""
    lang = get_user_language(request)
    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event(event_id)
        if not detection:
            raise HTTPException(
                status_code=404, 
                detail=i18n_service.translate("errors.detection_not_found", lang=lang)
            )
            
        deleted = await repo.delete_by_frigate_event(event_id)
        if deleted:
            await broadcaster.broadcast({
                "type": "detection_deleted",
                "data": {
                    "frigate_event": event_id,
                    "timestamp": detection.detection_time.isoformat()
                }
            })
            return {"status": "deleted", "event_id": event_id}
        raise HTTPException(
            status_code=404, 
            detail=i18n_service.translate("errors.detection_not_found", lang=lang)
        )


class HideResponse(BaseModel):
    """Response for hide/unhide action."""
    status: str
    event_id: str
    is_hidden: bool


class FavoriteResponse(BaseModel):
    """Response for favorite/unfavorite action."""
    status: str
    event_id: str
    is_favorite: bool


@router.post("/events/{event_id}/hide", response_model=HideResponse)
async def toggle_hide_event(
    event_id: str,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """Toggle the hidden/ignored status of a detection. Owner only."""
    lang = get_user_language(request)
    async with get_db() as db:
        repo = DetectionRepository(db)
        new_status = await repo.toggle_hidden(event_id)

        if new_status is None:
            raise HTTPException(
                status_code=404, 
                detail=i18n_service.translate("errors.detection_not_found", lang=lang)
            )

        detection = await repo.get_by_frigate_event(event_id)
        if detection:
            await broadcaster.broadcast({
                "type": "detection_updated",
                "data": _detection_updated_payload(detection)
            })

        action = "hidden" if new_status else "unhidden"
        log.info(f"Detection {action}", event_id=event_id, is_hidden=new_status)

        return HideResponse(
            status="updated",
            event_id=event_id,
            is_hidden=new_status
        )


@router.post("/events/{event_id}/favorite", response_model=FavoriteResponse)
async def favorite_event(
    event_id: str,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """Mark a detection as favorite. Owner only."""
    lang = get_user_language(request)
    async with get_db() as db:
        repo = DetectionRepository(db)
        result = await repo.favorite_detection(event_id, created_by=auth.username)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.detection_not_found", lang=lang)
            )

        detection = await repo.get_by_frigate_event(event_id)
        if detection:
            await broadcaster.broadcast({
                "type": "detection_updated",
                "data": _detection_updated_payload(detection)
            })

        return FavoriteResponse(status="updated", event_id=event_id, is_favorite=True)


@router.delete("/events/{event_id}/favorite", response_model=FavoriteResponse)
async def unfavorite_event(
    event_id: str,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """Remove favorite marker from a detection. Owner only."""
    lang = get_user_language(request)
    async with get_db() as db:
        repo = DetectionRepository(db)
        result = await repo.unfavorite_detection(event_id)
        if result is None:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.detection_not_found", lang=lang)
            )

        detection = await repo.get_by_frigate_event(event_id)
        if detection:
            await broadcaster.broadcast({
                "type": "detection_updated",
                "data": _detection_updated_payload(detection)
            })

        return FavoriteResponse(status="updated", event_id=event_id, is_favorite=False)


class UpdateDetectionRequest(BaseModel):
    """Request to manually update a detection's species."""
    display_name: str = Field(..., min_length=1, description="New species name")


class ReclassifyResponse(BaseModel):
    """Response from reclassification."""
    status: str
    event_id: str
    old_species: str
    new_species: str
    new_score: float
    updated: bool
    actual_strategy: Literal["snapshot", "video"]


class ClassificationStatusResponse(BaseModel):
    event_id: str
    video_classification_status: str | None = None
    video_classification_error: str | None = None
    video_classification_timestamp: str | None = None
    video_classification_provider: str | None = None
    video_classification_backend: str | None = None
    video_classification_model_id: str | None = None
    video_classification_model_name: str | None = None


@router.get("/events/{event_id}/classification-status", response_model=ClassificationStatusResponse)
async def get_event_classification_status(
    event_id: str,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """Get current video classification status for a single event. Owner only."""
    lang = get_user_language(request)
    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event(event_id)
        if not detection:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.detection_not_found", lang=lang)
            )

        ts = detection.video_classification_timestamp
        return ClassificationStatusResponse(
            event_id=event_id,
            video_classification_status=detection.video_classification_status,
            video_classification_error=detection.video_classification_error,
            video_classification_timestamp=ts.isoformat() if ts else None,
            video_classification_provider=detection.video_classification_provider,
            video_classification_backend=detection.video_classification_backend,
            video_classification_model_id=detection.video_classification_model_id,
            video_classification_model_name=_video_classification_model_name(detection.video_classification_model_id),
        )


@router.post("/events/{event_id}/reclassify", response_model=ReclassifyResponse)
async def reclassify_event(
    event_id: str,
    request: Request,
    strategy: Literal["snapshot", "video"] = Query("snapshot", description="Classification strategy"),
    auth: AuthContext = Depends(require_owner)
):
    """
    Re-run the classifier on an existing detection.

    Can use either a single snapshot or a video clip (Temporal Ensemble).
    """
    lang = get_user_language(request)

    async with get_db() as db:
        repo = DetectionRepository(db)
        detection = await repo.get_by_frigate_event(event_id)

        if not detection:
            raise HTTPException(
                status_code=404,
                detail=i18n_service.translate("errors.detection_not_found", lang=lang)
            )

        old_species = detection.display_name
        classifier = get_classifier()
        started_reclassification = False
        completion_broadcasted = False

        async def broadcast_reclassification_started(mode: Literal["snapshot", "video"]) -> None:
            nonlocal started_reclassification
            started_reclassification = True
            await broadcaster.broadcast({
                "type": "reclassification_started",
                "data": {
                    "event_id": event_id,
                    "strategy": mode
                }
            })

        async def broadcast_reclassification_completed(results_payload: list) -> None:
            nonlocal completion_broadcasted
            completion_broadcasted = True
            await broadcaster.broadcast({
                "type": "reclassification_completed",
                "data": {
                    "event_id": event_id,
                    "results": results_payload
                }
            })

        async def broadcast_video_status(status: str, error: str | None = None):
            await repo.update_video_status(event_id, status, error=error)
            refreshed = await repo.get_by_frigate_event(event_id)
            payload_source = refreshed or detection
            await broadcaster.broadcast({
                "type": "detection_updated",
                "data": _detection_updated_payload(
                    payload_source,
                    overrides={
                        "video_classification_status": status,
                        "video_classification_error": error,
                    }
                )
            })

        try:
            # Determine effective strategy
            # If video requested but no clip, fallback to snapshot
            event_data, event_error = await frigate_client.get_event_with_error(event_id, timeout=8.0)
            has_clip = event_data.get("has_clip", False) if event_data else False

            effective_strategy = strategy
            if strategy == "video" and not has_clip:
                log.warning("Video strategy requested but no clip available, falling back to snapshot", event_id=event_id)
                await broadcast_video_status("failed", event_error or "clip_unavailable")
                effective_strategy = "snapshot"

            results = []

            if effective_strategy == "video":
                await broadcast_video_status("processing", None)
                # Fetch clip - check cache first
                from app.services.media_cache import media_cache
                clip_data = None
                clip_error = None
                clip_source = "frigate"
                cached_path = media_cache.get_clip_path(event_id)

                if cached_path:
                    log.info("Using cached clip for reclassification", event_id=event_id)
                    with open(cached_path, 'rb') as f:
                        clip_data = f.read()
                    clip_source = "cache"
                else:
                    clip_data, clip_error = await frigate_client.get_clip_with_error(event_id, timeout=10.0)

                if not clip_data:
                    log.warning("Failed to fetch clip data, falling back to snapshot", event_id=event_id)
                    await broadcast_video_status("failed", clip_error or "clip_fetch_failed")
                    effective_strategy = "snapshot"
                else:
                    if not (clip_data.startswith(b'\x00\x00\x00\x18ftyp') or b'ftyp' in clip_data[:32]):
                        log.warning("Clip data invalid, falling back to snapshot", event_id=event_id)
                        await broadcast_video_status("failed", "clip_invalid")
                        effective_strategy = "snapshot"
                    else:
                        # Save to temp file for OpenCV
                        import tempfile
                        import os
                        import cv2

                        def _clip_decodes(path: str) -> bool:
                            cap = cv2.VideoCapture(path)
                            if not cap.isOpened():
                                cap.release()
                                return False
                            ok, _frame = cap.read()
                            cap.release()
                            return ok

                        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                            tmp.write(clip_data)
                            tmp_path = tmp.name

                        valid_clip = _clip_decodes(tmp_path)
                        if not valid_clip:
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)
                            log.warning("Clip decode failed, falling back to snapshot", event_id=event_id, source=clip_source)
                            await broadcast_video_status("failed", "clip_decode_failed")
                            if clip_source == "cache":
                                await media_cache.delete_cached_media(event_id)
                                clip_data, clip_error = await frigate_client.get_clip_with_error(event_id, timeout=10.0)
                                if clip_data and (clip_data.startswith(b'\x00\x00\x00\x18ftyp') or b'ftyp' in clip_data[:32]):
                                    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                                        tmp.write(clip_data)
                                        tmp_path = tmp.name
                                    valid_clip = _clip_decodes(tmp_path)
                                    if not valid_clip and os.path.exists(tmp_path):
                                        os.remove(tmp_path)
                                else:
                                    valid_clip = False
                            if not valid_clip:
                                effective_strategy = "snapshot"

                        if effective_strategy != "snapshot" and valid_clip:
                            try:
                                if settings.media_cache.high_quality_event_snapshots:
                                    try:
                                        await high_quality_snapshot_service.replace_from_clip_bytes(event_id, clip_data)
                                    except Exception as e:
                                        log.warning(
                                            "High-quality snapshot upgrade failed during manual video reclassification",
                                            event_id=event_id,
                                            error=str(e),
                                        )

                                # Broadcast start of video reclassification
                                await broadcast_reclassification_started("video")

                                # Define progress callback to broadcast real-time progress via SSE
                                async def progress_callback(current_frame, total_frames, frame_score, top_label, frame_thumb=None, frame_index=None, clip_total=None, model_name=None):
                                    await broadcaster.broadcast({
                                        "type": "reclassification_progress",
                                        "data": {
                                            "event_id": event_id,
                                            "current_frame": current_frame,
                                            "total_frames": total_frames,
                                            "frame_score": frame_score,
                                            "top_label": top_label,
                                            "frame_thumb": frame_thumb,
                                            "frame_index": frame_index,
                                            "clip_total": clip_total,
                                            "model_name": model_name
                                        }
                                    })

                                results = await classifier.classify_video_async(
                                    tmp_path,
                                    progress_callback=progress_callback,
                                    camera_name=detection.camera_name,
                                )

                                # Broadcast completion
                                await broadcast_reclassification_completed(results)
                            finally:
                                if os.path.exists(tmp_path):
                                    os.remove(tmp_path)

                        if not results:
                            log.warning("Video classification yielded no results, falling back to snapshot", event_id=event_id)
                            await broadcast_video_status("failed", "video_no_results")
                            effective_strategy = "snapshot"
                        else:
                            top_result = results[0]
                            await repo.update_video_classification(
                                frigate_event=event_id,
                                label=top_result["label"],
                                score=top_result["score"],
                                index=top_result["index"],
                                status="completed",
                                provider=top_result.get("inference_provider"),
                                backend=top_result.get("inference_backend"),
                                model_id=top_result.get("model_id"),
                            )
                            await broadcast_video_status("completed", None)

            # Snapshot strategy (Default or Fallback)
            if effective_strategy == "snapshot":
                await broadcast_reclassification_started("snapshot")

                snapshot_data = await frigate_client.get_snapshot(event_id, crop=True, quality=95)
                if not snapshot_data:
                    # Still broadcast completion if it failed so UI can stop spinner
                    await broadcast_reclassification_completed([])
                    raise HTTPException(
                        status_code=502,
                        detail=i18n_service.translate("errors.events.snapshot_fetch_failed", lang)
                    )

                image = Image.open(BytesIO(snapshot_data))
                results = await classifier.classify_async(
                    image,
                    camera_name=detection.camera_name,
                    input_context={"is_cropped": True},
                )

                # Broadcast completion
                await broadcast_reclassification_completed(results)

            if not results:
                raise HTTPException(
                    status_code=500,
                    detail=i18n_service.translate("errors.events.reclassification_failed", lang)
                )

            top = results[0]
            
            # Apply the result via DetectionService to ensure consistent logic (Unknown Bird relabeling, audio, etc)
            from app.services.detection_service import DetectionService
            svc = DetectionService(classifier)
            await svc.apply_video_result(
                frigate_event=event_id,
                video_label=top['label'],
                video_score=top['score'],
                video_index=top['index'],
                manual_tagged=True,
                video_provider=top.get("inference_provider"),
                video_backend=top.get("inference_backend"),
            )

            # Re-fetch updated detection for the response
            updated_detection = await repo.get_by_frigate_event(event_id)
            if not updated_detection:
                updated_detection = detection # Fallback

            return ReclassifyResponse(
                status="success",
                event_id=event_id,
                old_species=old_species,
                new_species=updated_detection.display_name,
                new_score=updated_detection.score,
                updated=True,
                actual_strategy=effective_strategy
            )
        except HTTPException:
            if started_reclassification and not completion_broadcasted:
                await broadcast_reclassification_completed([])
            raise
        except Exception as exc:
            if started_reclassification and not completion_broadcasted:
                await broadcast_reclassification_completed([])
            log.error(
                "Unexpected reclassification failure",
                event_id=event_id,
                strategy=strategy,
                error=str(exc),
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=i18n_service.translate("errors.events.reclassification_failed", lang)
            ) from exc


@router.patch("/events/{event_id}")
async def update_event(
    event_id: str,
    update_request: UpdateDetectionRequest,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """
    Manually update a detection's species name. Owner only.
    Use this to correct misidentifications.
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

        old_species = detection.display_name
        old_category_name = detection.category_name
        old_score = detection.score
        new_species = update_request.display_name.strip()

        log.debug("Manual tag request",
                  event_id=event_id,
                  old_species=old_species,
                  new_species=new_species,
                  frigate_event=detection.frigate_event)

        if _normalize_species_name(old_species) == _normalize_species_name(new_species):
            return {
                "status": "unchanged",
                "event_id": event_id,
                "species": old_species or new_species
            }

        resolved_aliases = await repo.resolve_species_aliases(new_species, language=lang)
        if _manual_update_is_alias_noop(detection, new_species, resolved_aliases):
            log.info(
                "Manual tag request resolved to existing species alias",
                event_id=event_id,
                old_species=old_species,
                requested_species=new_species,
                scientific_name=resolved_aliases.get("scientific_name"),
                taxa_id=resolved_aliases.get("taxa_id"),
            )
            return {
                "status": "unchanged",
                "event_id": event_id,
                "species": old_species or new_species
            }

        unknown_labels = {
            *(label.lower() for label in settings.classification.unknown_bird_labels),
            "unknown bird",
        }
        normalized_label = "Unknown Bird" if new_species.lower() in unknown_labels else new_species

        # 1. Get taxonomy for the new species (Force refresh to fix potential bad cache).
        # If the user entered a localized alias, prefer the resolved scientific/common name.
        taxonomy_lookup_name = (
            resolved_aliases.get("scientific_name")
            or resolved_aliases.get("common_name")
            or normalized_label
        )
        taxonomy: dict = {}
        if normalized_label != "Unknown Bird":
            try:
                taxonomy = await taxonomy_service.get_names(taxonomy_lookup_name, force_refresh=True)
            except Exception as exc:
                log.warning(
                    "Manual tag taxonomy lookup failed; using local alias resolution fallback",
                    event_id=event_id,
                    requested_species=new_species,
                    taxonomy_lookup_name=taxonomy_lookup_name,
                    error=str(exc),
                )

        sci_name = (
            taxonomy.get("scientific_name")
            or resolved_aliases.get("scientific_name")
            or normalized_label
        )
        com_name = taxonomy.get("common_name") or resolved_aliases.get("common_name")
        t_id = taxonomy.get("taxa_id") if taxonomy.get("taxa_id") is not None else resolved_aliases.get("taxa_id")

        # Avoid persisting localized or partial taxonomy when refresh fails:
        # once we know the scientific name, prefer canonical cache names for storage
        # and let UI localization render translations.
        if sci_name and (not com_name or t_id is None):
            canonical_cache_names = await repo.get_taxonomy_names(sci_name)
            if canonical_cache_names.get("scientific_name"):
                sci_name = canonical_cache_names["scientific_name"]
            if not com_name and canonical_cache_names.get("common_name"):
                com_name = canonical_cache_names["common_name"]
            if t_id is None and canonical_cache_names.get("taxa_id") is not None:
                t_id = canonical_cache_names["taxa_id"]

        stored_category_name = sci_name or normalized_label
        stored_display_name = stored_category_name
        if settings.classification.display_common_names and com_name:
            stored_display_name = com_name
        elif not settings.classification.display_common_names and sci_name:
            stored_display_name = sci_name

        # 2. Re-correlate audio with the new species
        try:
            audio_confirmed, audio_species, audio_score = await audio_service.correlate_species(
                target_time=detection.detection_time,
                species_name=sci_name,  # Use scientific name for matching
                camera_name=detection.camera_name
            )
        except Exception as exc:
            log.warning(
                "Audio re-correlation failed during manual tag update; continuing without audio confirmation",
                event_id=event_id,
                requested_species=new_species,
                scientific_name=sci_name,
                error=str(exc),
            )
            audio_confirmed, audio_species, audio_score = False, None, None

        # 3. Update the detection with new species, taxonomy, and re-correlated audio
        detection.display_name = stored_display_name
        detection.category_name = stored_category_name
        detection.scientific_name = sci_name
        detection.common_name = com_name
        detection.taxa_id = t_id

        # Execute update directly for reliability
        await db.execute("""
            UPDATE detections
            SET display_name = ?, category_name = ?,
                scientific_name = ?, common_name = ?, taxa_id = ?,
                audio_confirmed = ?, audio_species = ?, audio_score = ?,
                manual_tagged = 1
            WHERE frigate_event = ?
        """, (stored_display_name, stored_category_name,
              sci_name, com_name, t_id,
              1 if audio_confirmed else 0, audio_species, audio_score,
              event_id))

        model_id = _get_active_model_id_for_feedback()
        predicted_label = (old_category_name or old_species or "").strip()
        corrected_label = (stored_category_name or stored_display_name or "").strip()
        if predicted_label and corrected_label and predicted_label != corrected_label:
            await repo.insert_classification_feedback(
                frigate_event=event_id,
                camera_name=detection.camera_name,
                model_id=model_id,
                predicted_label=predicted_label,
                corrected_label=corrected_label,
                predicted_score=old_score,
                source="manual_tag",
            )
        await db.commit()

        log.info("Manually updated detection species",
                 event_id=event_id,
                 old_species=old_species,
                 new_species=stored_display_name,
                 requested_species=new_species,
                 scientific=sci_name,
                 audio_confirmed=audio_confirmed,
                 audio_species=audio_species)

        # Broadcast update with re-correlated audio
        refreshed_detection = await repo.get_by_frigate_event(event_id)
        payload_source = refreshed_detection or detection
        await broadcaster.broadcast({
            "type": "detection_updated",
            "data": _detection_updated_payload(
                payload_source,
                overrides={
                    "display_name": stored_display_name,
                    "manual_tagged": True,
                    "audio_confirmed": audio_confirmed,
                    "audio_species": audio_species,
                    "audio_score": audio_score,
                    "scientific_name": sci_name,
                    "common_name": com_name,
                    "taxa_id": t_id,
                }
            )
        })

        return {
            "status": "updated",
            "event_id": event_id,
            "old_species": old_species,
            "new_species": stored_display_name
        }


class WildlifeClassification(BaseModel):
    """A single wildlife classification result."""
    label: str
    score: float
    index: int


class WildlifeClassifyResponse(BaseModel):
    """Response from wildlife classification."""
    status: str
    event_id: str
    classifications: List[WildlifeClassification]


@router.post("/events/{event_id}/classify-wildlife", response_model=WildlifeClassifyResponse)
async def classify_wildlife(
    event_id: str,
    request: Request,
    auth: AuthContext = Depends(require_owner)
):
    """
    Classify a detection using the general wildlife model. Owner only.
    Fetches the snapshot from Frigate and runs it through the wildlife classifier.
    Does NOT update the database - user can manually tag if desired.
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

        # Fetch snapshot from Frigate using centralized client
        snapshot_data = await frigate_client.get_snapshot(event_id, crop=True, quality=95)
        if not snapshot_data:
            raise HTTPException(
                status_code=502,
                detail=i18n_service.translate("errors.events.snapshot_fetch_failed", lang)
            )

        # Classify with wildlife model
        image = Image.open(BytesIO(snapshot_data))
        classifier = get_classifier()
        results = await classifier.classify_wildlife_async(
            image,
            input_context={"is_cropped": True},
        )

        if not results:
            # Wildlife model not available or no results
            wildlife_status = classifier.get_wildlife_status()
            if not wildlife_status.get("enabled"):
                raise HTTPException(
                    status_code=503,
                    detail=i18n_service.translate("errors.events.wildlife_model_unavailable", lang)
                )
            raise HTTPException(
                status_code=500,
                detail=i18n_service.translate("errors.events.classification_failed", lang)
            )

        classifications = [
            WildlifeClassification(
                label=r['label'],
                score=r['score'],
                index=r['index']
            )
            for r in results
        ]

        log.info("Wildlife classification complete",
                 event_id=event_id,
                 top_result=results[0]['label'] if results else None,
                 top_score=results[0]['score'] if results else None)

        return WildlifeClassifyResponse(
            status="success",
            event_id=event_id,
            classifications=classifications
        )
