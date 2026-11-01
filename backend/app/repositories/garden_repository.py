"""Garden review storage has no dependency on bird history or species totals."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from contextlib import suppress
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from typing import Literal
import uuid

import aiosqlite

from app.utils.api_datetime import utc_naive_now
from app.models.garden import (
    GardenAutomaticCheck,
    GardenDomesticRoute,
    GardenIdentification,
    GardenOwnerIdentification,
    GardenSpecies,
)
from app.models.garden_crop import CROP_BYTES_LIMIT, CROP_COUNT_LIMIT, GardenCropEvidence
from app.models.garden_motion import MotionSource, MOTION_PADDING_SECONDS
from app.models.garden_media import KeptMediaEntry, KeptMediaRecord
from app.services.garden_automatic_policy import automatic_check_dismisses, saved_check_dismisses
from pydantic import ValidationError

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
    crop: GardenCropEvidence | None = None
    owner_identification: GardenOwnerIdentification | None = None
    # YA-WAMF's own copy, which never changes the review: excluded from equality so
    # keeping media cannot make a concurrent review or check look stale.
    kept_photo_sha256: str | None = field(default=None, compare=False)
    clip_kept: bool = field(default=False, compare=False)
    domestic_route: GardenDomesticRoute | None = None

    @property
    def review_token(self) -> str:
        state = [
            self.id,
            self.status,
            self.reviewed_at,
            self.automation_overridden,
            self.identification.model_dump(mode="json") if self.identification else None,
            self.owner_identification.model_dump(mode="json") if self.owner_identification else None,
        ]
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


class GardenRepository:
    _PHOTO_AVAILABLE = """CASE WHEN EXISTS (SELECT 1 FROM garden_motion_sources WHERE capture_id=garden_captures.id)
          THEN (SELECT image IS NOT NULL AND expires_at > strftime('%Y-%m-%dT%H:%M:%f','now')
                FROM garden_motion_sources WHERE capture_id=garden_captures.id)
          ELSE has_snapshot END"""
    _KEPT_PHOTO = """(SELECT photo_sha256 FROM garden_kept_media
          WHERE capture_id=garden_captures.id AND photo_state='kept' AND garden_captures.status='confirmed')"""
    _COLUMNS = f"""id, frigate_event, camera, label, observed_at, status,
        ({_PHOTO_AVAILABLE}) OR {_KEPT_PHOTO} IS NOT NULL, reviewed_at,
        (SELECT result_json FROM garden_identifications WHERE capture_id = garden_captures.id),
        (SELECT source_json FROM garden_motion_sources WHERE capture_id=garden_captures.id),
        (SELECT result_json FROM garden_automatic_checks WHERE capture_id=garden_captures.id),
        automation_overridden,
        (SELECT evidence_json FROM garden_saved_crops WHERE capture_id=garden_captures.id AND image IS NOT NULL),
        (SELECT json_object('species_id',species_id,'name',name,'scientific_name',scientific_name,'changed_at',changed_at)
          FROM garden_owner_identifications WHERE capture_id=garden_captures.id),
        {_KEPT_PHOTO},
        COALESCE((SELECT clip_state='kept' FROM garden_kept_media
          WHERE capture_id=garden_captures.id AND garden_captures.status='confirmed'), 0),
        (SELECT json_object('domestic_bird',domestic_bird,'origin',origin,'source_label',source_label,
                'source_scientific_name',source_scientific_name,'source_score',source_score,
                'source_model',source_model,'detection_id',detection_id,'routed_at',routed_at)
          FROM garden_domestic_routes WHERE capture_id=garden_captures.id)"""

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
            GardenCropEvidence.model_validate_json(row[12]) if row[12] else None,
            GardenOwnerIdentification.model_validate_json(row[13]) if row[13] else None,
            row[14],
            bool(row[15]),
            GardenDomesticRoute.model_validate_json(row[16]) if row[16] else None,
        )

    async def has_history(self) -> bool:
        async with self.db.execute("SELECT 1 FROM garden_captures LIMIT 1") as cursor:
            return await cursor.fetchone() is not None

    async def capture(self, event_id: str, camera: str, label: str, observed_at: str, has_snapshot: bool) -> bool:
        inserted = await self.db.execute(
            """INSERT INTO garden_captures (id, event_key, frigate_event, camera, label, observed_at, status, has_snapshot)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?) ON CONFLICT(event_key) DO NOTHING""",
            (uuid.uuid4().hex, self._key(event_id), event_id, camera, label, observed_at, has_snapshot),
        )
        await self.db.commit()
        return inserted.rowcount > 0

    async def block(self, event_id: str, *, create: bool, keep_domestic: bool = False) -> bool:
        """Remove an event's capture and media, leaving a tombstone.

        ``keep_domestic`` is for a relabel to bird, which revokes an animal capture but
        is exactly what a domestic bird recorded from a bird event is. Person and
        false-positive revocations never pass it.
        """
        target = "SELECT id FROM garden_captures WHERE event_key=?" + (
            " AND NOT EXISTS (SELECT 1 FROM garden_domestic_routes r WHERE r.capture_id=garden_captures.id)"
            if keep_domestic
            else ""
        )
        for table in (
            "garden_owner_identifications",
            "garden_domestic_routes",
            "garden_saved_crops",
            "garden_kept_media",
            "garden_automatic_checks",
            "garden_identifications",
        ):
            await self.db.execute(f"DELETE FROM {table} WHERE capture_id IN ({target})", (self._key(event_id),))
        if create:
            await self.db.execute(
                """INSERT INTO garden_captures (id, event_key, camera, label, observed_at, status, has_snapshot)
                   VALUES (?, ?, '', '', ?, 'blocked', 0) ON CONFLICT(event_key) DO NOTHING""",
                (uuid.uuid4().hex, self._key(event_id), utc_naive_now().isoformat()),
            )
        # A hashed tombstone stops delayed delivery resurrecting rejected media.
        updated = await self.db.execute(
            f"""UPDATE garden_captures SET frigate_event = NULL, camera = '', label = '', status = 'blocked',
               has_snapshot = 0, reviewed_at = NULL WHERE id IN ({target}) AND status != 'blocked'""",
            (self._key(event_id),),
        )
        await self.db.commit()
        return updated.rowcount > 0

    async def get(self, capture_id: str) -> GardenCapture | None:
        async with self.db.execute(
            f"SELECT {self._COLUMNS} FROM garden_captures WHERE id = ? AND status != 'blocked'",
            (capture_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return self._capture(row) if row else None

    async def confirmed_observed_at(self, frigate_event: str) -> str | None:
        """When a confirmed Frigate event capture was seen; None for any other state or event."""
        async with self.db.execute(
            "SELECT observed_at FROM garden_captures WHERE frigate_event = ? AND status = 'confirmed'",
            (frigate_event,),
        ) as cursor:
            row = await cursor.fetchone()
        return str(row[0]) if row else None

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
            await self.db.execute("DELETE FROM garden_saved_crops WHERE capture_id=?", (capture_id,))
            await self.db.execute("DELETE FROM garden_kept_media WHERE capture_id=?", (capture_id,))
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
            await self.db.executemany(
                "DELETE FROM garden_saved_crops WHERE capture_id=?", [(identity,) for identity in updated]
            )
            await self.db.executemany(
                "DELETE FROM garden_kept_media WHERE capture_id=?", [(identity,) for identity in updated]
            )
            changed = ",".join("?" for _ in updated)
            await self.db.execute(
                f"""UPDATE garden_identifications SET result_json=json_set(result_json,'$.review','dismissed')
                    WHERE capture_id IN ({changed})""",
                list(updated),
            )
        await self.db.commit()
        return [capture_id for capture_id in ids if capture_id in updated]

    async def dismiss_captures(self, targets: list[tuple[str, str]]) -> list[str]:
        """Dismiss exactly the unchanged snapshots the owner selected, never later arrivals."""
        if not 1 <= len(targets) <= 128 or len({identity for identity, _ in targets}) != len(targets):
            raise ValueError("Dismissal requires 1 to 128 unique capture snapshots")
        updated = []
        for identity, token in targets:
            async with self.db.execute(
                f"SELECT {self._COLUMNS} FROM garden_captures WHERE id=? AND status IN ('pending','confirmed')",
                (identity,),
            ) as cursor:
                row = await cursor.fetchone()
            if row is None or self._capture(row).review_token != token:
                continue
            # Comparing the original raw state closes the gap between the read
            # and write, including a species review that leaves presence alone.
            changed = await self.db.execute(
                """UPDATE garden_captures SET status='dismissed',reviewed_at=?,automation_overridden=1
                   WHERE id=? AND status=? AND reviewed_at IS ? AND automation_overridden=?
                   AND (SELECT result_json FROM garden_identifications WHERE capture_id=garden_captures.id) IS ?""",
                (utc_naive_now().isoformat(), identity, row[5], row[7], row[11], row[8]),
            )
            if changed.rowcount:
                updated.append(identity)
        if updated:
            placeholders = ",".join("?" for _ in updated)
            await self.db.execute(f"DELETE FROM garden_saved_crops WHERE capture_id IN ({placeholders})", updated)
            await self.db.execute(f"DELETE FROM garden_kept_media WHERE capture_id IN ({placeholders})", updated)
            await self.db.execute(
                f"""UPDATE garden_identifications SET result_json=json_set(result_json,'$.review','dismissed')
                    WHERE capture_id IN ({placeholders})""",
                updated,
            )
        await self.db.commit()
        return updated

    async def delete_older_than(self, cutoff: datetime) -> None:
        for table in ("garden_owner_identifications", "garden_domestic_routes"):
            await self.db.execute(
                f"DELETE FROM {table} WHERE capture_id IN (SELECT id FROM garden_captures WHERE observed_at < ?)",
                (cutoff.replace(tzinfo=None).isoformat(),),
            )
        await self.db.execute(
            "DELETE FROM garden_saved_crops WHERE capture_id IN (SELECT id FROM garden_captures WHERE observed_at < ?)",
            (cutoff.replace(tzinfo=None).isoformat(),),
        )
        await self.db.execute(
            "DELETE FROM garden_kept_media WHERE capture_id IN (SELECT id FROM garden_captures WHERE observed_at < ?)",
            (cutoff.replace(tzinfo=None).isoformat(),),
        )
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
        for table in (
            "garden_owner_identifications",
            "garden_domestic_routes",
            "garden_identifications",
            "garden_motion_sources",
            "garden_automatic_checks",
            "garden_saved_crops",
            "garden_kept_media",
        ):
            await self.db.execute(
                f"DELETE FROM {table} WHERE capture_id IN ({placeholders}) AND capture_id IN (SELECT id FROM garden_captures WHERE status='blocked')",
                ids,
            )
        await self.db.execute(f"UPDATE garden_motion_sources SET image=NULL WHERE capture_id IN ({placeholders})", ids)
        await self.db.commit()

    async def block_motion_overlap(self, camera: str, start: float, end: float) -> bool:
        async with self.db.execute(
            """SELECT capture_id FROM garden_motion_sources
               WHERE json_extract(source_json,'$.camera')=?
               AND json_extract(source_json,'$.clip_start') <= ?
               AND json_extract(source_json,'$.clip_end') >= ?""",
            (camera, end + MOTION_PADDING_SECONDS, start - MOTION_PADDING_SECONDS),
        ) as cursor:
            captures = await cursor.fetchall()
        async with self.db.execute(
            """SELECT s.capture_id FROM garden_saved_crops s JOIN garden_captures g ON g.id=s.capture_id
               WHERE g.camera=? AND json_extract(s.evidence_json,'$.source_start') <= ?
               AND json_extract(s.evidence_json,'$.source_end') >= ?""",
            (camera, end + MOTION_PADDING_SECONDS, start - MOTION_PADDING_SECONDS),
        ) as cursor:
            captures = set(captures) | set(await cursor.fetchall())
        async with self.db.execute(
            """SELECT k.capture_id FROM garden_kept_media k JOIN garden_captures g ON g.id=k.capture_id
               WHERE g.camera=? AND k.source_start <= ? AND k.source_end >= ?""",
            (camera, end + MOTION_PADDING_SECONDS, start - MOTION_PADDING_SECONDS),
        ) as cursor:
            captures = list(captures | set(await cursor.fetchall()))
        changed = False
        for (capture_id,) in captures:
            changed = await self.block_capture(capture_id) or changed
        return changed

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

    async def block_capture(self, capture_id: str) -> bool:
        await self.db.execute("DELETE FROM garden_owner_identifications WHERE capture_id=?", (capture_id,))
        await self.db.execute("DELETE FROM garden_domestic_routes WHERE capture_id=?", (capture_id,))
        await self.db.execute("DELETE FROM garden_saved_crops WHERE capture_id=?", (capture_id,))
        await self.db.execute("DELETE FROM garden_kept_media WHERE capture_id=?", (capture_id,))
        await self.db.execute("DELETE FROM garden_automatic_checks WHERE capture_id=?", (capture_id,))
        await self.db.execute("DELETE FROM garden_identifications WHERE capture_id=?", (capture_id,))
        await self.db.execute("DELETE FROM garden_motion_sources WHERE capture_id=?", (capture_id,))
        updated = await self.db.execute(
            """UPDATE garden_captures SET frigate_event=NULL,camera='',label='',status='blocked',
               has_snapshot=0,reviewed_at=NULL WHERE id=? AND status!='blocked'""",
            (capture_id,),
        )
        await self.db.commit()
        return updated.rowcount > 0

    async def latest_automatic_check(self) -> GardenAutomaticCheck | None:
        async with self.db.execute(
            """SELECT result_json FROM garden_automatic_checks
               WHERE json_extract(result_json,'$.outcome') != 'unavailable'
               ORDER BY json_extract(result_json,'$.checked_at') DESC LIMIT 1"""
        ) as cursor:
            row = await cursor.fetchone()
        return GardenAutomaticCheck.model_validate_json(row[0]) if row else None

    async def next_automatic_check(
        self, cameras: list[str], retry_before: str, *, policy_version: int | None = None, country: str | None = None
    ) -> GardenCapture | None:
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
                    AND json_extract(result_json,'$.checked_at') < ?)
                  OR EXISTS (SELECT 1 FROM garden_automatic_checks WHERE capture_id=id
                    AND json_extract(result_json,'$.outcome') != 'unavailable'
                    AND ? IS NOT NULL AND COALESCE(json_extract(result_json,'$.policy_version'),0) < ?)
                  OR EXISTS (SELECT 1 FROM garden_automatic_checks WHERE capture_id=id
                    AND json_extract(result_json,'$.decision_reason')='location_required' AND ? IS NOT NULL))
                ORDER BY EXISTS (SELECT 1 FROM garden_automatic_checks WHERE capture_id=id), observed_at, id LIMIT 1""",
            (*cameras, retry_before, policy_version, policy_version, country),
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
                original.automatic_check.model_dump_json(exclude_unset=True) if original.automatic_check else None,
            ),
        )
        return cursor.rowcount > 0

    async def save_automatic_naming(
        self,
        original: GardenCapture,
        result: GardenAutomaticCheck,
        named: GardenIdentification,
        *,
        crop: tuple[GardenCropEvidence, bytes] | None = None,
        route: GardenDomesticRoute | None = None,
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
        if route is not None:
            await self._insert_domestic_route(original.id, route)
        if crop is not None:
            evidence, image = crop
            await self.save_crop(
                replace(original, status="confirmed", identification=named), evidence, image, commit=False
            )
        await self.db.commit()
        return True

    async def _insert_domestic_route(self, capture_id: str, route: GardenDomesticRoute) -> None:
        await self.db.execute(
            """INSERT INTO garden_domestic_routes(capture_id,domestic_bird,origin,source_label,source_scientific_name,
                 source_score,source_model,detection_id,routed_at) VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(capture_id) DO NOTHING""",
            (
                capture_id,
                route.domestic_bird,
                route.origin,
                route.source_label,
                route.source_scientific_name,
                route.source_score,
                route.source_model,
                route.detection_id,
                route.routed_at,
            ),
        )

    async def save_domestic_capture(
        self, event_id: str, camera: str, observed_at: str, has_snapshot: bool, route: GardenDomesticRoute
    ) -> str | None:
        """Confirm a Frigate bird event as a declared domestic bird, once per event.

        An existing capture or privacy tombstone for the event wins, so a repeated or
        revoked event never creates a second record. Returns the new capture id.
        """
        capture_id = uuid.uuid4().hex
        inserted = await self.db.execute(
            """INSERT INTO garden_captures (id, event_key, frigate_event, camera, label, observed_at, status, has_snapshot)
               VALUES (?, ?, ?, ?, 'bird', ?, 'confirmed', ?) ON CONFLICT(event_key) DO NOTHING""",
            (capture_id, self._key(event_id), event_id, camera, observed_at, has_snapshot),
        )
        if not inserted.rowcount:
            await self.db.commit()
            return None
        await self._insert_domestic_route(capture_id, route)
        await self.db.commit()
        return capture_id

    async def move_detection_to_garden(
        self,
        detection_id: int,
        event_id: str,
        camera: str,
        observed_at: str,
        has_snapshot: bool,
        route: GardenDomesticRoute,
    ) -> str | None:
        """Record a bird detection as the domestic bird it is, and hide the bird record together.

        This is the one write that touches bird history from Garden, so both happen in a
        single transaction or not at all. The bird row is hidden, not deleted, so showing
        it again restores it. None means Garden already holds this Frigate event.
        """
        capture_id = uuid.uuid4().hex
        inserted = await self.db.execute(
            """INSERT INTO garden_captures (id, event_key, frigate_event, camera, label, observed_at, status, has_snapshot)
               VALUES (?, ?, ?, ?, 'bird', ?, 'confirmed', ?) ON CONFLICT(event_key) DO NOTHING""",
            (capture_id, self._key(event_id), event_id, camera, observed_at, has_snapshot),
        )
        if not inserted.rowcount:
            await self.db.rollback()
            return None
        await self._insert_domestic_route(capture_id, route)
        hidden = await self.db.execute(
            "UPDATE detections SET is_hidden=1 WHERE id=? AND frigate_event=? AND COALESCE(is_hidden,0)=0",
            (detection_id, event_id),
        )
        if not hidden.rowcount:
            await self.db.rollback()
            return None
        await self.db.commit()
        return capture_id

    async def save_automatic_check(self, original: GardenCapture, result: GardenAutomaticCheck) -> bool:
        changed = await self._write_automatic_check(original, result)
        if changed and automatic_check_dismisses(result.outcome, result.decision_reason):
            await self.db.execute(
                "UPDATE garden_captures SET status='dismissed' WHERE id=? AND status='pending' AND automation_overridden=0",
                (original.id,),
            )
        await self.db.commit()
        return changed

    async def dismiss_pending_by_saved_checks(self) -> int:
        """Dismiss pending captures whose saved check the current policy dismisses.

        A capture the owner restored or reviewed (``automation_overridden``) is never moved.
        """
        rows = await (
            await self.db.execute(
                """SELECT c.id, a.result_json FROM garden_captures c
                   JOIN garden_automatic_checks a ON a.capture_id = c.id
                   WHERE c.status='pending' AND c.automation_overridden=0"""
            )
        ).fetchall()
        dismissed = 0
        for capture_id, result_json in rows:
            try:
                check = GardenAutomaticCheck.model_validate_json(result_json)
            except ValidationError:
                # An unreadable saved check decides nothing; the capture keeps waiting for a person.
                continue
            if not saved_check_dismisses(check):
                continue
            cursor = await self.db.execute(
                "UPDATE garden_captures SET status='dismissed' WHERE id=? AND status='pending' AND automation_overridden=0",
                (capture_id,),
            )
            dismissed += cursor.rowcount
        await self.db.commit()
        return dismissed

    async def save_identification(self, original: GardenCapture, result: GardenIdentification) -> bool:
        cursor = await self.db.execute(
            """INSERT INTO garden_identifications(capture_id,result_json)
               SELECT id, ? FROM garden_captures WHERE id=? AND status=? AND reviewed_at IS ?
               AND status = 'confirmed'
               AND json((SELECT result_json FROM garden_identifications WHERE capture_id=id)) IS json(?)
               AND NOT EXISTS (SELECT 1 FROM garden_owner_identifications WHERE capture_id=id)
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
        if cursor.rowcount and action == "dismissed":
            # A discarded SpeciesNet name takes the domestic bird it stood for with it.
            await self.db.execute(
                "DELETE FROM garden_domestic_routes WHERE capture_id=? AND origin='garden_check'", (capture_id,)
            )
        await self.db.commit()
        return cursor.rowcount > 0

    async def save_crop(
        self, original: GardenCapture, evidence: GardenCropEvidence, image: bytes, *, commit: bool = True
    ) -> bool:
        if not image or len(image) > CROP_BYTES_LIMIT or hashlib.sha256(image).hexdigest() != evidence.crop_sha256:
            raise ValueError("Saved crop differs from its evidence")
        if bool(original.motion_source) != (evidence.source_kind == "motion"):
            raise ValueError("Saved crop source kind differs from its capture")
        if original.motion_source and (evidence.source_start, evidence.source_end) != (
            original.motion_source.clip_start,
            original.motion_source.clip_end,
        ):
            raise ValueError("Saved crop window differs from its recording")
        if original.motion_source and original.motion_source.image_sha256 != evidence.source_sha256:
            raise ValueError("Saved crop source differs from the motion photo")
        cursor = await self.db.execute(
            """INSERT INTO garden_saved_crops(capture_id,image,evidence_json,state,retry_after,updated_at)
               SELECT id,?,?,'available',NULL,? FROM garden_captures
               WHERE id=? AND status='confirmed' AND reviewed_at IS ? AND camera=? AND frigate_event IS ?
               AND json((SELECT result_json FROM garden_identifications WHERE capture_id=id)) IS json(?)
               AND json((SELECT source_json FROM garden_motion_sources WHERE capture_id=id)) IS json(?)
               ON CONFLICT(capture_id) DO UPDATE SET image=excluded.image,evidence_json=excluded.evidence_json,
                   state='available',retry_after=NULL,updated_at=excluded.updated_at
               WHERE garden_saved_crops.image IS NULL""",
            (
                image,
                evidence.model_dump_json(),
                utc_naive_now().isoformat(),
                original.id,
                original.reviewed_at,
                original.camera,
                original.frigate_event,
                original.identification.model_dump_json() if original.identification else None,
                original.motion_source.model_dump_json() if original.motion_source else None,
            ),
        )
        if not cursor.rowcount:
            if commit:
                await self.db.rollback()
            return False
        # The budget is enforced by the same write transaction as the insert.
        await self.db.execute(
            """UPDATE garden_saved_crops SET image=NULL,state='evicted',retry_after=NULL WHERE capture_id IN (
               SELECT c.capture_id FROM garden_saved_crops c JOIN garden_captures g ON g.id=c.capture_id
               WHERE c.image IS NOT NULL AND c.capture_id != ? ORDER BY g.observed_at,c.capture_id
               LIMIT (SELECT MAX(0,COUNT(*)-?) FROM garden_saved_crops WHERE image IS NOT NULL))""",
            (original.id, CROP_COUNT_LIMIT),
        )
        if commit:
            await self.db.commit()
        return True

    async def crop_photo(self, capture_id: str) -> bytes | None:
        async with self.db.execute(
            """SELECT s.image,s.evidence_json FROM garden_saved_crops s JOIN garden_captures g ON g.id=s.capture_id
               WHERE g.id=? AND g.status='confirmed' AND s.image IS NOT NULL""",
            (capture_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        evidence = GardenCropEvidence.model_validate_json(row[1])
        image = bytes(row[0])
        if hashlib.sha256(image).hexdigest() != evidence.crop_sha256:
            raise GardenPhotoUnavailable("Saved animal crop differs from its evidence")
        return image

    async def next_crop(self, cameras: list[str]) -> GardenCapture | None:
        if not cameras:
            return None
        placeholders = ",".join("?" for _ in cameras)
        async with self.db.execute(
            f"""SELECT {self._COLUMNS} FROM garden_captures
                WHERE status='confirmed' AND camera IN ({placeholders}) AND ({self._PHOTO_AVAILABLE})
                AND NOT EXISTS (SELECT 1 FROM garden_saved_crops WHERE capture_id=id
                  AND (image IS NOT NULL OR retry_after IS NULL OR retry_after > ?))
                AND (SELECT COUNT(*) FROM garden_saved_crops WHERE image IS NOT NULL) < ?
                ORDER BY observed_at DESC,id DESC LIMIT 1""",
            (*cameras, utc_naive_now().isoformat(), CROP_COUNT_LIMIT),
        ) as cursor:
            row = await cursor.fetchone()
        return self._capture(row) if row else None

    async def crop_unavailable(self, capture_id: str) -> None:
        await self.db.execute(
            """INSERT INTO garden_saved_crops(capture_id,image,evidence_json,state,retry_after,updated_at)
               SELECT id,NULL,NULL,'unavailable',?,? FROM garden_captures WHERE id=? AND status='confirmed'
               ON CONFLICT(capture_id) DO UPDATE SET retry_after=excluded.retry_after,updated_at=excluded.updated_at
               WHERE garden_saved_crops.state='unavailable'""",
            ((utc_naive_now() + timedelta(hours=1)).isoformat(), utc_naive_now().isoformat(), capture_id),
        )
        await self.db.commit()

    async def crop_storage(self) -> dict[str, int]:
        async with self.db.execute(
            "SELECT COUNT(*),COALESCE(SUM(length(image)),0) FROM garden_saved_crops WHERE image IS NOT NULL"
        ) as cursor:
            count, size = await cursor.fetchone()
        return {"count": count, "bytes": size, "limit": CROP_COUNT_LIMIT, "max_bytes_per_crop": CROP_BYTES_LIMIT}

    async def rename_species(self, capture_id: str, token: str, species: GardenSpecies | None) -> GardenCapture | None:
        async with self.db.execute(
            f"SELECT {self._COLUMNS} FROM garden_captures WHERE id=? AND status!='blocked'", (capture_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        current = self._capture(row)
        if current.status != "confirmed" or current.review_token != token:
            raise ValueError("This capture changed. Refresh it before changing its species.")
        now = utc_naive_now().isoformat()
        # This is the first write: compare the raw owner and model evidence under
        # SQLite's writer lock, so a second owner or privacy revocation always wins.
        changed = await self.db.execute(
            """UPDATE garden_captures SET reviewed_at=?,automation_overridden=1
               WHERE id=? AND status='confirmed' AND reviewed_at IS ? AND automation_overridden=?
               AND (SELECT result_json FROM garden_identifications WHERE capture_id=id) IS ?
               AND (SELECT json_object('species_id',species_id,'name',name,'scientific_name',scientific_name,'changed_at',changed_at)
                    FROM garden_owner_identifications WHERE capture_id=id) IS ?""",
            (now, capture_id, row[7], row[11], row[8], row[13]),
        )
        if not changed.rowcount:
            await self.db.rollback()
            raise ValueError("This capture changed. Refresh it before changing its species.")
        if species is None:
            await self.db.execute("DELETE FROM garden_owner_identifications WHERE capture_id=?", (capture_id,))
        else:
            await self.db.execute(
                """INSERT INTO garden_owner_identifications(capture_id,species_id,name,scientific_name,changed_at) VALUES (?,?,?,?,?)
                   ON CONFLICT(capture_id) DO UPDATE SET species_id=excluded.species_id,name=excluded.name,
                   scientific_name=excluded.scientific_name,changed_at=excluded.changed_at""",
                (capture_id, species.species_id, species.name, species.scientific_name, now + "Z"),
            )
        await self.db.commit()
        return await self.get(capture_id)

    async def kept_media_record(self, capture_id: str) -> KeptMediaRecord | None:
        async with self.db.execute(
            """SELECT photo_state,photo_source,photo_sha256,photo_bytes,clip_state,clip_sha256,clip_bytes,
                      source_start,source_end,retry_after FROM garden_kept_media WHERE capture_id=?""",
            (capture_id,),
        ) as cursor:
            row = await cursor.fetchone()
        return KeptMediaRecord(*row) if row else None

    async def save_kept_media(self, original: GardenCapture, record: KeptMediaRecord) -> bool:
        """Record kept media only while the capture is still the confirmed one it was fetched for."""
        cursor = await self.db.execute(
            """INSERT INTO garden_kept_media(capture_id,photo_state,photo_source,photo_sha256,photo_bytes,
                   clip_state,clip_sha256,clip_bytes,source_start,source_end,retry_after,updated_at)
               SELECT id,?,?,?,?,?,?,?,?,?,?,? FROM garden_captures
               WHERE id=? AND status='confirmed' AND camera=? AND frigate_event IS ?
               AND json((SELECT source_json FROM garden_motion_sources WHERE capture_id=id)) IS json(?)
               ON CONFLICT(capture_id) DO UPDATE SET photo_state=excluded.photo_state,
                   photo_source=excluded.photo_source,photo_sha256=excluded.photo_sha256,
                   photo_bytes=excluded.photo_bytes,clip_state=excluded.clip_state,
                   clip_sha256=excluded.clip_sha256,clip_bytes=excluded.clip_bytes,
                   source_start=excluded.source_start,source_end=excluded.source_end,
                   retry_after=excluded.retry_after,updated_at=excluded.updated_at""",
            (
                record.photo_state,
                record.photo_source,
                record.photo_sha256,
                record.photo_bytes,
                record.clip_state,
                record.clip_sha256,
                record.clip_bytes,
                record.source_start,
                record.source_end,
                record.retry_after,
                utc_naive_now().isoformat(),
                original.id,
                original.camera,
                original.frigate_event,
                original.motion_source.model_dump_json() if original.motion_source else None,
            ),
        )
        if not cursor.rowcount:
            await self.db.rollback()
            return False
        await self.db.commit()
        return True

    async def next_media_to_keep(
        self, cameras: list[str], *, since: str | None, clips: bool, now: str
    ) -> GardenCapture | None:
        """The newest confirmed capture with media still to keep or a retry that is due."""
        if not cameras:
            return None
        placeholders = ",".join("?" for _ in cameras)
        async with self.db.execute(
            f"""SELECT {self._COLUMNS} FROM garden_captures
                WHERE status='confirmed' AND camera IN ({placeholders}) AND (? IS NULL OR observed_at >= ?)
                AND (NOT EXISTS (SELECT 1 FROM garden_kept_media WHERE capture_id=id)
                  OR EXISTS (SELECT 1 FROM garden_kept_media k WHERE k.capture_id=id
                    AND (k.retry_after IS NULL OR k.retry_after <= ?)
                    AND (k.photo_state='retry' OR k.clip_state='retry'
                      OR (? AND k.clip_state IS NULL AND garden_captures.frigate_event IS NOT NULL
                          AND NOT EXISTS (SELECT 1 FROM garden_motion_sources WHERE capture_id=id)))))
                ORDER BY observed_at DESC, id DESC LIMIT 1""",
            (*cameras, since, since, now, clips),
        ) as cursor:
            row = await cursor.fetchone()
        return self._capture(row) if row else None

    async def garden_clip(self, frigate_event: str) -> tuple[bool, str | None, int | None]:
        """Whether an event belongs to Garden, and the confirmed capture and size of its kept clip."""
        async with self.db.execute(
            """SELECT g.id, g.status='confirmed' AND k.clip_state='kept', k.clip_bytes FROM garden_captures g
               LEFT JOIN garden_kept_media k ON k.capture_id=g.id WHERE g.frigate_event=?""",
            (frigate_event,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return False, None, None
        return (True, row[0], int(row[2])) if row[1] else (True, None, None)

    async def kept_media_files(self) -> set[tuple[str, str]]:
        """Every (capture, kind) whose file may stay on disk; anything else is swept."""
        async with self.db.execute(
            """SELECT k.capture_id, k.photo_state='kept', k.clip_state IS 'kept' FROM garden_kept_media k
               JOIN garden_captures g ON g.id=k.capture_id WHERE g.status='confirmed'"""
        ) as cursor:
            rows = await cursor.fetchall()
        files = set()
        for capture_id, photo, clip in rows:
            if photo:
                files.add((capture_id, "photo"))
            if clip:
                files.add((capture_id, "clip"))
        return files

    async def kept_media_entries(self) -> list[KeptMediaEntry]:
        async with self.db.execute(
            """SELECT k.capture_id, g.observed_at, COALESCE(k.photo_bytes,0)+COALESCE(k.clip_bytes,0)
               FROM garden_kept_media k JOIN garden_captures g ON g.id=k.capture_id
               WHERE g.status='confirmed' AND (k.photo_state='kept' OR k.clip_state IS 'kept')"""
        ) as cursor:
            return [KeptMediaEntry(*row) for row in await cursor.fetchall()]

    async def kept_media_observed_before(self, cutoff: datetime) -> list[str]:
        async with self.db.execute(
            """SELECT k.capture_id FROM garden_kept_media k JOIN garden_captures g ON g.id=k.capture_id
               WHERE g.observed_at < ? AND (k.photo_state='kept' OR k.clip_state IS 'kept')""",
            (cutoff.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),),
        ) as cursor:
            return [row[0] for row in await cursor.fetchall()]

    async def evict_kept_media(self, capture_ids: list[str]) -> None:
        """Release kept files without recreating them: an evicted copy is settled, not retried."""
        if not capture_ids:
            return
        placeholders = ",".join("?" for _ in capture_ids)
        await self.db.execute(
            f"""UPDATE garden_kept_media SET
                photo_state=CASE WHEN photo_state='kept' THEN 'evicted' ELSE photo_state END,
                photo_sha256=NULL, photo_bytes=NULL,
                clip_state=CASE WHEN clip_state='kept' THEN 'evicted' ELSE clip_state END,
                clip_sha256=NULL, clip_bytes=NULL, updated_at=?
                WHERE capture_id IN ({placeholders})""",
            (utc_naive_now().isoformat(), *capture_ids),
        )
        await self.db.commit()
