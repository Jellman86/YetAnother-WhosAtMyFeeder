"""Private, paginated animal reviews. Confirmation records presence, not species."""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated, Literal

from app.auth import AuthContext, require_owner
from app.database import get_db
from app.repositories.garden_visit_repository import GardenVisitRepository
from app.repositories.garden_repository import (
    GardenCapture,
    GardenPhotoUnavailable,
    GardenRepository,
    GardenStatus,
    GardenTimelineStatus,
)
from app.services.garden_capture_service import garden_capture_service
from app.services import garden_motion_privacy
from app.models.garden import (
    GardenIdentification,
    GardenIdentificationStatus,
    GardenIdentifyRequest,
    GardenVariant,
    GardenPhotoCheck,
    GardenPhotoCheckRequest,
    GardenAutomaticCheck,
)
from app.models.garden_motion import MotionSource, GardenMotionStatus
from app.services.garden_motion import garden_motion_service
from app.services.garden_identification import garden_identification_service
from app.services.species_names import species_name_lookup


def require_garden_beta() -> None:
    from app.config import settings

    if not settings.system.beta_garden_animals:
        raise HTTPException(
            404, "Garden animals is a beta feature that is switched off. Turn it on in Settings, Beta features."
        )


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(
    prefix="/garden",
    tags=["garden"],
    dependencies=[Depends(require_owner), Depends(require_garden_beta), Depends(private_response)],
)


class GardenCaptureResponse(BaseModel):
    id: str
    camera: str
    frigate_label: str
    observed_at: str
    status: GardenStatus
    reviewed_at: str | None
    snapshot_url: str | None
    identification: GardenIdentification | None = None
    source_kind: Literal["frigate_event", "motion"] = "frigate_event"
    motion_source: MotionSource | None = None
    automatic_check: GardenAutomaticCheck | None = None
    automatic_check_overridden: bool = False


class GardenCapturePage(BaseModel):
    items: list[GardenCaptureResponse]
    total: int
    limit: int
    offset: int


class GardenBatchReviewRequest(BaseModel):
    ids: list[Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]] = Field(min_length=1, max_length=128)
    action: Literal["dismiss", "restore"]


class GardenBatchReviewResponse(BaseModel):
    updated_ids: list[str]
    skipped_count: int


async def _response(capture: GardenCapture, names: dict[int, str] | None = None) -> GardenCaptureResponse:
    identification = capture.identification
    if identification and identification.species_id:
        if names is None:
            names = await asyncio.to_thread(
                species_name_lookup.display_names, [identification.species_id], language="en"
            )
        if name := names.get(identification.species_id):
            identification = identification.model_copy(update={"name": name})
    return GardenCaptureResponse(
        id=capture.id,
        camera=capture.camera,
        frigate_label=capture.label,
        observed_at=capture.observed_at + "Z",
        status=capture.status,
        reviewed_at=capture.reviewed_at + "Z" if capture.reviewed_at else None,
        snapshot_url=f"/api/garden/{capture.id}/snapshot" if capture.has_snapshot else None,
        identification=identification,
        source_kind="motion" if capture.motion_source else "frigate_event",
        motion_source=capture.motion_source,
        automatic_check=capture.automatic_check,
        automatic_check_overridden=capture.automation_overridden,
    )


async def _page(items: list[GardenCapture], total: int, limit: int, offset: int) -> GardenCapturePage:
    names = await asyncio.to_thread(
        species_name_lookup.display_names,
        [item.identification.species_id for item in items if item.identification and item.identification.species_id],
        language="en",
    )
    return GardenCapturePage(
        items=[await _response(item, names) for item in items], total=total, limit=limit, offset=offset
    )


@router.get("", response_model=GardenCapturePage)
async def list_captures(
    response: Response,
    status: GardenStatus = "pending",
    limit: int = Query(20, ge=1, le=128),
    offset: int = Query(0, ge=0),
) -> GardenCapturePage:
    response.headers["Cache-Control"] = "private, no-store"
    async with get_db() as db:
        repository = GardenRepository(db)
        items = await repository.list(status, limit, offset)
        total = await repository.count(status)
    return await _page(items, total, limit, offset)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


