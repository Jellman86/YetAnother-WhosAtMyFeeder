import json
import math
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
import structlog

from app.config import settings
from app.services.range_filter import HotspotRegion, is_valid_region_code

log = structlog.get_logger()

EBIRD_BASE_URL = "https://api.ebird.org/v2"
TAXONOMY_CACHE_TTL = timedelta(hours=24)
DEFAULT_TIMEOUT_SECONDS = 15.0
#: The full taxonomy with every category is about 6 MB; nothing eBird sends is legitimately larger.
DEFAULT_MAX_RESPONSE_BYTES = 32 * 1024 * 1024
#: A regional list is a JSON array of six-letter codes: 4,000 species is about 40 KB.
REGION_LIST_MAX_BYTES = 512 * 1024
#: Hotspot and region-info responses are small; a radius search returns at most a few hundred rows.
REFERENCE_MAX_BYTES = 2 * 1024 * 1024
REGION_LOOKUP_RADIUS_KM = 25
LOCALE_CACHE_TTL = timedelta(hours=24)


_SPECIES_CODE = re.compile(r"^[a-z0-9]{3,12}$")


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.asin(min(1.0, math.sqrt(a)))


def _normalize_name(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value).casefold()
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[_\-]+", " ", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


#: Languages whose bare code eBird does not publish, or publishes far less
#: completely than a regional variant. See
#: docs/plans/2026-08-19-species-reference-source-decision.md for the figures.
_PREFERRED_REGIONAL_LOCALE = {
    "pt": "pt_BR",
    "zh": "zh_SIM",
}


def _normalize_locale(value: str) -> str:
    """One comparable form for codes written `pt_BR`, `pt-BR` or `PT-br`."""
    return str(value or "").strip().replace("_", "-").lower()


class EbirdResponseTooLarge(ValueError):
    """eBird sent more than a bounded request accepts; the body is discarded unread."""


