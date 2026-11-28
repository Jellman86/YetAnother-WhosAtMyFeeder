from fastapi import APIRouter, Depends, Request, Query, HTTPException, Path as ApiPath
from fastapi.responses import Response
import httpx
from datetime import datetime, timedelta, timezone, tzinfo
import structlog
from pydantic import BaseModel, Field
from typing import Literal
from app.utils.diagnostic_redaction import safe_connection_error
from app.services.audio.audio_service import audio_service
from app.services.audio.heard_groups import (
    HEARD_GROUP_GAP_SECONDS,
    ConfirmedVisit,
    HeardCall,
    attribute_calls,
    fold_heard_calls,
)
from app.repositories.visit_repository import VisitRepository
from app.services.broadcaster import broadcaster
from app.services.leaderboard_window import (
    LEADERBOARD_SPAN_DESCRIPTION,
    WindowMismatch,
    LeaderboardWindows,
    leaderboard_windows,
    previous_window_is_complete,
)
from app.services.weekday_hour_grid import weekday_hour_grid
from app.config import settings
from app.auth import AuthContext, require_owner
from app.auth import get_auth_context_with_legacy
from app.ratelimit import guest_rate_limit
from app.database import get_db
from app.repositories.audio_history_repository import AudioHistoryRepository, filter_names_a_source
from app.utils.audio_source_identity import AudioSourceDirectory
from app.repositories.detection_repository import DetectionRepository, match_audio_history_visual_events
from app.utils.language import get_user_language
from app.utils.timezone import calendar_timezone
from app.utils.audio_localization import localize_audio_detections
from app.utils.canonical_species import should_hide_species_label
from app.utils.api_datetime import parse_storage_datetime, serialize_api_datetime
from app.utils.public_access import privacy_checked_db, public_event_visible, public_events_window

router = APIRouter(prefix="/audio", tags=["audio"])


async def require_public_audio(auth: AuthContext = Depends(get_auth_context_with_legacy)) -> AuthContext:
    """Audio is the owner's to share (#291): a visitor is refused plainly
    when the switch is off, instead of audio being the one medium with no
    control at all."""
    if not auth.is_owner and not (settings.public_access.enabled and settings.public_access.show_audio):
        raise HTTPException(status_code=403, detail="Audio is not shared publicly on this instance.")
    return auth


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


class AudioVisibilityRequest(BaseModel):
    hidden: bool


class AudioVisibilityResponse(BaseModel):
    id: int
    hidden: bool


class AudioBulkVisibilityRequest(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=500)
    hidden: bool


class AudioBulkVisibilityResponse(BaseModel):
    updated_count: int
    ids: list[int]
    hidden: bool


class AudioHiddenCountResponse(BaseModel):
    hidden_count: int


@router.get("/history/hidden-count", response_model=AudioHiddenCountResponse)
async def get_hidden_audio_count(auth: AuthContext = Depends(require_owner)) -> AudioHiddenCountResponse:
    """Count hidden BirdNET-Go audio detections (owner only)."""
    async with privacy_checked_db(get_db) as db:
        hidden_count = await AudioHistoryRepository(db).count_hidden_audio_detections()
    return AudioHiddenCountResponse(hidden_count=hidden_count)


@router.patch("/history/visibility", response_model=AudioBulkVisibilityResponse)
async def set_audio_visibility_bulk(
    body: AudioBulkVisibilityRequest,
    auth: AuthContext = Depends(require_owner),
) -> AudioBulkVisibilityResponse:
    """Hide or restore multiple BirdNET-Go audio detections in one call (owner only)."""
    updated_ids = await audio_service.set_hidden_bulk(body.ids, body.hidden)
    if updated_ids:
        await broadcaster.broadcast({"type": "audio_history_changed"})
    return AudioBulkVisibilityResponse(updated_count=len(updated_ids), ids=updated_ids, hidden=body.hidden)


