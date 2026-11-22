"""Per-species counts from sealed daily totals and lost captures, for windows of history (#949).

The Leaderboard and the species list count stored captures. After an age cleanup a sealed day keeps
only its favourites and the newest few of each species, so those counts would fall. This gathers
what the stored rows no longer hold, the way the species stats and the timeline already do:

- a window takes a sealed day's total only when the whole day lies inside it, so a rolling window
  that opens part way through a sealed day keeps that day's stored captures instead of its total;
- ``ranges`` names the sealed days a window took, and the caller leaves stored captures inside them
  out of its own counts, because the totals already include them;
- a capture Frigate lost still counts on its live day.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, tzinfo

import aiosqlite

from app.repositories.daily_totals_repository import DailyTotalsRepository
from app.services.daily_history import first_whole_day, sealed_ranges
from app.utils.calendar_day import local_date


@dataclass(frozen=True)
class CountWindow:
    """A naive-UTC ``[start, end)``; a ``start`` of None reaches back to the first sealed day."""

    start: datetime | None
    end: datetime


@dataclass
class SealedSpecies:
    """One canonical species' captures and visits per window, in the order the windows were given."""

    species: str
    scientific_name: str | None
    common_name: str | None
    taxa_id: int | None
    captures: list[int]
    visits: list[int]


@dataclass
class SealedSpeciesCounts:
    ranges: list[tuple[datetime, datetime]] = field(default_factory=list)
    by_key: dict[str, SealedSpecies] = field(default_factory=dict)


def whole_days(window: CountWindow, zone: tzinfo, floor: date | None) -> tuple[date | None, date] | None:
    """The first and last local days wholly inside ``window`` and not before ``floor``, or None."""
    last = local_date(window.end, zone=zone)
    if last is None:
        return None
    # The day holding ``end`` runs past it, so the last whole day is the one before.
    last -= timedelta(days=1)
    first = first_whole_day(window.start, zone) if window.start is not None else None
    if floor is not None:
        first = floor if first is None else max(first, floor)
    if first is not None and first > last:
        return None
    return first, last


async def sealed_species_counts(
    db: aiosqlite.Connection, windows: Sequence[CountWindow], *, zone: tzinfo, floor: date | None
) -> SealedSpeciesCounts:
    """Sealed totals and lost captures per species for each window; ``floor`` keeps a guest's window."""
    repo = DailyTotalsRepository(db)
    spans = [whole_days(window, zone, floor) for window in windows]
    found = SealedSpeciesCounts()

    def entry(key: str, species: str, scientific: str | None, common: str | None, taxa: int | None) -> SealedSpecies:
        current = found.by_key.get(key)
        if current is None:
            current = SealedSpecies(species, scientific, common, taxa, [0] * len(windows), [0] * len(windows))
            found.by_key[key] = current
        else:
            current.scientific_name = current.scientific_name or scientific
            current.common_name = current.common_name or common
            current.taxa_id = current.taxa_id if current.taxa_id is not None else taxa
        return current

    present = [span for span in spans if span is not None]
    if present:
        first = None if any(span[0] is None for span in present) else min(span[0] for span in present)
        sealed = await repo.sealed_days(first, max(span[1] for span in present))
        taken = {
            day
            for day in sealed
            if any(span is not None and (span[0] is None or span[0] <= day) and day <= span[1] for span in spans)
        }
        found.ranges = sealed_ranges(taken, zone)
        for total in await repo.totals(min(taken), max(taken)) if taken else []:
            if total.day not in taken:
                continue
            species = entry(
                total.species_key, total.display_name, total.scientific_name, total.common_name, total.taxa_id
            )
            for index, span in enumerate(spans):
                if span is not None and (span[0] is None or span[0] <= total.day) and total.day <= span[1]:
                    species.captures[index] += total.capture_count
                    species.visits[index] += total.visit_count

    for index, window in enumerate(windows):
        for lost in await repo.lost_captures(window.start, window.end):
            entry(lost.species_key, lost.display_name, lost.scientific_name, None, None).captures[index] += 1
    return found
