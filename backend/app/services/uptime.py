"""Turning heartbeat rows into an availability window.

The application records a heartbeat on a fixed interval. A stretch with no
heartbeats is a stretch where it was not running, which is the only honest
uptime signal available without an external monitor. Everything here is pure so
it can be tested without a database or a clock.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal, Sequence

#: How often the application records that it is alive.
HEARTBEAT_INTERVAL_MINUTES = 5

#: A bucket is only counted as down once more than this much time has no heartbeat,
#: so a single missed write during a slow moment is not reported as an outage.
MISSED_HEARTBEAT_TOLERANCE = 2

BucketState = Literal["up", "down", "unknown"]


@dataclass(frozen=True)
class UptimeBucket:
    start: datetime
    state: BucketState
    samples: int


@dataclass(frozen=True)
class UptimeWindow:
    window_start: datetime
    window_end: datetime
    bucket_minutes: int
    buckets: list[UptimeBucket]
    #: None when nothing is known about the window at all.
    uptime_ratio: float | None
    longest_gap_minutes: int
    longest_gap_start: datetime | None


def _as_utc(value: datetime) -> datetime:
    """Rows come back from SQLite without a timezone; they are always UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def build_uptime_window(
    samples: Iterable[datetime],
    *,
    now: datetime,
    hours: int = 24,
    bucket_minutes: int = 60,
    first_recorded_at: datetime | None = None,
) -> UptimeWindow:
    now = _as_utc(now)
    window_start = now - timedelta(hours=hours)
    first_known = _as_utc(first_recorded_at) if first_recorded_at is not None else None

    ordered: Sequence[datetime] = sorted(_as_utc(sample) for sample in samples)
    in_window = [sample for sample in ordered if window_start <= sample <= now]

    bucket_count = max((hours * 60) // bucket_minutes, 1)
    buckets: list[UptimeBucket] = []
    for index in range(bucket_count):
        bucket_start = window_start + timedelta(minutes=bucket_minutes * index)
        bucket_end = bucket_start + timedelta(minutes=bucket_minutes)
        seen = sum(1 for sample in in_window if bucket_start <= sample < bucket_end)

        if seen:
            state: BucketState = "up"
        elif first_known is None or bucket_end <= first_known:
            # Nothing was being recorded yet, which is not the same as being down.
            state = "unknown"
        else:
            state = "down"

        buckets.append(UptimeBucket(start=bucket_start, state=state, samples=seen))

    measured = [bucket for bucket in buckets if bucket.state != "unknown"]
    up = [bucket for bucket in measured if bucket.state == "up"]
    uptime_ratio = (len(up) / len(measured)) if measured else None

    longest_gap = timedelta(0)
    longest_gap_start: datetime | None = None
    tolerance = timedelta(minutes=HEARTBEAT_INTERVAL_MINUTES * MISSED_HEARTBEAT_TOLERANCE)
    for previous, following in zip(in_window, in_window[1:]):
        gap = following - previous
        if gap > tolerance and gap > longest_gap:
            longest_gap = gap
            longest_gap_start = previous

    return UptimeWindow(
        window_start=window_start,
        window_end=now,
        bucket_minutes=bucket_minutes,
        buckets=buckets,
        uptime_ratio=uptime_ratio,
        longest_gap_minutes=int(longest_gap.total_seconds() // 60),
        longest_gap_start=longest_gap_start,
    )
