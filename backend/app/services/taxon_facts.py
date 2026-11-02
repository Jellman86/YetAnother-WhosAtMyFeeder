"""What the family tree says about each taxon at this install: visits, calls and its own photograph.

Per-species spans come from the detection history (the shared visit rule), confirmed Garden
visits and BirdNET-Go detections. They fold up the classification, so a group states the
species seen beneath it, their visits and the most recent one, and is illustrated by its
most-seen member. The catalogue and the history are separate databases that meet only through
the opaque ``species_id``.

A visitor reads the shared window only, a call count only while audio is shared, and a
photograph only where the route that serves it would let them load it.
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal, Mapping, Optional
from urllib.parse import quote

from app.config import settings
from app.database import get_db
from app.repositories.audio_history_repository import AudioHistoryRepository
from app.repositories.detection_repository import DetectionRepository
from app.repositories.garden_repository import GardenRepository
from app.repositories.garden_visit_repository import GardenVisitRepository
from app.repositories.visit_repository import VisitRepository
from app.services import garden_public
from app.services.classification_input_provenance import cached_snapshot_input_provenance
from app.services.media_cache import media_cache
from app.services.taxonomy_tree import taxonomy_tree
from app.utils.api_datetime import utc_naive_datetime
from app.utils.public_access import effective_public_events_days, public_events_window, public_media_window

Source = Literal["camera", "garden"]
SOURCES: tuple[Source, ...] = ("camera", "garden")

#: The newest captures of a species looked at for a stored crop, as the leaderboard's portraits do.
PHOTO_CANDIDATES_PER_SPECIES = 8
#: A group tries its most-seen members in turn for a photograph, this many at most.
PHOTO_MEMBERS_TRIED = 3
#: Metadata files one request may read, so a level full of whole scenes cannot become a cache scan.
PHOTO_METADATA_READS = 60
#: How long a reader's history aggregate and a species' photograph are reused.
SNAPSHOT_SECONDS = 60
PHOTO_SECONDS = 120
PHOTO_CACHE_ENTRIES = 4096


@dataclass(frozen=True)
class VisitSpan:
    visits: int
    first_seen: datetime
    last_seen: datetime


@dataclass(frozen=True)
class HeardSpan:
    count: int
    last_heard: datetime


@dataclass(frozen=True)
class SpeciesRecord:
    visits: int
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    heard: int
    last_heard: Optional[datetime]
    sources: tuple[Source, ...]


@dataclass(frozen=True)
class TaxonRecord:
    visits: int
    species_seen: int
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    heard: int
    last_heard: Optional[datetime]
    sources: tuple[Source, ...]
    #: The species seen beneath the taxon (or the species itself), most-seen first.
    members: tuple[int, ...]


@dataclass(frozen=True)
class TaxonPhoto:
    url: str
    kind: Source
    species_id: int
    taken_at: datetime


@dataclass(frozen=True)
class TaxonFacts:
    taxon_id: int
    rank: str
    visits: int
    species_seen: int
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    #: None when audio is not shared with this reader: unknown, not zero.
    heard: Optional[int]
    last_heard: Optional[datetime]
    sources: tuple[Source, ...]
    photo: Optional[TaxonPhoto]


def _earliest(*values: Optional[datetime]) -> Optional[datetime]:
    present = [value for value in values if value is not None]
    return min(present) if present else None


def _latest(*values: Optional[datetime]) -> Optional[datetime]:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def combine_species(
    *, camera: Mapping[int, VisitSpan], garden: Mapping[int, VisitSpan], heard: Mapping[int, HeardSpan]
) -> dict[int, SpeciesRecord]:
    """One record per species: camera and Garden visits added, the widest span, and its calls."""
    records: dict[int, SpeciesRecord] = {}
    for species_id in sorted({*camera, *garden, *heard}):
        spans = {"camera": camera.get(species_id), "garden": garden.get(species_id)}
        seen = [span for span in spans.values() if span]
        calls = heard.get(species_id)
        records[species_id] = SpeciesRecord(
            visits=sum(span.visits for span in seen),
            first_seen=_earliest(*(span.first_seen for span in seen)),
            last_seen=_latest(*(span.last_seen for span in seen)),
            heard=calls.count if calls else 0,
            last_heard=calls.last_heard if calls else None,
            sources=tuple(source for source in SOURCES if (span := spans[source]) and span.visits > 0),
        )
    return records


def ordered_members(records: Mapping[int, SpeciesRecord], species_ids: Iterable[int]) -> tuple[int, ...]:
    """The species seen here among those given, most visits first, then the most recently seen."""
    seen = [species_id for species_id in set(species_ids) if species_id in records and records[species_id].visits > 0]
    seen.sort(
        key=lambda species_id: (-records[species_id].visits, -_ordinal(records[species_id].last_seen), species_id)
    )
    return tuple(seen)


def _ordinal(value: Optional[datetime]) -> float:
    return value.timestamp() if value else 0.0


def roll_up(
    records: Mapping[int, SpeciesRecord], members_by_taxon: Mapping[int, Iterable[int]]
) -> dict[int, TaxonRecord]:
    """Each taxon's facts over the species beneath it. A taxon with nothing recorded beneath it is left out."""
    rolled: dict[int, TaxonRecord] = {}
    for taxon_id, members in members_by_taxon.items():
        beneath = [records[species_id] for species_id in set(members) if species_id in records]
        if not beneath:
            continue
        rolled[taxon_id] = TaxonRecord(
            visits=sum(record.visits for record in beneath),
            species_seen=sum(1 for record in beneath if record.visits > 0),
            first_seen=_earliest(*(record.first_seen for record in beneath)),
            last_seen=_latest(*(record.last_seen for record in beneath)),
            heard=sum(record.heard for record in beneath),
            last_heard=_latest(*(record.last_heard for record in beneath)),
            sources=tuple(source for source in SOURCES if any(source in record.sources for record in beneath)),
            members=ordered_members(records, members),
        )
    return rolled