@router.patch("/history/{detection_id}", response_model=AudioVisibilityResponse)
async def set_audio_visibility(
    body: AudioVisibilityRequest,
    detection_id: int = ApiPath(..., ge=1),
    auth: AuthContext = Depends(require_owner),
) -> AudioVisibilityResponse:
    if not await audio_service.set_hidden(detection_id, body.hidden):
        raise HTTPException(status_code=404, detail="Audio detection not found")
    await broadcaster.broadcast({"type": "audio_history_changed"})
    return AudioVisibilityResponse(id=detection_id, hidden=body.hidden)


class AudioSourceNameResponse(BaseModel):
    name: str
    last_seen: str | None = Field(
        description="The newest visible call under this name, as UTC ISO 8601; null when only hidden calls carry it."
    )
    current: bool = Field(description="Whether this is the name on the stream's newest call.")
    offer_link_by_id: bool = Field(
        description=(
            "An earlier name only this stream has carried and no source carries now: a camera linked by it "
            "can be offered the stream id."
        )
    )


class AudioSourceResponse(BaseModel):
    source_name: str = Field(description="The name on the stream's newest call, or its id when it sent no name.")
    mapping_value: str = Field(
        description="What a camera's audio link should hold: the stream id, or the name as calls carry it when the source sends no id."
    )
    source_id: str | None = Field(default=None, description="BirdNET-Go's id for the stream; kept across a rename.")
    source_node: str | None = Field(default=None, description="The BirdNET-Go install that sent the stream's calls.")
    installs_sharing_id: list[str] = Field(
        default_factory=list,
        description="Every install sending this stream id, decided over every stream before `limit`; empty unless more than one.",
    )
    last_seen: str = Field(description="The newest visible call carrying the value to save, as UTC ISO 8601.")
    names: list[AudioSourceNameResponse] = Field(
        default_factory=list, description="Every name the stream has carried, the current one first."
    )


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
    scientific_name: str | None = None
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
    # The name on the source's newest call: a renamed source is one entry with all of its calls.
    source_name: str
    # BirdNET-Go's id for the source, which tells apart two sources that carry the same name.
    # Null for calls from before BirdNET-Go reported ids.
    source_id: str | None = None
    # The BirdNET-Go install the source belongs to, which tells apart two installs whose sources
    # share a name and an id. Null when its calls name none.
    source_node: str | None = None
    count: int
    last_heard: str


class AudioSummaryResponse(BaseModel):
    # The window counted, which for a guest is the requested one narrowed to the shared history.
    window_start: str
    window_end: str
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
    span: Literal["today", "day", "week", "month", "all"]
    window_start: str
    window_end: str
    # Whether a guest's allowance moved window_start later than the span asks for.
    window_shortened: bool = False
    history_start: str | None = None
    previous_window_complete: bool = False
    # Why the previous window is no fair comparison whatever the history holds, or null when it is:
    # a clock change in today, a guest's allowance cutting either window, or cleanup having removed
    # captures from part of one.
    previous_window_mismatch: WindowMismatch | None = None
    species: list[AudioSpeciesLeaderboardItemResponse]


class AudioContextDetectionResponse(AudioDetectionResponse):
    offset_seconds: int
    scientific_name: str | None = None
    matches_visual: bool = False


def _normalized_species_aliases(*values: str | None) -> set[str]:
    return {value.strip().casefold() for value in values if isinstance(value, str) and value.strip()}


class AudioHistoryQuery(BaseModel):
    start_date: datetime
    end_date: datetime
    public_start: datetime | None = None
    public_end: datetime | None = None

    @property
    def counted_end(self) -> datetime:
        """The last instant counted: the requested end, or the exclusive end of a guest's shared day."""
        return min(self.end_date, self.public_end) if self.public_end else self.end_date


