"""The About page's opener: this install's own captures, and the wider community's count.

The reel at the top of About shows one recent photograph per species, newest first, and only
photographs that are crops. A full frame at thumbnail size is a picture of a feeder, not of a
bird, so it is left out rather than shown small. Which stored photograph is a crop is recorded
in the media cache's snapshot metadata; the database does not know.
"""

import asyncio
from collections import OrderedDict
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path as FilePath
from typing import Awaitable, Callable, Optional

import aiofiles
import aiofiles.os
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
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
from app.utils.public_access import effective_public_media_days

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
        max_days = effective_public_media_days()
        if max_days > 0:
            start_datetime = datetime.combine(date.today() - timedelta(days=max_days), datetime.min.time())
        else:
            start_datetime = datetime.combine(date.today(), datetime.min.time())
            end_datetime = datetime.combine(date.today(), datetime.max.time())

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
        raise HTTPException(status_code=404, detail="Snapshot not found")
    try:
        content = await reel_image_for(path)
    except Exception:  # a corrupt file is a missing photograph, not a broken page
        raise HTTPException(status_code=404, detail="Snapshot not found")
    # The photograph can change (a candidate applied, the HQ pipeline settling), and a guest's
    # browser must not keep a copy once snapshots are turned off: same rule as the snapshot route.
    return Response(content=content, media_type="image/jpeg", headers=SNAPSHOT_NO_STORE_HEADERS)


@router.get("/about/community", response_model=CommunityStatsResponse)
@guest_rate_limit()
async def get_about_community(request: Request) -> CommunityStatsResponse:
    """How many installs reported to the telemetry service this week. Cached for an hour."""
    return CommunityStatsResponse(**(await community_stats_service.get_stats()))
