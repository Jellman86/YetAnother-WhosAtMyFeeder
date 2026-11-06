"""Decide whether a classification names a bird that lives where the feeder is (#696).

A wildlife-wide classifier knows birds from every continent, so a feeder on the
US west coast is occasionally told it saw a European species. eBird publishes
the species ever recorded in each region; this module holds the rules that turn
that list into an admission decision. Everything here is pure: the caller
passes in the list, the candidates and the time, so each rule is testable on
its own.

The rules, in the order they protect the owner:

- **Fail open.** No list, a stale list, a list for a different place, or an
  invalid list filters nothing. Rejecting real birds because a range service
  is down would be worse than the problem being solved.
- **Positive evidence only.** A species is out of range only when eBird's own
  taxonomy names it and the regional list does not. A label the catalogue
  cannot identify, or a species eBird does not use, is never filtered.
- **Presence evidence only adds.** A species BirdNET-Go has heard here is in
  range whatever the list says; on its own that evidence can never reject.
- **Fall back before skipping.** When the top prediction is out of range, the
  highest-scoring in-range alternative that still clears the threshold is kept
  instead, the way BirdNET restricts its own label set by location.
- **Owners are never second-guessed.** A species an owner chose is not filtered.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

RegionLevel = Literal["county", "state", "country"]
LocationPrecision = Literal["exact", "approximate", "country_only", "none"]
SpeciesVerdict = Literal["in_range", "out_of_range", "unknown"]
DecisionOutcome = Literal["not_filtered", "in_range", "fallback", "skipped"]
FilterReason = Literal[
    "active",
    "ready",
    "needs_location",
    "needs_ebird_key",
    "waiting_for_list",
    "lookup_failed",
    "location_changed",
    "list_stale",
    "list_unusable",
]

#: eBird's regional lists change slowly; a weekly refresh keeps new county records.
REFRESH_INTERVAL = timedelta(days=7)
#: After a failed refresh, try again this soon rather than waiting a week.
RETRY_INTERVAL = timedelta(hours=6)
#: Beyond this age a list is no longer trusted to reject anything.
MAX_LIST_AGE = timedelta(days=30)
#: A county with fewer recorded species than this is under-birded, not species-poor:
#: its list would reject common birds nobody has bothered to report there.
MIN_COUNTY_SPECIES = 100
#: The richest country lists (Colombia, Peru) hold under 2,000 species. A list far
#: larger than any real region is a malformed response, not a range.
MAX_REGION_SPECIES = 4000
#: When fewer than half of a regional list's species resolve to catalogue identities,
#: the mismatch is in the naming, not the birds, and the list cannot be trusted to reject.
MIN_MAPPED_FRACTION = 0.5
#: At most this many neighbouring counties are combined around a feeder near a border.
MAX_NEIGHBOUR_REGIONS = 3
#: Hotspots further than this from the feeder say nothing about which county it is in.
NEIGHBOUR_RADIUS_KM = 10.0

_REGION_CODE = re.compile(r"^[A-Z]{2}(-[A-Z0-9]{1,3}){0,2}$")
_LEVEL_ORDER: dict[RegionLevel, int] = {"country": 0, "state": 1, "county": 2}


@dataclass(frozen=True)
class RangeList:
    """One validated regional list, already resolved to catalogue identities.

    ``in_range`` holds the species recorded in the region; ``known`` holds every
    species eBird's taxonomy names at all, which is what makes an absence from
    ``in_range`` positive evidence rather than a naming gap.
    """

    source: str
    region_code: str
    region_codes: tuple[str, ...]
    region_name: str | None
    region_level: RegionLevel
    location_key: str
    fetched_at: datetime
    region_species_total: int
    in_range: frozenset[int]
    known: frozenset[int]
    names: Mapping[int, tuple[str, str | None]] = field(default_factory=dict)
    heard: frozenset[int] = frozenset()
    note: str | None = None

    @property
    def mapped_species(self) -> int:
        return len(self.in_range)


@dataclass(frozen=True)
class RangeCandidate:
    """One classifier output as the range rule sees it.

    ``admissible`` is the caller's verdict from every other admission rule
    (threshold, blocked species, non-bird guard), so the range rule never
    resurrects an output those rules already refused.
    """

    label: str
    score: float
    species_id: int | None
    admissible: bool = True


@dataclass(frozen=True)
class RangeDecision:
    outcome: DecisionOutcome
    chosen_index: int | None
    original: RangeCandidate | None
    reason: str


@dataclass(frozen=True)
class HotspotRegion:
    """The region codes of one eBird hotspot and its distance from the feeder."""

    country: str
    state: str | None
    county: str | None
    distance_km: float


def is_valid_region_code(code: str | None) -> bool:
    return bool(code) and bool(_REGION_CODE.fullmatch(str(code)))


def location_precision(latitude: float | None, longitude: float | None, country_code: str | None) -> LocationPrecision:
    """How finely the configured location pins the feeder down.

    Coordinates written to one decimal place (about 11 km) cannot place a feeder
    in a county, so they are treated as approximate. With no coordinates, a
    configured country is still enough for a country list.
    """
    if latitude is not None and longitude is not None:
        if _decimal_places(latitude) <= 1 and _decimal_places(longitude) <= 1:
            return "approximate"
        return "exact"
    if country_code:
        return "country_only"
    return "none"


def _decimal_places(value: float) -> int:
    text = f"{float(value):.6f}".rstrip("0")
    return len(text.split(".", 1)[1]) if "." in text else 0


def location_key(
    precision: LocationPrecision, latitude: float | None, longitude: float | None, country_code: str | None
) -> str:
    """A stable name for the place a list was fetched for, so a move is noticed.

    Rounded to about 1 km: moving a feeder across the garden must not discard a list.
    """
    if precision in {"exact", "approximate"} and latitude is not None and longitude is not None:
        return f"geo:{round(float(latitude), 2):.2f},{round(float(longitude), 2):.2f}"
    if precision == "country_only" and country_code:
        return f"country:{country_code}"
    return "none"


def choose_regions(
    *,
    preferred_level: RegionLevel,
    precision: LocationPrecision,
    hotspots: Sequence[HotspotRegion],
    country_code: str | None,
) -> tuple[RegionLevel, tuple[str, ...]] | None:
    """Pick the region level and codes to fetch, never finer than the location supports.

    An approximate location is capped at state level. Near a county border the
    nearest hotspot can sit across the line, so every county with a hotspot
    within ``NEIGHBOUR_RADIUS_KM`` is combined: a slightly wider list costs a
    little filtering, a wrong county would reject the feeder's own birds.
    """
    if precision == "none":
        return None
    if precision == "country_only" or not hotspots:
        return ("country", (country_code,)) if is_valid_region_code(country_code) else None

    ceiling: RegionLevel = "state" if precision == "approximate" else "county"
    level: RegionLevel = preferred_level if _LEVEL_ORDER[preferred_level] <= _LEVEL_ORDER[ceiling] else ceiling
    ordered = sorted(hotspots, key=lambda hotspot: hotspot.distance_km)
    nearest = ordered[0]

    if level == "county" and is_valid_region_code(nearest.county):
        codes = [nearest.county]
        for hotspot in ordered[1:]:
            if hotspot.distance_km > NEIGHBOUR_RADIUS_KM or len(codes) >= MAX_NEIGHBOUR_REGIONS:
                break
            if is_valid_region_code(hotspot.county) and hotspot.county not in codes:
                codes.append(str(hotspot.county))
        return "county", tuple(str(code) for code in codes)
    if level in {"county", "state"} and is_valid_region_code(nearest.state):
        return "state", (str(nearest.state),)
    if is_valid_region_code(nearest.country):
        return "country", (nearest.country,)
    return None


def county_list_too_short(mapped_species: int) -> bool:
    return mapped_species < MIN_COUNTY_SPECIES


def validate_range_list(range_list: RangeList, *, now: datetime) -> str | None:
    """Return why a list must not be used, or None when it is fit to filter with."""
    if not is_valid_region_code(range_list.region_code) or not all(
        is_valid_region_code(code) for code in range_list.region_codes
    ):
        return "invalid_region"
    if range_list.fetched_at > now + timedelta(minutes=5):
        return "future_timestamp"
    if range_list.region_species_total <= 0 or not range_list.in_range:
        return "empty_list"
    if range_list.region_species_total > MAX_REGION_SPECIES * max(1, len(range_list.region_codes)):
        return "too_large"
    if not range_list.in_range <= range_list.known:
        return "inconsistent"
    if range_list.mapped_species < range_list.region_species_total * MIN_MAPPED_FRACTION:
        return "poorly_mapped"
    return None


def is_stale(range_list: RangeList, *, now: datetime) -> bool:
    return now - range_list.fetched_at > MAX_LIST_AGE


def refresh_due(
    range_list: RangeList | None,
    *,
    now: datetime,
    current_location_key: str,
    last_failure_at: datetime | None,
) -> bool:
    if last_failure_at is not None and now - last_failure_at < RETRY_INTERVAL:
        return False
    if range_list is None or range_list.location_key != current_location_key:
        return True
    return now - range_list.fetched_at >= REFRESH_INTERVAL


@dataclass(frozen=True)
class FilterState:
    filtering: bool
    reason: FilterReason
    problem: str | None = None


def filter_state(
    *,
    enabled: bool,
    precision: LocationPrecision,
    ebird_configured: bool,
    range_list: RangeList | None,
    current_location_key: str,
    now: datetime,
    last_error: str | None,
) -> FilterState:
    """Name, in one reason, whether the filter is rejecting anything right now and why not.

    The reasons are ordered by what the owner must fix first, so the status line
    always points at the next real step.
    """
    if precision == "none":
        return FilterState(False, "needs_location")
    if not ebird_configured:
        return FilterState(False, "needs_ebird_key")
    if range_list is None:
        return FilterState(False, "lookup_failed" if last_error else "waiting_for_list", last_error)
    problem = validate_range_list(range_list, now=now)
    if problem:
        return FilterState(False, "list_unusable", problem)
    if range_list.location_key != current_location_key:
        return FilterState(False, "location_changed")
    if is_stale(range_list, now=now):
        return FilterState(False, "list_stale", last_error)
    return FilterState(enabled, "active" if enabled else "ready")


def species_verdict(range_list: RangeList, species_id: int | None) -> SpeciesVerdict:
    if species_id is None:
        return "unknown"
    if species_id in range_list.in_range or species_id in range_list.heard:
        return "in_range"
    if species_id in range_list.known:
        return "out_of_range"
    return "unknown"


def decide_range_admission(
    candidates: Sequence[RangeCandidate],
    *,
    active_list: RangeList | None,
    threshold: float,
    owner_confirmed: bool = False,
) -> RangeDecision:
    """Decide what the range rule does with an already-selected prediction.

    ``candidates[0]`` is the prediction every other rule selected; the rest are
    the lower-ranked outputs of the same classification, best first. Only a
    positively in-range alternative that clears ``threshold`` and every other
    rule may replace an out-of-range selection. An unidentifiable alternative is
    not a safe substitute, so with none in range the detection is skipped and
    left for the owner to recover.
    """
    if not candidates:
        return RangeDecision("not_filtered", None, None, "no_candidates")
    selected = candidates[0]
    if owner_confirmed:
        return RangeDecision("not_filtered", 0, selected, "owner_confirmed")
    if active_list is None:
        return RangeDecision("not_filtered", 0, selected, "inactive")

    verdict = species_verdict(active_list, selected.species_id)
    if verdict == "unknown":
        return RangeDecision("not_filtered", 0, selected, "unmapped")
    if verdict == "in_range":
        return RangeDecision("in_range", 0, selected, "in_range")

    for index, alternative in enumerate(candidates[1:], start=1):
        if (
            alternative.admissible
            and alternative.score >= threshold
            and species_verdict(active_list, alternative.species_id) == "in_range"
        ):
            return RangeDecision("fallback", index, selected, "out_of_range")
    return RangeDecision("skipped", None, selected, "out_of_range")