def _history_window(
    days: int, start_date: datetime | None, end_date: datetime | None, auth: AuthContext
) -> AudioHistoryQuery:
    now = datetime.now(timezone.utc)
    resolved_end = end_date
    if resolved_end is None:
        resolved_end = now
    elif resolved_end.tzinfo is None:
        resolved_end = resolved_end.replace(tzinfo=timezone.utc)

    resolved_start = start_date
    if resolved_start is None:
        resolved_start = resolved_end - timedelta(days=days)
    elif resolved_start.tzinfo is None:
        resolved_start = resolved_start.replace(tzinfo=timezone.utc)

    public_start, public_end = (None, None) if auth.is_owner else public_events_window(now)
    if not auth.is_owner:
        resolved_start = max(resolved_start, public_start)
        if public_end:
            resolved_end = min(resolved_end, public_end)

    return AudioHistoryQuery(
        start_date=resolved_start, end_date=resolved_end, public_start=public_start, public_end=public_end
    )


async def _viewer_source_directory(
    repo: AudioHistoryRepository,
    *,
    public_start: datetime | None,
    public_end: datetime | None,
    only_hidden: bool = False,
) -> AudioSourceDirectory:
    """The sources a view names, read from the calls it may show.

    A guest's is read from the shared window only, so no source name or id from outside it reaches
    them: not as a label, not through a source or search filter, and not by an older call joining a
    source renamed before the window. The owner's hidden view names and counts hidden calls, and
    every call the owner keeps decides which source an older id-less call belongs to.
    """
    return await repo.load_audio_source_directory(
        minimum_start=public_start,
        maximum_end=public_end,
        hidden=only_hidden,
        # Only an owner's view is unbounded at its start; a guest's never sees hidden calls.
        owner_evidence=public_start is None,
    )


@router.get("/recent", response_model=list[AudioDetectionResponse])
@guest_rate_limit()
async def get_recent_audio(
    request: Request, limit: int = Query(default=10, ge=1, le=500), auth: AuthContext = Depends(require_public_audio)
):
    """Get the most recent audio detections from the memory buffer."""
    if auth.is_owner:
        detections = await audio_service.get_recent_detections(limit=limit)
    else:
        # The memory buffer can lag owner hide decisions. Authoritative persisted
        # visibility is applied before paging, rather than filtering a stale buffer.
        now = datetime.now(timezone.utc)
        public_start, public_end = public_events_window(now)
        async with privacy_checked_db(get_db) as db:
            result = await AudioHistoryRepository(db).get_audio_history(
                start_date=public_start,
                end_date=now,
                limit=limit,
                maximum_end=public_end,
            )
        detections = result["items"]
    lang = get_user_language(request) or "en"
    await localize_audio_detections(detections, lang)
    # Drop scientific_name from the response — it is an internal hook for localization
    # and is not part of the public Recent Audio contract.
    for detection in detections:
        detection.pop("scientific_name", None)
    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names
    if hide_sensor:
        for detection in detections:
            detection["sensor_id"] = None
            detection["source_name"] = None
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
    search: str | None = Query(default=None, max_length=120),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    only_hidden: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    auth: AuthContext = Depends(require_public_audio),
):
    """Browse persisted BirdNET-Go detections separately from visual detections."""
    if only_hidden and not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner privileges required to view hidden audio detections")
    window = _history_window(days, start_date, end_date, auth)
    lang = get_user_language(request) or "en"
    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names

    if hide_sensor:
        source = None
    async with privacy_checked_db(get_db) as db:
        repo = DetectionRepository(db)
        audio_repo = AudioHistoryRepository(db)
        async with audio_repo.one_reading():
            # Read only for a filter that names a source: a plain window needs no names but its own.
            directory = (
                await _viewer_source_directory(
                    audio_repo, public_start=window.public_start, public_end=window.public_end, only_hidden=only_hidden
                )
                if filter_names_a_source(source, search, not hide_sensor)
                else None
            )
            result = await audio_repo.get_audio_history(
                start_date=window.start_date,
                end_date=window.end_date,
                species=species,
                source=source,
                min_confidence=min_confidence,
                maximum_end=window.public_end,
                only_hidden=only_hidden,
                search=search,
                search_include_source=not hide_sensor,
                limit=limit,
                offset=offset,
                directory=directory,
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
                candidate_start = max(candidate_start, window.public_start)
            candidates = await repo.get_audio_visual_match_candidates(
                start_date=candidate_start,
                end_date=candidate_end,
                scientific_names={item["scientific_name"] for item in result["items"] if item.get("scientific_name")},
                maximum_end=window.public_end,
            )
            matches = match_audio_history_visual_events(
                result["items"],
                candidates,
                window_seconds=correlation_window,
                camera_audio_mapping=settings.frigate.camera_audio_mapping,
            )
            for item in result["items"]:
                item["matched_visual_event_id"] = matches.get(item["id"])
    await localize_audio_detections(result["items"], lang)

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
    search: str | None = Query(default=None, max_length=120),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    only_hidden: bool = Query(default=False),
    auth: AuthContext = Depends(require_public_audio),
):
    """Summarise persisted BirdNET-Go detection history."""
    if only_hidden and not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner privileges required to view hidden audio detections")
    window = _history_window(days, start_date, end_date, auth)
    lang = get_user_language(request) or "en"
    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names

    if hide_sensor:
        source = None
    async with privacy_checked_db(get_db) as db:
        repo = AudioHistoryRepository(db)
        async with repo.one_reading():
            result = await repo.get_audio_history_summary(
                directory=await _viewer_source_directory(
                    repo, public_start=window.public_start, public_end=window.public_end, only_hidden=only_hidden
                ),
                start_date=window.start_date,
                end_date=window.end_date,
                species=species,
                source=source,
                min_confidence=min_confidence,
                maximum_end=window.public_end,
                only_hidden=only_hidden,
                search=search,
                search_include_source=not hide_sensor,
                calendar_zone=calendar_timezone(request),
            )
    # The scientific name stays: `species` is translated, so it is the only name the activity grid
    # can be asked for exactly.
    await localize_audio_detections(result["top_species"], lang)
    if hide_sensor:
        result["sources"] = []
        result["source_count"] = 0
    result["window_start"] = serialize_api_datetime(window.start_date)
    result["window_end"] = serialize_api_datetime(window.counted_end)

    return result


