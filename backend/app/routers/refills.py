"""Feeder refills: record one, list a window of them, delete one (#946). Owner only.

Refill times show when someone was in the garden, so guests never read them.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.auth import AuthContext, require_owner
from app.config import settings
from app.database import get_db
from app.models.feeder_refill import RefillSource, StoredRefill
from app.repositories.feeder_refill_repository import FeederRefillRepository
from app.services.feeder_refills import (
    NOTE_MAX_LENGTH,
    SOURCE_EVENT_ID_MAX_LENGTH,
    RefillOutcome,
    RefillRefused,
    RefillRequest,
    record_refill,
)
from app.utils.api_datetime import ExactInstant, serialize_api_datetime, utc_naive_datetime, utc_naive_now

router = APIRouter(prefix="/refills", tags=["refills"])

DEFAULT_WINDOW = timedelta(days=30)
MAX_WINDOW = timedelta(days=400)
MAX_LIMIT = 500
MAX_OFFSET = 100_000


class FeederRefill(BaseModel):
    id: int
    refilled_at: str = Field(description="When the feeder was filled, in UTC")
    camera_name: str | None = Field(description="The camera watching that feeder; null when none was given")
    source: RefillSource = Field(description="manual: recorded in YA-WAMF; api: sent by an automation; mqtt: by MQTT")
    note: str | None = Field(description="Plain text, one line; show it as text, never as markup")
    source_event_id: str | None = Field(description="The automation's own id for the event, when it sent one")
    created_at: str = Field(description="When YA-WAMF stored the refill, in UTC")


class FeederRefillCreate(BaseModel):
    refilled_at: ExactInstant | None = Field(
        default=None,
        description="When the feeder was filled, with its offset. Null records it now. A time in the future is refused.",
    )
    camera_name: str | None = Field(
        default=None, max_length=100, description="A configured camera, or null when the refill is for no one camera"
    )
    source: Literal["manual", "api"] = Field(
        default="api", description="manual when the owner recorded it in YA-WAMF; api for an automation"
    )
    note: str | None = Field(default=None, max_length=NOTE_MAX_LENGTH * 4)
    source_event_id: str | None = Field(
        default=None,
        max_length=SOURCE_EVENT_ID_MAX_LENGTH,
        description="An automation's id for this event; sending the same id again records nothing new",
    )


class FeederRefillRecorded(BaseModel):
    outcome: RefillOutcome = Field(
        description=(
            "recorded: stored as a new refill; same_event: this automation event id was already stored; "
            "within_cooldown: a refill of the same camera was already stored within 15 minutes"
        )
    )
    refill: FeederRefill = Field(description="The refill stored now, or the one already stored that this repeats")


class FeederRefillPage(BaseModel):
    items: list[FeederRefill]
    total: int = Field(description="Refills in the window")
    limit: int
    offset: int
    start: str
    end: str


class FeederRefillDeleted(BaseModel):
    id: int
    deleted: bool = Field(description="Always true; the refill is gone and cannot be restored")


def _refill(stored: StoredRefill) -> FeederRefill:
    return FeederRefill(
        id=stored.id,
        refilled_at=serialize_api_datetime(stored.refilled_at) or "",
        camera_name=stored.camera_name,
        source=stored.source,
        note=stored.note,
        source_event_id=stored.source_event_id,
        created_at=serialize_api_datetime(stored.created_at) or "",
    )


@router.get("", response_model=FeederRefillPage)
async def list_refills(
    start: ExactInstant | None = Query(None, description="Earliest refill time, with its offset; 30 days before end"),
    end: ExactInstant | None = Query(None, description="Latest refill time, with its offset; now when left out"),
    limit: int = Query(100, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    auth: AuthContext = Depends(require_owner),
) -> FeederRefillPage:
    """Refills in a window of at most 400 days, newest first."""
    window_end = utc_naive_datetime(end) if end is not None else utc_naive_now()
    window_start = utc_naive_datetime(start) if start is not None else window_end - DEFAULT_WINDOW
    if window_start > window_end:
        raise HTTPException(status_code=422, detail="The window's start must not be after its end.")
    if window_end - window_start > MAX_WINDOW:
        raise HTTPException(status_code=422, detail="Ask for at most 400 days of refills at a time.")
    async with get_db() as db:
        items, total = await FeederRefillRepository(db).in_window(window_start, window_end, limit=limit, offset=offset)
    return FeederRefillPage(
        items=[_refill(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        start=serialize_api_datetime(window_start) or "",
        end=serialize_api_datetime(window_end) or "",
    )


@router.post(
    "",
    response_model=FeederRefillRecorded,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": FeederRefillRecorded, "description": "Already stored; nothing new was recorded"}},
)
async def create_refill(
    body: FeederRefillCreate, response: Response, auth: AuthContext = Depends(require_owner)
) -> FeederRefillRecorded:
    """Record a refill. A repeat of one already stored records nothing new and returns that one with 200."""
    request = RefillRequest(
        source=body.source,
        refilled_at=body.refilled_at,
        camera_name=body.camera_name,
        note=body.note,
        source_event_id=body.source_event_id,
    )
    try:
        async with get_db() as db:
            decision = await record_refill(
                FeederRefillRepository(db), request, now=utc_naive_now(), configured_cameras=settings.frigate.camera
            )
    except RefillRefused as refused:
        raise HTTPException(status_code=422, detail=str(refused)) from refused
    if decision.refill is None:
        raise HTTPException(status_code=500, detail="The refill could not be stored. Try again.")
    if decision.outcome != "recorded":
        response.status_code = status.HTTP_200_OK
    return FeederRefillRecorded(outcome=decision.outcome, refill=_refill(decision.refill))


@router.delete("/{refill_id}", response_model=FeederRefillDeleted)
async def delete_refill(refill_id: int, auth: AuthContext = Depends(require_owner)) -> FeederRefillDeleted:
    """Delete a refill permanently. It cannot be restored; record it again if it was deleted by mistake."""
    async with get_db() as db:
        deleted = await FeederRefillRepository(db).delete(refill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="No refill has that id. It may already have been deleted.")
    return FeederRefillDeleted(id=refill_id, deleted=True)
