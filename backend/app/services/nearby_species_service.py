"""Which species birders have reported near this feeder recently, from eBird.

A wildlife-wide classifier knows ten thousand species from every continent and
will name a Dunnock "Golden-crowned Sparrow" now and then. Nothing in a
detection says that is implausible; the fact that no birder within 50 km has
reported the species this month does. The leaderboard uses this to say so.

It runs only where eBird is already configured, and it sends eBird the
approximate location (one decimal place, about 11 km), never the exact one: at
a 50 km radius the extra precision changes nothing.
"""

import asyncio
import time
from dataclasses import dataclass

import structlog

from app.config import settings
from app.services.ebird_service import _normalize_name, ebird_service
from app.utils.public_access import approximate_coordinate

log = structlog.get_logger()

NEARBY_RADIUS_KM = 50
NEARBY_DAYS_BACK = 30
# eBird's recent-observations route returns one row per species; 10000 is its ceiling.
NEARBY_MAX_RESULTS = 10000
CACHE_TTL_SECONDS = 6 * 60 * 60
FAILURE_RETRY_SECONDS = 15 * 60
# A leaderboard must never wait on a third party for long; an unanswered check is unknown.
LOOKUP_TIMEOUT_SECONDS = 4.0


@dataclass(frozen=True)
class NearbyReport:
    radius_km: int
    days_back: int
    names: frozenset[str]


def build_nearby_report(items: list[dict], *, radius_km: int, days_back: int) -> NearbyReport:
    names: set[str] = set()
    for item in items:
        for key in ("sciName", "comName"):
            name = _normalize_name(str(item.get(key) or ""))
            if name:
                names.add(name)
    return NearbyReport(radius_km=radius_km, days_back=days_back, names=frozenset(names))


def reported_nearby(
    report: NearbyReport | None, *, scientific_name: str | None, common_name: str | None
) -> bool | None:
    """True or False when the report can answer for this species; None when it cannot.

    A name eBird does not use (a mammal, or a taxonomy that splits differently)
    comes back False, which is still true: nobody reported it under that name.
    """
    if report is None:
        return None
    candidates = [_normalize_name(name) for name in (scientific_name, common_name) if name]
    if not candidates:
        return None
    return any(candidate in report.names for candidate in candidates)


class NearbySpeciesService:
    def __init__(self) -> None:
        self._cached: tuple[tuple[float, float], NearbyReport] | None = None
        self._cached_at = 0.0
        # None until a lookup fails. A zero would read as "failed at boot" on a host whose
        # monotonic clock is younger than the back-off, and suppress every lookup until then.
        self._failed_at: float | None = None
        self._lock = asyncio.Lock()

    def _location(self) -> tuple[float, float] | None:
        lat = approximate_coordinate(settings.location.latitude)
        lng = approximate_coordinate(settings.location.longitude)
        if lat is None or lng is None:
            return None
        return lat, lng

    async def get_report(self) -> NearbyReport | None:
        if not ebird_service.is_configured():
            return None
        location = self._location()
        if location is None:
            return None
        now = time.monotonic()
        if self._cached and self._cached[0] == location and now - self._cached_at < CACHE_TTL_SECONDS:
            return self._cached[1]
        if self._failed_at is not None and now - self._failed_at < FAILURE_RETRY_SECONDS:
            return self._cached[1] if self._cached and self._cached[0] == location else None
        try:
            return await asyncio.wait_for(self._refresh(location), timeout=LOOKUP_TIMEOUT_SECONDS)
        except Exception as error:  # noqa: BLE001 - any failure means "unknown", never an error page
            self._failed_at = time.monotonic()
            log.warning("Nearby species lookup unavailable", error=type(error).__name__)
            return self._cached[1] if self._cached and self._cached[0] == location else None

    async def _refresh(self, location: tuple[float, float]) -> NearbyReport:
        async with self._lock:
            if self._cached and self._cached[0] == location and time.monotonic() - self._cached_at < CACHE_TTL_SECONDS:
                return self._cached[1]
            items = await ebird_service.get_recent_observations(
                lat=location[0],
                lng=location[1],
                dist_km=NEARBY_RADIUS_KM,
                back_days=NEARBY_DAYS_BACK,
                max_results=NEARBY_MAX_RESULTS,
            )
            report = build_nearby_report(items, radius_km=NEARBY_RADIUS_KM, days_back=NEARBY_DAYS_BACK)
            self._cached = (location, report)
            self._cached_at = time.monotonic()
            return report


nearby_species_service = NearbySpeciesService()
