"""Persistence operations for species taxonomy, search, and information caches."""

from datetime import datetime

import aiosqlite


class SpeciesRepository:
    """Own SQL used by the species HTTP surface."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def lookup_taxonomy(self, candidate: str, language: str) -> tuple[str | None, str | None, int | None] | None:
        async with self.db.execute(
            """SELECT scientific_name, COALESCE(manual_common_name, common_name), taxa_id,
                      manual_common_name FROM taxonomy_cache
               WHERE LOWER(scientific_name) = LOWER(?) OR LOWER(common_name) = LOWER(?)
                  OR LOWER(manual_common_name) = LOWER(?) LIMIT 1""",
            (candidate, candidate, candidate),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        scientific_name, common_name, taxa_id, manual_common_name = row
        if language != "en" and taxa_id and not manual_common_name:
            async with self.db.execute(
                "SELECT common_name FROM taxonomy_translations WHERE taxa_id = ? AND language_code = ?",
                (taxa_id, language),
            ) as cursor:
                translated = await cursor.fetchone()
            if translated and translated[0]:
                common_name = translated[0]
        return scientific_name, common_name, taxa_id

    async def get_cached_info(self, *, species_name: str, taxa_id: int | None, language: str) -> aiosqlite.Row | None:
        columns = """title, description, extract, thumbnail_url, wikipedia_url, source, source_url,
                     summary_source, summary_source_url, scientific_name, conservation_status, cached_at, taxa_id"""
        if taxa_id:
            cursor = await self.db.execute(
                f"SELECT {columns} FROM species_info_cache WHERE taxa_id = ? AND language = ? ORDER BY cached_at DESC LIMIT 1",
                (taxa_id, language),
            )
        else:
            cursor = await self.db.execute(
                f"SELECT {columns} FROM species_info_cache WHERE species_name = ? AND language = ?",
                (species_name, language),
            )
        try:
            return await cursor.fetchone()
        finally:
            await cursor.close()

    async def save_cached_info(
        self,
        *,
        species_name: str,
        taxa_id: int | None,
        language: str,
        values: dict[str, object],
        cached_at: datetime,
    ) -> None:
        existing = None
        if taxa_id:
            cursor = await self.db.execute(
                "SELECT id FROM species_info_cache WHERE taxa_id = ? AND language = ? LIMIT 1", (taxa_id, language)
            )
            existing = await cursor.fetchone()
            await cursor.close()

        payload = (
            species_name,
            language,
            values.get("title"),
            taxa_id,
            values.get("description"),
            values.get("extract"),
            values.get("thumbnail_url"),
            values.get("wikipedia_url"),
            values.get("source"),
            values.get("source_url"),
            values.get("summary_source"),
            values.get("summary_source_url"),
            values.get("scientific_name"),
            values.get("conservation_status"),
            cached_at,
        )
        if existing:
            cursor = await self.db.execute(
                "SELECT id FROM species_info_cache WHERE species_name = ? AND language = ? LIMIT 1",
                (species_name, language),
            )
            name_row = await cursor.fetchone()
            await cursor.close()
            if name_row and name_row[0] != existing[0]:
                await self.db.execute("DELETE FROM species_info_cache WHERE id = ?", (name_row[0],))
            await self.db.execute(
                """UPDATE species_info_cache SET species_name=?, language=?, title=?, taxa_id=?, description=?,
                   extract=?, thumbnail_url=?, wikipedia_url=?, source=?, source_url=?, summary_source=?,
                   summary_source_url=?, scientific_name=?, conservation_status=?, cached_at=? WHERE id=?""",
                (*payload, existing[0]),
            )
        else:
            await self.db.execute(
                """INSERT INTO species_info_cache
                   (species_name, language, title, taxa_id, description, extract, thumbnail_url, wikipedia_url,
                    source, source_url, summary_source, summary_source_url, scientific_name, conservation_status, cached_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(species_name, language) DO UPDATE SET language=excluded.language,
                    title=excluded.title, taxa_id=excluded.taxa_id, description=excluded.description,
                    extract=excluded.extract, thumbnail_url=excluded.thumbnail_url,
                    wikipedia_url=excluded.wikipedia_url, source=excluded.source, source_url=excluded.source_url,
                    summary_source=excluded.summary_source, summary_source_url=excluded.summary_source_url,
                    scientific_name=excluded.scientific_name, conservation_status=excluded.conservation_status,
                    cached_at=excluded.cached_at""",
                payload,
            )
        await self.db.commit()

    async def search_labels(self, query: str, language: str) -> list[str]:
        pattern = f"%{query.casefold()}%"
        labels: list[str] = []
        async with self.db.execute(
            """SELECT scientific_name, COALESCE(manual_common_name, common_name)
               FROM taxonomy_cache WHERE LOWER(scientific_name) LIKE ?
                  OR LOWER(common_name) LIKE ? OR LOWER(manual_common_name) LIKE ?""",
            (pattern, pattern, pattern),
        ) as cursor:
            for row in await cursor.fetchall():
                labels.extend(value for value in row if value)
        if language != "en":
            async with self.db.execute(
                """SELECT tc.scientific_name, COALESCE(tc.manual_common_name, tc.common_name)
                   FROM taxonomy_translations tt
                   JOIN taxonomy_cache tc ON tc.taxa_id = tt.taxa_id
                   WHERE tt.language_code = ? AND LOWER(tt.common_name) LIKE ?""",
                (language, pattern),
            ) as cursor:
                for row in await cursor.fetchall():
                    labels.extend(value for value in row if value)
        async with self.db.execute(
            """SELECT DISTINCT display_name, category_name, scientific_name, common_name FROM detections
               WHERE is_hidden = 0 AND (LOWER(COALESCE(display_name,'')) LIKE ?
                 OR LOWER(COALESCE(category_name,'')) LIKE ? OR LOWER(COALESCE(scientific_name,'')) LIKE ?
                 OR LOWER(COALESCE(common_name,'')) LIKE ?)""",
            (pattern, pattern, pattern, pattern),
        ) as cursor:
            for row in await cursor.fetchall():
                labels.extend(value for value in row if value)
        return labels

    async def clear_cached_info(self, species_name: str, taxa_id: int | None) -> None:
        if taxa_id:
            await self.db.execute(
                "DELETE FROM species_info_cache WHERE species_name = ? OR taxa_id = ?", (species_name, taxa_id)
            )
        else:
            await self.db.execute("DELETE FROM species_info_cache WHERE species_name = ?", (species_name,))
        await self.db.commit()
