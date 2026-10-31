"""The range filter's state, its preview, and the detections it set aside (#696). Owner only."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.auth import AuthContext, require_owner
from app.services.range_filter_service import range_filter_service

router = APIRouter(prefix="/range-filter", tags=["range-filter"])

RegionLevelName = Literal["county", "state", "country"]


class RangeRegion(BaseModel):
    code: str
    codes: list[str] = Field(description="Every eBird region combined into the list, nearest first")
    name: str | None = None
    level: RegionLevelName
    note: str | None = Field(None, description="Why the level differs from the setting, e.g. county_list_too_short")


class RangeModelCoverage(BaseModel):
    bird_species: int = Field(description="Bird species the active model can name")
    out_of_range: int = Field(description="Of those, species eBird names that the regional list does not")
    unmatched: int = Field(description="Model labels with no exact eBird identity, which are never filtered")


class RangeDecisionCounts(BaseModel):
    window_days: int
    fallback: int
    skipped: int


class RangeFilterStatus(BaseModel):
    enabled: bool
    filtering: bool = Field(description="True only while new detections are actually being range-checked")
    reason: Literal[
        "active",
        "ready",
        "needs_location",
        "needs_ebird_key",
        "waiting_for_list",
        "lookup_failed",
        "location_changed",
        "list_stale",
        "list_unusable",
    ]
    problem: str | None = None
    source: Literal["ebird"]
    location_precision: Literal["exact", "approximate", "country_only", "none"]
    region_level_setting: RegionLevelName
    ebird_configured: bool
    birdnet_enabled: bool
    region: RangeRegion | None = None
    species_in_range: int | None = None
    region_species_total: int | None = None
    heard_species: int = Field(description="Species BirdNET-Go heard here in the last year")
    heard_only_species: int = Field(description="Heard species the regional list does not include")
    refreshed_at: str | None = None
    next_refresh_at: str | None = None
    stale_after: str | None = None
    refreshing: bool
    last_error: str | None = None
    last_attempt_at: str | None = None
    model: RangeModelCoverage | None = None
    recent: RangeDecisionCounts


class RangePreviewSpecies(BaseModel):
    species_id: int
    scientific_name: str
    common_name: str | None = None
    detections: int | None = None
    last_seen: str | None = None


class RangeFilterPreview(BaseModel):
    available: bool
    window_days: int
    recently_seen: list[RangePreviewSpecies]
    model_out_of_range_total: int | None = None
    examples: list[RangePreviewSpecies]


class RangeSkip(BaseModel):
    frigate_event: str
    camera: str | None = None
    detected_at: str | None = None
    decided_at: str | None = None
    label: str
    score: float
    region_code: str


class RangeSkipsResponse(BaseModel):
    items: list[RangeSkip]


class RangeDecisionDetail(BaseModel):
    outcome: Literal["fallback", "skipped"]
    original_label: str
    original_score: float
    chosen_label: str | None = None
    chosen_score: float | None = None
    region_code: str
    decided_at: str | None = None


class RangeDecisionResponse(BaseModel):
    decision: RangeDecisionDetail | None = None


@router.get("/status", response_model=RangeFilterStatus)
async def get_range_filter_status(auth: AuthContext = Depends(require_owner)) -> RangeFilterStatus:
    """What the range filter is doing now, the list behind it, and why it is not filtering when it is not."""
    return RangeFilterStatus.model_validate(await range_filter_service.status())


@router.post("/refresh", response_model=RangeFilterStatus)
async def refresh_range_list(auth: AuthContext = Depends(require_owner)) -> RangeFilterStatus:
    """Fetch the regional list again in the background; poll the status to see it finish."""
    range_filter_service.request_refresh()
    return RangeFilterStatus.model_validate(await range_filter_service.status())


@router.get("/preview", response_model=RangeFilterPreview)
async def get_range_filter_preview(auth: AuthContext = Depends(require_owner)) -> RangeFilterPreview:
    """Species the filter would set aside, those recently recorded here first. Read-only."""
    return RangeFilterPreview.model_validate(await range_filter_service.preview())


@router.get("/skips", response_model=RangeSkipsResponse)
async def get_range_filter_skips(
    limit: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_owner),
) -> RangeSkipsResponse:
    """Detections set aside as out of range, newest first, so a vagrant can be found and recorded by hand."""
    return RangeSkipsResponse(
        items=[RangeSkip.model_validate(item) for item in await range_filter_service.recent_skips(limit=limit)]
    )


@router.get("/decisions/{frigate_event}", response_model=RangeDecisionResponse)
async def get_range_filter_decision(
    frigate_event: str, auth: AuthContext = Depends(require_owner)
) -> RangeDecisionResponse:
    """What the range filter changed for one detection, or nothing when it changed nothing."""
    decision = await range_filter_service.decision_for(frigate_event[:256])
    return RangeDecisionResponse(decision=RangeDecisionDetail.model_validate(decision) if decision else None)
