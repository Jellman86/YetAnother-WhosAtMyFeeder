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
from app.services.daily_totals_lookup import is_unknown_label
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
    # Keys stored under a label the live count treats as Unknown bird, by the same rule.
    unknown_keys: set[str] = field(default_factory=set)

    def pop_unknown(self) -> list[SealedSpecies]:
        """Take the Unknown bird species out, for the one Unknown bird row."""
        return [self.by_key.pop(key) for key in sorted(self.unknown_keys) if key in self.by_key]


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
        # Totals exist only for sealed days, so a span's totals are exactly the days it took.
        for total in await repo.window_totals(spans) if taken else []:
            species = entry(
                total.species_key, total.display_name, total.scientific_name, total.common_name, total.taxa_id
            )
            for index in range(len(windows)):
                species.captures[index] += total.captures[index]
                species.visits[index] += total.visits[index]
            if any(is_unknown_label(label) for label in total.labels):
                found.unknown_keys.add(total.species_key)

    for index, window in enumerate(windows):
        for lost in await repo.lost_captures(window.start, window.end):
            entry(lost.species_key, lost.display_name, lost.scientific_name, None, None).captures[index] += 1
            if is_unknown_label(lost.display_name):
                found.unknown_keys.add(lost.species_key)
    return found


def _bird_identity(taxa_id: int | None, name: str | None) -> tuple[int | None, str]:
    return taxa_id, str(name or "").strip().lower()


def with_sealed_species(stats: list[dict], sealed: dict[str, SealedSpecies]) -> list[dict]:
    """Add each species' sealed and lost captures to the all-time species list, by canonical key.

    A sealed day keeps the key its rows had when it was sealed. When the catalogue backfill later
    gives the stored rows a ``species_id``, the keys differ but the bird does not, so a sealed key
    with no stored row joins the stored row for the same taxon or name, as ``_fold_same_bird``
    matches the Leaderboard's rows (#359). Stored rows are not folded into one another here: each
    keeps the key its rolling figures are looked up by. A species whose every capture was cleaned
    up keeps a row with its count and no capture times.
    """
    by_key = {row["unified_key"]: row for row in stats}
    by_taxa: dict[int, dict] = {}
    by_name: dict[str, dict] = {}

    def index(row: dict) -> None:
        taxa_id, name = _bird_identity(row.get("taxa_id"), row.get("species"))
        if taxa_id is not None:
            by_taxa.setdefault(taxa_id, row)
        if name:
            by_name.setdefault(name, row)

    for row in stats:
        index(row)
    for key, species in sealed.items():
        taxa_id, name = _bird_identity(species.taxa_id, species.species)
        row = by_key.get(key) or (by_taxa.get(taxa_id) if taxa_id is not None else None) or by_name.get(name)
        if row is not None:
            row["count"] += species.captures[0]
            for field, value in (
                ("scientific_name", species.scientific_name),
                ("common_name", species.common_name),
                ("taxa_id", species.taxa_id),
            ):
                if row.get(field) is None and value is not None:
                    row[field] = value
            continue
        row = {
            "species": species.species,
            "count": species.captures[0],
            "scientific_name": species.scientific_name,
            "common_name": species.common_name,
            "taxa_id": species.taxa_id,
            "unified_key": key,
            "first_seen": None,
            "last_seen": None,
            "species_id": int(key.removeprefix("species:")) if key.startswith("species:") else None,
            "manual_common_name": None,
        }
        by_key[key] = row
        index(row)
    merged = [row for row in by_key.values() if row["count"] > 0]
    merged.sort(key=lambda row: row["count"], reverse=True)
    return merged
