"""Persistence operations for eBird export data."""

from collections.abc import AsyncIterator
from datetime import datetime

import aiosqlite


class EbirdRepository:
    """Read detection rows used to build an eBird spreadsheet export."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def iter_export_rows(
        self, *, start: datetime | None, end_exclusive: datetime | None
    ) -> AsyncIterator[aiosqlite.Row]:
        clauses: list[str] = []
        params: list[datetime] = []
        if start is not None:
            clauses.append("d.detection_time >= ?")
            params.append(start)
        if end_exclusive is not None:
            clauses.append("d.detection_time < ?")
            params.append(end_exclusive)
        date_clause = f" AND {' AND '.join(clauses)}" if clauses else ""

        async with self.db.execute(
            f"""
            SELECT d.display_name, d.scientific_name, d.detection_time, d.score,
                   d.camera_name, d.common_name, d.video_classification_provider,
                   d.video_classification_backend,
                   COALESCE(
                     (SELECT tt.common_name FROM taxonomy_translations tt
                      WHERE d.taxa_id IS NOT NULL AND tt.taxa_id = d.taxa_id
                        AND tt.language_code = 'en' LIMIT 1),
                     (SELECT tt.common_name FROM taxonomy_translations tt
                      JOIN taxonomy_cache tc ON tc.taxa_id = tt.taxa_id
                      WHERE d.scientific_name IS NOT NULL
                        AND LOWER(tc.scientific_name) = LOWER(d.scientific_name)
                        AND tt.language_code = 'en' LIMIT 1),
                     (SELECT tc.common_name FROM taxonomy_cache tc
                      WHERE d.scientific_name IS NOT NULL
                        AND LOWER(tc.scientific_name) = LOWER(d.scientific_name)
                        AND LOWER(tc.common_name) != LOWER(tc.scientific_name)
                      ORDER BY tc.id ASC LIMIT 1),
                     (SELECT tc.common_name FROM taxonomy_cache tc
                      WHERE d.taxa_id IS NOT NULL AND tc.taxa_id = d.taxa_id
                        AND LOWER(tc.common_name) != LOWER(tc.scientific_name)
                      ORDER BY tc.id ASC LIMIT 1)
                   ) AS english_common_name
            FROM detections d
            WHERE d.is_hidden = 0
            {date_clause}
            ORDER BY d.detection_time DESC
            """,
            params,
        ) as cursor:
            async for row in cursor:
                yield row