class AudioActivityHeatmapCell(BaseModel):
    day_of_week: int  # 0=Sunday..6=Saturday
    hour: int  # 0..23
    count: int


class AudioActivityHeatmapResponse(BaseModel):
    """Calls heard per local weekday and hour: the same cell shape as the camera grid's."""

    window_start: str
    window_end: str
    total_count: int
    max_cell_count: int
    cells: list[AudioActivityHeatmapCell]


@router.get("/activity-heatmap", response_model=AudioActivityHeatmapResponse)
@guest_rate_limit()
async def get_audio_activity_heatmap(
    request: Request,
    days: int = Query(default=30, ge=1, le=3650),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    species: str | None = Query(default=None, max_length=120),
    source: str | None = Query(default=None, max_length=120),
    search: str | None = Query(default=None, max_length=120),
    min_confidence: float | None = Query(default=None, ge=0.0, le=1.0),
    only_hidden: bool = Query(default=False),
    scientific_name: str | None = Query(
        default=None,
        max_length=200,
        description="Limit the grid to one species exactly, by its scientific name",
    ),
    auth: AuthContext = Depends(require_public_audio),
) -> AudioActivityHeatmapResponse:
    """Calls heard by weekday and hour in the viewer's time zone, over the summary's window and filters."""
    if only_hidden and not auth.is_owner:
        raise HTTPException(status_code=403, detail="Owner privileges required to view hidden audio detections")
    window = _history_window(days, start_date, end_date, auth)
    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names
    if hide_sensor:
        source = None
    async with privacy_checked_db(get_db) as db:
        repo = AudioHistoryRepository(db)
        async with repo.one_reading():
            utc_quarter_hour_counts = await repo.get_audio_activity_utc_quarter_hour_counts(
                directory=(
                    await _viewer_source_directory(
                        repo, public_start=window.public_start, public_end=window.public_end, only_hidden=only_hidden
                    )
                    if filter_names_a_source(source, search, not hide_sensor)
                    else None
                ),
                start_date=window.start_date,
                end_date=window.end_date,
                species=species,
                source=source,
                min_confidence=min_confidence,
                maximum_end=window.public_end,
                scientific_name=scientific_name,
                only_hidden=only_hidden,
                search=search,
                search_include_source=not hide_sensor,
            )
    grid = weekday_hour_grid(utc_quarter_hour_counts, calendar_timezone(request))
    return AudioActivityHeatmapResponse(
        window_start=serialize_api_datetime(window.start_date),
        window_end=serialize_api_datetime(window.counted_end),
        total_count=grid.total_count,
        max_cell_count=grid.max_cell_count,
        cells=[
            AudioActivityHeatmapCell(day_of_week=cell.day_of_week, hour=cell.hour, count=cell.count)
            for cell in grid.cells
        ],
    )