def _stamp(value: str) -> datetime:
    """A stored time as naive UTC: detection rows and Garden captures both store UTC."""
    return utc_naive_datetime(datetime.fromisoformat(value.strip().removesuffix("Z")))


Window = tuple[Optional[datetime], Optional[datetime]]


@dataclass(frozen=True)
class ReaderScope:
    """What one reader may see. Hashable and built from the sharing settings, so it keys the caches."""

    guest: bool
    #: Naive UTC; the end is exclusive.
    history: Window
    #: Where this reader may load photographs; None when none are shared.
    media: Optional[Window]
    audio: bool
    garden: bool
    shared_days: Optional[int]


def reader_scope(*, is_owner: bool, now: Optional[datetime] = None) -> ReaderScope:
    garden = garden_public.garden_visible(is_owner=is_owner)
    if is_owner:
        return ReaderScope(False, (None, None), (None, None), True, garden, None)
    start, end = public_events_window(now)
    history = (utc_naive_datetime(start), utc_naive_datetime(end) if end else None)
    media: Optional[Window] = None
    if settings.public_access.show_snapshots:
        media_start, media_end = public_media_window(now)
        media = (utc_naive_datetime(media_start), utc_naive_datetime(media_end) if media_end else None)
    return ReaderScope(
        True, history, media, bool(settings.public_access.show_audio), garden, effective_public_events_days()
    )


def _intersect(a: Window, b: Window) -> Window:
    return _latest(a[0], b[0]), _earliest(a[1], b[1])


def _inclusive_end(end: Optional[datetime]) -> Optional[datetime]:
    """Visit grouping and Garden scopes take an inclusive end; the reader windows' ends are exclusive."""
    return end - timedelta(microseconds=1) if end is not None else None


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    return value.replace(tzinfo=timezone.utc) if value is not None else None


@dataclass(frozen=True)
class _Snapshot:
    records: dict[int, SpeciesRecord]
    rolled: dict[int, TaxonRecord]


