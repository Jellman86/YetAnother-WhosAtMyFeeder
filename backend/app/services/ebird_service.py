import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
import structlog

from app.config import settings

log = structlog.get_logger()

EBIRD_BASE_URL = "https://api.ebird.org/v2"
TAXONOMY_CACHE_TTL = timedelta(hours=24)
LOCALE_CACHE_TTL = timedelta(hours=24)


def _normalize_name(value: str) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value).casefold()
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[_\-]+", " ", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


class EbirdService:
    def __init__(self) -> None:
        # Cache results per locale: {locale: {"fetched_at": datetime, "items": [], "index": {}}}
        self._taxonomy_cache: Dict[str, Dict[str, Any]] = {}
        # Cache locale codes: {"fetched_at": datetime, "codes": set[str], "map": dict[str, str]}
        self._locale_cache: Dict[str, Any] = {}

    def _headers(self) -> dict:
        if not settings.ebird.api_key:
            return {}
        return {"X-eBirdApiToken": settings.ebird.api_key}

    def is_configured(self) -> bool:
        return bool(settings.ebird.enabled and settings.ebird.api_key)

    async def _fetch_json(self, path: str, params: dict) -> List[Dict[str, Any]]:
        url = f"{EBIRD_BASE_URL}{path}"
        headers = self._headers()
        if not headers:
            raise ValueError("eBird API key not configured")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as e:
            log.error("eBird API error", status_code=e.response.status_code, url=str(e.request.url), detail=e.response.text)
            raise
        except Exception as e:
            log.error("eBird connection error", error=str(e), url=url)
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
        requested = (locale or settings.ebird.locale or "en").strip().replace("_", "-")
        if not requested:
            requested = "en"

        supported = await self._get_supported_locales()
        lower_map = {c.lower(): c for c in supported}

        exact = lower_map.get(requested.lower())
        if exact:
            return exact

        lang = requested.split("-")[0].lower()
        bare_lang = lower_map.get(lang)
        if bare_lang:
            return bare_lang

        regional_matches = sorted(c for c in supported if c.lower().startswith(f"{lang}-"))
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
        
        self._taxonomy_cache[effective_locale] = {
            "fetched_at": now, 
            "items": items, 
            "index": index
        }
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

    def simplify_observations(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        simplified = []
        for item in items:
            simplified.append({
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
            })
        return simplified


ebird_service = EbirdService()