class HeardGroupResponse(BaseModel):
    species: str
    scientific_name: str | None = None
    first_heard: str
    last_heard: str
    call_count: int
    best_confidence: float
    best_heard: str
    best_birdnet_id: int | None = None
    source_name: str | None = None


class HeardVisitCallsResponse(BaseModel):
    visit_id: str
    start_time: str
    end_time: str
    scientific_name: str | None = None
    call_count: int


class HeardGroupsResponse(BaseModel):
    groups: list[HeardGroupResponse]
    matched_visits: list[HeardVisitCallsResponse] = []
    call_count: int
    truncated: bool
    gap_seconds: int
    correlation_window_seconds: int


HEARD_GROUP_MAX_CALLS = 20_000
HEARD_GROUP_MAX_SPAN = timedelta(days=93)


@router.get("/heard-groups", response_model=HeardGroupsResponse)
@guest_rate_limit()
async def get_heard_groups(
    request: Request,
    start_date: datetime = Query(...),
    end_date: datetime = Query(...),
    auth: AuthContext = Depends(require_public_audio),
):
    """BirdNET-Go calls in a window, for the Explorer's heard bands.

    The Explorer asks for the span its page of visits covers. Calls that support a visit the
    pipeline confirmed are counted on that visit; the rest are folded per species into bouts of
    no more than ``gap_seconds`` of silence, so a chattering sparrow is one entry rather than forty.
    """
    window = _history_window(1, start_date, end_date, auth)
    if window.end_date <= window.start_date:
        return HeardGroupsResponse(
            groups=[],
            matched_visits=[],
            call_count=0,
            truncated=False,
            gap_seconds=HEARD_GROUP_GAP_SECONDS,
            correlation_window_seconds=max(0, int(settings.frigate.audio_correlation_window_seconds)),
        )
    if window.end_date - window.start_date > HEARD_GROUP_MAX_SPAN:
        raise HTTPException(status_code=422, detail="Ask for at most 93 days of heard calls at a time.")
    lang = get_user_language(request) or "en"
    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names

    correlation_window = max(0, int(settings.frigate.audio_correlation_window_seconds))
    async with privacy_checked_db(get_db) as db:
        result = await AudioHistoryRepository(db).get_audio_history(
            start_date=window.start_date,
            end_date=window.end_date,
            maximum_end=window.public_end,
            limit=HEARD_GROUP_MAX_CALLS,
            offset=0,
        )
        # A visit that began before the window can still own calls inside it, so the visit window
        # reaches back further; an hour covers any visit the 60 s grouping rule produces in practice.
        visit_rows = await VisitRepository(db).confirmed_visit_spans(
            start=(window.start_date - timedelta(seconds=correlation_window) - timedelta(hours=1)).replace(tzinfo=None),
            end=(window.end_date + timedelta(seconds=correlation_window)).replace(tzinfo=None),
            public_audio=not auth.is_owner,
        )

    calls = [
        HeardCall(
            timestamp=datetime.fromisoformat(item["timestamp"]),
            species=item["species"],
            scientific_name=item.get("scientific_name"),
            confidence=float(item["confidence"] or 0.0),
            birdnet_id=item.get("birdnet_id"),
            source_name=None if hide_sensor else item.get("source_name"),
            mapping_keys=frozenset(item.get("_mapping_keys") or ()),
        )
        for item in result["items"]
    ]
    visits = [
        ConfirmedVisit(
            visit_id=str(row["visit_id"]),
            start=datetime.fromisoformat(str(row["start_time"])),
            end=datetime.fromisoformat(str(row["end_time"])),
            camera_name=str(row["camera_name"] or ""),
            scientific_key=str(row["name_key"] or ""),
            names=frozenset(
                name.strip().casefold() for name in (row["common_name"], row["display_name"]) if isinstance(name, str)
            ),
        )
        for row in visit_rows
    ]
    if window.public_start is not None:
        # A guest is told about no visit older than their window, not even its id.
        public_start = window.public_start.replace(tzinfo=None)
        visits = [visit for visit in visits if visit.start.replace(tzinfo=None) >= public_start]
    matched, unmatched = attribute_calls(
        calls,
        visits,
        window_seconds=correlation_window,
        camera_audio_mapping=settings.frigate.camera_audio_mapping,
    )
    by_visit = {visit.visit_id: visit for visit in visits}
    groups = [
        {
            "species": group.species,
            "scientific_name": group.scientific_name,
            "first_heard": serialize_api_datetime(group.first_heard),
            "last_heard": serialize_api_datetime(group.last_heard),
            "call_count": group.call_count,
            "best_confidence": group.best_confidence,
            "best_heard": serialize_api_datetime(group.best_heard),
            "best_birdnet_id": group.best_birdnet_id,
            "source_name": group.source_name,
        }
        for group in fold_heard_calls(unmatched)
    ]
    await localize_audio_detections(groups, lang)
    return HeardGroupsResponse(
        groups=[HeardGroupResponse(**group) for group in groups],
        matched_visits=[
            HeardVisitCallsResponse(
                visit_id=visit_id,
                start_time=serialize_api_datetime(by_visit[visit_id].start),
                end_time=serialize_api_datetime(by_visit[visit_id].end),
                scientific_name=by_visit[visit_id].scientific_key or None,
                call_count=count,
            )
            for visit_id, count in matched.items()
        ],
        call_count=len(calls),
        truncated=result["total"] > len(calls),
        gap_seconds=HEARD_GROUP_GAP_SECONDS,
        correlation_window_seconds=max(0, int(settings.frigate.audio_correlation_window_seconds)),
    )


