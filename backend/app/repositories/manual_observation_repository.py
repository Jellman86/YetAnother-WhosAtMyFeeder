from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime

import aiosqlite

from app.utils.api_datetime import utc_naive_now


@dataclass(slots=True)
class ManualObservationDraft:
    id: str
    status: str
    media_type: str
    original_filename: str
    content_type: str
    content_sha256: str
    size_bytes: int
    source_filename: str
    progress_current: int = 0
    progress_total: int = 0
    progress_message: str | None = None
    results: list[dict] | None = None
    error_code: str | None = None
    error_message: str | None = None
    saved_event_id: str | None = None
    notes: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_source: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ManualObservationRepository:
    _COLUMNS = """id, status, media_type, original_filename, content_type, content_sha256,
        size_bytes, source_filename, progress_current, progress_total, progress_message,
        results_json, error_code, error_message, saved_event_id, notes, latitude, longitude,
        location_source, created_at, updated_at"""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    @staticmethod
    def _from_row(row: tuple) -> ManualObservationDraft:
        return ManualObservationDraft(
            id=row[0],
            status=row[1],
            media_type=row[2],
            original_filename=row[3],
            content_type=row[4],
            content_sha256=row[5],
            size_bytes=int(row[6]),
            source_filename=row[7],
            progress_current=int(row[8] or 0),
            progress_total=int(row[9] or 0),
            progress_message=row[10],
            results=json.loads(row[11]) if row[11] else None,
            error_code=row[12],
            error_message=row[13],
            saved_event_id=row[14],
            notes=row[15],
            latitude=float(row[16]) if row[16] is not None else None,
            longitude=float(row[17]) if row[17] is not None else None,
            location_source=row[18],
            created_at=datetime.fromisoformat(row[19]) if isinstance(row[19], str) else row[19],
            updated_at=datetime.fromisoformat(row[20]) if isinstance(row[20], str) else row[20],
        )

    async def create(self, draft: ManualObservationDraft) -> None:
        now = utc_naive_now()
        await self.db.execute(
            """INSERT INTO manual_observation_drafts (
                id, status, media_type, original_filename, content_type, content_sha256,
                size_bytes, source_filename, progress_current, progress_total, latitude, longitude,
                location_source, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                draft.id,
                draft.status,
                draft.media_type,
                draft.original_filename,
                draft.content_type,
                draft.content_sha256,
                draft.size_bytes,
                draft.source_filename,
                draft.progress_current,
                draft.progress_total,
                draft.latitude,
                draft.longitude,
                draft.location_source,
                now,
                now,
            ),
        )
        await self.db.commit()

    async def get(self, draft_id: str) -> ManualObservationDraft | None:
        async with self.db.execute(
            f"SELECT {self._COLUMNS} FROM manual_observation_drafts WHERE id = ?", (draft_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return self._from_row(row) if row else None

    async def get_by_hash(self, content_sha256: str) -> ManualObservationDraft | None:
        async with self.db.execute(
            f"SELECT {self._COLUMNS} FROM manual_observation_drafts WHERE content_sha256 = ?", (content_sha256,)
        ) as cursor:
            row = await cursor.fetchone()
        return self._from_row(row) if row else None

    async def get_by_event_id(self, event_id: str) -> ManualObservationDraft | None:
        async with self.db.execute(
            f"SELECT {self._COLUMNS} FROM manual_observation_drafts WHERE saved_event_id = ?", (event_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return self._from_row(row) if row else None

    async def list_expired_unsaved_ids(self, cutoff: datetime) -> list[str]:
        async with self.db.execute(
            """SELECT id FROM manual_observation_drafts
               WHERE saved_event_id IS NULL AND updated_at < ?""",
            (cutoff,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def metadata_by_event_ids(self, event_ids: list[str]) -> dict[str, dict[str, object]]:
        ids = [event_id for event_id in event_ids if event_id.startswith("manual_")]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        async with self.db.execute(
            f"""SELECT saved_event_id, notes, latitude, longitude, location_source
                FROM manual_observation_drafts WHERE saved_event_id IN ({placeholders})""",
            ids,
        ) as cursor:
            rows = await cursor.fetchall()
        return {
            str(row[0]): {
                "notes": str(row[1]) if row[1] else None,
                "latitude": float(row[2]) if row[2] is not None else None,
                "longitude": float(row[3]) if row[3] is not None else None,
                "location_source": str(row[4]) if row[4] else None,
            }
            for row in rows
            if row[0]
        }

    async def update_progress(self, draft_id: str, current: int, total: int, message: str | None = None) -> None:
        await self.db.execute(
            """UPDATE manual_observation_drafts SET progress_current = ?, progress_total = ?,
               progress_message = ?, updated_at = ? WHERE id = ?""",
            (max(0, current), max(0, total), message, utc_naive_now(), draft_id),
        )
        await self.db.commit()

    async def mark_analyzing(self, draft_id: str) -> None:
        await self.db.execute(
            """UPDATE manual_observation_drafts SET status = 'analyzing', error_code = NULL,
               error_message = NULL, progress_current = 0, progress_total = 0, updated_at = ? WHERE id = ?""",
            (utc_naive_now(), draft_id),
        )
        await self.db.commit()

    async def mark_ready(self, draft_id: str, results: list[dict]) -> None:
        await self.db.execute(
            """UPDATE manual_observation_drafts SET status = 'ready', results_json = ?,
               progress_current = CASE WHEN progress_total > 0 THEN progress_total ELSE 1 END,
               progress_total = CASE WHEN progress_total > 0 THEN progress_total ELSE 1 END,
               progress_message = NULL, updated_at = ? WHERE id = ?""",
            (json.dumps(results), utc_naive_now(), draft_id),
        )
        await self.db.commit()

    async def mark_failed(self, draft_id: str, code: str, message: str) -> None:
        await self.db.execute(
            """UPDATE manual_observation_drafts SET status = 'failed', error_code = ?,
               error_message = ?, progress_message = NULL, updated_at = ? WHERE id = ?""",
            (code, message[:500], utc_naive_now(), draft_id),
        )
        await self.db.commit()

    async def mark_saved(
        self,
        draft_id: str,
        event_id: str,
        notes: str | None,
        *,
        latitude: float | None,
        longitude: float | None,
        location_source: str | None,
    ) -> None:
        await self.db.execute(
            """UPDATE manual_observation_drafts SET status = 'saved', saved_event_id = ?, notes = ?,
               latitude = ?, longitude = ?, location_source = ?, updated_at = ? WHERE id = ?""",
            (event_id, notes, latitude, longitude, location_source, utc_naive_now(), draft_id),
        )
        await self.db.commit()

    async def delete(self, draft_id: str) -> bool:
        cursor = await self.db.execute("DELETE FROM manual_observation_drafts WHERE id = ?", (draft_id,))
        await self.db.commit()
        return bool(cursor.rowcount)
