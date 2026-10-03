"""Feeder facts, shared card media, and the wider community's count.

About opens on a feeder portrait; the leaderboard uses the same card-sized photographs and
visit films. The legacy showcase list remains available. Stored crop provenance comes from
the media cache metadata, so full scenes are not mistaken for close photographs of a bird.
"""

import asyncio
import os
from collections import OrderedDict
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path as FilePath
from typing import Awaitable, Callable, Literal, Optional
from urllib.parse import quote

import aiofiles
import aiofiles.os
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel

from app.auth import AuthContext, get_auth_context_with_legacy
from app.config import settings
from app.database import get_db
from app.models import Detection
from app.ratelimit import guest_rate_limit
from app.repositories.detection_repository import DetectionRepository
from app.routers.proxy import SNAPSHOT_NO_STORE_HEADERS, require_event_access, validate_event_id
from app.services.classification_input_provenance import cached_snapshot_input_provenance
from app.services.community_stats_service import community_stats_service
from app.services.media_cache import media_cache
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.utils.api_datetime import serialize_api_datetime
from app.utils.language import get_user_language
from app.utils.canonical_species import should_hide_species_label
from app.utils.public_access import effective_public_events_days, public_events_window, public_media_window

router = APIRouter()

# How far back the reel looks, and how many metadata files it will read to fill itself.
SHOWCASE_SCAN_LIMIT = 400
SHOWCASE_METADATA_READS = 60
SHOWCASE_DEFAULT_LIMIT = 12

# The stored photograph can be a full-resolution frame of several megabytes; a card wants a
# few hundred pixels. The reel serves a resized copy, kept in memory for the handful of
# photographs the reel can show, keyed on the file so a re-chosen frame is picked up.
REEL_IMAGE_MAX_EDGE = 480
REEL_IMAGE_QUALITY = 82
REEL_IMAGE_CACHE_ENTRIES = 48
_reel_images: "OrderedDict[tuple[str, int, int], bytes]" = OrderedDict()
_reel_lock = asyncio.Lock()


class ShowcaseItem(BaseModel):
    frigate_event: str
    display_name: str
    common_name: str | None = None
    scientific_name: str | None = None
    taxa_id: int | None = None
    detection_time: str
    score: float
    camera_name: str | None = None


class ShowcaseResponse(BaseModel):
    items: list[ShowcaseItem]


# A species seen once could be a misidentification; the newest arrival is one seen a few times, or confirmed.
NEWEST_ARRIVAL_MIN_DETECTIONS = 3


class PortraitSpecies(BaseModel):
    # The label the history stores, which opens the species; the display name is for reading.
    species: str
    display_name: str
    scientific_name: str | None = None
    taxa_id: int | None = None
    first_seen: str


class PortraitDay(BaseModel):
    # The viewer's calendar day, YYYY-MM-DD.
    date: str
    visits: int


class PortraitVisit(BaseModel):
    frigate_event: str
    display_name: str
    scientific_name: str | None = None
    taxa_id: int | None = None
    detection_time: str
    image_url: str
    # A few silent seconds of the visit, once made; the photograph stands in until then.
    film_url: str | None = None


class FeederPortraitResponse(BaseModel):
    # "all" is the whole history; "shared" is the window a guest is shown, `shared_days` long.
    scope: Literal["all", "shared"]
    shared_days: int | None = None
    started_at: str | None = None
    visits: int
    detections: int
    species: int
    busiest_day: PortraitDay | None = None
    newest_arrival: PortraitSpecies | None = None
    latest_visit: PortraitVisit | None = None


class CommunityStatsResponse(BaseModel):
    enabled: bool
    active_installs: int | None = None
    total_installs: int | None = None
    checked_at: str | None = None
    error: str | None = None


def species_key(detection: Detection) -> str:
    """One entry per species: the taxon when known, else the name as the classifier wrote it."""
    if detection.taxa_id:
        return f"taxa:{detection.taxa_id}"
    return f"name:{(detection.display_name or '').strip().casefold()}"


def is_crop_source(source: object) -> bool:
    """One definition of a crop: the same provenance the classifier trusts for a cached photograph."""
    return cached_snapshot_input_provenance({"source": source}).is_cropped