def _audio_leaderboard_windows(
    span: str, *, now: datetime, zone: tzinfo, floor: datetime | None, ceiling: datetime | None
) -> LeaderboardWindows:
    """The visual leaderboard's windows for ``span``, so Seen, Heard and Both count the same stretch.

    ``all`` reaches back to the epoch, so every stored call counts and the prior window holds nothing.
    """
    if span != "all":
        return leaderboard_windows(span, now=now, zone=zone, floor=floor, ceiling=ceiling)
    epoch = datetime(1970, 1, 1)
    end = now.astimezone(timezone.utc).replace(tzinfo=None)
    start = max(epoch, floor) if floor is not None else epoch
    end = min(end, ceiling) if ceiling is not None else end
    return LeaderboardWindows(start, end, start, start, mismatch=None, shortened=False)


@router.get("/species", response_model=AudioSpeciesLeaderboardResponse)
@guest_rate_limit()
async def get_audio_species_leaderboard(
    request: Request,
    span: Literal["today", "day", "week", "month", "all"] = Query(
        default="week", description=f"{LEADERBOARD_SPAN_DESCRIPTION} `all`: every stored call."
    ),
    auth: AuthContext = Depends(require_public_audio),
):
    """Heard-count leaderboard over persisted BirdNET-Go detections.

    Returns one row per species (grouped by scientific name where available) with the
    current-window heard count plus the prior window for trend, so the Species page can
    merge these onto the camera "seen" leaderboard. Species names are localized through
    the same taxonomy path as the visual leaderboard so client-side matching lines up.
    """
    now = datetime.now(timezone.utc)
    public_cutoff, public_end = (None, None) if auth.is_owner else public_events_window(now)
    windows = _audio_leaderboard_windows(
        span,
        now=now,
        zone=calendar_timezone(request),
        floor=public_cutoff.replace(tzinfo=None) if public_cutoff is not None else None,
        ceiling=public_end.replace(tzinfo=None) if public_end is not None else None,
    )
    window_start, window_end = windows.start, windows.end
    prev_start, prev_end = windows.prev_start, windows.prev_end
    lang = get_user_language(request) or "en"
    unknown_labels = getattr(settings.classification, "unknown_bird_labels", None) or []

    async with privacy_checked_db(get_db) as db:
        repo = AudioHistoryRepository(db)
        rows = await repo.get_audio_species_counts(
            window_start=window_start,
            window_end=window_end,
            prev_start=prev_start,
            prev_end=prev_end,
        )
        history_start = await repo.get_audio_history_start(minimum_start=public_cutoff, maximum_end=public_end)
    await localize_audio_detections(rows, lang)

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
        "window_start": window_start.replace(tzinfo=timezone.utc).isoformat(),
        "window_end": window_end.replace(tzinfo=timezone.utc).isoformat(),
        "window_shortened": windows.shortened,
        "previous_window_mismatch": windows.mismatch,
        "history_start": serialize_api_datetime(history_start) if history_start else None,
        "previous_window_complete": windows.comparable
        and prev_start < prev_end
        and previous_window_is_complete(history_start=history_start, prev_start=prev_start),
        "species": species,
    }


