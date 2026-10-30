"""Private, paginated animal reviews. Confirmation records presence, not species."""

import asyncio
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from typing import Annotated, Literal

from app.auth import AuthContext, require_owner
from app.config import settings
from app.routers.proxy import validate_event_id
from app.database import get_db
from app.repositories.garden_visit_repository import GardenVisitRepository
from app.repositories.garden_repository import (
    GardenCapture,
    GardenPhotoUnavailable,
    GardenRepository,
    GardenStatus,
    GardenTimelineStatus,
)
from app.services.garden_notifications import garden_notification_service
from app.services.garden_capture_service import garden_capture_service
from app.services import garden_motion_privacy
from app.models.garden import (
    GardenIdentification,
    GardenOwnerIdentification,
    GardenSpecies,
    GardenRenameRequest,
    GardenNotificationStatus,
    GardenIdentificationStatus,
    GardenIdentifyRequest,
    GardenVariant,
    GardenPhotoCheck,
    GardenPhotoCheckRequest,
    GardenAutomaticCheck,
)
from app.models.garden_motion import MotionSource, GardenMotionStatus
from app.models.garden_crop import GardenCropEvidence, GardenCropStorage
from app.services.garden_crop_service import garden_crop_service
from app.services.garden_motion import garden_motion_service
from app.services.garden_identification import garden_identification_service
from app.services.species_names import SpeciesIdentityNames, species_name_lookup, vernacular_case
from app.utils.language import get_user_language


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
    crop_url: str | None = None
    crop: GardenCropEvidence | None = None
    identification: GardenIdentification | None = None
    owner_identification: GardenOwnerIdentification | None = None
    # The standing identification's catalogue name, so the record can show it as birds do.
    scientific_name: str | None = None
    source_kind: Literal["frigate_event", "motion"] = "frigate_event"
    motion_source: MotionSource | None = None
    automatic_check: GardenAutomaticCheck | None = None
    automatic_check_overridden: bool = False
    review_token: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    clip_event: str | None = Field(
        None, description="The Frigate event whose clip plays for this capture, while clips are enabled"
    )


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


class GardenDismissTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    review_token: str = Field(pattern=r"^[a-f0-9]{64}$")


class GardenDismissRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    captures: list[GardenDismissTarget] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def unique_captures(self) -> "GardenDismissRequest":
        if len({capture.id for capture in self.captures}) != len(self.captures):
            raise ValueError("Capture snapshots must have unique IDs")
        return self


async def _response(
    capture: GardenCapture, language: str, names: dict[int, SpeciesIdentityNames] | None = None
) -> GardenCaptureResponse:
    identification = capture.identification
    scientific_name = None
    if identification and identification.species_id:
        if names is None:
            names = await asyncio.to_thread(species_name_lookup.resolve, [identification.species_id], language=language)
        catalogue = names.get(identification.species_id)
        name = (catalogue.display if catalogue else None) or identification.name
        if name:
            identification = identification.model_copy(update={"name": vernacular_case(name)})
        scientific_name = catalogue.scientific if catalogue else None
    owner = capture.owner_identification
    if owner:
        if names is None or owner.species_id not in names:
            names = await asyncio.to_thread(species_name_lookup.resolve, [owner.species_id], language=language)
        catalogue = names.get(owner.species_id)
        owner = owner.model_copy(
            update={"name": vernacular_case((catalogue.display if catalogue else None) or owner.name)}
        )
        scientific_name = owner.scientific_name
    return GardenCaptureResponse(
        id=capture.id,
        camera=capture.camera,
        frigate_label=capture.label,
        observed_at=capture.observed_at + "Z",
        status=capture.status,
        reviewed_at=capture.reviewed_at + "Z" if capture.reviewed_at else None,
        snapshot_url=f"/api/garden/{capture.id}/snapshot" if capture.has_snapshot else None,
        crop_url=f"/api/garden/{capture.id}/crop" if capture.status == "confirmed" and capture.crop else None,
        crop=capture.crop,
        identification=identification,
        owner_identification=owner,
        scientific_name=scientific_name,
        source_kind="motion" if capture.motion_source else "frigate_event",
        motion_source=capture.motion_source,
        automatic_check=capture.automatic_check,
        automatic_check_overridden=capture.automation_overridden,
        review_token=capture.review_token,
        # The clip proxy's own identifier rule, so a capture never offers a clip it would refuse.
        clip_event=capture.frigate_event
        if settings.frigate.clips_enabled
        and not capture.motion_source
        and capture.frigate_event
        and validate_event_id(capture.frigate_event)
        else None,
    )


