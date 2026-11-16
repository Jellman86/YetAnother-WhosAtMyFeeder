"""What YA-WAMF learned when it asked Frigate about one event.

Only a not-found answer is evidence that Frigate no longer has an event. A
Frigate that is down, slow or erroring leaves the question unanswered, and the
record must not report that as an absence.
"""

from __future__ import annotations

from typing import TypedDict

from app.models import FrigateEventCheck
from app.services.frigate_readiness import (
    FRIGATE_NOT_READY,
    NOT_READY_CONNECTION,
    NOT_READY_SERVER_ERROR,
    NOT_READY_TIMEOUT,
)


class EventAvailability(TypedDict):
    """One event's media flags, with the Frigate answer they were read from."""

    has_frigate_event: bool
    frigate_event_check: FrigateEventCheck
    has_clip: bool
    has_snapshot: bool


_NOT_READY_CHECK: dict[str, FrigateEventCheck] = {
    NOT_READY_TIMEOUT: "timed_out",
    NOT_READY_SERVER_ERROR: "failed",
    NOT_READY_CONNECTION: "unreachable",
}
_UNAUTHORIZED_ERRORS = frozenset({"event_http_401", "event_http_403"})


def classify_event_check(
    event_data: dict | None, error: str | None, not_ready_cause: str | None = None
) -> FrigateEventCheck:
    """Name the outcome of `FrigateClient.get_event_with_error` for the reader of a record.

    `frigate_not_ready` only says the read was put off or folded into a wider outage, so
    `not_ready_cause` (the readiness gate's record of what failed) decides which outage it
    was. Without one, nothing is known about the event and no cause is invented.
    """
    if event_data:
        return "found"
    if error == "event_not_found":
        return "not_found"
    if error == FRIGATE_NOT_READY:
        return _NOT_READY_CHECK.get(not_ready_cause or "", "not_checked")
    if error == "event_request_error":
        return "unreachable"
    if error == "event_timeout":
        return "timed_out"
    if error in _UNAUTHORIZED_ERRORS:
        return "unauthorized"
    return "failed"
