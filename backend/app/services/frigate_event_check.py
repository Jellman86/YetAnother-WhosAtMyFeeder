"""What YA-WAMF learned when it asked Frigate about one event.

Only a not-found answer is evidence that Frigate no longer has an event. A
Frigate that is down, slow or erroring leaves the question unanswered, and the
record must not report that as an absence.
"""

from __future__ import annotations

from typing import TypedDict

from app.models import FrigateEventCheck
from app.services.frigate_readiness import FRIGATE_NOT_READY


class EventAvailability(TypedDict):
    """One event's media flags, with the Frigate answer they were read from."""

    has_frigate_event: bool
    frigate_event_check: FrigateEventCheck
    has_clip: bool
    has_snapshot: bool


_UNREACHABLE_ERRORS = frozenset({FRIGATE_NOT_READY, "event_request_error"})


def classify_event_check(event_data: dict | None, error: str | None) -> FrigateEventCheck:
    """Name the outcome of `FrigateClient.get_event_with_error` for the reader of a record."""
    if event_data:
        return "found"
    if error == "event_not_found":
        return "not_found"
    if error in _UNREACHABLE_ERRORS:
        return "unreachable"
    if error == "event_timeout":
        return "timed_out"
    return "failed"
