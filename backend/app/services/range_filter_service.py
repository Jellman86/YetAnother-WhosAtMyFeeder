"""Keep the regional species list current and answer range questions without I/O (#696).

The list is fetched in the background, never on the detection path: a refresh
runs at most weekly while the filter is on, or when the owner asks. Detection
admission only reads the list already in memory, so a slow or failing eBird
costs nothing but the filter, which then filters nothing.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import aiosqlite
import httpx
import pycountry
import structlog

from app.config import settings
from app.database import get_db
from app.repositories.range_filter_repository import (
    RangeDecisionRecord,
    RangeFilterRepository,
    StoredRangeList,
    StoredTaxon,
)
from app.services.ebird_service import EbirdResponseTooLarge, EbirdService, ebird_service
from app.services.model_taxon_map import scientific_name_from_label
from app.services.range_filter import (
    MAX_LIST_AGE,
    REFRESH_INTERVAL,
    FilterState,
    RangeCandidate,
    LocationPrecision,
    RangeList,
    RegionLevel,
    choose_regions,
    county_list_too_short,
    filter_state,
    location_key,
    location_precision,
    refresh_due,
    species_verdict,
    validate_range_list,
)
from app.services.species_catalog_resolver import SpeciesCatalogResolver, species_catalog_resolver
from app.utils.api_datetime import serialize_api_datetime, utc_naive_datetime, utc_naive_now
from app.utils.classifier_labels import normalize_classifier_label
from app.utils.public_access import approximate_coordinate
from app.utils.tasks import create_background_task

log = structlog.get_logger()

SOURCE = "ebird"
#: BirdNET-Go evidence from the last year counts as presence; older calls say less about today.
HEARD_WINDOW = timedelta(days=365)
#: Decisions are kept long enough to find a vagrant from last season, then pruned.
DECISION_RETENTION = timedelta(days=365)
LOOP_INTERVAL_SECONDS = 3600
DECISION_WINDOW_DAYS = 30
PREVIEW_WINDOW_DAYS = 90
PREVIEW_SEEN_LIMIT = 20
PREVIEW_EXAMPLE_LIMIT = 12
REFRESH_TIMEOUT_SECONDS = 120.0
_REGION_LEVELS: dict[str, RegionLevel] = {"county": "county", "state": "state", "country": "country"}
_BINOMIAL = re.compile(r"^[A-Z][a-z]+ [a-z][a-z-]+( [a-z][a-z-]+)?$")


class RangeRefreshError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LocationFacts:
    precision: LocationPrecision
    key: str
    latitude: float | None
    longitude: float | None
    country_code: str | None


def country_code(value: str | None) -> str | None:
    """The ISO alpha-2 code eBird uses for a configured country name or code."""
    name = " ".join((value or "").split())
    name = {"uk": "GB", "great britain": "GB"}.get(name.casefold(), name)
    if not name:
        return None
    try:
        return str(pycountry.countries.lookup(name).alpha_2)
    except LookupError:
        return None


def configured_location() -> LocationFacts:
    latitude = settings.location.latitude
    longitude = settings.location.longitude
    code = country_code(settings.location.country)
    precision = location_precision(latitude, longitude, code)
    return LocationFacts(
        precision=precision,
        # The region level is part of the key: asking for a county list after a state list
        # must fetch a new list, exactly as moving the feeder does.
        key=f"{location_key(precision, latitude, longitude, code)}|{settings.classification.range_filter_region_level}",
        latitude=latitude,
        longitude=longitude,
        country_code=code,
    )


def species_code_index(taxonomy: list[dict[str, Any]]) -> tuple[dict[str, StoredTaxon], dict[str, str]]:
    """eBird's species, keyed by code, and how each subspecies group or form reports as a species.

    A region list contains subspecies groups ("Yellow-rumped Warbler (Myrtle)") as
    well as species. Each reports as its species, either through eBird's own
    `reportAs` or, failing that, through the binomial at the front of its
    trinomial, which is the same identity written more specifically.
    """
    species: dict[str, StoredTaxon] = {}
    species_by_name: dict[str, str] = {}
    for item in taxonomy:
        if not isinstance(item, dict) or item.get("category") != "species":
            continue
        code = str(item.get("speciesCode") or "").strip()
        scientific = str(item.get("sciName") or "").strip()
        if not code or not scientific:
            continue
        common = str(item.get("comName") or "").strip() or None
        species[code] = StoredTaxon(code, scientific[:200], common[:200] if common else None, False)
        species_by_name[scientific.casefold()] = code

    reports_as: dict[str, str] = {}
    for item in taxonomy:
        if not isinstance(item, dict) or item.get("category") not in {"issf", "form", "intergrade", "domestic"}:
            continue
        code = str(item.get("speciesCode") or "").strip()
        parent = str(item.get("reportAs") or "").strip()
        if not parent:
            words = str(item.get("sciName") or "").split()
            parent = species_by_name.get(" ".join(words[:2]).casefold(), "") if len(words) >= 2 else ""
        if code and parent in species:
            reports_as[code] = parent
    return species, reports_as


def regional_species_codes(codes: list[str], species: dict[str, StoredTaxon], reports_as: dict[str, str]) -> set[str]:
    """The species-level codes in a region list; "duck sp." and hybrids name no species and are dropped."""
    found: set[str] = set()
    for code in codes:
        if code in species:
            found.add(code)
        elif code in reports_as:
            found.add(reports_as[code])
    return found


def build_range_list(
    stored: StoredRangeList,
    taxa: list[StoredTaxon],
    resolve: Callable[[str], Optional[int]],
) -> RangeList:
    in_range: set[int] = set()
    known: set[int] = set()
    names: dict[int, tuple[str, str | None]] = {}
    for taxon in taxa:
        species_id = resolve(taxon.scientific_name)
        if species_id is None:
            continue
        known.add(species_id)
        names.setdefault(species_id, (taxon.scientific_name, taxon.common_name))
        if taxon.in_region:
            in_range.add(species_id)
    level = _REGION_LEVELS.get(stored.region_level, "country")
    return RangeList(
        source=stored.source,
        region_code=stored.region_code,
        region_codes=stored.region_codes,
        region_name=stored.region_name,
        region_level=level,
        location_key=stored.location_key,
        fetched_at=stored.fetched_at,
        region_species_total=stored.region_species_total,
        in_range=frozenset(in_range),
        known=frozenset(known),
        names=names,
        note=stored.note,
    )


def _resolver_lookup(resolver: SpeciesCatalogResolver) -> Callable[[str], Optional[int]]:
    def resolve(name: str) -> Optional[int]:
        species_id, _reason = resolver.resolve_scientific_name(name)
        return species_id

    return resolve


def _failure_code(error: BaseException) -> str:
    if isinstance(error, RangeRefreshError):
        return error.code
    if isinstance(error, httpx.HTTPStatusError):
        return "ebird_key_rejected" if error.response.status_code in {401, 403} else "ebird_error"
    if isinstance(error, (httpx.TimeoutException, httpx.TransportError, asyncio.TimeoutError)):
        return "ebird_unreachable"
    if isinstance(error, EbirdResponseTooLarge):
        return "response_too_large"
    if isinstance(error, ValueError):
        return "invalid_response"
    return "refresh_failed"


class RangeFilterService:
    def __init__(
        self,
        *,
        ebird: EbirdService | None = None,
        resolver: SpeciesCatalogResolver | None = None,
        clock: Callable[[], datetime] = utc_naive_now,
    ) -> None:
        self._ebird = ebird or ebird_service
        self._resolver = resolver or species_catalog_resolver
        self._clock = clock
        self._list: RangeList | None = None
        self._heard: frozenset[int] = frozenset()
        self._merged: RangeList | None = None
        self._last_error: str | None = None
        self._last_attempt_at: datetime | None = None
        self._last_failure_at: datetime | None = None
        self._last_attempt_key: str | None = None
        self._refresh_task: asyncio.Task[None] | None = None
        self._loop_task: asyncio.Task[None] | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = create_background_task(self._run(), name="range_filter_loop")

    async def stop(self) -> None:
        for task in (self._loop_task, self._refresh_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        self._loop_task = None
        self._refresh_task = None

    async def _run(self) -> None:
        await self.load()
        while True:
            try:
                await self.reload_heard()
                if settings.classification.range_filter_enabled and self._refresh_due():
                    await self.refresh()
                async with get_db() as db:
                    await RangeFilterRepository(db).prune_decisions(self._clock() - DECISION_RETENTION)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # noqa: BLE001 - the loop must outlive one bad pass
                log.warning("Range filter maintenance pass failed", error=type(error).__name__)
            await asyncio.sleep(LOOP_INTERVAL_SECONDS)

    async def load(self) -> None:
        """Read the stored list into memory; a list that fails validation is kept out."""
        async with get_db() as db:
            loaded = await RangeFilterRepository(db).load_list(SOURCE)
        if loaded is None:
            self._set_list(None)
            return
        stored, taxa = loaded
        range_list = await asyncio.to_thread(build_range_list, stored, taxa, _resolver_lookup(self._resolver))
        self._set_list(range_list)

    async def reload_heard(self) -> None:
        async with get_db() as db:
            rows = await RangeFilterRepository(db).heard_species(self._clock() - HEARD_WINDOW)

        def resolve() -> frozenset[int]:
            lookup = _resolver_lookup(self._resolver)
            heard: set[int] = set()
            for species_id, scientific_name in rows:
                resolved = species_id if species_id is not None else lookup(scientific_name or "")
                if resolved is not None:
                    heard.add(resolved)
            return frozenset(heard)

        self._heard = await asyncio.to_thread(resolve)
        self._merged = None

    def _set_list(self, range_list: RangeList | None) -> None:
        self._list = range_list
        self._merged = None

    # ── Refresh ──────────────────────────────────────────────────────────

    def _refresh_due(self) -> bool:
        return refresh_due(
            self._list,
            now=self._clock(),
            current_location_key=configured_location().key,
            last_failure_at=self._last_failure_at,
        )

    @property
    def refreshing(self) -> bool:
        return self._refresh_task is not None and not self._refresh_task.done()

    def request_refresh(self) -> bool:
        """Start a background refresh unless one is running; returns whether one is now running."""
        if not self.refreshing:
            self._refresh_task = create_background_task(self.refresh(), name="range_filter_refresh")
        return True

    async def settings_changed(self) -> None:
        """Fetch a list for the new place or level in the background once the filter is on."""
        if configured_location().key != self._last_attempt_key:
            # A failure for the old place or level says nothing about the new one.
            self._last_failure_at = None
            self._last_error = None
        if settings.classification.range_filter_enabled and self._refresh_due():
            self.request_refresh()

    async def refresh(self) -> None:
        location = configured_location()
        if location.precision == "none" or not self._ebird.is_configured():
            return
        self._last_attempt_at = self._clock()
        self._last_attempt_key = location.key
        try:
            range_list, stored, taxa = await asyncio.wait_for(self._fetch(location), timeout=REFRESH_TIMEOUT_SECONDS)
            async with get_db() as db:
                await RangeFilterRepository(db).replace_list(stored, taxa)
            self._set_list(range_list)
            self._last_error = None
            self._last_failure_at = None
            log.info(
                "Range list refreshed",
                source=SOURCE,
                region=range_list.region_code,
                level=range_list.region_level,
                species=range_list.mapped_species,
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - every failure leaves the filter open, never closed
            self._last_error = _failure_code(error)
            self._last_failure_at = self._clock()
            log.warning("Range list refresh failed; filtering stays open", reason=self._last_error)

    async def _fetch(self, location: LocationFacts) -> tuple[RangeList, StoredRangeList, list[StoredTaxon]]:
        hotspots = []
        if location.latitude is not None and location.longitude is not None and location.precision != "none":
            query_lat = approximate_coordinate(location.latitude)
            query_lng = approximate_coordinate(location.longitude)
            hotspots = await self._ebird.get_nearby_hotspot_regions(
                query_lat=float(query_lat if query_lat is not None else location.latitude),
                query_lng=float(query_lng if query_lng is not None else location.longitude),
                feeder_lat=location.latitude,
                feeder_lng=location.longitude,
            )
        preferred: RegionLevel = settings.classification.range_filter_region_level
        choice = choose_regions(
            preferred_level=preferred,
            precision=location.precision,
            hotspots=hotspots,
            country_code=location.country_code,
        )
        if choice is None:
            raise RangeRefreshError("region_not_found")

        taxonomy = await self._ebird.get_taxonomy("en")
        if not taxonomy:
            raise RangeRefreshError("taxonomy_unavailable")
        species, reports_as = species_code_index(taxonomy)
        if not species:
            raise RangeRefreshError("taxonomy_unavailable")

        level, codes = choice
        note: str | None = None
        regional = await self._regional_codes(codes, species, reports_as)
        if level == "county" and county_list_too_short(len(regional)):
            state_code = hotspots[0].state if hotspots else None
            if state_code:
                level, codes, note = "state", (state_code,), "county_list_too_short"
                regional = await self._regional_codes(codes, species, reports_as)
        region_name = await self._ebird.get_region_name(codes[0])

        stored = StoredRangeList(
            source=SOURCE,
            region_code=codes[0],
            region_codes=tuple(codes),
            region_name=region_name,
            region_level=level,
            location_key=location.key,
            fetched_at=self._clock(),
            region_species_total=len(regional),
            note=note,
        )
        taxa = [replace(taxon, in_region=code in regional) for code, taxon in species.items()]
        range_list = await asyncio.to_thread(build_range_list, stored, taxa, _resolver_lookup(self._resolver))
        problem = validate_range_list(range_list, now=self._clock())
        if problem:
            raise RangeRefreshError(f"list_{problem}")
        return range_list, stored, taxa

    async def _regional_codes(
        self, codes: tuple[str, ...], species: dict[str, StoredTaxon], reports_as: dict[str, str]
    ) -> set[str]:
        regional: set[str] = set()
        for code in codes:
            regional |= regional_species_codes(await self._ebird.get_region_species_codes(code), species, reports_as)
        return regional

    # ── Detection-path reads (no I/O) ────────────────────────────────────

    def state(self) -> FilterState:
        location = configured_location()
        return filter_state(
            enabled=bool(settings.classification.range_filter_enabled),
            precision=location.precision,
            ebird_configured=self._ebird.is_configured(),
            range_list=self._list,
            current_location_key=location.key,
            now=self._clock(),
            last_error=self._last_error,
        )

    def _with_heard(self) -> RangeList | None:
        if self._list is None:
            return None
        if self._merged is None:
            self._merged = replace(self._list, heard=self._heard)
        return self._merged

    def active_list(self) -> RangeList | None:
        """The list admission may filter with right now, or None when the filter must stay open."""
        if not settings.classification.range_filter_enabled:
            return None
        return self._with_heard() if self.state().filtering else None

    def species_id_for(self, candidate: dict[str, Any]) -> int | None:
        """Exact catalogue identity for a classifier output, or None when it cannot be named exactly.

        The model output mapping comes first. A label that is itself a scientific
        name resolves through the catalogue's accepted names; a common name never
        does, because near-miss names are how a filter would reject the wrong bird.
        """
        label = normalize_classifier_label(candidate.get("label"))
        index = candidate.get("index")
        if isinstance(index, int) and index >= 0:
            species_id = self._resolver.cached_output_species_id(candidate.get("model_sha256"), index, label)
            if species_id is not None:
                return species_id
        scientific = scientific_name_from_label(label) or (label if _BINOMIAL.fullmatch(label) else None)
        return self._resolver.cached_species_id_for_name(scientific)

    def candidate(self, classification: dict[str, Any], *, admissible: bool) -> RangeCandidate:
        try:
            score = float(classification.get("score") or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        return RangeCandidate(
            label=normalize_classifier_label(classification.get("label")),
            score=score,
            species_id=self.species_id_for(classification),
            admissible=admissible,
        )

    def verdict_for(self, classification: dict[str, Any]) -> str:
        active = self.active_list()
        if active is None:
            return "unknown"
        return species_verdict(active, self.species_id_for(classification))

    # ── Decisions ────────────────────────────────────────────────────────

    async def record_decision(
        self,
        *,
        frigate_event: str,
        outcome: str,
        original_label: str,
        original_score: float,
        original_species_id: int | None,
        chosen_label: str | None,
        chosen_score: float | None,
        region_code: str,
        camera: str | None,
        detected_at: datetime | None,
        db: aiosqlite.Connection | None = None,
    ) -> None:
        """Remember a fallback or a skip; a failure here never affects the detection itself.

        A caller already holding a connection passes it, so recording never waits on
        a second one from the pool.
        """
        if outcome not in {"fallback", "skipped"}:
            return
        record = RangeDecisionRecord(
            frigate_event=frigate_event,
            outcome=outcome,
            camera=camera,
            detected_at=utc_naive_datetime(detected_at) if detected_at else None,
            decided_at=self._clock(),
            original_label=original_label[:200],
            original_score=float(original_score),
            original_species_id=original_species_id,
            chosen_label=chosen_label[:200] if chosen_label else None,
            chosen_score=chosen_score,
            region_code=region_code[:16],
            source=SOURCE,
        )
        try:
            if db is not None:
                await RangeFilterRepository(db).record_decision(record)
            else:
                async with get_db() as own:
                    await RangeFilterRepository(own).record_decision(record)
        except Exception as error:  # noqa: BLE001 - evidence is best-effort, the decision already stands
            log.warning("Could not record range filter decision", event_id=frigate_event, error=type(error).__name__)

    # ── Owner-facing summaries ───────────────────────────────────────────

    @property
    def current_list(self) -> RangeList | None:
        return self._with_heard()

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def _previewable_list(self) -> RangeList | None:
        """The list as the owner should see it: valid and for this place, fresh or not."""
        range_list = self._with_heard()
        if range_list is None or validate_range_list(range_list, now=self._clock()) is not None:
            return None
        if range_list.location_key != configured_location().key:
            return None
        return range_list

    async def model_coverage(self) -> dict[str, int] | None:
        """How the active model's birds fall against the list: out of range, and never filterable."""
        range_list = self._previewable_list()
        if range_list is None:
            return None
        coverage = await asyncio.to_thread(self._active_model_coverage)
        if coverage is None:
            return None
        named = coverage.birds | coverage.ungrouped
        return {
            "bird_species": len(coverage.birds),
            "out_of_range": sum(1 for species_id in named if species_verdict(range_list, species_id) == "out_of_range"),
            "unmatched": len(coverage.birds - range_list.known) + coverage.unresolved_outputs,
        }

    def _active_model_coverage(self) -> Any:
        from app.services.classifier_service import get_classifier
        from app.services.model_eval_service import active_catalogue_model_sha256

        return self._resolver.model_species_coverage(active_catalogue_model_sha256(get_classifier()))

    async def status(self) -> dict[str, Any]:
        location = configured_location()
        current = self.state()
        range_list = self._with_heard()
        since = self._clock() - timedelta(days=DECISION_WINDOW_DAYS)
        async with get_db() as db:
            counts = await RangeFilterRepository(db).count_decisions_since(since)
        return {
            "enabled": bool(settings.classification.range_filter_enabled),
            "filtering": current.filtering,
            "reason": current.reason,
            "problem": current.problem,
            "source": SOURCE,
            "location_precision": location.precision,
            "region_level_setting": settings.classification.range_filter_region_level,
            "ebird_configured": self._ebird.is_configured(),
            "birdnet_enabled": bool(settings.frigate.birdnet_enabled),
            "region": (
                {
                    "code": range_list.region_code,
                    "codes": list(range_list.region_codes),
                    "name": range_list.region_name,
                    "level": range_list.region_level,
                    "note": range_list.note,
                }
                if range_list
                else None
            ),
            "species_in_range": range_list.mapped_species if range_list else None,
            "region_species_total": range_list.region_species_total if range_list else None,
            "heard_species": len(self._heard),
            "heard_only_species": len(range_list.heard - range_list.in_range) if range_list else 0,
            "refreshed_at": serialize_api_datetime(range_list.fetched_at) if range_list else None,
            "next_refresh_at": serialize_api_datetime(range_list.fetched_at + REFRESH_INTERVAL) if range_list else None,
            "stale_after": serialize_api_datetime(range_list.fetched_at + MAX_LIST_AGE) if range_list else None,
            "refreshing": self.refreshing,
            "last_error": self._last_error,
            "last_attempt_at": serialize_api_datetime(self._last_attempt_at),
            "model": await self.model_coverage(),
            "recent": {"window_days": DECISION_WINDOW_DAYS, **counts},
        }

    async def preview(self, *, window_days: int = PREVIEW_WINDOW_DAYS) -> dict[str, Any]:
        """Which species the filter would set aside: those seen here lately first, then the model's others."""
        range_list = self._previewable_list()
        if range_list is None:
            return {
                "available": False,
                "window_days": window_days,
                "recently_seen": [],
                "model_out_of_range_total": None,
                "examples": [],
            }
        async with get_db() as db:
            sightings = await RangeFilterRepository(db).recent_species_sightings(
                self._clock() - timedelta(days=window_days)
            )

        def entry(species_id: int, **extra: Any) -> dict[str, Any]:
            scientific, common = range_list.names.get(species_id, ("", None))
            return {"species_id": species_id, "scientific_name": scientific, "common_name": common, **extra}

        recently_seen = [
            entry(
                sighting.species_id,
                detections=sighting.detections,
                last_seen=serialize_api_datetime(sighting.last_seen),
            )
            for sighting in sightings
            if species_verdict(range_list, sighting.species_id) == "out_of_range"
        ][:PREVIEW_SEEN_LIMIT]

        coverage = await asyncio.to_thread(self._active_model_coverage)
        model_total: int | None = None
        examples: list[dict[str, Any]] = []
        if coverage is not None:
            seen_ids = {item["species_id"] for item in recently_seen}
            out_of_range = [
                species_id
                for species_id in coverage.birds | coverage.ungrouped
                if species_verdict(range_list, species_id) == "out_of_range"
            ]
            model_total = len(out_of_range)
            ordered = sorted(
                (species_id for species_id in out_of_range if species_id not in seen_ids),
                key=lambda species_id: (range_list.names.get(species_id, ("", None))[1] or "").casefold(),
            )
            examples = [entry(species_id) for species_id in ordered[:PREVIEW_EXAMPLE_LIMIT]]
        return {
            "available": True,
            "window_days": window_days,
            "recently_seen": recently_seen,
            "model_out_of_range_total": model_total,
            "examples": examples,
        }

    async def recent_skips(self, *, limit: int) -> list[dict[str, Any]]:
        async with get_db() as db:
            records = await RangeFilterRepository(db).recent_skips(limit=limit)
        return [
            {
                "frigate_event": record.frigate_event,
                "camera": record.camera,
                "detected_at": serialize_api_datetime(record.detected_at),
                "decided_at": serialize_api_datetime(record.decided_at),
                "label": record.original_label,
                "score": record.original_score,
                "region_code": record.region_code,
            }
            for record in records
        ]

    async def decision_for(self, frigate_event: str) -> dict[str, Any] | None:
        async with get_db() as db:
            record = await RangeFilterRepository(db).get_decision(frigate_event)
        if record is None:
            return None
        return {
            "outcome": record.outcome,
            "original_label": record.original_label,
            "original_score": record.original_score,
            "chosen_label": record.chosen_label,
            "chosen_score": record.chosen_score,
            "region_code": record.region_code,
            "decided_at": serialize_api_datetime(record.decided_at),
        }


range_filter_service = RangeFilterService()
