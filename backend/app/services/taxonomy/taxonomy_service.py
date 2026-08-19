import httpx
import os
import structlog

from app.services.species_reference import species_reference
import asyncio
import aiosqlite
from typing import Any, Optional, Dict
from datetime import datetime
from app.database import get_db
from app.config import settings
from app.services.ebird_service import ebird_service
from app.utils.enrichment import get_effective_enrichment_settings

log = structlog.get_logger()


# A cached "not found" records that one lookup found nothing, which is a weaker
# claim than the species not existing. Re-test it periodically so a wrong negative
# cannot withhold a name indefinitely.
TAXONOMY_NOT_FOUND_RETRY_SECONDS = max(
    3600.0,
    float(os.getenv("TAXONOMY_NOT_FOUND_RETRY_SECONDS", str(7 * 24 * 3600))),
)


def _negative_entry_expired(last_updated: Any, *, now: Optional[datetime] = None) -> bool:
    """Whether a cached not-found result is old enough to re-test.

    An unreadable or missing timestamp counts as expired: the cost of one extra
    lookup is smaller than withholding a species name forever.
    """
    if not last_updated:
        return True

    reference = now or datetime.now()
    if isinstance(last_updated, datetime):
        recorded = last_updated
    else:
        text = str(last_updated).strip()
        recorded = None
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                recorded = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if recorded is None:
            try:
                recorded = datetime.fromisoformat(text)
            except ValueError:
                return True

    if recorded.tzinfo is not None:
        recorded = recorded.replace(tzinfo=None)
    return (reference - recorded).total_seconds() > TAXONOMY_NOT_FOUND_RETRY_SECONDS


def _parenthetical_aliases(value: str) -> tuple[Optional[str], Optional[str]]:
    """Split a trailing parenthetical alias without regex backtracking."""
    normalized = value.strip()
    if not normalized.endswith(")"):
        return None, None
    opening = normalized.find("(")
    if opening < 0:
        return None, None
    left = normalized[:opening].strip() or None
    right = normalized[opening + 1 : -1].strip() or None
    return left, right


class TaxonomyLookupUnavailable(Exception):
    """The taxonomy provider could not be reached or did not return an answer.

    Distinct from the provider answering that it holds no matching taxon.
    """


