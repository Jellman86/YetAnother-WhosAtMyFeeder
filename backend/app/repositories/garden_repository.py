"""Garden review storage has no dependency on bird history or species totals."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import suppress
from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3
from typing import Literal
import uuid

import aiosqlite

from app.utils.api_datetime import utc_naive_now
from app.models.garden import GardenIdentification, GardenAutomaticCheck
from app.models.garden_motion import MotionSource, MOTION_PADDING_SECONDS

MOTION_PHOTO_LIMIT = 128
MOTION_PHOTO_BYTES = 512 * 1024


GardenStatus = Literal["pending", "confirmed", "dismissed"]
# What the Explorer can ask for: its default view of animals, or one review state.
GardenTimelineStatus = Literal["reviewable", "pending", "confirmed", "dismissed"]


class GardenPhotoUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class GardenCapture:
    id: str
    frigate_event: str | None
    camera: str
    label: str
    observed_at: str
    status: GardenStatus
    has_snapshot: bool
    reviewed_at: str | None
    identification: GardenIdentification | None = None
    motion_source: MotionSource | None = None
    automatic_check: GardenAutomaticCheck | None = None
    automation_overridden: bool = False


class GardenRepository:
    _PHOTO_AVAILABLE = """CASE WHEN EXISTS (SELECT 1 FROM garden_motion_sources WHERE capture_id=garden_captures.id)
          THEN (SELECT image IS NOT NULL AND expires_at > strftime('%Y-%m-%dT%H:%M:%f','now')
                FROM garden_motion_sources WHERE capture_id=garden_captures.id)
          ELSE has_snapshot END"""
    _COLUMNS = f"""id, frigate_event, camera, label, observed_at, status,
        {_PHOTO_AVAILABLE}, reviewed_at,
        (SELECT result_json FROM garden_identifications WHERE capture_id = garden_captures.id),
        (SELECT source_json FROM garden_motion_sources WHERE capture_id=garden_captures.id),
        (SELECT result_json FROM garden_automatic_checks WHERE capture_id=garden_captures.id),
        automation_overridden"""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    @staticmethod
    def _key(event_id: str) -> str:
        return hashlib.sha256(event_id.encode()).hexdigest()

    @staticmethod
    def _capture(row: tuple) -> GardenCapture:
        return GardenCapture(
            *row[:6],
            bool(row[6]),
            row[7],
            GardenIdentification.model_validate_json(row[8]) if row[8] else None,
            MotionSource.model_validate_json(row[9]) if row[9] else None,
            GardenAutomaticCheck.model_validate_json(row[10]) if row[10] else None,
            bool(row[11]),
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
            "DELETE FROM garden_automatic_checks WHERE capture_id IN (SELECT id FROM garden_captures WHERE event_key=?)",
            (self._key(event_id),),
        )
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
        available = f" AND ({self._PHOTO_AVAILABLE})" if status == "pending" else ""
        async with self.db.execute(
            f"SELECT {self._COLUMNS} FROM garden_captures WHERE status = ?{available} ORDER BY observed_at DESC, id DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        ) as cursor:
            return [self._capture(row) for row in await cursor.fetchall()]

    async def count(self, status: GardenStatus) -> int:
        available = f" AND ({self._PHOTO_AVAILABLE})" if status == "pending" else ""
        async with self.db.execute(
            f"SELECT COUNT(*) FROM garden_captures WHERE status = ?{available}", (status,)
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    def _timeline_filter(
        self, start: datetime | None, end: datetime | None, camera: str | None, status: GardenTimelineStatus
    ) -> tuple[str, list[str]]:
        # A pending capture without a photo cannot be reviewed, as on the review list.
        reviewable_pending = f"(status = 'pending' AND ({self._PHOTO_AVAILABLE}))"
        clauses = [
            {
                "reviewable": f"(status = 'confirmed' OR {reviewable_pending})",
                "pending": reviewable_pending,
                "confirmed": "status = 'confirmed'",
                "dismissed": "status = 'dismissed'",
            }[status]
        ]
        values: list[str] = []
        if start is not None:
            clauses.append("observed_at >= ?")
            values.append(start.astimezone(timezone.utc).replace(tzinfo=None).isoformat())
        if end is not None:
            clauses.append("observed_at <= ?")
            values.append(end.astimezone(timezone.utc).replace(tzinfo=None).isoformat())
        if camera:
            clauses.append("camera = ?")
            values.append(camera)
        return " AND ".join(clauses), values

    async def timeline(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
        camera: str | None,
        newest_first: bool,
        limit: int,
        offset: int,
        status: GardenTimelineStatus = "reviewable",
    ) -> list[GardenCapture]:
        """Captures the Explorer shows: by default confirmed animals and those awaiting review."""
        where, values = self._timeline_filter(start, end, camera, status)
        direction = "DESC" if newest_first else "ASC"
        async with self.db.execute(
            f"SELECT {self._COLUMNS} FROM garden_captures WHERE {where} "
            f"ORDER BY observed_at {direction}, id {direction} LIMIT ? OFFSET ?",
            (*values, limit, offset),
        ) as cursor:
            return [self._capture(row) for row in await cursor.fetchall()]

    async def timeline_count(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
        camera: str | None,
        status: GardenTimelineStatus = "reviewable",
    ) -> int:
        where, values = self._timeline_filter(start, end, camera, status)
        async with self.db.execute(f"SELECT COUNT(*) FROM garden_captures WHERE {where}", values) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def review(self, capture_id: str, status: GardenStatus) -> GardenCapture | None:
        # The write lock checks photo availability against concurrent reclamation.
        updated = await self.db.execute(
            f"""UPDATE garden_captures SET status = ?, reviewed_at = ?, automation_overridden=1
               WHERE id = ? AND status != 'blocked' AND (? = 'dismissed' OR ({self._PHOTO_AVAILABLE}))""",
            (
                status,
                utc_naive_now().isoformat() if status != "pending" else None,
                capture_id,
                status,
            ),
        )
        if not updated.rowcount:
            await self.db.rollback()
            if await self.get(capture_id):
                raise GardenPhotoUnavailable("This capture has no available photo. Refresh to review a newer capture.")
            return None
        if status != "confirmed":
            await self.db.execute(
                "UPDATE garden_identifications SET result_json=json_set(result_json,'$.review','dismissed') WHERE capture_id=?",
                (capture_id,),
            )
        await self.db.commit()
        return await self.get(capture_id)

    async def review_batch(self, ids: list[str], action: Literal["dismiss", "restore"]) -> list[str]:
        if not 1 <= len(ids) <= 128:
            raise ValueError("Batch review requires 1 to 128 explicit capture IDs")
        status, previous = ("dismissed", "pending") if action == "dismiss" else ("pending", "dismissed")
        placeholders = ",".join("?" for _ in ids)
        available = f" AND ({self._PHOTO_AVAILABLE})" if action == "restore" else ""
        # The expected status protects another owner's review and the explicit
        # ID set excludes captures collected after the page was loaded.
        async with self.db.execute(
            f"""UPDATE garden_captures SET status=?,reviewed_at=?,automation_overridden=1
                WHERE id IN ({placeholders}) AND status=?{available} RETURNING id""",
            (status, utc_naive_now().isoformat() if action == "dismiss" else None, *ids, previous),
        ) as cursor:
            updated = {row[0] for row in await cursor.fetchall()}
        if updated:
            changed = ",".join("?" for _ in updated)
            await self.db.execute(
                f"""UPDATE garden_identifications SET result_json=json_set(result_json,'$.review','dismissed')
                    WHERE capture_id IN ({changed})""",
                list(updated),
            )
        await self.db.commit()
        return [capture_id for capture_id in ids if capture_id in updated]

    async def delete_older_than(self, cutoff: datetime) -> None:
        await self.db.execute(
            "DELETE FROM garden_automatic_checks WHERE capture_id IN (SELECT id FROM garden_captures WHERE observed_at < ?)",
            (cutoff.replace(tzinfo=None).isoformat(),),
        )
        await self.db.execute(
            "DELETE FROM garden_motion_sources WHERE capture_id IN (SELECT id FROM garden_captures WHERE observed_at < ?)",
            (cutoff.replace(tzinfo=None).isoformat(),),
        )
        await self.db.execute(
            "DELETE FROM garden_identifications WHERE capture_id IN (SELECT id FROM garden_captures WHERE observed_at < ?)",
            (cutoff.replace(tzinfo=None).isoformat(),),
        )
        await self.db.execute(
            "DELETE FROM garden_captures WHERE observed_at < ?", (cutoff.replace(tzinfo=None).isoformat(),)
        )
        await self.db.commit()

    async def capture_motion(self, source: MotionSource, image: bytes) -> str | None:
        if not image or len(image) > MOTION_PHOTO_BYTES or hashlib.sha256(image).hexdigest() != source.image_sha256:
            raise ValueError("Motion photo exceeds its limit or differs from its evidence checksum")
        capture_id = uuid.uuid4().hex
        observed = datetime.fromtimestamp(source.clip_start + source.frame_offset, timezone.utc).replace(tzinfo=None)
        expires = datetime.fromtimestamp(source.clip_end, timezone.utc).replace(tzinfo=None) + timedelta(days=3)
        await self.db.execute("SAVEPOINT garden_motion_capture")
        released = False
        try:
            # The write lock serializes the quota check with every other writer.
            inserted = await self.db.execute(
                """INSERT INTO garden_captures(id,event_key,frigate_event,camera,label,observed_at,status,has_snapshot)
                   VALUES (?,?,NULL,?,'animal',?,'pending',1) ON CONFLICT(event_key) DO NOTHING""",
                (capture_id, source.key, source.camera, observed.isoformat()),
            )
            if not inserted.rowcount:
                await self.db.execute("RELEASE garden_motion_capture")
                return None
            await self._reclaim_dismissed_photos()
            stored = await self.db.execute(
                """INSERT INTO garden_motion_sources(capture_id,source_json,image,expires_at)
                   SELECT ?,?,?,? WHERE (SELECT COUNT(*) FROM garden_motion_sources WHERE image IS NOT NULL) < ?""",
                (capture_id, source.model_dump_json(), image, expires.isoformat(), MOTION_PHOTO_LIMIT),
            )
            if not stored.rowcount:
                await self.db.execute("ROLLBACK TO garden_motion_capture")
                await self.db.execute("RELEASE garden_motion_capture")
                return None
            await self.advance_motion_cursor(source.camera, source.clip_end, commit=False)
            await self.db.execute("RELEASE garden_motion_capture")
            released = True
            await self.db.commit()
            return capture_id
        except BaseException:
            if not released:
                with suppress(sqlite3.OperationalError):
                    await self.db.execute("ROLLBACK TO garden_motion_capture")
                    await self.db.execute("RELEASE garden_motion_capture")
            raise

    async def motion_photo(self, capture_id: str) -> bytes | None:
        async with self.db.execute(
            """SELECT image FROM garden_motion_sources JOIN garden_captures ON id=capture_id
               WHERE id=? AND status!='blocked' AND expires_at > ?""",
            (capture_id, utc_naive_now().isoformat()),
        ) as cursor:
            row = await cursor.fetchone()
        return bytes(row[0]) if row and row[0] else None

    async def motion_storage_full(self) -> bool:
        async with self.db.execute(
            """SELECT COUNT(*) FROM garden_motion_sources JOIN garden_captures ON id=capture_id
               WHERE image IS NOT NULL AND status != 'dismissed'"""
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] >= MOTION_PHOTO_LIMIT

    async def _reclaim_dismissed_photos(self) -> None:
        # Keep Undo photos until a successful new capture needs their space.
        await self.db.execute(
            """UPDATE garden_motion_sources SET image=NULL WHERE capture_id IN (
                 SELECT capture_id FROM garden_motion_sources JOIN garden_captures ON id=capture_id
                 WHERE image IS NOT NULL AND status='dismissed'
                 ORDER BY reviewed_at, id
                 LIMIT (SELECT MAX(0,COUNT(*)-?+1) FROM garden_motion_sources WHERE image IS NOT NULL))""",
            (MOTION_PHOTO_LIMIT,),
        )

    async def expire_motion_photos(self) -> None:
        async with self.db.execute(
            """SELECT capture_id,status FROM garden_motion_sources JOIN garden_captures ON id=capture_id
               WHERE expires_at <= ? AND (image IS NOT NULL OR status!='confirmed') LIMIT 8""",
            (utc_naive_now().isoformat(),),
        ) as cursor:
            expired = await cursor.fetchall()
        if not expired:
            return
        ids = [row[0] for row in expired]
        placeholders = ",".join("?" for _ in ids)
        # Acquire the writer lock and recheck status: a concurrent confirmation
        # must survive expiry even if the initial read saw an unconfirmed row.
        await self.db.execute(
            f"""UPDATE garden_captures SET frigate_event=NULL,camera='',label='',status='blocked',
               has_snapshot=0,reviewed_at=NULL WHERE id IN ({placeholders}) AND status!='confirmed'""",
            ids,
        )
        for table in ("garden_identifications", "garden_motion_sources", "garden_automatic_checks"):
            await self.db.execute(
                f"DELETE FROM {table} WHERE capture_id IN ({placeholders}) AND capture_id IN (SELECT id FROM garden_captures WHERE status='blocked')",
                ids,
            )
        await self.db.execute(f"UPDATE garden_motion_sources SET image=NULL WHERE capture_id IN ({placeholders})", ids)
        await self.db.commit()

    async def block_motion_overlap(self, camera: str, start: float, end: float) -> None:
        async with self.db.execute(
            """SELECT capture_id FROM garden_motion_sources
               WHERE json_extract(source_json,'$.camera')=?
               AND json_extract(source_json,'$.clip_start') <= ?
               AND json_extract(source_json,'$.clip_end') >= ?""",
            (camera, end + MOTION_PADDING_SECONDS, start - MOTION_PADDING_SECONDS),
        ) as cursor:
            captures = await cursor.fetchall()
        for (capture_id,) in captures:
            await self.block_capture(capture_id)

    async def motion_cursor(self, camera: str) -> float | None:
        async with self.db.execute("SELECT last_end FROM garden_motion_cursors WHERE camera=?", (camera,)) as cursor:
            row = await cursor.fetchone()
        return float(row[0]) if row else None

    async def advance_motion_cursor(self, camera: str, end: float, *, commit: bool = True) -> None:
        await self.db.execute(
            """INSERT INTO garden_motion_cursors(camera,last_end) VALUES (?,?)
               ON CONFLICT(camera) DO UPDATE SET last_end=MAX(last_end,excluded.last_end)""",
            (camera, end),
        )
        if commit:
            await self.db.commit()

    async def block_capture(self, capture_id: str) -> None:
        await self.db.execute("DELETE FROM garden_automatic_checks WHERE capture_id=?", (capture_id,))
        await self.db.execute("DELETE FROM garden_identifications WHERE capture_id=?", (capture_id,))
        await self.db.execute("DELETE FROM garden_motion_sources WHERE capture_id=?", (capture_id,))
        await self.db.execute(
            """UPDATE garden_captures SET frigate_event=NULL,camera='',label='',status='blocked',
               has_snapshot=0,reviewed_at=NULL WHERE id=?""",
            (capture_id,),
        )
        await self.db.commit()

    async def next_automatic_check(self, cameras: list[str], retry_before: str) -> GardenCapture | None:
        if not cameras:
            return None
        placeholders = ",".join("?" for _ in cameras)
        async with self.db.execute(
            f"""SELECT {self._COLUMNS} FROM garden_captures
                WHERE status='pending' AND automation_overridden=0 AND ({self._PHOTO_AVAILABLE})
                AND camera IN ({placeholders}) AND (
                  NOT EXISTS (SELECT 1 FROM garden_automatic_checks WHERE capture_id=id)
                  OR EXISTS (SELECT 1 FROM garden_automatic_checks WHERE capture_id=id
                    AND json_extract(result_json,'$.outcome')='unavailable'
                    AND json_extract(result_json,'$.checked_at') < ?))
                ORDER BY EXISTS (SELECT 1 FROM garden_automatic_checks WHERE capture_id=id), observed_at, id LIMIT 1""",
            (*cameras, retry_before),
        ) as cursor:
            row = await cursor.fetchone()
        return self._capture(row) if row else None

    async def _write_automatic_check(self, original: GardenCapture, result: GardenAutomaticCheck) -> bool:
        # A single write transaction compares both the previous assessment and
        # the owner-override bit. A dismiss/restore cycle must win over inference.
        cursor = await self.db.execute(
            f"""INSERT INTO garden_automatic_checks(capture_id,result_json)
                SELECT id,? FROM garden_captures WHERE id=? AND status='pending'
                AND automation_overridden=0 AND ({self._PHOTO_AVAILABLE})
                AND json((SELECT result_json FROM garden_automatic_checks WHERE capture_id=id)) IS json(?)
                ON CONFLICT(capture_id) DO UPDATE SET result_json=excluded.result_json""",
            (
                result.model_dump_json(),
                original.id,
                original.automatic_check.model_dump_json() if original.automatic_check else None,
            ),
        )
        return cursor.rowcount > 0

    async def save_automatic_naming(
        self, original: GardenCapture, result: GardenAutomaticCheck, named: GardenIdentification
    ) -> bool:
        """Record the check, confirm presence and name the animal together, or change nothing."""
        if result.outcome != "animal" or not named.automatic or named.review != "accepted":
            raise ValueError("Automatic naming needs an accepted automatic suggestion for an animal")
        if not await self._write_automatic_check(original, result):
            await self.db.rollback()
            return False
        # reviewed_at stays empty and the override bit stays clear: no owner has reviewed it,
        # so any later owner action still takes precedence.
        confirmed = await self.db.execute(
            "UPDATE garden_captures SET status='confirmed' WHERE id=? AND status='pending' AND automation_overridden=0",
            (original.id,),
        )
        if not confirmed.rowcount:
            await self.db.rollback()
            return False
        await self.db.execute(
            """INSERT INTO garden_identifications(capture_id,result_json) VALUES(?,?)
               ON CONFLICT(capture_id) DO UPDATE SET result_json=excluded.result_json
               WHERE json_extract(garden_identifications.result_json,'$.review') != 'accepted'""",
            (original.id, named.model_dump_json()),
        )
        await self.db.commit()
        return True

    async def save_automatic_check(self, original: GardenCapture, result: GardenAutomaticCheck) -> bool:
        changed = await self._write_automatic_check(original, result)
        if changed and result.outcome in {"bird", "non_animal"}:
            await self.db.execute(
                "UPDATE garden_captures SET status='dismissed' WHERE id=? AND status='pending' AND automation_overridden=0",
                (original.id,),
            )
        await self.db.commit()
        return changed

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