@router.get("/timeline", response_model=GardenCapturePage)
async def capture_timeline(
    start: datetime | None = None,
    end: datetime | None = None,
    camera: str | None = Query(None, max_length=128),
    order: Literal["newest", "oldest"] = "newest",
    status: GardenTimelineStatus = "reviewable",
    limit: int = Query(48, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> GardenCapturePage:
    """Captures by time for the Explorer: confirmed and awaiting review unless one review state is asked for."""
    start, end = _as_utc(start), _as_utc(end)
    if start is not None and end is not None and start > end:
        raise HTTPException(422, "The window starts after it ends.")
    async with get_db() as db:
        repository = GardenRepository(db)
        items = await repository.timeline(
            start=start,
            end=end,
            camera=camera,
            newest_first=order == "newest",
            limit=limit,
            offset=offset,
            status=status,
        )
        total = await repository.timeline_count(start=start, end=end, camera=camera, status=status)
    return await _page(items, total, limit, offset)


class GardenVisitResponse(BaseModel):
    id: str
    kind: Literal["position", "visit"]
    start_time: str
    end_time: str
    capture_count: int
    representative: GardenCaptureResponse


class GardenVisitPage(BaseModel):
    visits: list[GardenVisitResponse]
    total: int
    capture_total: int
    limit: int
    offset: int


@router.get("/visits", response_model=GardenVisitPage)
async def garden_visits(
    start: datetime | None = None,
    end: datetime | None = None,
    camera: str | None = Query(None, max_length=128),
    order: Literal["newest", "oldest"] = "newest",
    status: GardenTimelineStatus = "reviewable",
    limit: int = Query(48, ge=1, le=200),
    offset: int = Query(0, ge=0),
    page_start: datetime | None = None,
    page_end: datetime | None = None,
) -> GardenVisitPage:
    start, end = _as_utc(start), _as_utc(end)
    if start is not None and end is not None and start > end:
        raise HTTPException(422, "The window starts after it ends.")
    async with get_db() as db:
        repo = GardenVisitRepository(db)
        rows, total, captures = await repo.visits(
            start=start,
            end=end,
            camera=camera,
            newest_first=order == "newest",
            status=status,
            limit=limit,
            offset=offset,
            page_start=_as_utc(page_start),
            page_end=_as_utc(page_end),
        )
        records = await repo.get_many([row["representative"] for row in rows])
        presented = await _page(records, len(records), limit, offset)
        by_id = {item.id: item for item in presented.items}
        visits = [
            GardenVisitResponse(
                id=row["id"],
                kind="position" if row["position"] else "visit",
                start_time=row["start_time"] + "Z",
                end_time=row["end_time"] + "Z",
                capture_count=row["capture_count"],
                representative=by_id[row["representative"]],
            )
            for row in rows
            if row["representative"] in by_id
        ]
    return GardenVisitPage(visits=visits, total=total, capture_total=captures, limit=limit, offset=offset)


@router.get("/visits/{visit_id}/captures", response_model=GardenCapturePage)
async def garden_visit_captures(
    visit_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    camera: str | None = Query(None, max_length=128),
    status: GardenTimelineStatus = "reviewable",
    limit: int = Query(128, ge=1, le=128),
    offset: int = Query(0, ge=0),
) -> GardenCapturePage:
    start, end = _as_utc(start), _as_utc(end)
    if start is not None and end is not None and start > end:
        raise HTTPException(422, "The window starts after it ends.")
    async with get_db() as db:
        items, total = await GardenVisitRepository(db).visit_captures(
            visit_id, start=start, end=end, camera=camera, status=status, limit=limit, offset=offset
        )
    if not total:
        raise HTTPException(404, "Garden visit is no longer available. Refresh the history.")
    return await _page(items, total, limit, offset)


@router.post("/review-batch", response_model=GardenBatchReviewResponse)
async def review_batch(request: GardenBatchReviewRequest) -> GardenBatchReviewResponse:
    ids = list(dict.fromkeys(request.ids))
    async with garden_motion_privacy.lock:
        garden_identification_service.invalidate_photo_checks()
        async with get_db() as db:
            updated = await GardenRepository(db).review_batch(ids, request.action)
    return GardenBatchReviewResponse(updated_ids=updated, skipped_count=len(ids) - len(updated))


@router.get("/identification", response_model=GardenIdentificationStatus)
async def identification_status(response: Response) -> GardenIdentificationStatus:
    response.headers["Cache-Control"] = "private, no-store"
    return await garden_identification_service.status()


@router.post("/models/{variant}/install", response_model=GardenIdentificationStatus)
async def install_garden_model(variant: GardenVariant) -> GardenIdentificationStatus:
    return await garden_identification_service.install(variant)


@router.get("/motion", response_model=GardenMotionStatus)
async def motion_status() -> GardenMotionStatus:
    return await garden_motion_service.status()


@router.post("/motion/install", response_model=GardenMotionStatus)
async def install_motion_detector() -> GardenMotionStatus:
    return await garden_motion_service.install()


@router.post("/{capture_id}/check-photo", response_model=GardenPhotoCheck)
async def check_photo(capture_id: str, request: GardenPhotoCheckRequest) -> GardenPhotoCheck:
    return await garden_identification_service.check_photo(capture_id, request)


@router.post("/{capture_id}/identify", response_model=GardenCaptureResponse)
async def identify_capture(capture_id: str, request: GardenIdentifyRequest) -> GardenCaptureResponse:
    await garden_identification_service.identify(capture_id, request)
    return await _response(await garden_capture_service.get(capture_id))


@router.post("/{capture_id}/identification/{action}", response_model=GardenCaptureResponse)
async def review_identification(capture_id: str, action: Literal["accept", "dismiss"]) -> GardenCaptureResponse:
    async with garden_motion_privacy.lock:
        garden_identification_service.invalidate_photo_checks()
        await garden_identification_service.review(capture_id, action)
    return await _response(await garden_capture_service.get(capture_id))


async def _review(capture_id: str, status: GardenStatus) -> GardenCaptureResponse:
    async with garden_motion_privacy.lock:
        garden_identification_service.invalidate_photo_checks()
        async with get_db() as db:
            try:
                capture = await GardenRepository(db).review(capture_id, status)
            except GardenPhotoUnavailable as error:
                raise HTTPException(409, str(error)) from error
    if capture is None:
        raise HTTPException(404, "Garden capture not found")
    return await _response(capture)


@router.post("/{capture_id}/confirm", response_model=GardenCaptureResponse)
async def confirm_capture(capture_id: str) -> GardenCaptureResponse:
    return await _review(capture_id, "confirmed")


@router.post("/{capture_id}/dismiss", response_model=GardenCaptureResponse)
async def dismiss_capture(capture_id: str) -> GardenCaptureResponse:
    return await _review(capture_id, "dismissed")


@router.post("/{capture_id}/restore", response_model=GardenCaptureResponse)
async def restore_capture(capture_id: str) -> GardenCaptureResponse:
    return await _review(capture_id, "pending")


@router.get("/{capture_id}/snapshot", response_class=Response, response_model=None)
async def capture_snapshot(capture_id: str, _auth: AuthContext = Depends(require_owner)) -> Response:
    image = await garden_capture_service.snapshot(capture_id)
    return Response(
        image,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