class TaxonomyService:
    """Service to handle bidirectional scientific <-> common name lookups using iNaturalist."""

    API_URL = "https://api.inaturalist.org/v1/taxa"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get HTTP client with thread-safe lazy initialization."""
        if self._client is None:
            async with self._client_lock:
                # Double-check pattern to avoid race condition
                if self._client is None:
                    self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def get_names(
        self, query_name: str, db: Optional[aiosqlite.Connection] = None, force_refresh: bool = False
    ) -> Dict[str, Optional[str]]:
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
                    return {"scientific_name": query_name, "common_name": None, "taxa_id": None}
                return cached

        # 2. Lookup from iNaturalist (Base)
        # We always need iNat for the taxa_id and scientific name structure
        log.info("Taxonomy lookup (iNaturalist)", query=query_name, force_refresh=force_refresh)

        # Try raw name first, then try splitting parentheticals if it looks like an alias
        lookup_names = [query_name]
        left, right = _parenthetical_aliases(query_name)
        if left or right:
            if left and left not in lookup_names:
                lookup_names.append(left)
            if right and right not in lookup_names:
                lookup_names.append(right)

        result = None
        lookup_unavailable = False
        for name in lookup_names:
            try:
                result = await self._lookup_inaturalist(name)
            except TaxonomyLookupUnavailable:
                lookup_unavailable = True
                break
            if result:
                break

        if not result:
            # The bundled reference answers when the network could not. It is
            # deliberately here rather than ahead of iNaturalist: a hit carries no
            # taxon id, so resolving from it first would cost enrichment the id it
            # needs for every covered species. Placed here it costs nothing and
            # gives offline installs, and installs riding out an outage, a name.
            reference_hit = species_reference.lookup(query_name)
            if reference_hit:
                log.info(
                    "Taxonomy resolved from bundled reference",
                    query=query_name,
                    scientific_name=reference_hit.get("scientific_name"),
                    lookup_unavailable=lookup_unavailable,
                )
                # Not cached: the row would carry no taxon id, and a later lookup
                # with the network back should still be able to supply one.
                return {
                    "scientific_name": reference_hit.get("scientific_name"),
                    "common_name": reference_hit.get("common_name"),
                    "taxa_id": None,
                }

            # 4. Save Failure to Cache (to prevent retrying forever), but only when
            # iNaturalist actually answered. Recording a provider outage as
            # "no such species" would withhold the name until something repairs it.
            if not lookup_unavailable:
                await self._save_to_cache(
                    {"scientific_name": query_name, "common_name": None, "taxa_id": None, "is_not_found": True}, db=db
                )
            return {"scientific_name": query_name, "common_name": None, "taxa_id": None}

        # 3. Enrichment Override (eBird)
        # If user prefers eBird common names, try to fetch and store as translation
        effective = get_effective_enrichment_settings()
        if effective["taxonomy_source"] == "ebird":
            try:
                sci_name = result.get("scientific_name") or query_name
                locale = settings.ebird.locale or "en"
                ebird_common = await ebird_service.get_common_name(sci_name, locale=locale)

                if ebird_common:
                    if locale == "en":
                        # Overwrite English common name in main result
                        log.info(
                            "Overriding canonical common name with eBird (en)",
                            original=result.get("common_name"),
                            ebird=ebird_common,
                        )
                        result["common_name"] = ebird_common
                    else:
                        # Store as translation, do NOT overwrite the main result (which should remain English for exporter compatibility)
                        log.info(
                            "Storing localized eBird common name in translations", locale=locale, ebird=ebird_common
                        )
                        await self._save_translation_to_cache(result["taxa_id"], locale, ebird_common, db=db)
            except Exception as e:
                log.warning("Failed to lookup eBird common name", error=str(e))

        # 4. Save Success to Cache
        await self._save_to_cache(result, db=db, replace_negative_name=query_name)
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
            """SELECT scientific_name, COALESCE(manual_common_name, common_name), taxa_id,
                      is_not_found, thumbnail_url, last_updated
               FROM taxonomy_cache
               WHERE LOWER(scientific_name) = LOWER(?)
                  OR LOWER(common_name) = LOWER(?)
                  OR LOWER(manual_common_name) = LOWER(?)
               ORDER BY is_not_found ASC, last_updated DESC
               LIMIT 1""",
            (name, name, name),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                if bool(row[3]) and _negative_entry_expired(row[5]):
                    # Report a miss so the caller looks the species up again.
                    return None
                return {
                    "scientific_name": row[0],
                    "common_name": row[1],
                    "taxa_id": row[2],
                    "is_not_found": bool(row[3]),
                    "thumbnail_url": row[4],
                }
        return None

    async def _save_to_cache(
        self,
        data: Dict,
        db: Optional[aiosqlite.Connection] = None,
        replace_negative_name: Optional[str] = None,
    ):
        """Save a lookup result to the local cache."""
        if db:
            if replace_negative_name:
                await self._delete_negative_cache_match(db, replace_negative_name)
            await self._insert_cache(db, data)
        else:
            async with get_db() as db:
                if replace_negative_name:
                    await self._delete_negative_cache_match(db, replace_negative_name)
                await self._insert_cache(db, data)
                await db.commit()

    async def _delete_negative_cache_match(self, db: aiosqlite.Connection, name: str) -> None:
        """Remove an obsolete negative row before storing a successful alias lookup."""
        await db.execute(
            """DELETE FROM taxonomy_cache
               WHERE is_not_found = 1
                 AND (LOWER(scientific_name) = LOWER(?) OR LOWER(common_name) = LOWER(?))""",
            (name, name),
        )

    async def _insert_cache(self, db: aiosqlite.Connection, data: Dict):
        await db.execute(
            """INSERT INTO taxonomy_cache
               (scientific_name, common_name, taxa_id, is_not_found, thumbnail_url, last_updated) 
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(scientific_name) DO UPDATE SET
                   common_name = excluded.common_name,
                   taxa_id = excluded.taxa_id,
                   is_not_found = excluded.is_not_found,
                   thumbnail_url = excluded.thumbnail_url,
                   last_updated = excluded.last_updated""",
            (
                data["scientific_name"],
                data["common_name"],
                data.get("taxa_id"),
                1 if data.get("is_not_found") else 0,
                data.get("thumbnail_url"),
                datetime.now(),
            ),
        )

    async def _lookup_inaturalist(self, name: str) -> Optional[Dict]:
        """Query the iNaturalist API.

        Returns the taxon, or None when iNaturalist answered and holds no match.
        Raises :class:`TaxonomyLookupUnavailable` when the request itself failed,
        because "we could not ask" says nothing about whether the taxon exists.
        """
        try:
            params = {"q": name, "per_page": 1, "locale": "en"}

            client = await self._get_client()
            resp = await client.get(self.API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            if not isinstance(data, dict):
                raise ValueError("iNaturalist response is not an object")

            total_results = data.get("total_results")
            if not isinstance(total_results, int) or isinstance(total_results, bool):
                raise ValueError("iNaturalist response has an invalid total_results value")
            if total_results == 0:
                return None

            results = data.get("results")
            if not isinstance(results, list) or not results or not isinstance(results[0], dict):
                raise ValueError("iNaturalist response has no usable result")

            taxon = results[0]
            scientific_name = taxon.get("name")
            taxa_id = taxon.get("id")
            if not isinstance(scientific_name, str) or not scientific_name.strip():
                raise ValueError("iNaturalist result has no scientific name")
            if not isinstance(taxa_id, int) or isinstance(taxa_id, bool):
                raise ValueError("iNaturalist result has no numeric taxon id")

            common_name = taxon.get("preferred_common_name")
            if not isinstance(common_name, str):
                common_name = None
            photo = taxon.get("default_photo")
            photo = photo if isinstance(photo, dict) else {}
            thumbnail_url = photo.get("square_url")
            if not isinstance(thumbnail_url, str):
                thumbnail_url = None

            return {
                "scientific_name": scientific_name,
                "common_name": common_name,
                "taxa_id": taxa_id,
                "thumbnail_url": thumbnail_url,
            }
        except Exception as e:
            log.warning("iNaturalist lookup failed", query=name, error=str(e))
            raise TaxonomyLookupUnavailable(str(e)) from e

    async def get_canonical_english_name(
        self, taxa_id: int, db: Optional[aiosqlite.Connection] = None
    ) -> Optional[str]:
        """Return the canonical English common name from taxonomy_cache for a taxa_id.

        This is the authoritative English name stored at classification/taxonomy time,
        used to normalize display when the detection row may have been stored with a
        non-English common_name (e.g. after a language switch).
        """
        if not taxa_id:
            return None
        try:
            if db:
                return await self._query_canonical_english(db, taxa_id)
            async with get_db() as conn:
                return await self._query_canonical_english(conn, taxa_id)
        except Exception as e:
            log.warning("Canonical English name lookup failed", taxa_id=taxa_id, error=str(e))
        return None

    async def _query_canonical_english(self, db: aiosqlite.Connection, taxa_id: int) -> Optional[str]:
        async with db.execute(
            """SELECT COALESCE(manual_common_name, common_name)
               FROM taxonomy_cache WHERE taxa_id = ? AND is_not_found = 0 LIMIT 1""",
            (taxa_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row and row[0] else None

    async def get_common_name_override(
        self, scientific_name: str, db: aiosqlite.Connection
    ) -> Optional[Dict[str, Optional[str]]]:
        """Return provider, manual, and effective names for a cached taxon."""
        async with db.execute(
            """SELECT scientific_name, common_name, manual_common_name
               FROM taxonomy_cache
               WHERE LOWER(scientific_name) = LOWER(?) AND is_not_found = 0
               LIMIT 1""",
            (scientific_name,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        return {
            "scientific_name": row[0],
            "provider_common_name": row[1],
            "manual_common_name": row[2],
            "effective_common_name": row[2] or row[1],
        }

    async def set_common_name_override(
        self,
        scientific_name: str,
        common_name: str,
        db: aiosqlite.Connection,
    ) -> Optional[Dict[str, Optional[str]]]:
        """Set a manual name without replacing provider-owned taxonomy data."""
        cursor = await db.execute(
            """UPDATE taxonomy_cache SET manual_common_name = ?
               WHERE LOWER(scientific_name) = LOWER(?) AND is_not_found = 0""",
            (common_name, scientific_name),
        )
        try:
            if cursor.rowcount == 0:
                return None
        finally:
            await cursor.close()
        return await self.get_common_name_override(scientific_name, db)

    async def clear_common_name_override(
        self, scientific_name: str, db: aiosqlite.Connection
    ) -> Optional[Dict[str, Optional[str]]]:
        """Clear a manual name and expose the provider value again."""
        cursor = await db.execute(
            """UPDATE taxonomy_cache SET manual_common_name = NULL
               WHERE LOWER(scientific_name) = LOWER(?) AND is_not_found = 0""",
            (scientific_name,),
        )
        try:
            if cursor.rowcount == 0:
                return None
        finally:
            await cursor.close()
        return await self.get_common_name_override(scientific_name, db)

    async def get_localized_common_name(
        self, taxa_id: int, lang: str, db: Optional[aiosqlite.Connection] = None
    ) -> Optional[str]:
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

    async def _get_translation_from_cache(
        self, taxa_id: int, lang: str, db: Optional[aiosqlite.Connection] = None
    ) -> Optional[str]:
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
            "SELECT common_name FROM taxonomy_translations WHERE taxa_id = ? AND language_code = ?", (taxa_id, lang)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
        return None

    async def _save_translation_to_cache(
        self, taxa_id: int, lang: str, common_name: str, db: Optional[aiosqlite.Connection] = None
    ):
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
            (taxa_id, lang, common_name),
        )

    async def _lookup_localized_inaturalist(self, taxa_id: int, lang: str) -> Optional[str]:
        """Query the iNaturalist API for a specific taxon and locale."""
        try:
            url = f"{self.API_URL}/{taxa_id}"
            params = {"locale": lang}

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

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


taxonomy_service = TaxonomyService()
