import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
import structlog

from app.config import settings

log = structlog.get_logger()

EBIRD_BASE_URL = "https://api.ebird.org/v2"
TAXONOMY_CACHE_TTL = timedelta(hours=24)


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


class EbirdService:
    def __init__(self) -> None:
        # Cache results per locale: {locale: {"fetched_at": datetime, "items": [], "index": {}}}
        self._taxonomy_cache: Dict[str, Dict[str, Any]] = {}

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
        effective_locale = locale or settings.ebird.locale or "en"
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
            return []
            
        index: Dict[str, str] = {}
        for item in items:
            code = item.get("speciesCode")
            if not code:
                continue
            com = item.get("comName") or ""
            sci = item.get("sciName") or ""
            if com:
                index[_normalize_name(com)] = code
            if sci:
                index[_normalize_name(sci)] = code
        
        self._taxonomy_cache[effective_locale] = {
            "fetched_at": now, 
            "items": items, 
            "index": index
        }
        return items

    async def resolve_species_code(self, name: str) -> Optional[str]:
        if not name:
            return None
        # Use default settings locale for code resolution
        await self.get_taxonomy()
        
        # We need to search across ALL cached indices to find the code if possible,
        # but usually it's in the default locale.
        for cache in self._taxonomy_cache.values():
            index = cache.get("index", {})
            code = index.get(_normalize_name(name))
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
