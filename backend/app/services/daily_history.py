"""Joining sealed daily totals to stored captures without counting anything twice (#949).

A sealed day is read only from its totals; every other day only from its stored rows. These
helpers decide which side of that line a stored hour falls on and what a response should say
about how far back its counts come from totals.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timezone, tzinfo


@dataclass(frozen=True)
class DayCoverage:
    """``totals_through``: the last day counted from totals rather than stored captures.

    ``partial`` is true when some of those days were sealed after older captures were already
    gone; ``complete_from`` is then the first day from which the totals are whole, if there is one.
    """

    totals_through: date | None
    complete_from: date | None
    partial: bool


def _local_day(instant: datetime, zone: tzinfo) -> date:
    return instant.replace(tzinfo=timezone.utc).astimezone(zone).date()


def split_by_seal(
    hourly_counts: list[tuple[datetime, int]], sealed: Collection[date], *, zone: tzinfo
) -> tuple[list[tuple[datetime, int]], int]:
    """Stored UTC-hour counts on live days, and how many stored captures fell on sealed days."""
    if not sealed:
        return hourly_counts, 0
    live = [(hour, count) for hour, count in hourly_counts if _local_day(hour, zone) not in sealed]
    return live, sum(count for hour, count in hourly_counts if _local_day(hour, zone) in sealed)


def coverage(sealed: Mapping[date, bool]) -> DayCoverage:
    """What a response reports about the sealed days it used, keyed day -> complete."""
    if not sealed:
        return DayCoverage(totals_through=None, complete_from=None, partial=False)
    incomplete = [day for day, complete in sealed.items() if not complete]
    if not incomplete:
        return DayCoverage(totals_through=max(sealed), complete_from=None, partial=False)
    later_complete = sorted(day for day, complete in sealed.items() if complete and day > max(incomplete))
    return DayCoverage(
        totals_through=max(sealed), complete_from=later_complete[0] if later_complete else None, partial=True
    )


def local_noon_utc(day: date, zone: tzinfo) -> datetime:
    """A day's total sits at its local noon, inside the day whatever the viewer's offset."""
    return datetime.combine(day, time(12), tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)


def local_midnight_utc(day: date, zone: tzinfo) -> datetime:
    """Naive-UTC start of one instance-local day."""
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
