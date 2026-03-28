import re
from datetime import datetime
from typing import Optional

import aiosqlite
import structlog

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.services.taxonomy.taxonomy_service import taxonomy_service


log = structlog.get_logger()


class CanonicalIdentityRepairService:
    _REPAIR_CANDIDATE_WHERE = """
        (
            scientific_name IS NULL
            OR common_name IS NULL
            OR taxa_id IS NULL
        )
    """

    def __init__(self) -> None:
        self._unknown_labels = {
            "unknown bird",
            *(
                str(label).strip().lower()
                for label in (settings.classification.unknown_bird_labels or [])
                if str(label).strip()
            ),
        }
        self._status = {
            "is_running": False,
            "processed": 0,
            "total": 0,
            "current_item": None,
            "error": None,
        }

    def get_status(self) -> dict:
        return dict(self._status)

    def _lookup_candidates(self, row: dict) -> list[str]:
        candidates: list[str] = []
        for raw in (row.get("scientific_name"), row.get("category_name"), row.get("display_name")):
            if not isinstance(raw, str):
                continue
            normalized = raw.strip()
            if not normalized or normalized.lower() in self._unknown_labels:
                continue
            if normalized not in candidates:
                candidates.append(normalized)
            match = re.match(r"^(.*?)\s*\((.*?)\)\s*$", normalized)
            if match:
                for group in (match.group(1).strip(), match.group(2).strip()):
                    if group and group.lower() not in self._unknown_labels and group not in candidates:
                        candidates.append(group)
        return candidates

    @staticmethod
    def _candidate_improves(row: dict, taxonomy: dict) -> bool:
        if not taxonomy:
            return False

        candidate_taxa = taxonomy.get("taxa_id")
        candidate_sci = str(taxonomy.get("scientific_name") or "").strip()
        current_taxa = row.get("taxa_id")
        current_sci = str(row.get("scientific_name") or "").strip()

        if current_taxa is not None and candidate_taxa is not None and current_taxa != candidate_taxa:
            return False
        if current_sci and candidate_sci and current_sci.lower() != candidate_sci.lower():
            return False

        return (
            (not current_sci and bool(candidate_sci))
            or (not row.get("common_name") and bool(taxonomy.get("common_name")))
            or (current_taxa is None and candidate_taxa is not None)
        )

    async def _fetch_batch(
        self,
        db: aiosqlite.Connection,
        *,
        batch_size: int,
        skipped_ids: set[int],
    ) -> list[dict]:
        params: list = []
        query = f"""
            SELECT id, display_name, category_name, scientific_name, common_name, taxa_id
            FROM detections
            WHERE {self._REPAIR_CANDIDATE_WHERE}
        """
        if skipped_ids:
            placeholders = ",".join(["?"] * len(skipped_ids))
            query += f" AND id NOT IN ({placeholders})"
            params.extend(sorted(skipped_ids))
        query += """
            ORDER BY detection_time ASC, id ASC
            LIMIT ?
        """
        params.append(batch_size)
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [
            {
                "id": row[0],
                "display_name": row[1],
                "category_name": row[2],
                "scientific_name": row[3],
                "common_name": row[4],
                "taxa_id": row[5],
            }
            for row in rows
        ]

    async def _count_candidates(self, db: aiosqlite.Connection) -> int:
        async with db.execute(
            f"""
            SELECT COUNT(*)
            FROM detections
            WHERE {self._REPAIR_CANDIDATE_WHERE}
            """
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0] or 0) if row else 0

    async def _resolve_taxonomy(self, repo: DetectionRepository, db: aiosqlite.Connection, row: dict) -> dict:
        for candidate in self._lookup_candidates(row):
            cached = await repo.get_taxonomy_names(candidate)
            if self._candidate_improves(row, cached):
                return cached
            fetched = await taxonomy_service.get_names(candidate, db=db)
            if self._candidate_improves(row, fetched):
                return fetched
        return {}

    async def _update_row(self, db: aiosqlite.Connection, row: dict, taxonomy: dict) -> bool:
        assignments: list[str] = []
        params: list[object] = []

        candidate_sci = str(taxonomy.get("scientific_name") or "").strip()
        if not row.get("scientific_name") and candidate_sci:
            assignments.append("scientific_name = ?")
            params.append(candidate_sci)

        candidate_common = str(taxonomy.get("common_name") or "").strip()
        if candidate_common and not row.get("common_name"):
            assignments.append("common_name = ?")
            params.append(candidate_common)

        candidate_taxa = taxonomy.get("taxa_id")
        if row.get("taxa_id") is None and candidate_taxa is not None:
            assignments.append("taxa_id = ?")
            params.append(candidate_taxa)

        if not assignments:
            return False

        await db.execute(
            f"""
            UPDATE detections
            SET {", ".join(assignments)}
            WHERE id = ?
            """,
            [*params, int(row["id"])],
        )
        return True

    async def _rebuild_rollups(self, repo: DetectionRepository, db: aiosqlite.Connection) -> int:
        oldest = await repo.get_oldest_detection_date()
        if oldest is None:
            return 0
        return await repo.rebuild_all_rollups(oldest.date(), datetime.utcnow().date())

    async def run(
        self,
        *,
        db: Optional[aiosqlite.Connection] = None,
        batch_size: int = 200,
    ) -> dict:
        own_connection = db is None
        if own_connection:
            async with get_db() as owned_db:
                return await self.run(db=owned_db, batch_size=batch_size)

        repo = DetectionRepository(db)
        processed = 0
        updated = 0
        skipped_ids: set[int] = set()
        self._status = {
            "is_running": True,
            "processed": 0,
            "total": await self._count_candidates(db),
            "current_item": None,
            "error": None,
        }

        try:
            while True:
                rows = await self._fetch_batch(db, batch_size=batch_size, skipped_ids=skipped_ids)
                if not rows:
                    break

                batch_updated = 0
                for row in rows:
                    self._status["current_item"] = (
                        row.get("scientific_name")
                        or row.get("category_name")
                        or row.get("display_name")
                        or f"id:{row.get('id')}"
                    )
                    if not self._lookup_candidates(row):
                        skipped_ids.add(int(row["id"]))
                        processed += 1
                        self._status["processed"] = processed
                        continue

                    taxonomy = await self._resolve_taxonomy(repo, db, row)
                    if self._candidate_improves(row, taxonomy):
                        row_updated = await self._update_row(db, row, taxonomy)
                        if row_updated:
                            batch_updated += 1
                            updated += 1
                    else:
                        skipped_ids.add(int(row["id"]))
                    processed += 1
                    self._status["processed"] = processed

                await db.commit()
                log.info(
                    "canonical_identity_repair_batch",
                    batch_size=len(rows),
                    batch_updated=batch_updated,
                    processed=processed,
                    updated=updated,
                )
                if batch_updated == 0 and len(rows) < batch_size:
                    break

            rollups_rebuilt = await self._rebuild_rollups(repo, db)
            summary = {
                "processed": processed,
                "updated": updated,
                "rollups_rebuilt": rollups_rebuilt,
            }
            self._status["current_item"] = "Completed"
            log.info("canonical_identity_repair_complete", **summary)
            return summary
        except Exception as exc:
            self._status["error"] = str(exc)
            raise
        finally:
            self._status["is_running"] = False


canonical_identity_repair_service = CanonicalIdentityRepairService()
