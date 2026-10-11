"""Private, paginated animal reviews. Confirmation records presence, not species."""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from app.auth import AuthContext, require_owner
from app.database import get_db
from app.repositories.garden_repository import GardenCapture, GardenRepository, GardenStatus
from app.services.garden_capture_service import garden_capture_service


router = APIRouter(prefix="/garden", tags=["garden"], dependencies=[Depends(require_owner)])


class GardenCaptureResponse(BaseModel):
    id: str
    camera: str
    frigate_label: str
    observed_at: str
    status: GardenStatus
    reviewed_at: str | None
    snapshot_url: str | None


class GardenCapturePage(BaseModel):
    items: list[GardenCaptureResponse]
    total: int
    limit: int
    offset: int


def _response(capture: GardenCapture) -> GardenCaptureResponse:
    return GardenCaptureResponse(
        id=capture.id,
        camera=capture.camera,
        frigate_label=capture.label,
        observed_at=capture.observed_at + "Z",
        status=capture.status,
        reviewed_at=capture.reviewed_at + "Z" if capture.reviewed_at else None,
        snapshot_url=f"/api/garden/{capture.id}/snapshot" if capture.has_snapshot else None,
    )


@router.get("", response_model=GardenCapturePage)
async def list_captures(
    status: GardenStatus = "pending",
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> GardenCapturePage:
    async with get_db() as db:
        repository = GardenRepository(db)
        items = await repository.list(status, limit, offset)
        total = await repository.count(status)
    return GardenCapturePage(items=[_response(item) for item in items], total=total, limit=limit, offset=offset)


async def _review(capture_id: str, status: GardenStatus) -> GardenCaptureResponse:
    async with get_db() as db:
        capture = await GardenRepository(db).review(capture_id, status)
    if capture is None:
        raise HTTPException(404, "Garden capture not found")
    return _response(capture)


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
