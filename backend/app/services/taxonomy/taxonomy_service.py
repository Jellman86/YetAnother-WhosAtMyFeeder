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
        self._client: Optional[httpx.AsyncClient] = None
        self._sync_status = {
            "is_running": False,
            "total": 0,
            "processed": 0,
            "current_item": None,
            "error": None
        }

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    def get_sync_status(self) -> dict:
        return self._sync_status

    async def get_names(self, query_name: str, db: Optional[aiosqlite.Connection] = None) -> Dict[str, Optional[str]]:
        """
        Get both scientific and common names for a given name.
        Checks local cache first, then pings iNaturalist.
        """
        # 1. Check Cache
        cached = await self._get_from_cache(query_name, db=db)
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
            await self._save_to_cache(result, db=db)
            return result
        else:
            # 4. Save Failure to Cache (to prevent retrying forever)
            await self._save_to_cache({
                "scientific_name": query_name,
                "common_name": None,
                "taxa_id": None,
                "is_not_found": True
            }, db=db)

        return {
            "scientific_name": query_name,
            "common_name": None,
            "taxa_id": None
        }

    async def _get_from_cache(self, name: str, db: Optional[aiosqlite.Connection] = None) -> Optional[Dict]:
        """Check the local taxonomy_cache table."""
        try:
            if db:
                return await self._query_cache(db, name)
            else:
                async with get_db() as db:
                    return await self._query_cache(db, name)
        except Exception as e:
            log.warning("Taxonomy cache lookup failed", error=str(e))
        return None

    async def _query_cache(self, db: aiosqlite.Connection, name: str) -> Optional[Dict]:
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
        return None

    async def _save_to_cache(self, data: Dict, db: Optional[aiosqlite.Connection] = None):
        """Save a lookup result to the local cache."""
        if db:
            await self._insert_cache(db, data)
        else:
            async with get_db() as db:
                await self._insert_cache(db, data)
                await db.commit()

    async def _insert_cache(self, db: aiosqlite.Connection, data: Dict):
        await db.execute(
            """INSERT OR REPLACE INTO taxonomy_cache 
               (scientific_name, common_name, taxa_id, is_not_found, last_updated) 
               VALUES (?, ?, ?, ?, ?)""",
            (data["scientific_name"], data["common_name"], data.get("taxa_id"), 1 if data.get("is_not_found") else 0, datetime.now())
        )

    async def _lookup_inaturalist(self, name: str) -> Optional[Dict]:
        """Query the iNaturalist API."""
        try:
            params = {
                "q": name,
                "per_page": 1,
                "locale": "en"
            }
            
            client = self._get_client()
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
                    
                    # Get names (passing existing db connection)
                    taxonomy = await self.get_names(name, db=db)
                    
                    if taxonomy and (taxonomy.get("scientific_name") or taxonomy.get("common_name")):
                        scientific_name = taxonomy.get("scientific_name")
                        common_name = taxonomy.get("common_name")
                        taxa_id = taxonomy.get("taxa_id")

                        await db.execute("""
                            UPDATE detections 
                            SET scientific_name = ?, common_name = ?, taxa_id = ?
                            WHERE display_name = ?
                        """, (scientific_name, common_name, taxa_id, name))
                        # Commit every few items or at the end for performance
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

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

taxonomy_service = TaxonomyService()
