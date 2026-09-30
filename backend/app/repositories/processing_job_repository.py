"""Persistent retry state for bounded background processing jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite


@dataclass(frozen=True)
class ProcessingJobState:
    pipeline: str
    event_id: str
    status: str
    attempt_count: int
    retry_after: Optional[datetime]
    last_error: Optional[str]
    revision: int = 0

    def can_attempt(self, now: datetime) -> bool:
        if self.status in {"succeeded", "terminal"}:
            return False
        if self.retry_after is None:
            return True
        comparable_now = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        comparable_retry = (
            self.retry_after if self.retry_after.tzinfo is not None else self.retry_after.replace(tzinfo=timezone.utc)
        )
        return comparable_now >= comparable_retry


def _parse_datetime(value: object) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class ProcessingJobRepository:
    """Read and update persistent state for an event-scoped processing pipeline."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def enqueue(self, pipeline: str, event_id: str, *, force: bool = False) -> bool:
        """Persist intent before admitting work into the bounded memory queue."""
        await self.db.execute(
            """INSERT INTO processing_job_state (pipeline,event_id,status,attempt_count,updated_at)
            SELECT ?, frigate_event, 'queued', 0, CURRENT_TIMESTAMP FROM detections WHERE frigate_event=?
            ON CONFLICT(pipeline,event_id) DO UPDATE SET status='queued', retry_after=NULL,
                last_error=NULL, attempt_count=0, revision=processing_job_state.revision+1, updated_at=CURRENT_TIMESTAMP
            WHERE ?""",
            (pipeline, event_id, int(force)),
        )
        async with self.db.execute("SELECT changes()") as cursor:
            row = await cursor.fetchone()
        await self.db.commit()
        return bool(row and row[0])

    async def list_due(self, pipeline: str, now: datetime, *, limit: int = 100) -> list[str]:
        async with self.db.execute(
            """SELECT event_id FROM processing_job_state WHERE pipeline=?
            AND status IN ('queued','retryable') AND (retry_after IS NULL OR julianday(retry_after) <= julianday(?))
            ORDER BY updated_at, event_id LIMIT ?""",
            (pipeline, now.isoformat(), limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [str(row[0]) for row in rows]

    async def pending_count(self, pipeline: str) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM processing_job_state WHERE pipeline=? AND status IN ('queued','retryable')",
            (pipeline,),
        ) as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def mark_storage_evicted(self, pipeline: str, event_id: str) -> None:
        """Caller owns the transaction with filesystem deletion and favourite recheck."""
        await self.db.execute(
            """INSERT INTO processing_job_state (pipeline,event_id,status,attempt_count,last_error,revision)
            SELECT ?,frigate_event,'terminal',0,'storage_evicted',0 FROM detections WHERE frigate_event=?
            ON CONFLICT(pipeline,event_id) DO UPDATE SET status='terminal',retry_after=NULL,
                last_error='storage_evicted',revision=processing_job_state.revision+1""",
            (pipeline, event_id),
        )

    async def list_pending(self, pipeline: str, *, limit: int = 500) -> list[dict]:
        async with self.db.execute(
            """SELECT event_id,status,retry_after,updated_at FROM processing_job_state
            WHERE pipeline=? AND status IN ('queued','retryable') ORDER BY updated_at,event_id LIMIT ?""",
            (pipeline, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            {"event_id": row[0], "status": row[1], "retry_after": row[2], "updated_at": str(row[3])} for row in rows
        ]

    async def get(self, pipeline: str, event_id: str) -> Optional[ProcessingJobState]:
        async with self.db.execute(
            """
            SELECT pipeline, event_id, status, attempt_count, retry_after, last_error, revision
            FROM processing_job_state
            WHERE pipeline = ? AND event_id = ?
            """,
            (pipeline, event_id),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return ProcessingJobState(
            pipeline=str(row[0]),
            event_id=str(row[1]),
            status=str(row[2]),
            attempt_count=int(row[3] or 0),
            retry_after=_parse_datetime(row[4]),
            last_error=str(row[5]) if row[5] is not None else None,
            revision=int(row[6] or 0),
        )

    async def record_success(self, pipeline: str, event_id: str, *, expected_revision: int | None = None) -> None:
        await self.db.execute(
            """
            INSERT INTO processing_job_state (
                pipeline, event_id, status, attempt_count, retry_after, last_error, updated_at
            ) VALUES (?, ?, 'succeeded', 0, NULL, NULL, CURRENT_TIMESTAMP)
            ON CONFLICT(pipeline, event_id) DO UPDATE SET
                status = 'succeeded',
                retry_after = NULL,
                last_error = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE ? IS NULL OR processing_job_state.revision = ?
            """,
            (pipeline, event_id, expected_revision, expected_revision),
        )
        await self.db.commit()

    async def record_failure(
        self,
        pipeline: str,
        event_id: str,
        *,
        error: str,
        retry_delays_seconds: tuple[float, ...],
        now: Optional[datetime] = None,
        expected_revision: int | None = None,
    ) -> ProcessingJobState:
        current = await self.get(pipeline, event_id)
        if current is not None and expected_revision is not None and current.revision != expected_revision:
            return current
        attempt_count = int(current.attempt_count if current is not None else 0) + 1
        timestamp = now or datetime.now(timezone.utc)
        if attempt_count > len(retry_delays_seconds):
            status = "terminal"
            retry_after = None
        else:
            status = "retryable"
            retry_after = timestamp + timedelta(seconds=max(0.0, retry_delays_seconds[attempt_count - 1]))

        await self.db.execute(
            """
            INSERT INTO processing_job_state (
                pipeline, event_id, status, attempt_count, retry_after, last_error, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(pipeline, event_id) DO UPDATE SET
                status = excluded.status,
                attempt_count = excluded.attempt_count,
                retry_after = excluded.retry_after,
                last_error = excluded.last_error,
                updated_at = CURRENT_TIMESTAMP
            WHERE ? IS NULL OR processing_job_state.revision = ?
            """,
            (
                pipeline,
                event_id,
                status,
                attempt_count,
                retry_after,
                str(error)[:500],
                expected_revision,
                expected_revision,
            ),
        )
        await self.db.commit()
        return ProcessingJobState(
            pipeline=pipeline,
            event_id=event_id,
            status=status,
            attempt_count=attempt_count,
            retry_after=retry_after,
            last_error=str(error)[:500],
        )
