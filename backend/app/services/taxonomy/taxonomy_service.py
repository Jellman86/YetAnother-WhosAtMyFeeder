import httpx
import structlog
import asyncio
from typing import Optional, Tuple, Dict
from datetime import datetime
from app.database import get_db

log = structlog.get_logger()

class TaxonomyService:
    """Service to handle bidirectional scientific <-> common name lookups using iNaturalist."""
    
    API_URL = "https://api.inaturalist.org/v1/taxa"

    async def get_names(self, query_name: str) -> Dict[str, Optional[str]]:
        """
        Get both scientific and common names for a given name.
        Checks local cache first, then pings iNaturalist.
        """
        # 1. Check Cache
        cached = await self._get_from_cache(query_name)
        if cached:
            return cached

        # 2. Lookup from iNaturalist
        log.info("Taxonomy lookup (iNaturalist)", query=query_name)
        result = await self._lookup_inaturalist(query_name)
        
        if result:
            # 3. Save to Cache
            await self._save_to_cache(result)
            return result

        return {
            "scientific_name": query_name,
            "common_name": None,
            "taxa_id": None
        }

    async def _get_from_cache(self, name: str) -> Optional[Dict]:
        """Check the local taxonomy_cache table."""
        async with get_db() as db:
            # Check scientific name first
            async with db.execute(
                "SELECT scientific_name, common_name, taxa_id FROM taxonomy_cache WHERE LOWER(scientific_name) = LOWER(?) OR LOWER(common_name) = LOWER(?)",
                (name, name)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "scientific_name": row[0],
                        "common_name": row[1],
                        "taxa_id": row[2]
                    }
        return None

    async def _save_to_cache(self, data: Dict):
        """Save a lookup result to the local cache."""
        async with get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO taxonomy_cache 
                   (scientific_name, common_name, taxa_id, last_updated) 
                   VALUES (?, ?, ?, ?)""",
                (data["scientific_name"], data["common_name"], data["taxa_id"], datetime.now())
            )
            await db.commit()

    async def _lookup_inaturalist(self, name: str) -> Optional[Dict]:
        """Query the iNaturalist API."""
        try:
            params = {
                "q": name,
                "per_page": 1,
                "locale": "en" # Can be made configurable later
            }
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self.API_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                
                if data.get("total_results", 0) > 0:
                    taxon = data["results"][0]
                    return {
                        "scientific_name": taxon.get("name"),
                        "common_name": taxon.get("preferred_common_name"),
                        "taxa_id": taxon.get("id")
                    }
        except Exception as e:
            log.warning("iNaturalist lookup failed", query=name, error=str(e))
            
        return None

taxonomy_service = TaxonomyService()
