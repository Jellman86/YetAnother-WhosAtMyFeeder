from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth import AuthContext, get_auth_context_with_legacy
from app.config import settings
from app.database import get_db
from app.models import DetectionVisitResponse, DetectionVisitsResponse, VisitCapturesResponse
from app.repositories.visit_repository import VisitRepository
from app.routers.events import (
    _enforce_max_date_range,
    parse_species_filter,
    present_events,
    resolve_species_display_filter_aliases,
)
from app.utils.api_datetime import utc_naive_datetime
from app.ratelimit import guest_rate_limit
from app.services.visit_grouping import VISIT_GAP_SECONDS
from app.utils.public_access import effective_public_events_days, public_utc_day


router = APIRouter(tags=["visits"])


def visible_visit_window(
    auth: AuthContext,
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    if not auth.is_owner and settings.public_access.enabled:
        days = effective_public_events_days()
        cutoff = datetime.combine(public_utc_day() - timedelta(days=max(days, 0)), datetime.min.time())
        start = max(start, cutoff) if start else cutoff
        if days <= 0:
            today_end = datetime.combine(public_utc_day(), datetime.max.time())
            end = min(end, today_end) if end else today_end
    _enforce_max_date_range(start.date() if start else None, end.date() if end else None)
    return start, end


@router.get("/visits", response_model=DetectionVisitsResponse)
@guest_rate_limit()
async def get_visits(
    request: Request,
    limit: int = Query(24, ge=1, le=100),
    offset: int = Query(0, ge=0),
    start_date: date | None = None,
    end_date: date | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    species: str | None = None,
    camera: str | None = None,
    multiple_species_only: bool = False,
    favorites: bool = False,
    audio_confirmed_only: bool = False,
    only_hidden: bool = False,
    sort: str = Query("newest", pattern="^(newest|oldest|confidence)$"),
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> DetectionVisitsResponse:
    start = (
        utc_naive_datetime(start_time)
        if start_time
        else datetime.combine(start_date, datetime.min.time())
        if start_date
        else None
    )
    end = (
        utc_naive_datetime(end_time)
        if end_time
        else datetime.combine(end_date, datetime.max.time())
        if end_date
        else None
    )
    start, end = visible_visit_window(auth, start, end)
    if not auth.is_owner:
        only_hidden = False
        limit = min(limit, 50)
        if settings.public_access.enabled and not settings.public_access.show_camera_names:
            camera = None
        if not settings.public_access.show_audio:
            audio_confirmed_only = False
    species_name, taxa_id = parse_species_filter(species)
    species_name, aliases = resolve_species_display_filter_aliases(species_name, taxa_id)
    async with get_db() as db:
        repo = VisitRepository(db)
        headers, total = await repo.list_visits(
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
        events = [await repo.get_by_frigate_event(event_id) for event_id in event_ids]
    presented = await present_events([event for event in events if event is not None], request, auth)
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
    start_date: date | None = None,
    end_date: date | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    only_hidden: bool = False,
    auth: AuthContext = Depends(get_auth_context_with_legacy),
) -> VisitCapturesResponse:
    start = (
        utc_naive_datetime(start_time)
        if start_time
        else datetime.combine(start_date, datetime.min.time())
        if start_date
        else None
    )
    end = (
        utc_naive_datetime(end_time)
        if end_time
        else datetime.combine(end_date, datetime.max.time())
        if end_date
        else None
    )
    start, end = visible_visit_window(auth, start, end)
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
