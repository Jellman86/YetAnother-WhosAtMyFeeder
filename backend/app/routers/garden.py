"""Private, paginated animal reviews. Confirmation records presence, not species."""

import asyncio
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from typing import Annotated, Literal

from app.auth import AuthContext, get_auth_context_with_legacy, require_owner
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
from app.services.garden_notifications import (
    configured_channels,
    current_delivery_channels,
    garden_notification_service,
)
from app.services.garden_capture_service import garden_capture_service
from app.services.garden_domestic_birds import DOMESTIC_BIRDS, DomesticBirdKey
from app.services import garden_motion_privacy
from app.services import garden_public
from app.ratelimit import guest_rate_limit
from app.models.garden import (
    GardenDomesticRoute,
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
from app.utils.api_datetime import utc_naive_now
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
# Confirmed history and its photos, readable by public visitors under the bird detection rules.
public_router = APIRouter(
    prefix="/garden",
    tags=["garden"],
    dependencies=[Depends(require_garden_beta), Depends(private_response)],
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
    domestic_route: GardenDomesticRoute | None = Field(
        None, description="Set when this capture is a domestic bird the owner keeps, with the evidence that said so"
    )
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
    elif capture.domestic_route and capture.status == "confirmed":
        scientific_name = DOMESTIC_BIRDS[capture.domestic_route.domestic_bird].record_scientific_name
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
        domestic_route=capture.domestic_route,
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


def _guest_view(capture: GardenCaptureResponse) -> GardenCaptureResponse:
    """A visitor's copy: no review controls or check internals, and media only as the owner shares it."""
    photo = garden_public.guest_photo_visible(capture.observed_at)
    return capture.model_copy(
        update={
            "camera": garden_public.guest_camera(capture.camera),
            "review_token": None,
            "automatic_check": None,
            "automatic_check_overridden": False,
            "domestic_route": capture.domestic_route.model_copy(update={"detection_id": None, "source_model": None})
            if capture.domestic_route
            else None,
            "snapshot_url": capture.snapshot_url if photo else None,
            "crop_url": capture.crop_url if photo else None,
            "clip_event": capture.clip_event if garden_public.guest_clip_visible(capture.observed_at) else None,
        }
    )


async def _page(
    items: list[GardenCapture], total: int, limit: int, offset: int, language: str, *, guest: bool = False
) -> GardenCapturePage:
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
    presented = [await _response(item, language, names) for item in items]
    if guest:
        presented = [_guest_view(item) for item in presented]
    return GardenCapturePage(items=presented, total=total, limit=limit, offset=offset)


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


class _HistoryScope(BaseModel):
    start: datetime | None
    end: datetime | None
    camera: str | None
    status: GardenTimelineStatus
    guest: bool


def _require_public_access(auth: AuthContext) -> None:
    """A visitor's session reads nothing once the owner has switched public access off."""
    if not auth.is_owner and not settings.public_access.enabled:
        raise HTTPException(403, "Public access is switched off.")


def _history_scope(
    auth: AuthContext,
    start: datetime | None,
    end: datetime | None,
    camera: str | None,
    status: GardenTimelineStatus,
) -> _HistoryScope:
    """Validate the window, then hold a visitor to confirmed animals in the public history window."""
    start, end = _as_utc(start), _as_utc(end)
    if start is not None and end is not None and start > end:
        raise HTTPException(422, "The window starts after it ends.")
    if auth.is_owner:
        return _HistoryScope(start=start, end=end, camera=camera, status=status, guest=False)
    _require_public_access(auth)
    start, end = garden_public.guest_history_window(start, end)
    if not settings.public_access.show_camera_names:
        camera = None
    return _HistoryScope(start=start, end=end, camera=camera, status="confirmed", guest=True)


@public_router.get("/timeline", response_model=GardenCapturePage)
@guest_rate_limit()
async def capture_timeline(
    request: Request,
    auth: AuthContext = Depends(get_auth_context_with_legacy),
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
    scope = _history_scope(auth, start, end, camera, status)
    if scope.guest:
        limit = min(limit, 50)
    async with get_db() as db:
        repository = GardenRepository(db)
        items = await repository.timeline(
            start=scope.start,
            end=scope.end,
            camera=scope.camera,
            newest_first=order == "newest",
            limit=limit,
            offset=offset,
            status=scope.status,
        )
        total = await repository.timeline_count(
            start=scope.start, end=scope.end, camera=scope.camera, status=scope.status
        )
    return await _page(items, total, limit, offset, language, guest=scope.guest)


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


@public_router.get("/visits", response_model=GardenVisitPage)
@guest_rate_limit()
async def garden_visits(
    request: Request,
    auth: AuthContext = Depends(get_auth_context_with_legacy),
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
    scope = _history_scope(auth, start, end, camera, status)
    if scope.guest:
        limit = min(limit, 50)
    async with get_db() as db:
        repo = GardenVisitRepository(db)
        rows, total, captures = await repo.visits(
            start=scope.start,
            end=scope.end,
            camera=scope.camera,
            newest_first=order == "newest",
            status=scope.status,
            limit=limit,
            offset=offset,
            page_start=_as_utc(page_start),
            page_end=_as_utc(page_end),
        )
        records = await repo.get_many([row["representative"] for row in rows])
        presented = await _page(records, len(records), limit, offset, language, guest=scope.guest)
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


@public_router.get("/visits/{visit_id}/captures", response_model=GardenCapturePage)
@guest_rate_limit()
async def garden_visit_captures(
    request: Request,
    visit_id: str,
    auth: AuthContext = Depends(get_auth_context_with_legacy),
    language: str = Depends(get_user_language),
    start: datetime | None = None,
    end: datetime | None = None,
    camera: str | None = Query(None, max_length=128),
    status: GardenTimelineStatus = "reviewable",
    limit: int = Query(128, ge=1, le=128),
    offset: int = Query(0, ge=0),
) -> GardenCapturePage:
    scope = _history_scope(auth, start, end, camera, status)
    async with get_db() as db:
        items, total = await GardenVisitRepository(db).visit_captures(
            visit_id,
            start=scope.start,
            end=scope.end,
            camera=scope.camera,
            status=scope.status,
            limit=limit,
            offset=offset,
        )
    if not total:
        raise HTTPException(404, "Garden visit is no longer available. Refresh the history.")
    return await _page(items, total, limit, offset, language, guest=scope.guest)


@router.get("/notifications", response_model=GardenNotificationStatus)
async def garden_notification_status() -> GardenNotificationStatus:
    return GardenNotificationStatus(
        enabled=garden_notification_service.enabled(),
        use_bird_channels=settings.frigate.garden_notifications_use_bird_channels,
        channels=settings.frigate.garden_notification_channels,
        delivery_channels=current_delivery_channels(),
        include_photo=settings.frigate.garden_notifications_include_photo,
        configured=configured_channels(),
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


class GardenDomesticBirdOption(BaseModel):
    key: DomesticBirdKey
    declared: bool
    scientific_names: list[str] = Field(description="Every catalogue name that stands for this bird")
    species_ids: list[int] = Field(description="Those names resolved to catalogue identities")


@router.get("/domestic-birds", response_model=list[GardenDomesticBirdOption])
async def domestic_birds() -> list[GardenDomesticBirdOption]:
    """The domestic birds an owner can declare, so a bird record can be matched by exact identity."""
    from app.services.garden_domestic_service import species_ids_by_bird

    resolved = await asyncio.to_thread(species_ids_by_bird)
    declared = set(settings.frigate.garden_domestic_birds)
    return [
        GardenDomesticBirdOption(
            key=key,
            declared=key in declared,
            scientific_names=list(bird.scientific_names),
            species_ids=sorted(resolved.get(key, ())),
        )
        for key, bird in DOMESTIC_BIRDS.items()
    ]


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
    decided_at = utc_naive_now()
    capture = await garden_capture_service.get(capture_id)
    if action == "accept":
        await garden_notification_service.schedule(capture_id, accepted_at=decided_at)
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


async def _require_shared_photo(capture_id: str, auth: AuthContext) -> None:
    """A visitor's photo request succeeds only for a confirmed capture whose photo the owner shares."""
    if auth.is_owner:
        return
    _require_public_access(auth)
    async with get_db() as db:
        capture = await GardenRepository(db).get(capture_id)
    if (
        capture is None
        or capture.status != "confirmed"
        or not garden_public.guest_history_visible(capture.observed_at)
        or not garden_public.guest_photo_visible(capture.observed_at)
    ):
        raise HTTPException(404, "Garden photo not found")


@public_router.get("/captures/{capture_id}", response_model=GardenCaptureResponse)
@guest_rate_limit()
async def get_capture(
    request: Request,
    capture_id: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")],
    auth: AuthContext = Depends(get_auth_context_with_legacy),
    language: str = Depends(get_user_language),
) -> GardenCaptureResponse:
    """One capture's record, as a notification links to it; a visitor reads confirmed, shared ones only."""
    if not auth.is_owner:
        _require_public_access(auth)
    async with get_db() as db:
        capture = await GardenRepository(db).get(capture_id)
    if capture is None or (
        not auth.is_owner
        and (capture.status != "confirmed" or not garden_public.guest_history_visible(capture.observed_at))
    ):
        raise HTTPException(404, "Garden capture not found")
    presented = await _response(capture, language)
    return presented if auth.is_owner else _guest_view(presented)


@public_router.get("/{capture_id}/snapshot", response_class=Response, response_model=None)
@guest_rate_limit()
async def capture_snapshot(
    request: Request, capture_id: str, auth: AuthContext = Depends(get_auth_context_with_legacy)
) -> Response:
    await _require_shared_photo(capture_id, auth)
    image = await garden_capture_service.snapshot(capture_id)
    return Response(
        image,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@public_router.get("/{capture_id}/crop", response_class=Response, response_model=None)
@guest_rate_limit()
async def capture_crop(
    request: Request, capture_id: str, auth: AuthContext = Depends(get_auth_context_with_legacy)
) -> Response:
    await _require_shared_photo(capture_id, auth)
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
