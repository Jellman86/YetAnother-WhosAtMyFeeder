from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth import AuthContext, get_auth_context_with_legacy
from app.config import settings
from app.database import get_db
from app.models import DetectionVisitResponse, DetectionVisitsResponse, VisitCapturesResponse
from app.repositories.visit_repository import VisitRepository
from app.routers.events import (
    CALENDAR_DAY_HELP,
    parse_species_filter,
    present_events,
    requested_calendar_window,
    resolve_species_display_filter_aliases,
    visible_history_window,
)
from app.utils.api_datetime import utc_naive_datetime
from app.utils.calendar_day import CalendarDay
from app.ratelimit import guest_rate_limit
from app.services.explorer_search import bird_taxon_members
from app.services.visit_grouping import VISIT_GAP_SECONDS


router = APIRouter(tags=["visits"])

# A busy feeder sees about 200 visits a day; one page holds a whole day with room to spare.
MAX_VISITS_PAGE = 500


def visible_visit_window(
    auth: AuthContext,
    start_day: CalendarDay | None,
    end_day: CalendarDay | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    """Exact instants win over calendar days; the viewer's allowance narrows either."""
    day_start, day_end = requested_calendar_window(start_day, end_day)
    start = utc_naive_datetime(start_time) if start_time else day_start
    end = utc_naive_datetime(end_time) if end_time else day_end
    return visible_history_window(auth, start, end)


@router.get("/visits", response_model=DetectionVisitsResponse)
@guest_rate_limit()
async def get_visits(
    request: Request,
    limit: int = Query(24, ge=1, le=MAX_VISITS_PAGE),
    offset: int = Query(0, ge=0, description="Visits to skip; `total` counts every matching visit"),
    start_date: CalendarDay | None = Query(None, description=f"First day (inclusive): {CALENDAR_DAY_HELP}"),
    end_date: CalendarDay | None = Query(None, description=f"Last day (inclusive): {CALENDAR_DAY_HELP}"),
    start_time: datetime | None = Query(None, description="Exact start instant; overrides start_date"),
    end_time: datetime | None = Query(None, description="Exact end instant; overrides end_date"),
    species: str | None = None,
    camera: str | None = None,
    multiple_species_only: bool = False,
    favorites: bool = False,
    audio_confirmed_only: bool = False,
    only_hidden: bool = False,
    sort: str = Query("newest", pattern="^(newest|oldest|confidence)$"),
    taxon: int | None = Query(None, ge=1, description="Catalogue taxon: only species at or beneath it"),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> DetectionVisitsResponse:
    start, end = visible_visit_window(auth, start_date, end_date, start_time, end_time)
    if not auth.is_owner:
        only_hidden = False
        limit = min(limit, 50)
        if settings.public_access.enabled and not settings.public_access.show_camera_names:
            camera = None
        if not settings.public_access.show_audio:
            audio_confirmed_only = False
    species_name, taxa_id = parse_species_filter(species)
    species_name, aliases = resolve_species_display_filter_aliases(species_name, taxa_id)
    species_ids = await bird_taxon_members(taxon) if taxon else None
    async with get_db() as db:
        repo = VisitRepository(db)
        headers, total = await repo.list_visits(
            species_ids=species_ids,
            start=start,
            end=end,
            camera=camera,
            hidden_only=only_hidden,
            limit=limit,
            offset=offset,
            species=species_name,
            species_any=aliases,
            taxa_id=taxa_id,
            favorites=favorites,
            audio_only=audio_confirmed_only,
            public_audio=not auth.is_owner,
            sort=sort,
            multiple_species_only=multiple_species_only and auth.is_owner,
        )
        event_ids = list(
            dict.fromkeys(
                str(header[key])
                for header in headers
                for key in ("representative_event", "latest_event", "peak_event")
                if header.get(key)
            )
        )
        events = await repo.get_by_frigate_events(event_ids)
    presented = await present_events([events[event_id] for event_id in event_ids if event_id in events], request, auth)
    by_id = {event.frigate_event: event for event in presented}
    visits = []
    for header in headers:
        representative = by_id.get(header["representative_event"])
        latest = by_id.get(header["latest_event"])
        if representative is None or latest is None:
            continue
        visits.append(
            DetectionVisitResponse(
                visit_id=header["visit_id"],
                start_time=header["start_time"],
                end_time=header["end_time"],
                capture_count=header["capture_count"],
                best_score=header["best_score"],
                needs_review=representative.display_name == "Unknown Bird"
                or (not header["manual_tagged"] and header["best_score"] < settings.classification.threshold),
                owner_confirmed=bool(header["manual_tagged"])
                and representative.display_name.strip().casefold() not in {"", "unknown bird"},
                audio_confirmed=bool(header["audio_confirmed"])
                and (auth.is_owner or settings.public_access.show_audio),
                representative=representative,
                latest=latest,
                peak_capture=by_id.get(header.get("peak_event")),
            )
        )
    return DetectionVisitsResponse(visits=visits, total=total, gap_seconds=VISIT_GAP_SECONDS)


@router.get("/visits/{visit_id}/captures", response_model=VisitCapturesResponse)
@guest_rate_limit()
async def get_visit_captures(
    visit_id: str,
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    start_date: CalendarDay | None = Query(None, description=f"First day (inclusive): {CALENDAR_DAY_HELP}"),
    end_date: CalendarDay | None = Query(None, description=f"Last day (inclusive): {CALENDAR_DAY_HELP}"),
    start_time: datetime | None = Query(None, description="Exact start instant; overrides start_date"),
    end_time: datetime | None = Query(None, description="Exact end instant; overrides end_date"),
    only_hidden: bool = False,
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> VisitCapturesResponse:
    start, end = visible_visit_window(auth, start_date, end_date, start_time, end_time)
    async with get_db() as db:
        captures, total = await VisitRepository(db).visit_captures(
            visit_id,
            start=start,
            end=end,
            hidden_only=only_hidden and auth.is_owner,
            limit=limit,
            offset=offset,
        )
    if total == 0:
        raise HTTPException(404, "Visit is unavailable in this history window")
    return VisitCapturesResponse(captures=await present_events(captures, request, auth), total=total)
