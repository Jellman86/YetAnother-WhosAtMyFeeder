"""Feeder refills: when the owner, or an automation acting for them, filled a feeder (#946).

A refill explains a jump in visits that weather and time of day do not, so it is kept beside the
detection history and never changes it. Every request is untrusted: the time, camera, note and
automation event id are checked here before anything is stored.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal

from app.models.feeder_refill import NewRefill, RefillSource, StoredRefill
from app.utils.api_datetime import utc_naive_datetime

if TYPE_CHECKING:
    from app.repositories.feeder_refill_repository import FeederRefillRepository

RefillOutcome = Literal["recorded", "same_event", "within_cooldown"]
RefusalCode = Literal["future_time", "unknown_camera", "note_too_long", "invalid_source_event_id"]

# One trip to the feeder can be recorded twice: a double tap, or a door sensor that opens and
# closes. Refills of one camera this close together are one refill.
REFILL_COOLDOWN = timedelta(minutes=15)
NOTE_MAX_LENGTH = 280
SOURCE_EVENT_ID_MAX_LENGTH = 128

_REFUSALS: dict[RefusalCode, str] = {
    "future_time": "A refill cannot be recorded in the future. Check the time and its time zone.",
    "unknown_camera": "That camera is not one YA-WAMF watches. Choose a configured camera or leave the camera empty.",
    "note_too_long": f"A refill note can be at most {NOTE_MAX_LENGTH} characters.",
    "invalid_source_event_id": (
        f"An automation event id must be 1 to {SOURCE_EVENT_ID_MAX_LENGTH} printable characters with no line breaks."
    ),
}


class RefillRefused(ValueError):
    """A refill request that cannot be stored, with a plain-language reason."""

    def __init__(self, code: RefusalCode) -> None:
        super().__init__(_REFUSALS[code])
        self.code: RefusalCode = code


@dataclass(frozen=True)
class RefillRequest:
    source: RefillSource
    refilled_at: datetime | None = None
    camera_name: str | None = None
    note: str | None = None
    source_event_id: str | None = None


@dataclass(frozen=True)
class RefillDecision:
    """What happened to a refill request, and the refill stored for it or the stored one it repeats."""

    outcome: RefillOutcome
    refill: StoredRefill | None = None


def _plain_note(note: str | None) -> str | None:
    if note is None:
        return None
    if len(note) > NOTE_MAX_LENGTH:
        raise RefillRefused("note_too_long")
    # Line breaks, tabs and other control characters become spaces, so a note is one line of text.
    spaced = "".join(" " if unicodedata.category(character)[0] == "C" else character for character in note)
    return " ".join(spaced.split()) or None


def _source_event_id(value: str | None) -> str | None:
    if value is None:
        return None
    # Refused rather than tidied, so two different automation events never become one id.
    if not value or len(value) > SOURCE_EVENT_ID_MAX_LENGTH or not value.isprintable() or value != value.strip():
        raise RefillRefused("invalid_source_event_id")
    return value


def _camera(value: str | None, configured_cameras: Iterable[str]) -> str | None:
    if value is None or not value.strip():
        return None
    name = value.strip()
    if name not in set(configured_cameras):
        raise RefillRefused("unknown_camera")
    return name


def prepare_refill(request: RefillRequest, *, now: datetime, configured_cameras: Iterable[str]) -> NewRefill:
    """Check a refill request against the clock and the configured cameras, or refuse it."""
    current = utc_naive_datetime(now)
    at = current.replace(microsecond=0) if request.refilled_at is None else utc_naive_datetime(request.refilled_at)
    if at > current:
        raise RefillRefused("future_time")
    return NewRefill(
        refilled_at=at,
        camera_name=_camera(request.camera_name, configured_cameras),
        source=request.source,
        note=_plain_note(request.note),
        source_event_id=_source_event_id(request.source_event_id),
    )


def decide_refill(
    refill: NewRefill, *, same_event: StoredRefill | None, nearby: Sequence[StoredRefill]
) -> RefillDecision:
    """Whether a checked refill is new, a repeat of one automation event, or the same trip to the feeder."""
    if same_event is not None:
        return RefillDecision("same_event", same_event)
    candidates = [
        stored
        for stored in nearby
        if stored.camera_name == refill.camera_name and abs(stored.refilled_at - refill.refilled_at) <= REFILL_COOLDOWN
    ]
    if not candidates:
        return RefillDecision("recorded")
    nearest = min(candidates, key=lambda stored: (abs(stored.refilled_at - refill.refilled_at), stored.id))
    return RefillDecision("within_cooldown", nearest)


async def record_refill(
    repository: FeederRefillRepository, request: RefillRequest, *, now: datetime, configured_cameras: Iterable[str]
) -> RefillDecision:
    """Store a refill unless it repeats one already stored; return what happened and the refill."""
    refill = prepare_refill(request, now=now, configured_cameras=configured_cameras)
    # Checking and storing share one write transaction, so two requests for one trip cannot both
    # find the cooldown window empty and both be stored.
    async with repository.write_transaction():
        event_id = refill.source_event_id
        same_event = await repository.by_source_event_id(event_id) if event_id is not None else None
        nearby = []
        if same_event is None:
            # A valid instant near either end of the calendar can have a cooldown extending beyond it.
            start = max(refill.refilled_at, datetime.min + REFILL_COOLDOWN) - REFILL_COOLDOWN
            end = min(refill.refilled_at, datetime.max - REFILL_COOLDOWN) + REFILL_COOLDOWN
            nearby = await repository.near(refill.camera_name, start, end)
        decision = decide_refill(refill, same_event=same_event, nearby=nearby)
        if decision.refill is None:
            return RefillDecision("recorded", await repository.insert(refill))
        if decision.outcome == "within_cooldown" and event_id is not None:
            await repository.remember_source_event(event_id, decision.refill.id)
        return decision
