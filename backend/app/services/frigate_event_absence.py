"""How often to mention that Frigate no longer has an event.

Frigate's retention is shorter than the detection history we keep, so an older
detection's upstream event is gone for good. The events list checks media
availability for every row it renders, which meant reporting that same expected,
permanent and unactionable condition once per row per page load: 958 log lines
in 22 hours from 29 events on the reference deployment, drowning the warnings
that do need a person.

This remembers that an absence has been reported recently, so it is stated once
per window instead of once per render. It deliberately does **not** decide
whether the event exists. Frigate is still asked every time, so a restored event
or a transient 404 during a Frigate restart is never answered from stale memory.
Whether a detection's media is really gone is settled by the maintenance
reconcile, which is the only place allowed to act on it.
"""

from __future__ import annotations

from typing import Callable, Optional

DEFAULT_TTL_SECONDS = 300.0
DEFAULT_MAX_ENTRIES = 2048


class FrigateEventAbsence:
    """Throttles repeat reports of an event Frigate has retired.

    Not thread-safe by design: it is only touched from the event loop, and a
    lost update costs one duplicate log line, never a wrong answer, because
    nothing reads this to decide whether the event exists.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._ttl = max(0.0, float(ttl_seconds))
        self._max_entries = max(1, int(max_entries))
        self._clock = clock or _monotonic
        self._absent_since: dict[str, float] = {}

    @property
    def tracked_count(self) -> int:
        return len(self._absent_since)

    def record_absent(self, event_id: str) -> bool:
        """Note a 404. Returns True when this absence is worth reporting.

        True on the first sighting and again once the window has passed, so an
        operator still sees the condition periodically without it repeating on
        every render.
        """
        if self._ttl <= 0.0:
            return True
        now = self._clock()
        recorded = self._absent_since.get(event_id)
        first_sighting = recorded is None or (now - recorded) >= self._ttl
        if first_sighting:
            self._reclaim(now)
        self._absent_since[event_id] = now
        return first_sighting

    def record_present(self, event_id: str) -> None:
        """Frigate answered, so a later absence is news again and is reported."""
        self._absent_since.pop(event_id, None)

    def _reclaim(self, now: float) -> None:
        """Drop expired entries, then oldest-first if still over the cap."""
        expired = [key for key, seen in self._absent_since.items() if now - seen >= self._ttl]
        for key in expired:
            self._absent_since.pop(key, None)
        overflow = len(self._absent_since) + 1 - self._max_entries
        if overflow > 0:
            oldest = sorted(self._absent_since.items(), key=lambda item: item[1])[:overflow]
            for key, _ in oldest:
                self._absent_since.pop(key, None)


def _monotonic() -> float:
    import time

    return time.monotonic()


frigate_event_absence = FrigateEventAbsence()