async def _require_audio_media_visibility(birdnet_id: int, auth: AuthContext) -> None:
    if auth.is_owner:
        return
    public_start, public_end = public_events_window()
    async with privacy_checked_db(get_db) as db:
        visible = await AudioHistoryRepository(db).public_birdnet_media_visible(
            birdnet_id, public_start, maximum_end=public_end
        )
    if not visible:
        raise HTTPException(status_code=404, detail="Audio detection not found")


@router.get("/spectrogram/{birdnet_id}", response_class=Response)
async def get_audio_spectrogram(
    birdnet_id: int,
    width: int = Query(default=400, ge=64, le=1600),
    auth: AuthContext = Depends(require_public_audio),
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
    await _require_audio_media_visibility(birdnet_id, auth)
    target = f"{base_url}/api/v2/spectrogram/{birdnet_id}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(target, params={"width": width})
    except httpx.HTTPError as exc:
        log.warning("birdnet_spectrogram_proxy_failed", id=birdnet_id, error=safe_connection_error(exc))
        raise HTTPException(status_code=502, detail="BirdNET-Go unreachable")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Spectrogram not found")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"BirdNET-Go returned {response.status_code}")
    media_type = response.headers.get("content-type", "image/png")
    return Response(
        content=response.content,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=86400" if auth.is_owner else "private, no-store"},
    )


@router.get("/clip/{birdnet_id}", response_class=Response)
async def get_audio_clip(
    birdnet_id: int,
    request: Request,
    auth: AuthContext = Depends(require_public_audio),
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
    await _require_audio_media_visibility(birdnet_id, auth)
    target = f"{base_url}/api/v2/audio/{birdnet_id}"
    forward_headers: dict[str, str] = {}
    if range_header := request.headers.get("range"):
        forward_headers["Range"] = range_header
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(target, headers=forward_headers)
    except httpx.HTTPError as exc:
        log.warning("birdnet_clip_proxy_failed", id=birdnet_id, error=safe_connection_error(exc))
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
    pass_through["Cache-Control"] = "private, max-age=86400" if auth.is_owner else "private, no-store"
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
    auth: AuthContext = Depends(require_public_audio),
):
    """Get audio detections near a specific detection time."""
    target_time = timestamp
    if target_time.tzinfo is None:
        target_time = target_time.replace(tzinfo=timezone.utc)

    mapping_value = "*" if not camera else (settings.frigate.camera_audio_mapping or {}).get(camera)
    if not auth.is_owner and not settings.public_access.show_camera_names:
        mapping_value = "*"

    lang = get_user_language(request) or "en"
    public_start, public_end = (None, None) if auth.is_owner else public_events_window()
    async with privacy_checked_db(get_db) as db:
        repo = AudioHistoryRepository(db)
        detections, suppressed_by_mapping = await repo.get_audio_context(
            target_time=target_time,
            window_seconds=window_seconds,
            mapping_value=mapping_value,
            limit=limit,
            minimum_start=public_start,
            maximum_end=public_end,
        )
    await localize_audio_detections(detections, lang)
    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names
    if hide_sensor:
        for detection in detections:
            detection["sensor_id"] = None
            detection["source_name"] = None
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
    auth: AuthContext = Depends(require_public_audio),
):
    """Get BirdNET-Go detections near a persisted visual event.

    Event-scoped lookup ensures the server's current source mapping and
    correlation window are applied even when audio arrived after the visual
    event's ingest-time correlation attempt.
    """
    lang = get_user_language(request) or "en"
    policy_now = datetime.now(timezone.utc)
    public_start, public_end = (None, None) if auth.is_owner else public_events_window(policy_now)
    async with privacy_checked_db(get_db) as db:
        repo = DetectionRepository(db)
        event = await repo.get_by_frigate_event(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Detection not found")

        if not auth.is_owner and not public_event_visible(event, policy_now):
            raise HTTPException(status_code=404, detail="Detection not found")

        mapping_value = None
        if settings.frigate.camera_audio_mapping:
            mapping_value = settings.frigate.camera_audio_mapping.get(event.camera_name)

        detections, suppressed_by_mapping = await AudioHistoryRepository(db).get_audio_context(
            target_time=event.detection_time,
            window_seconds=settings.frigate.audio_correlation_window_seconds,
            mapping_value=mapping_value,
            limit=8,
            minimum_start=public_start,
            maximum_end=public_end,
        )
        visual_aliases = _normalized_species_aliases(
            event.display_name,
            event.category_name,
            event.scientific_name,
            event.common_name,
        )
        for detection in detections:
            audio_aliases = _normalized_species_aliases(
                detection.get("species"),
                detection.get("scientific_name"),
            )
            detection["matches_visual"] = bool(visual_aliases.intersection(audio_aliases))
    await localize_audio_detections(detections, lang)

    hide_sensor = not auth.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names
    if hide_sensor:
        for detection in detections:
            detection["sensor_id"] = None
            detection["source_name"] = None
    response.headers[AUDIO_SUPPRESSED_BY_MAPPING_HEADER] = str(suppressed_by_mapping)
    return detections


def _api_time(stored: str) -> str:
    return serialize_api_datetime(parse_storage_datetime(stored)) or stored


@router.get("/sources", response_model=list[AudioSourceResponse])
async def get_audio_sources(
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(require_owner),
) -> list[AudioSourceResponse]:
    """The BirdNET-Go sources a camera can be linked to, one per stream, newest first (owner only).

    Each stream is listed under its current name with every name it carried, so the owner can link
    a camera by the stream's id and keep the link across a rename. Which earlier names warrant a
    rename notice is decided here, from every stream, before the list is cut to ``limit``.
    """
    async with privacy_checked_db(get_db) as db:
        links = await AudioHistoryRepository(db).load_audio_source_links()
    return [
        AudioSourceResponse(
            source_name=link.source_name,
            mapping_value=link.mapping_value,
            source_id=link.source_id,
            source_node=link.source_node,
            installs_sharing_id=link.installs_sharing_id,
            last_seen=_api_time(link.last_seen),
            names=[
                AudioSourceNameResponse(
                    name=name.name,
                    last_seen=_api_time(name.last_seen) if name.last_seen else None,
                    current=name.current,
                    offer_link_by_id=name.offer_link_by_id,
                )
                for name in link.names
            ],
        )
        for link in links[:limit]
    ]
