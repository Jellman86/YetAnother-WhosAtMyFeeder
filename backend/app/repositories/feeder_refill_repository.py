"""Storage for feeder refills (#946). Times are naive UTC strings, so they sort and compare as text."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

import aiosqlite

from app.models.feeder_refill import NewRefill, RefillSource, StoredRefill
from app.utils.api_datetime import parse_storage_datetime, serialize_storage_datetime, utc_naive_now

_COLUMNS = "id, refilled_at, camera_name, source, note, source_event_id, created_at"


def _from_row(row: aiosqlite.Row | tuple) -> StoredRefill:
    source: RefillSource = row[3]
    return StoredRefill(
        id=int(row[0]),
        refilled_at=parse_storage_datetime(row[1]),
        camera_name=row[2],
        source=source,
        note=row[4],
        source_event_id=row[5],
        created_at=parse_storage_datetime(row[6]),
    )


class FeederRefillRepository:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    @asynccontextmanager
    async def write_transaction(self) -> AsyncIterator[None]:
        """Hold the database's write lock from the first read, so what was read still holds at commit."""
        if self.db.in_transaction:
            raise RuntimeError("A refill write requires an idle connection")
        try:
            async with self.db.execute("BEGIN IMMEDIATE"):
                pass
            yield
            await self.db.commit()
        except BaseException:
            await self.db.rollback()
            raise

    async def get(self, refill_id: int) -> StoredRefill | None:
        async with self.db.execute(f"SELECT {_COLUMNS} FROM feeder_refills WHERE id = ?", (refill_id,)) as cursor:
            row = await cursor.fetchone()
        return _from_row(row) if row else None

    async def by_source_event_id(self, source_event_id: str) -> StoredRefill | None:
        async with self.db.execute(
            f"SELECT {_COLUMNS} FROM feeder_refills WHERE id = COALESCE("
            "(SELECT id FROM feeder_refills WHERE source_event_id = ?), "
            "(SELECT refill_id FROM feeder_refill_event_aliases WHERE source_event_id = ?))",
            (source_event_id, source_event_id),
        ) as cursor:
            row = await cursor.fetchone()
        return _from_row(row) if row else None

    async def remember_source_event(self, source_event_id: str, refill_id: int) -> None:
        """Tie a cooldown-suppressed event to the refill it repeated for future retries."""
        async with self.db.execute(
            "INSERT INTO feeder_refill_event_aliases (source_event_id, refill_id) VALUES (?, ?)",
            (source_event_id, refill_id),
        ):
            pass

    async def near(self, camera_name: str | None, start: datetime, end: datetime) -> list[StoredRefill]:
        """Refills of one camera, or of no camera, between two times inclusive."""
        async with self.db.execute(
            f"SELECT {_COLUMNS} FROM feeder_refills WHERE camera_name IS ? AND refilled_at BETWEEN ? AND ?"
            " ORDER BY refilled_at, id LIMIT 50",
            (camera_name, serialize_storage_datetime(start), serialize_storage_datetime(end)),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_from_row(row) for row in rows]

    async def insert(self, refill: NewRefill) -> StoredRefill:
        """Store a refill inside the caller's transaction; a stored automation event id is refused by the schema."""
        cursor = await self.db.execute(
            "INSERT INTO feeder_refills (refilled_at, camera_name, source, note, source_event_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                serialize_storage_datetime(refill.refilled_at),
                refill.camera_name,
                refill.source,
                refill.note,
                refill.source_event_id,
                serialize_storage_datetime(utc_naive_now().replace(microsecond=0)),
            ),
        )
        refill_id = cursor.lastrowid
        await cursor.close()
        stored = await self.get(refill_id) if refill_id is not None else None
        if stored is None:
            raise RuntimeError("A stored refill could not be read back")
        return stored

    async def in_window(
        self, start: datetime, end: datetime, *, limit: int, offset: int
    ) -> tuple[list[StoredRefill], int]:
        """One page of the refills between two times inclusive, newest first, and how many there are."""
        bounds = (serialize_storage_datetime(start), serialize_storage_datetime(end))
        async with self.db.execute(
            "SELECT COUNT(*) FROM feeder_refills WHERE refilled_at BETWEEN ? AND ?", bounds
        ) as cursor:
            row = await cursor.fetchone()
        total = int(row[0]) if row else 0
        async with self.db.execute(
            f"SELECT {_COLUMNS} FROM feeder_refills WHERE refilled_at BETWEEN ? AND ?"
            " ORDER BY refilled_at DESC, id DESC LIMIT ? OFFSET ?",
            (*bounds, limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
        return [_from_row(row) for row in rows], total

    async def delete(self, refill_id: int) -> bool:
        cursor = await self.db.execute("DELETE FROM feeder_refills WHERE id = ?", (refill_id,))
        deleted = cursor.rowcount == 1
        await cursor.close()
        await self.db.commit()
        return deleted