class EbirdService:
    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
        # Cache results per locale: {locale: {"fetched_at": datetime, "items": [], "index": {}}}
        self._taxonomy_cache: Dict[str, Dict[str, Any]] = {}
        # Cache locale codes: {"fetched_at": datetime, "codes": set[str], "map": dict[str, str]}
        self._locale_cache: Dict[str, Any] = {}
        # Tests substitute the network here; production always uses the default transport.
        self._transport = transport

    def _headers(self) -> dict:
        if not settings.ebird.api_key:
            return {}
        return {"X-eBirdApiToken": settings.ebird.api_key}

    def is_configured(self) -> bool:
        return bool(settings.ebird.enabled and settings.ebird.api_key)

    async def _fetch_json(
        self,
        path: str,
        params: dict,
        *,
        max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> Any:
        """GET one eBird resource with the key in a header, bounded in time and size.

        The key travels only in the `X-eBirdApiToken` header to eBird's own host and
        is never part of a URL, a log line or an error message.
        """
        url = f"{EBIRD_BASE_URL}{path}"
        headers = self._headers()
        if not headers:
            raise ValueError("eBird API key not configured")

        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
                async with client.stream("GET", url, params=params, headers=headers) as resp:
                    if resp.status_code >= 400:
                        detail = (await resp.aread())[:500].decode("utf-8", errors="replace")
                        log.error("eBird API error", status_code=resp.status_code, path=path, detail=detail)
                        resp.raise_for_status()
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise EbirdResponseTooLarge(f"eBird response for {path} exceeds {max_bytes} bytes")
                    body = bytearray()
                    async for chunk in resp.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise EbirdResponseTooLarge(f"eBird response for {path} exceeds {max_bytes} bytes")
            return json.loads(bytes(body))
        except httpx.HTTPStatusError:
            raise
        except Exception as e:
            log.error("eBird connection error", error=type(e).__name__, path=path)
            raise

    async def _get_supported_locales(self) -> set[str]:
        now = datetime.utcnow()
        fetched_at = self._locale_cache.get("fetched_at")
        if fetched_at and now - fetched_at < LOCALE_CACHE_TTL:
            cached_codes = self._locale_cache.get("codes") or set()
            if cached_codes:
                return set(cached_codes)

        # If eBird is not configured yet, keep behavior deterministic.
        if not self.is_configured():
            return {"en"}

        codes: set[str] = set()
        try:
            payload = await self._fetch_json("/ref/taxa-locales/ebird", {"fmt": "json"})
            for entry in payload:
                code = None
                if isinstance(entry, dict):
                    code = entry.get("code") or entry.get("locale")
                elif isinstance(entry, str):
                    code = entry
                if not code:
                    continue
                clean = str(code).strip()
                if clean:
                    codes.add(clean)
        except Exception as e:
            log.warning("Failed to fetch eBird locale codes", error=str(e))

        if not codes:
            codes = {"en"}

        self._locale_cache = {
            "fetched_at": now,
            "codes": codes,
            "map": {c.lower(): c for c in codes},
        }
        return set(codes)

    async def resolve_locale(self, locale: Optional[str] = None) -> str:
        """Map a requested language onto the closest code eBird actually publishes.

        eBird publishes codes with underscores (`pt_BR`), while requests arrive
        with either separator, so everything is compared on one normalized form.
        Some languages need a regional variant: `pt` is not published at all, and
        `zh` carries far fewer translated names than `zh_SIM`. Figures are in
        docs/plans/2026-08-19-species-reference-source-decision.md.
        """
        requested = _normalize_locale(locale or settings.ebird.locale or "en") or "en"

        supported = await self._get_supported_locales()
        lower_map = {_normalize_locale(code): code for code in supported}

        lang = requested.split("-")[0]
        preferred = lower_map.get(_normalize_locale(_PREFERRED_REGIONAL_LOCALE.get(lang, "")))

        # A bare language with a preferred variant takes it. An explicit regional
        # request is matched exactly below, so choosing `zh_HK` still works.
        if requested == lang and preferred:
            return preferred

        exact = lower_map.get(requested)
        if exact:
            return exact

        # An unrecognised regional variant belongs with its language's preferred
        # form rather than whichever region happens to sort first.
        if preferred:
            return preferred

        bare_lang = lower_map.get(lang)
        if bare_lang:
            return bare_lang

        regional_matches = sorted(code for key, code in lower_map.items() if key.startswith(f"{lang}-"))
        if regional_matches:
            return regional_matches[0]

        return lower_map.get("en", "en")

    async def get_recent_observations(
        self,
        lat: float,
        lng: float,
        dist_km: int,
        back_days: int,
        max_results: int,
        species_code: Optional[str] = None,
        notable: bool = False,
    ) -> List[Dict[str, Any]]:
        if not self.is_configured():
            return []

        if notable:
            path = "/data/obs/geo/recent/notable"
        elif species_code:
            path = f"/data/obs/geo/recent/{species_code}"
        else:
            path = "/data/obs/geo/recent"

        params = {
            "lat": lat,
            "lng": lng,
            "dist": dist_km,
            "back": back_days,
            "maxResults": max_results,
            "locale": settings.ebird.locale,
        }
        return await self._fetch_json(path, params)

    async def get_taxonomy(self, locale: Optional[str] = None) -> List[Dict[str, Any]]:
        effective_locale = await self.resolve_locale(locale)
        now = datetime.utcnow()

        cache = self._taxonomy_cache.get(effective_locale)
        if cache and cache.get("fetched_at") and now - cache["fetched_at"] < TAXONOMY_CACHE_TTL:
            return cache["items"]

        if not self.is_configured():
            return []

        params = {
            "fmt": "json",
            "locale": effective_locale,
            "cat": "species,issf,spuh,slash",
        }
        try:
            items = await self._fetch_json("/ref/taxonomy/ebird", params)
        except Exception as e:
            log.error("Failed to fetch eBird taxonomy", locale=effective_locale, error=str(e))
            # Fallback to English taxonomy if locale lookup fails.
            if effective_locale.lower() != "en":
                try:
                    english_locale = await self.resolve_locale("en")
                    if english_locale != effective_locale:
                        return await self.get_taxonomy(locale=english_locale)
                except Exception:
                    pass
            return []

        index: Dict[str, str] = {}
        for item in items:
            code = item.get("speciesCode")
            if not code:
                continue
            com = item.get("comName") or ""
            sci = item.get("sciName") or ""
            if com:
                normalized = _normalize_name(com)
                if normalized:
                    index[normalized] = code
            if sci:
                normalized = _normalize_name(sci)
                if normalized:
                    index[normalized] = code

        self._taxonomy_cache[effective_locale] = {"fetched_at": now, "items": items, "index": index}
        return items

    async def resolve_species_code(self, name: str, locale: Optional[str] = None) -> Optional[str]:
        if not name:
            return None
        normalized_name = _normalize_name(name)
        if not normalized_name:
            return None

        preferred_locales: list[str] = []
        for candidate in (locale, settings.ebird.locale, "en"):
            if not candidate:
                continue
            resolved = await self.resolve_locale(candidate)
            if resolved not in preferred_locales:
                preferred_locales.append(resolved)
            await self.get_taxonomy(locale=resolved)

        # Try preferred locale caches first.
        for locale_code in preferred_locales:
            cache = self._taxonomy_cache.get(locale_code)
            if not cache:
                continue
            code = cache.get("index", {}).get(normalized_name)
            if code:
                return code

        # Fallback to any cached locale.
        for cache in self._taxonomy_cache.values():
            index = cache.get("index", {})
            code = index.get(normalized_name)
            if code:
                return code

        return None

    async def get_common_name(self, scientific_name: str, locale: Optional[str] = None) -> Optional[str]:
        """Resolve common name from scientific name using eBird taxonomy."""
        if not scientific_name:
            return None

        # Ensure taxonomy is loaded for requested locale
        items = await self.get_taxonomy(locale)

        # Search for scientific name match
        normalized_sci = _normalize_name(scientific_name)
        for item in items:
            sci = item.get("sciName") or ""
            if _normalize_name(sci) == normalized_sci:
                return item.get("comName")

        return None

    async def get_nearby_hotspot_regions(
        self,
        *,
        query_lat: float,
        query_lng: float,
        feeder_lat: float,
        feeder_lng: float,
    ) -> List[HotspotRegion]:
        """The region codes of eBird hotspots around the feeder, nearest first.

        eBird has no reverse-geocoding endpoint, but every hotspot carries its
        country, state and county codes, so the hotspots around a point name the
        regions it lies in. eBird is sent the approximate point; distances are
        measured locally from the exact one, which never leaves this host.
        """
        payload = await self._fetch_json(
            "/ref/hotspot/geo",
            {"lat": query_lat, "lng": query_lng, "dist": REGION_LOOKUP_RADIUS_KM, "fmt": "json"},
            max_bytes=REFERENCE_MAX_BYTES,
        )
        regions: List[HotspotRegion] = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            try:
                lat = float(item["lat"])
                lng = float(item["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            country = str(item.get("countryCode") or "").strip().upper()
            if not is_valid_region_code(country):
                continue
            state = str(item.get("subnational1Code") or "").strip().upper() or None
            county = str(item.get("subnational2Code") or "").strip().upper() or None
            regions.append(
                HotspotRegion(
                    country=country,
                    state=state if is_valid_region_code(state) else None,
                    county=county if is_valid_region_code(county) else None,
                    distance_km=_haversine_km(feeder_lat, feeder_lng, lat, lng),
                )
            )
        return sorted(regions, key=lambda region: region.distance_km)

    async def get_region_species_codes(self, region_code: str) -> List[str]:
        """Every taxon code eBird has recorded in a region, all seasons and years together."""
        if not is_valid_region_code(region_code):
            raise ValueError("invalid eBird region code")
        payload = await self._fetch_json(f"/product/spplist/{region_code}", {}, max_bytes=REGION_LIST_MAX_BYTES)
        if not isinstance(payload, list):
            raise ValueError("eBird regional list was not a list")
        return [code.strip() for code in payload if isinstance(code, str) and _SPECIES_CODE.fullmatch(code.strip())]

    async def get_region_name(self, region_code: str) -> Optional[str]:
        """eBird's own name for a region, such as "Sonoma County, California, US"; None if unavailable."""
        if not is_valid_region_code(region_code):
            return None
        try:
            payload = await self._fetch_json(
                f"/ref/region/info/{region_code}", {"regionNameFormat": "full"}, max_bytes=REFERENCE_MAX_BYTES
            )
        except Exception:
            return None
        name = payload.get("result") if isinstance(payload, dict) else None
        return str(name).strip()[:200] if isinstance(name, str) and name.strip() else None

    def simplify_observations(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        simplified = []
        for item in items:
            simplified.append(
                {
                    "species_code": item.get("speciesCode"),
                    "common_name": item.get("comName"),
                    "scientific_name": item.get("sciName"),
                    "observed_at": item.get("obsDt"),
                    "location_name": item.get("locName"),
                    "how_many": item.get("howMany"),
                    "lat": item.get("lat"),
                    "lng": item.get("lng"),
                    "obs_valid": item.get("obsValid"),
                    "obs_reviewed": item.get("obsReviewed"),
                }
            )
        return simplified


ebird_service = EbirdService()
