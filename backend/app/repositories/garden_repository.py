"""Garden review storage has no dependency on bird history or species totals."""

from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Literal
import uuid

import aiosqlite

from app.utils.api_datetime import utc_naive_now
from app.models.garden import GardenIdentification


GardenStatus = Literal["pending", "confirmed", "dismissed"]


@dataclass(frozen=True)
class GardenCapture:
    id: str
    frigate_event: str
    camera: str
    label: str
    observed_at: str
    status: GardenStatus
    has_snapshot: bool
    reviewed_at: str | None
    identification: GardenIdentification | None = None


class GardenRepository:
    _COLUMNS = """id, frigate_event, camera, label, observed_at, status, has_snapshot, reviewed_at,
        (SELECT result_json FROM garden_identifications WHERE capture_id = garden_captures.id)"""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    @staticmethod
    def _key(event_id: str) -> str:
        return hashlib.sha256(event_id.encode()).hexdigest()

    @staticmethod
    def _capture(row: tuple) -> GardenCapture:
        return GardenCapture(
            *row[:6], bool(row[6]), row[7], GardenIdentification.model_validate_json(row[8]) if row[8] else None
        )

    async def has_history(self) -> bool:
        async with self.db.execute("SELECT 1 FROM garden_captures LIMIT 1") as cursor:
            return await cursor.fetchone() is not None

    async def capture(self, event_id: str, camera: str, label: str, observed_at: str, has_snapshot: bool) -> None:
        await self.db.execute(
            """INSERT INTO garden_captures (id, event_key, frigate_event, camera, label, observed_at, status, has_snapshot)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?) ON CONFLICT(event_key) DO NOTHING""",
            (uuid.uuid4().hex, self._key(event_id), event_id, camera, label, observed_at, has_snapshot),
        )
        await self.db.commit()

    async def block(self, event_id: str, *, create: bool) -> None:
        await self.db.execute(
            "DELETE FROM garden_identifications WHERE capture_id IN (SELECT id FROM garden_captures WHERE event_key=?)",
            (self._key(event_id),),
        )
        if create:
            await self.db.execute(
                """INSERT INTO garden_captures (id, event_key, camera, label, observed_at, status, has_snapshot)
                   VALUES (?, ?, '', '', ?, 'blocked', 0) ON CONFLICT(event_key) DO NOTHING""",
                (uuid.uuid4().hex, self._key(event_id), utc_naive_now().isoformat()),
            )
        # A hashed tombstone stops delayed delivery resurrecting rejected media.
        await self.db.execute(
            """UPDATE garden_captures SET frigate_event = NULL, camera = '', label = '', status = 'blocked',
               has_snapshot = 0, reviewed_at = NULL WHERE event_key = ?""",
            (self._key(event_id),),
        )
        await self.db.commit()

    async def get(self, capture_id: str) -> GardenCapture | None:
        async with self.db.execute(
            f"SELECT {self._COLUMNS} FROM garden_captures WHERE id = ? AND status != 'blocked'",
            (capture_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return self._capture(row) if row else None

    async def list(self, status: GardenStatus, limit: int, offset: int) -> list[GardenCapture]:
        async with self.db.execute(
            f"SELECT {self._COLUMNS} FROM garden_captures WHERE status = ? ORDER BY observed_at DESC, id DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        ) as cursor:
            return [self._capture(row) for row in await cursor.fetchall()]

    async def count(self, status: GardenStatus) -> int:
        async with self.db.execute("SELECT COUNT(*) FROM garden_captures WHERE status = ?", (status,)) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def review(self, capture_id: str, status: GardenStatus) -> GardenCapture | None:
        if status != "confirmed":
            await self.db.execute(
                "UPDATE garden_identifications SET result_json=json_set(result_json,'$.review','dismissed') WHERE capture_id=?",
                (capture_id,),
            )
        await self.db.execute(
            "UPDATE garden_captures SET status = ?, reviewed_at = ? WHERE id = ? AND status != 'blocked'",
            (status, utc_naive_now().isoformat() if status != "pending" else None, capture_id),
        )
        await self.db.commit()
        return await self.get(capture_id)

    async def delete_older_than(self, cutoff: datetime) -> None:
        await self.db.execute(
            "DELETE FROM garden_identifications WHERE capture_id IN (SELECT id FROM garden_captures WHERE observed_at < ?)",
            (cutoff.replace(tzinfo=None).isoformat(),),
        )
        await self.db.execute(
            "DELETE FROM garden_captures WHERE observed_at < ?", (cutoff.replace(tzinfo=None).isoformat(),)
        )
        await self.db.commit()

    async def save_identification(self, original: GardenCapture, result: GardenIdentification) -> bool:
        cursor = await self.db.execute(
            """INSERT INTO garden_identifications(capture_id,result_json)
               SELECT id, ? FROM garden_captures WHERE id=? AND status=? AND reviewed_at IS ?
               AND status = 'confirmed'
               AND json((SELECT result_json FROM garden_identifications WHERE capture_id=id)) IS json(?)
               ON CONFLICT(capture_id) DO UPDATE SET result_json=excluded.result_json
               WHERE json_extract(garden_identifications.result_json,'$.review') != 'accepted'""",
            (
                result.model_dump_json(),
                original.id,
                original.status,
                original.reviewed_at,
                original.identification.model_dump_json() if original.identification else None,
            ),
        )
        await self.db.commit()
        return cursor.rowcount > 0

    async def review_identification(
        self,
        capture_id: str,
        action: Literal["accepted", "dismissed"],
        *,
        expected_image_sha256: str | None = None,
        expected: GardenIdentification | None = None,
    ) -> bool:
        cursor = await self.db.execute(
            """UPDATE garden_identifications SET result_json=json_set(result_json,'$.review',?)
               WHERE capture_id=? AND EXISTS (SELECT 1 FROM garden_captures WHERE id=capture_id AND status='confirmed')
               AND (? IS NULL OR json_extract(result_json,'$.image_sha256')=?)
               AND (? IS NULL OR json(result_json)=json(?))
               AND ( ?='dismissed' OR (json_extract(result_json,'$.outcome')='suggestion'
                 AND json_extract(result_json,'$.review')='unreviewed'))""",
            (
                action,
                capture_id,
                expected_image_sha256,
                expected_image_sha256,
                expected.model_dump_json() if expected else None,
                expected.model_dump_json() if expected else None,
                action,
            ),
        )
        await self.db.commit()
        return cursor.rowcount > 0