class TaxonFactsService:
    def __init__(self) -> None:
        self._snapshots: dict[ReaderScope, tuple[float, _Snapshot]] = {}
        self._photos: OrderedDict[tuple[ReaderScope, int], tuple[float, Optional[TaxonPhoto]]] = OrderedDict()
        self._lock = asyncio.Lock()

    def clear(self) -> None:
        self._snapshots.clear()
        self._photos.clear()

    async def _snapshot(self, scope: ReaderScope) -> _Snapshot:
        cached = self._snapshots.get(scope)
        if cached and time.monotonic() - cached[0] < SNAPSHOT_SECONDS:
            return cached[1]
        async with self._lock:
            cached = self._snapshots.get(scope)
            if cached and time.monotonic() - cached[0] < SNAPSHOT_SECONDS:
                return cached[1]
            snapshot = await self._build(scope)
            # Windows move at midnight and settings change: drop the readers nobody is any longer.
            self._snapshots = {key: value for key, value in self._snapshots.items() if key == scope}
            self._snapshots[scope] = (time.monotonic(), snapshot)
            return snapshot

    async def _build(self, scope: ReaderScope) -> _Snapshot:
        start, end = scope.history
        async with get_db() as db:
            camera = await VisitRepository(db).species_visit_spans(start=start, end=_inclusive_end(end))
            garden = (
                await GardenVisitRepository(db).species_visit_spans(
                    start=_aware(start), end=_aware(_inclusive_end(end))
                )
                if scope.garden
                else {}
            )
            heard = await AudioHistoryRepository(db).heard_by_species(start=start, end=end) if scope.audio else {}
        records = combine_species(
            camera={
                key: VisitSpan(visits, _stamp(first), _stamp(last)) for key, (visits, first, last) in camera.items()
            },
            garden={
                key: VisitSpan(visits, _stamp(first), _stamp(last)) for key, (visits, first, last) in garden.items()
            },
            heard={key: HeardSpan(count, _stamp(last)) for key, (count, last) in heard.items()},
        )
        members = await asyncio.to_thread(taxonomy_tree.members_by_taxon, list(records))
        return _Snapshot(records=records, rolled=roll_up(records, members))

    async def _photographs(self, scope: ReaderScope, species_ids: list[int]) -> dict[int, Optional[TaxonPhoto]]:
        """Each species' newest stored crop this reader may load: a camera crop or a Garden crop, whichever is newer."""
        if scope.media is None:
            return {species_id: None for species_id in species_ids}
        now = time.monotonic()
        found: dict[int, Optional[TaxonPhoto]] = {}
        wanted: list[int] = []
        for species_id in dict.fromkeys(species_ids):
            cached = self._photos.get((scope, species_id))
            if cached and now - cached[0] < PHOTO_SECONDS:
                found[species_id] = cached[1]
            else:
                wanted.append(species_id)
        if not wanted:
            return found
        start, end = _intersect(scope.history, scope.media)
        async with get_db() as db:
            events = await DetectionRepository(db).newest_events_by_species(
                wanted, per_species=PHOTO_CANDIDATES_PER_SPECIES, start_date=start, end_date=end
            )
            crops = (
                await GardenRepository(db).newest_crops(wanted, start=_aware(start), end=_aware(_inclusive_end(end)))
                if scope.garden
                else {}
            )
        reads = 0
        for species_id in wanted:
            camera: Optional[TaxonPhoto] = None
            complete = True
            for event, detected_at in events.get(species_id, []):
                if reads >= PHOTO_METADATA_READS:
                    complete = False
                    break
                reads += 1
                metadata = await media_cache.get_snapshot_metadata(event)
                if cached_snapshot_input_provenance({"source": (metadata or {}).get("source")}).is_cropped:
                    camera = TaxonPhoto(
                        f"/api/about/showcase/{quote(event, safe='')}.jpg", "camera", species_id, _stamp(detected_at)
                    )
                    break
            garden: Optional[TaxonPhoto] = None
            if species_id in crops:
                capture_id, observed_at = crops[species_id]
                garden = TaxonPhoto(f"/api/garden/{capture_id}/crop", "garden", species_id, _stamp(observed_at))
            photo = max((p for p in (camera, garden) if p), key=lambda p: p.taken_at, default=None)
            found[species_id] = photo
            # A walk cut short by the read budget is not an answer; the next request finishes it.
            if complete or photo is not None:
                self._photos[(scope, species_id)] = (now, photo)
        while len(self._photos) > PHOTO_CACHE_ENTRIES:
            self._photos.popitem(last=False)
        return found

    async def facts(self, taxon_ids: Iterable[int], scope: ReaderScope) -> list[TaxonFacts]:
        """Facts for each taxon the catalogue holds, in the order asked, each taxon once."""
        ids = list(dict.fromkeys(int(taxon_id) for taxon_id in taxon_ids))
        ranks = await asyncio.to_thread(taxonomy_tree.ranks, ids)
        snapshot = await self._snapshot(scope)
        known = [taxon_id for taxon_id in ids if taxon_id in ranks]
        candidates = {
            taxon_id: snapshot.rolled[taxon_id].members[:PHOTO_MEMBERS_TRIED]
            for taxon_id in known
            if taxon_id in snapshot.rolled
        }
        photos = await self._photographs(scope, [member for members in candidates.values() for member in members])
        results: list[TaxonFacts] = []
        for taxon_id in known:
            record = snapshot.rolled.get(taxon_id)
            photo = next((photos[m] for m in candidates.get(taxon_id, ()) if photos.get(m)), None)
            results.append(
                TaxonFacts(
                    taxon_id=taxon_id,
                    rank=ranks[taxon_id],
                    visits=record.visits if record else 0,
                    species_seen=record.species_seen if record else 0,
                    first_seen=record.first_seen if record else None,
                    last_seen=record.last_seen if record else None,
                    heard=(record.heard if record else 0) if scope.audio else None,
                    last_heard=record.last_heard if record and scope.audio else None,
                    sources=record.sources if record else (),
                    photo=photo,
                )
            )
        return results


taxon_facts_service = TaxonFactsService()
