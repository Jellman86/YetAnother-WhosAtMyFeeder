"""Reverse-geocoding service backed by OpenStreetMap Nominatim.

Resolves a (lat, lon) pair into a coarse administrative tuple
(state/region, country, free-form place description).

We cache results in-process keyed by lat/lon rounded to 2 decimal places
(~1.1 km), which is more than enough resolution for state/country and
keeps us well under Nominatim's 1 req/sec courtesy limit even with active
settings UI usage.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import httpx
import structlog

log = structlog.get_logger()

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "YA-WAMF/1.0 (https://github.com/Jellman86/YetAnother-WhosAtMyFeeder)"
CACHE_PRECISION = 2


@dataclass(frozen=True)
class ReverseGeocodeResult:
    state: Optional[str]
    country: Optional[str]
    place_guess: Optional[str]


class GeocodingService:
    def __init__(self) -> None:
        self._cache: dict[tuple[float, float], ReverseGeocodeResult] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _cache_key(lat: float, lon: float) -> tuple[float, float]:
        return (round(lat, CACHE_PRECISION), round(lon, CACHE_PRECISION))

    async def reverse(self, lat: float, lon: float) -> ReverseGeocodeResult:
        key = self._cache_key(lat, lon)
        async with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached

        try:
            async with httpx.AsyncClient(timeout=6.0, headers={"User-Agent": USER_AGENT}) as client:
                response = await client.get(
                    NOMINATIM_URL,
                    params={
                        "lat": f"{lat:.5f}",
                        "lon": f"{lon:.5f}",
                        "format": "jsonv2",
                        "zoom": 8,
                        "addressdetails": 1,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            log.warning("reverse_geocode_failed", lat=lat, lon=lon, error=str(exc))
            empty = ReverseGeocodeResult(state=None, country=None, place_guess=None)
            async with self._lock:
                self._cache[key] = empty
            return empty

        address = payload.get("address") if isinstance(payload, dict) else None
        address = address if isinstance(address, dict) else {}

        state = (
            address.get("state")
            or address.get("region")
            or address.get("province")
            or address.get("county")
        )
        country = address.get("country")

        place_parts = [
            address.get("city")
            or address.get("town")
            or address.get("village")
            or address.get("hamlet")
            or address.get("municipality"),
            state,
            country,
        ]
        place_guess = ", ".join(part for part in place_parts if part)

        result = ReverseGeocodeResult(
            state=state,
            country=country,
            place_guess=place_guess or None,
        )
        async with self._lock:
            self._cache[key] = result
        return result


geocoding_service = GeocodingService()
