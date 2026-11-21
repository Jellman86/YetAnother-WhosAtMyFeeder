"""Joining sealed daily totals to stored captures without counting anything twice (#949).

A sealed day is read only from its totals; every other day from its stored rows and the captures
Frigate lost. The boundary between them is an exact UTC range per sealed day, never an hour bucket,
so a zone half an hour off UTC splits a capture neither twice nor not at all.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo


@dataclass(frozen=True)
class DayCoverage:
    """``totals_through``: the last day counted from totals rather than stored captures.

    ``partial`` is true when some of those days began before tracking started, so cleanup may
    already have thinned them; ``complete_from`` is then the first day whose total is whole.
    """

    totals_through: date | None
    complete_from: date | None
    partial: bool


def local_midnight_utc(day: date, zone: tzinfo) -> datetime:
    """Naive-UTC start of one instance-local day."""
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)


def local_noon_utc(day: date, zone: tzinfo) -> datetime:
    """A day's total sits at its local noon, inside the day whatever the viewer's offset."""
    return datetime.combine(day, time(12), tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)


def first_whole_day(instant: datetime, zone: tzinfo) -> date:
    """The first local day that begins at or after a naive-UTC instant."""
    day = instant.replace(tzinfo=timezone.utc).astimezone(zone).date()
    return day if local_midnight_utc(day, zone) >= instant else day + timedelta(days=1)


def sealed_ranges(days: Collection[date], zone: tzinfo) -> list[tuple[datetime, datetime]]:
    """Naive-UTC ``[start, end)`` ranges covering the sealed days, touching days merged."""
    ranges: list[tuple[datetime, datetime]] = []
    for day in sorted(days):
        start, end = local_midnight_utc(day, zone), local_midnight_utc(day + timedelta(days=1), zone)
        if ranges and ranges[-1][1] == start:
            ranges[-1] = (ranges[-1][0], end)
        else:
            ranges.append((start, end))
    return ranges


def subtract_counts(counts: Mapping[str, int], sealed: Mapping[str, int]) -> dict[str, int]:
    """Bucketed counts with the captures inside sealed ranges taken out."""
    return {key: count - sealed.get(key, 0) for key, count in counts.items() if count - sealed.get(key, 0) > 0}


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