async def stored_crops(
    detections: list[Detection],
    *,
    limit: int,
    max_reads: int = SHOWCASE_METADATA_READS,
    read_source: Optional[Callable[[str], Awaitable[Optional[str]]]] = None,
) -> list[Detection]:
    """Walk newest-first, keeping the newest crop of each species.

    A species whose newest photograph is a whole scene is represented by its newest crop, not
    dropped. Stops at ``limit`` kept or ``max_reads`` metadata files read, whichever comes
    first, so a history full of whole scenes cannot turn the About page into a cache scan.
    """
    reader = read_source or _snapshot_source
    kept: list[Detection] = []
    kept_species: set[str] = set()
    reads = 0
    for detection in detections:
        if len(kept) >= limit or reads >= max_reads:
            break
        key = species_key(detection)
        if key in kept_species:
            continue
        reads += 1
        if is_crop_source(await reader(detection.frigate_event)):
            kept.append(detection)
            kept_species.add(key)
    return kept


async def _snapshot_source(event_id: str) -> str | None:
    metadata = await media_cache.get_snapshot_metadata(event_id)
    return (metadata or {}).get("source")


@router.get("/about/showcase", response_model=ShowcaseResponse)
@guest_rate_limit()
async def get_about_showcase(
    request: Request,
    limit: int = Query(default=SHOWCASE_DEFAULT_LIMIT, ge=1, le=40, description="Photographs to return"),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> ShowcaseResponse:
    """One recent crop per species, newest first. Guests see the same window as the Explorer."""
    if not (settings.media_cache.enabled and settings.media_cache.cache_snapshots):
        # Without a media cache there are no stored photographs to know anything about.
        return ShowcaseResponse(items=[])

    lang = get_user_language(request)
    is_guest = not auth.is_owner and settings.public_access.enabled
    if is_guest and not settings.public_access.show_snapshots:
        return ShowcaseResponse(items=[])
    hide_camera_names = is_guest and not settings.public_access.show_camera_names

    # Guests see the reel through the same window as the photographs themselves (#291).
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    if is_guest:
        start, end = public_media_window()
        start_datetime = start.replace(tzinfo=None)
        # The repository's date-range API has an inclusive upper bound.
        end_datetime = end.replace(tzinfo=None) - timedelta(microseconds=1) if end is not None else None

    async with get_db() as db:
        repo = DetectionRepository(db)
        recent = await repo.get_all(
            limit=SHOWCASE_SCAN_LIMIT,
            start_date=start_datetime,
            end_date=end_datetime,
            sort="newest",
        )

    picks = await stored_crops(recent, limit=limit)

    localized: dict[int, str] = {}
    if picks:
        async with get_db() as db:
            for detection in picks:
                if not detection.taxa_id or detection.taxa_id in localized:
                    continue
                name = (
                    await taxonomy_service.get_localized_common_name(detection.taxa_id, lang, db=db)
                    if lang != "en"
                    else await taxonomy_service.get_canonical_english_name(detection.taxa_id, db=db)
                )
                if name:
                    localized[detection.taxa_id] = name

    items = [
        ShowcaseItem(
            frigate_event=detection.frigate_event,
            display_name=localized.get(detection.taxa_id or -1) or detection.common_name or detection.display_name,
            common_name=localized.get(detection.taxa_id or -1) or detection.common_name,
            scientific_name=detection.scientific_name,
            taxa_id=detection.taxa_id,
            detection_time=serialize_api_datetime(detection.detection_time) or "",
            score=float(detection.score),
            camera_name=None if hide_camera_names else detection.camera_name,
        )
        for detection in picks
    ]
    return ShowcaseResponse(items=items)


async def _localized_name(taxa_id: int | None, lang: str, db) -> str | None:
    if not taxa_id:
        return None
    if lang != "en":
        return await taxonomy_service.get_localized_common_name(taxa_id, lang, db=db)
    return await taxonomy_service.get_canonical_english_name(taxa_id, db=db)


def newest_arrival(species: list[dict], unknown_labels: list[str]) -> dict | None:
    """The species first seen most recently, among those seen often enough, or confirmed, to trust."""
    unknown = {label.strip().casefold() for label in unknown_labels}
    trusted = [
        row
        for row in species
        if (row["species"] or "").strip().casefold() not in unknown
        and not should_hide_species_label(row["species"])
        and (row["confirmed"] or row["detections"] >= NEWEST_ARRIVAL_MIN_DETECTIONS)
    ]
    return max(trusted, key=lambda row: row["first_seen"], default=None)


def busiest_day(daily_visits: dict[str, int]) -> tuple[str, int] | None:
    """The day with the most visits; of equal days, the most recent."""
    if not daily_visits:
        return None
    return max(daily_visits.items(), key=lambda item: (item[1], item[0]))


@router.get("/about/portrait", response_model=FeederPortraitResponse)
@guest_rate_limit()
async def get_feeder_portrait(
    request: Request,
    utc_offset_minutes: int = Query(0, ge=-840, le=840, description="The viewer's offset from UTC, for calendar days"),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> FeederPortraitResponse:
    """This feeder in a few facts: since when, how many visits and species, its busiest day,
    its newest arrival, and its latest visit. Guests see the shared window, and are told so."""
    from app.services.visit_film_service import visit_film_service

    lang = get_user_language(request)
    is_guest = not auth.is_owner and settings.public_access.enabled
    start: datetime | None = None
    end: datetime | None = None
    if is_guest:
        window_start, window_end = public_events_window()
        start = window_start.replace(tzinfo=None)
        end = window_end.replace(tzinfo=None) if window_end is not None else None

    unknown_labels = settings.classification.unknown_bird_labels
    async with get_db() as db:
        repo = DetectionRepository(db)
        species = await repo.get_feeder_species_history(start_date=start, end_date=end)
        daily = await repo.get_daily_visit_counts(utc_offset_minutes=utc_offset_minutes, start_date=start, end_date=end)
        arrival = newest_arrival(species, unknown_labels)
        arrival_name = await _localized_name(arrival["taxa_id"], lang, db) if arrival else None

    latest: PortraitVisit | None = None
    media_allowed = settings.media_cache.enabled and settings.media_cache.cache_snapshots
    if media_allowed and (not is_guest or settings.public_access.show_snapshots):
        media_start: datetime | None = None
        media_end: datetime | None = None
        if is_guest:
            # A guest's latest visit is one they may open: inside the shared history and the shared photographs.
            window_start, window_end = public_media_window()
            media_start = max(window_start.replace(tzinfo=None), start) if start else window_start.replace(tzinfo=None)
            ends = [moment for moment in (window_end.replace(tzinfo=None) if window_end else None, end) if moment]
            # The repository's date-range API has an inclusive upper bound.
            media_end = min(ends) - timedelta(microseconds=1) if ends else None
        async with get_db() as db:
            recent = await DetectionRepository(db).get_all(
                limit=40, start_date=media_start, end_date=media_end, sort="newest"
            )
            picks = await stored_crops(recent, limit=1, max_reads=20)
            visit = picks[0] if picks else None
            visit_name = await _localized_name(visit.taxa_id, lang, db) if visit else None
        if visit is not None:
            film_url = None
            if not is_guest or settings.public_access.show_clips:
                if await visit_film_service.request(visit.frigate_event) == "ready":
                    film_url = f"/api/about/showcase/{quote(visit.frigate_event, safe='')}.webm"
            latest = PortraitVisit(
                frigate_event=visit.frigate_event,
                display_name=visit_name or visit.common_name or visit.display_name,
                scientific_name=visit.scientific_name,
                taxa_id=visit.taxa_id,
                detection_time=serialize_api_datetime(visit.detection_time) or "",
                image_url=f"/api/about/showcase/{quote(visit.frigate_event, safe='')}.jpg",
                film_url=film_url,
            )

    unknown = {label.strip().casefold() for label in unknown_labels}
    named = [
        row
        for row in species
        if (row["species"] or "").strip().casefold() not in unknown and not should_hide_species_label(row["species"])
    ]
    busiest = busiest_day(daily)
    return FeederPortraitResponse(
        scope="shared" if is_guest else "all",
        shared_days=effective_public_events_days() if is_guest else None,
        started_at=serialize_api_datetime(min(row["first_seen"] for row in species)) if species else None,
        visits=sum(daily.values()),
        detections=sum(row["detections"] for row in species),
        species=len(named),
        busiest_day=PortraitDay(date=busiest[0], visits=busiest[1]) if busiest else None,
        newest_arrival=PortraitSpecies(
            species=arrival["species"],
            display_name=arrival_name or arrival["common_name"] or arrival["species"],
            scientific_name=arrival["scientific_name"],
            taxa_id=arrival["taxa_id"],
            first_seen=serialize_api_datetime(arrival["first_seen"]) or "",
        )
        if arrival
        else None,
        latest_visit=latest,
    )


def resize_for_reel(image_bytes: bytes) -> bytes:
    """A card-sized JPEG of the stored photograph; the crop is kept, only the size changes."""
    with Image.open(BytesIO(image_bytes)) as opened:
        image = (ImageOps.exif_transpose(opened) or opened).convert("RGB")
        image.thumbnail((REEL_IMAGE_MAX_EDGE, REEL_IMAGE_MAX_EDGE))
        out = BytesIO()
        image.save(out, format="JPEG", quality=REEL_IMAGE_QUALITY, optimize=True)
        return out.getvalue()


async def reel_image_for(path: FilePath) -> bytes:
    stat = await aiofiles.os.stat(path)
    key = (str(path), int(stat.st_mtime), int(stat.st_size))
    async with _reel_lock:
        cached = _reel_images.get(key)
        if cached is not None:
            _reel_images.move_to_end(key)
            return cached
    async with aiofiles.open(path, "rb") as handle:
        raw = await handle.read()
    resized = await asyncio.to_thread(resize_for_reel, raw)
    async with _reel_lock:
        _reel_images[key] = resized
        _reel_images.move_to_end(key)
        while len(_reel_images) > REEL_IMAGE_CACHE_ENTRIES:
            _reel_images.popitem(last=False)
    return resized


@router.get("/about/showcase/{event_id}.jpg", response_class=Response)
@guest_rate_limit()
async def get_about_reel_image(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> Response:
    """The stored photograph at card size, under the same access rules as the photograph."""
    lang = get_user_language(request)
    if not validate_event_id(event_id):
        raise HTTPException(status_code=400, detail="Invalid event ID format")
    await require_event_access(event_id, auth, lang, media="snapshot")
    path = await media_cache.get_snapshot_path(event_id)
    if path is None:
        from app.services.archive_service import archive_service

        path = await archive_service.snapshot_path(event_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    try:
        content = await reel_image_for(path)
    except Exception:  # a corrupt file is a missing photograph, not a broken page
        raise HTTPException(status_code=404, detail="Snapshot not found")
    # The photograph can change (a candidate applied, the HQ pipeline settling), and a guest's
    # browser must not keep a copy once snapshots are turned off: same rule as the snapshot route.
    return Response(content=content, media_type="image/jpeg", headers=SNAPSHOT_NO_STORE_HEADERS)


@router.get(
    "/about/showcase/{event_id}.webm",
    response_class=Response,
    responses={200: {"content": {"video/webm": {}}}, 404: {"description": "No film, or not made yet"}},
)
@guest_rate_limit()
async def get_visit_film(
    request: Request,
    event_id: str = Path(..., min_length=1, max_length=64),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> Response:
    """A few silent seconds of the visit, framed on the bird, under the same rules as its clip.

    A film not made yet is asked for and answered 404 with `X-Film-Status: pending`; the card
    keeps its photograph until a later load finds the film.
    """
    from app.services.visit_film_service import FILMS_DIR, visit_film_service

    lang = get_user_language(request)
    if not validate_event_id(event_id):
        raise HTTPException(status_code=400, detail="Invalid event ID format")
    await require_event_access(event_id, auth, lang, media="clip")
    path = await visit_film_service.ready_path(event_id)
    if path is None:
        status = await visit_film_service.request(event_id)
        raise HTTPException(status_code=404, detail="Film not available", headers={"X-Film-Status": status})
    # Resolve symlinks off the event loop, then enforce containment at the response boundary.
    resolved_root, resolved_path = await asyncio.gather(
        asyncio.to_thread(os.path.realpath, FILMS_DIR), asyncio.to_thread(os.path.realpath, path)
    )
    safe_root = os.path.normpath(resolved_root)
    safe_path = os.path.normpath(resolved_path)
    if not safe_path.startswith(safe_root + os.sep):
        raise HTTPException(status_code=404, detail="Film not available")
    # A file response answers byte ranges, which Safari needs before it plays a video. Like the
    # photograph, a guest's browser must not keep a copy once clips are turned off.
    return FileResponse(safe_path, media_type="video/webm", headers=SNAPSHOT_NO_STORE_HEADERS)


@router.get("/about/community", response_model=CommunityStatsResponse)
@guest_rate_limit()
async def get_about_community(request: Request) -> CommunityStatsResponse:
    """How many installs reported to the telemetry service this week. Cached for an hour."""
    return CommunityStatsResponse(**(await community_stats_service.get_stats()))