async def _page(items: list[GardenCapture], total: int, limit: int, offset: int, language: str) -> GardenCapturePage:
    names = await asyncio.to_thread(
        species_name_lookup.resolve,
        [
            value
            for item in items
            for value in (
                item.identification.species_id if item.identification else None,
                item.owner_identification.species_id if item.owner_identification else None,
            )
            if value
        ],
        language=language,
    )
    return GardenCapturePage(
        items=[await _response(item, language, names) for item in items], total=total, limit=limit, offset=offset
    )


@router.get("", response_model=GardenCapturePage)
async def list_captures(
    response: Response,
    language: str = Depends(get_user_language),
    status: GardenStatus = "pending",
    limit: int = Query(20, ge=1, le=128),
    offset: int = Query(0, ge=0),
) -> GardenCapturePage:
    response.headers["Cache-Control"] = "private, no-store"
    async with get_db() as db:
        repository = GardenRepository(db)
        items = await repository.list(status, limit, offset)
        total = await repository.count(status)
    return await _page(items, total, limit, offset, language)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


@router.get("/timeline", response_model=GardenCapturePage)
async def capture_timeline(
    language: str = Depends(get_user_language),
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
    return await _page(items, total, limit, offset, language)


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
    language: str = Depends(get_user_language),
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
        presented = await _page(records, len(records), limit, offset, language)
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
    language: str = Depends(get_user_language),
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
    return await _page(items, total, limit, offset, language)


@router.get("/notifications", response_model=GardenNotificationStatus)
async def garden_notification_status() -> GardenNotificationStatus:
    from app.services.garden_notification_transport import channel_configured

    return GardenNotificationStatus(
        enabled=garden_notification_service.enabled(),
        channels=settings.frigate.garden_notification_channels,
        configured={channel: channel_configured(channel) for channel in ["discord", "telegram", "pushover", "email"]},
        attempts=await garden_notification_service.status_counts(),
    )


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


@router.post("/dismiss-captures", response_model=GardenBatchReviewResponse)
async def dismiss_captures(request: GardenDismissRequest) -> GardenBatchReviewResponse:
    async with garden_motion_privacy.lock:
        garden_identification_service.invalidate_photo_checks()
        async with get_db() as db:
            updated = await GardenRepository(db).dismiss_captures(
                [(capture.id, capture.review_token) for capture in request.captures]
            )
    if updated:
        from app.services.broadcaster import broadcaster

        await broadcaster.broadcast({"type": "garden_history_changed"})
    return GardenBatchReviewResponse(updated_ids=updated, skipped_count=len(request.captures) - len(updated))


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
async def identify_capture(
    capture_id: str, request: GardenIdentifyRequest, language: str = Depends(get_user_language)
) -> GardenCaptureResponse:
    await garden_identification_service.identify(capture_id, request)
    return await _response(await garden_capture_service.get(capture_id), language)


@router.post("/{capture_id}/identification/{action}", response_model=GardenCaptureResponse)
async def review_identification(
    capture_id: str, action: Literal["accept", "dismiss"], language: str = Depends(get_user_language)
) -> GardenCaptureResponse:
    async with garden_motion_privacy.lock:
        garden_identification_service.invalidate_photo_checks()
        await garden_identification_service.review(capture_id, action)
    capture = await garden_capture_service.get(capture_id)
    if action == "accept":
        await garden_notification_service.schedule(capture_id)
    return await _response(capture, language)


async def _review(capture_id: str, status: GardenStatus, language: str) -> GardenCaptureResponse:
    async with garden_motion_privacy.lock:
        garden_identification_service.invalidate_photo_checks()
        async with get_db() as db:
            try:
                capture = await GardenRepository(db).review(capture_id, status)
            except GardenPhotoUnavailable as error:
                raise HTTPException(409, str(error)) from error
    if capture is None:
        raise HTTPException(404, "Garden capture not found")
    return await _response(capture, language)


@router.post("/{capture_id}/confirm", response_model=GardenCaptureResponse)
async def confirm_capture(
    capture_id: str, background_tasks: BackgroundTasks, language: str = Depends(get_user_language)
) -> GardenCaptureResponse:
    result = await _review(capture_id, "confirmed", language)
    background_tasks.add_task(garden_crop_service.collect, capture_id)
    return result


@router.post("/{capture_id}/dismiss", response_model=GardenCaptureResponse)
async def dismiss_capture(capture_id: str, language: str = Depends(get_user_language)) -> GardenCaptureResponse:
    return await _review(capture_id, "dismissed", language)


@router.post("/{capture_id}/restore", response_model=GardenCaptureResponse)
async def restore_capture(capture_id: str, language: str = Depends(get_user_language)) -> GardenCaptureResponse:
    return await _review(capture_id, "pending", language)


@router.get("/{capture_id}/snapshot", response_class=Response, response_model=None)
async def capture_snapshot(capture_id: str, _auth: AuthContext = Depends(require_owner)) -> Response:
    image = await garden_capture_service.snapshot(capture_id)
    return Response(
        image,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{capture_id}/crop", response_class=Response, response_model=None)
async def capture_crop(capture_id: str) -> Response:
    async with garden_motion_privacy.lock:
        async with get_db() as db:
            try:
                image = await GardenRepository(db).crop_photo(capture_id)
            except GardenPhotoUnavailable as error:
                raise HTTPException(409, str(error)) from error
    if image is None:
        raise HTTPException(404, "No saved animal crop is available")
    return Response(
        image,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/crops/storage", response_model=GardenCropStorage)
async def crop_storage() -> GardenCropStorage:
    async with get_db() as db:
        return GardenCropStorage(**await GardenRepository(db).crop_storage())


@router.get("/species", response_model=list[GardenSpecies])
async def garden_species(
    q: str = Query(min_length=1, max_length=120), language: str = Depends(get_user_language)
) -> list[GardenSpecies]:
    try:
        return await asyncio.to_thread(garden_identification_service.catalog.owner_species, query=q, language=language)
    except (OSError, ValueError, sqlite3.Error) as error:
        raise HTTPException(503, "Garden species data is unavailable. Check startup diagnostics.") from error


async def _rename(capture_id: str, token: str, species: GardenSpecies | None, language: str) -> GardenCaptureResponse:
    async with garden_motion_privacy.lock:
        garden_identification_service.invalidate_photo_checks()
        async with get_db() as db:
            try:
                capture = await GardenRepository(db).rename_species(capture_id, token, species)
            except ValueError as error:
                raise HTTPException(409, str(error)) from error
    if capture is None:
        raise HTTPException(404, "Garden capture not found")
    from app.services.broadcaster import broadcaster

    await broadcaster.broadcast({"type": "garden_history_changed"})
    return await _response(capture, language)


@router.put("/{capture_id}/species", response_model=GardenCaptureResponse)
async def rename_species(
    capture_id: str, request: GardenRenameRequest, language: str = Depends(get_user_language)
) -> GardenCaptureResponse:
    try:
        choices = await asyncio.to_thread(garden_identification_service.catalog.owner_species, request.species_id)
    except (OSError, ValueError, sqlite3.Error) as error:
        raise HTTPException(503, "Garden species data is unavailable. Check startup diagnostics.") from error
    if not choices:
        raise HTTPException(422, "Choose a complete animal species from the Garden catalogue.")
    return await _rename(capture_id, request.review_token, choices[0], language)


@router.delete("/{capture_id}/species", response_model=GardenCaptureResponse)
async def clear_owner_species(
    capture_id: str, review_token: str = Query(pattern=r"^[a-f0-9]{64}$"), language: str = Depends(get_user_language)
) -> GardenCaptureResponse:
    return await _rename(capture_id, review_token, None, language)
