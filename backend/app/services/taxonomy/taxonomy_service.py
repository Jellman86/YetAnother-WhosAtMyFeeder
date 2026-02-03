import httpx
import structlog
import asyncio
import aiosqlite
from typing import Optional, Dict
from datetime import datetime
from app.database import get_db
from app.config import settings
from app.services.ebird_service import ebird_service

log = structlog.get_logger()

class TaxonomyService:
    """Service to handle bidirectional scientific <-> common name lookups using iNaturalist."""

    API_URL = "https://api.inaturalist.org/v1/taxa"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()
        self._sync_status = {
            "is_running": False,
            "total": 0,
            "processed": 0,
            "current_item": None,
            "error": None
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client with thread-safe lazy initialization."""
        if self._client is None:
            async with self._client_lock:
                # Double-check pattern to avoid race condition
                if self._client is None:
                    self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    def get_sync_status(self) -> dict:
        return self._sync_status

    async def get_names(self, query_name: str, db: Optional[aiosqlite.Connection] = None, force_refresh: bool = False) -> Dict[str, Optional[str]]:
        """
        Get both scientific and common names for a given name.
        Checks local cache first, then pings iNaturalist.
        If configured, tries to use eBird for the common name preference.
        """
        # 1. Check Cache (skip if forcing refresh)
        if not force_refresh:
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

        # 2. Lookup from iNaturalist (Base)
        # We always need iNat for the taxa_id and scientific name structure
        log.info("Taxonomy lookup (iNaturalist)", query=query_name, force_refresh=force_refresh)
        result = await self._lookup_inaturalist(query_name)

        if not result:
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
            
        # 3. Enrichment Override (eBird)
        # If user prefers eBird common names, try to fetch and override
        if settings.enrichment.taxonomy_source == "ebird":
             try:
                 # Use the scientific name we just found to lookup in eBird
                 # This is safer than using the raw query_name
                 sci_name = result.get("scientific_name") or query_name
                 ebird_common = await ebird_service.get_common_name(sci_name, locale=settings.ebird.locale)
                 
                 if ebird_common:
                     log.info("Overriding common name with eBird", original=result.get("common_name"), ebird=ebird_common)
                     result["common_name"] = ebird_common
             except Exception as e:
                 log.warning("Failed to lookup eBird common name, falling back to iNaturalist", error=str(e))

        # 4. Save Success to Cache
        await self._save_to_cache(result, db=db)
        return result

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
            "SELECT scientific_name, common_name, taxa_id, is_not_found, thumbnail_url FROM taxonomy_cache WHERE LOWER(scientific_name) = LOWER(?) OR LOWER(common_name) = LOWER(?)",
            (name, name)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    "scientific_name": row[0],
                    "common_name": row[1],
                    "taxa_id": row[2],
                    "is_not_found": bool(row[3]),
                    "thumbnail_url": row[4]
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
               (scientific_name, common_name, taxa_id, is_not_found, thumbnail_url, last_updated) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (data["scientific_name"], data["common_name"], data.get("taxa_id"), 1 if data.get("is_not_found") else 0, data.get("thumbnail_url"), datetime.now())
        )

    async def _lookup_inaturalist(self, name: str) -> Optional[Dict]:
        """Query the iNaturalist API."""
        try:
            params = {
                "q": name,
                "per_page": 1,
                "locale": "en"
            }

            client = await self._get_client()
            resp = await client.get(self.API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("total_results", 0) > 0:
                taxon = data["results"][0]
                photo = taxon.get("default_photo")
                thumb = photo.get("square_url") if photo else None
                return {
                    "scientific_name": taxon.get("name"),
                    "common_name": taxon.get("preferred_common_name"),
                    "taxa_id": taxon.get("id"),
                    "thumbnail_url": thumb
                }
        except Exception as e:
            log.warning("iNaturalist lookup failed", query=name, error=str(e))
            
        return None

    async def get_localized_common_name(self, taxa_id: int, lang: str, db: Optional[aiosqlite.Connection] = None) -> Optional[str]:
        """
        Get the localized common name for a species.
        Checks cache first, then pings iNaturalist.
        """
        if not taxa_id:
            return None

        # 1. Check Cache
        cached = await self._get_translation_from_cache(taxa_id, lang, db=db)
        if cached:
            return cached

        # 2. Lookup from iNaturalist
        log.info("Localized taxonomy lookup (iNaturalist)", taxa_id=taxa_id, lang=lang)
        result = await self._lookup_localized_inaturalist(taxa_id, lang)
        
        if result:
            # 3. Save to Cache
            await self._save_translation_to_cache(taxa_id, lang, result, db=db)
            return result

        return None

    async def _get_translation_from_cache(self, taxa_id: int, lang: str, db: Optional[aiosqlite.Connection] = None) -> Optional[str]:
        """Check the taxonomy_translations table."""
        try:
            if db:
                return await self._query_translation_cache(db, taxa_id, lang)
            else:
                async with get_db() as db:
                    return await self._query_translation_cache(db, taxa_id, lang)
        except Exception as e:
            log.warning("Taxonomy translation cache lookup failed", error=str(e))
        return None

    async def _query_translation_cache(self, db: aiosqlite.Connection, taxa_id: int, lang: str) -> Optional[str]:
        async with db.execute(
            "SELECT common_name FROM taxonomy_translations WHERE taxa_id = ? AND language_code = ?",
            (taxa_id, lang)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
        return None

    async def _save_translation_to_cache(self, taxa_id: int, lang: str, common_name: str, db: Optional[aiosqlite.Connection] = None):
        """Save a translation to the local cache."""
        if db:
            await self._insert_translation_cache(db, taxa_id, lang, common_name)
            await db.commit()
        else:
            async with get_db() as db:
                await self._insert_translation_cache(db, taxa_id, lang, common_name)
                await db.commit()

    async def _insert_translation_cache(self, db: aiosqlite.Connection, taxa_id: int, lang: str, common_name: str):
        await db.execute(
            """INSERT OR REPLACE INTO taxonomy_translations 
               (taxa_id, language_code, common_name) 
               VALUES (?, ?, ?)""",
            (taxa_id, lang, common_name)
        )

    async def _lookup_localized_inaturalist(self, taxa_id: int, lang: str) -> Optional[str]:
        """Query the iNaturalist API for a specific taxon and locale."""
        try:
            url = f"{self.API_URL}/{taxa_id}"
            params = {
                "locale": lang
            }

            client = await self._get_client()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("total_results", 0) > 0:
                taxon = data["results"][0]
                # iNaturalist returns preferred_common_name for the requested locale
                return taxon.get("preferred_common_name")
        except Exception as e:
            log.warning("Localized iNaturalist lookup failed", taxa_id=taxa_id, lang=lang, error=str(e))
            
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

                if not unique_names:
                    self._sync_status["current_item"] = "Database Healthy: No missing taxonomy found"
                    self._sync_status["is_running"] = False
                    return

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
