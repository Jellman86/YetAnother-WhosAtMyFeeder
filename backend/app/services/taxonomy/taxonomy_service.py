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

    def __init__(self):
        self._sync_status = {
            "is_running": False,
            "total": 0,
            "processed": 0,
            "current_item": None,
            "error": None
        }

    def get_sync_status(self) -> dict:
        return self._sync_status

    async def get_names(self, query_name: str) -> Dict[str, Optional[str]]:
        """
        Get both scientific and common names for a given name.
        Checks local cache first, then pings iNaturalist.
        """
        # 1. Check Cache
        cached = await self._get_from_cache(query_name)
        if cached:
            # If we previously found nothing, return the original name as scientific
            if cached.get("is_not_found"):
                return {
                    "scientific_name": query_name,
                    "common_name": None,
                    "taxa_id": None
                }
            return cached

        # 2. Lookup from iNaturalist
        log.info("Taxonomy lookup (iNaturalist)", query=query_name)
        result = await self._lookup_inaturalist(query_name)
        
        if result:
            # 3. Save Success to Cache
            await self._save_to_cache(result)
            return result
        else:
            # 4. Save Failure to Cache (to prevent retrying forever)
            await self._save_to_cache({
                "scientific_name": query_name,
                "common_name": None,
                "taxa_id": None,
                "is_not_found": True
            })

        return {
            "scientific_name": query_name,
            "common_name": None,
            "taxa_id": None
        }

    async def _get_from_cache(self, name: str) -> Optional[Dict]:
        """Check the local taxonomy_cache table."""
        try:
            async with get_db() as db:
                # Check scientific name first
                async with db.execute(
                    "SELECT scientific_name, common_name, taxa_id, is_not_found FROM taxonomy_cache WHERE LOWER(scientific_name) = LOWER(?) OR LOWER(common_name) = LOWER(?)",
                    (name, name)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            "scientific_name": row[0],
                            "common_name": row[1],
                            "taxa_id": row[2],
                            "is_not_found": bool(row[3])
                        }
        except Exception as e:
            log.warning("Taxonomy cache lookup failed (table might be missing)", error=str(e))
        return None

    async def _save_to_cache(self, data: Dict):
        """Save a lookup result to the local cache."""
        async with get_db() as db:
            await db.execute(
                """INSERT OR REPLACE INTO taxonomy_cache 
                   (scientific_name, common_name, taxa_id, is_not_found, last_updated) 
                   VALUES (?, ?, ?, ?, ?)""",
                (data["scientific_name"], data["common_name"], data.get("taxa_id"), 1 if data.get("is_not_found") else 0, datetime.now())
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

    async def run_background_sync(self):
        """Scan entire database for unsynced species and normalize them."""
        if self._sync_status["is_running"]:
            return

        try:
            self._sync_status = {
                "is_running": True,
                "total": 0,
                "processed": 0,
                "current_item": "Scanning database...",
                "error": None
            }

            # 1. Find all unique species names that don't have scientific_name or common_name populated
            async with get_db() as db:
                async with db.execute("""
                    SELECT DISTINCT display_name 
                    FROM detections 
                    WHERE scientific_name IS NULL OR common_name IS NULL
                """) as cursor:
                    rows = await cursor.fetchall()
                    unique_names = [row[0] for row in rows]

            self._sync_status["total"] = len(unique_names)
            log.info("Starting taxonomy background sync", unique_species=len(unique_names))

            for name in unique_names:
                self._sync_status["current_item"] = name
                
                # Get names (handles cache internally)
                taxonomy = await self.get_names(name)
                
                if taxonomy and (taxonomy.get("scientific_name") or taxonomy.get("common_name")):
                    # Bulk update all detections matching this display_name
                    async with get_db() as db:
                        await db.execute("""
                            UPDATE detections 
                            SET scientific_name = ?, common_name = ?, taxa_id = ?
                            WHERE display_name = ?
                        """, (taxonomy["scientific_name"], taxonomy["common_name"], taxonomy["taxa_id"], name))
                        await db.commit()
                
                self._sync_status["processed"] += 1
                
                # Rate limiting: 1 second delay to be kind to iNaturalist
                await asyncio.sleep(1.0)

            log.info("Taxonomy background sync completed")
            self._sync_status["current_item"] = "Completed"
            self._sync_status["is_running"] = False

        except Exception as e:
            log.error("Taxonomy sync failed", error=str(e))
            self._sync_status["error"] = str(e)
            self._sync_status["is_running"] = False

taxonomy_service = TaxonomyService()
