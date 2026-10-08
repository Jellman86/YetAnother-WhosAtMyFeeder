"""Durable one-scene bird scans with revision-fenced result publication."""

from dataclasses import dataclass
from uuid import uuid4
from collections.abc import Sequence

import aiosqlite


SAFE_SCAN_ERRORS = frozenset(
    {"scan_failed", "media_changed", "reviewed_other_frame", "interrupted", "detection_removed"}
)
_INPUT_COLUMNS = "candidate_id,image_ref,content_sha256,media_version,clip_variant,frame_index"


class BirdScanBusyError(ValueError):
    """Another immutable scene is already queued or running for this event."""


class BirdScanNotFoundError(ValueError):
    """The parent detection was removed or never existed."""


@dataclass(frozen=True)
class BirdScanJob:
    event_id: str
    generation: str
    candidate_id: str
    image_ref: str
    content_sha256: str
    media_version: str
    clip_variant: str
    frame_index: int
    status: str
    revision: int
    created_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None
    result_count: int | None
    retained_previous: bool
    error: str | None


def _job(row: Sequence | None, description: Sequence[Sequence] | None) -> BirdScanJob | None:
    if row is None:
        return None
    if description is None:
        raise ValueError("Scan query returned a row without column metadata")
    fields = dict(zip((column[0] for column in description), row, strict=True))
    fields["event_id"] = fields.pop("frigate_event")
    fields["retained_previous"] = bool(fields["retained_previous"])
    return BirdScanJob(**fields)


def _safe_error(error: str | None) -> str | None:
    return error if error is None or error in SAFE_SCAN_ERRORS else "scan_failed"


def _validate_count(result_count: int) -> None:
    if not isinstance(result_count, int) or isinstance(result_count, bool) or result_count < 0:
        raise ValueError("result_count must be a nonnegative integer")


class BirdScanRepository:
    """Mutations commit by default; publication can share its caller's transaction.

    With ``commit=False``, callers must commit or roll back, and must apply
    observations only after the revision-guarded publication returns True.
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def get(self, event_id: str) -> BirdScanJob | None:
        async with self.db.execute("SELECT * FROM bird_scan_jobs WHERE frigate_event=?", (event_id,)) as cursor:
            return _job(await cursor.fetchone(), cursor.description)

    async def enqueue(
        self,
        event_id: str,
        *,
        candidate_id: str,
        image_ref: str,
        content_sha256: str,
        media_version: str,
        clip_variant: str,
        frame_index: int,
        force: bool = False,
    ) -> BirdScanJob:
        inputs = (candidate_id, image_ref, content_sha256, media_version, clip_variant, frame_index)
        assignments = ",".join(f"{column}=excluded.{column}" for column in _INPUT_COLUMNS.split(","))
        different = " OR ".join(f"bird_scan_jobs.{column} != excluded.{column}" for column in _INPUT_COLUMNS.split(","))
        async with self.db.execute(
            f"""INSERT INTO bird_scan_jobs(frigate_event,generation,{_INPUT_COLUMNS},status)
                SELECT frigate_event,?,?,?,?,?,?,?,'queued' FROM detections WHERE frigate_event=?
                ON CONFLICT(frigate_event) DO UPDATE SET {assignments},status='queued',
                    revision=bird_scan_jobs.revision+1,created_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP,
                    started_at=NULL,completed_at=NULL,result_count=NULL,retained_previous=0,error=NULL
                WHERE bird_scan_jobs.status NOT IN ('queued','running')
                    AND (? OR bird_scan_jobs.status='failed' OR {different})
                RETURNING *""",
            (uuid4().hex, *inputs, event_id, int(force)),
        ) as cursor:
            changed = _job(await cursor.fetchone(), cursor.description)
        # The write transaction keeps admission and this deduplication read atomic.
        current = changed or await self.get(event_id)
        await self.db.commit()
        if current is None:
            raise BirdScanNotFoundError("Detection is unavailable")
        if changed is None and tuple(getattr(current, column) for column in _INPUT_COLUMNS.split(",")) != inputs:
            raise BirdScanBusyError("A different photograph is already being scanned")
        return current

    async def claim_next(self) -> BirdScanJob | None:
        async with self.db.execute(
            """UPDATE bird_scan_jobs SET status='running',revision=revision+1,
                started_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP,error=NULL
                WHERE frigate_event=(SELECT frigate_event FROM bird_scan_jobs WHERE status='queued'
                    ORDER BY created_at,frigate_event LIMIT 1) AND status='queued' RETURNING *"""
        ) as cursor:
            job = _job(await cursor.fetchone(), cursor.description)
        await self.db.commit()
        return job

    async def complete(
        self,
        event_id: str,
        revision: int,
        *,
        expected_generation: str,
        result_count: int,
        retained_previous: bool,
        error: str | None = None,
        commit: bool = True,
    ) -> bool:
        _validate_count(result_count)
        return await self._finish(
            event_id,
            revision,
            expected_generation=expected_generation,
            status="completed",
            result_count=result_count,
            retained_previous=retained_previous,
            error=error,
            commit=commit,
        )

    async def fail(
        self,
        event_id: str,
        revision: int,
        *,
        expected_generation: str,
        error: str,
        retained_previous: bool = False,
        commit: bool = True,
    ) -> bool:
        return await self._finish(
            event_id,
            revision,
            expected_generation=expected_generation,
            status="failed",
            result_count=None,
            retained_previous=retained_previous,
            error=error,
            commit=commit,
        )

    async def _finish(
        self,
        event_id: str,
        revision: int,
        *,
        expected_generation: str,
        status: str,
        result_count: int | None,
        retained_previous: bool,
        error: str | None,
        commit: bool,
    ) -> bool:
        async with self.db.execute(
            """UPDATE bird_scan_jobs SET status=?,result_count=?,retained_previous=?,error=?,
                revision=revision+1,completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                WHERE frigate_event=? AND revision=? AND generation=? AND status='running' RETURNING frigate_event""",
            (status, result_count, int(retained_previous), _safe_error(error), event_id, revision, expected_generation),
        ) as cursor:
            changed = await cursor.fetchone() is not None
        if commit:
            await self.db.commit()
        return changed

    async def recover_running(self) -> int:
        async with self.db.execute(
            """UPDATE bird_scan_jobs SET status='queued',revision=revision+1,started_at=NULL,
                updated_at=CURRENT_TIMESTAMP,error='interrupted' WHERE status='running'"""
        ) as cursor:
            changed = cursor.rowcount
        await self.db.commit()
        return changed

    async def pending_count(self) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) FROM bird_scan_jobs WHERE status IN ('queued','running')"
        ) as cursor:
            return int((await cursor.fetchone())[0])

    async def list_pending(self, *, limit: int = 100) -> list[BirdScanJob]:
        async with self.db.execute(
            """SELECT * FROM bird_scan_jobs WHERE status IN ('queued','running')
                ORDER BY created_at,frigate_event LIMIT ?""",
            (max(1, min(limit, 500)),),
        ) as cursor:
            return [_job(row, cursor.description) for row in await cursor.fetchall()]

    async def record_automatic_completed(
        self,
        event_id: str,
        *,
        candidate_id: str,
        image_ref: str,
        content_sha256: str,
        media_version: str,
        clip_variant: str,
        frame_index: int,
        expected_revision: int | None,
        expected_generation: str | None,
        result_count: int,
        retained_previous: bool,
        error: str | None = None,
        commit: bool = True,
    ) -> bool:
        """Publish automatic evidence only against state observed before its scan.

        None means no job existed before scanning. Existing active work always
        wins; every transition changes its revision, including manual completion.
        """
        _validate_count(result_count)
        if (expected_revision is None) != (expected_generation is None):
            raise ValueError("An existing scan needs both its generation and revision")
        inputs = (candidate_id, image_ref, content_sha256, media_version, clip_variant, frame_index)
        if expected_revision is None:
            query = f"""INSERT INTO bird_scan_jobs(frigate_event,generation,{_INPUT_COLUMNS},status,result_count,
                    retained_previous,error,completed_at)
                SELECT frigate_event,?,?,?,?,?,?,?,'completed',?,?,?,CURRENT_TIMESTAMP
                FROM detections WHERE frigate_event=? ON CONFLICT(frigate_event) DO NOTHING
                RETURNING frigate_event"""
            params = (uuid4().hex, *inputs, result_count, int(retained_previous), _safe_error(error), event_id)
        else:
            assignments = ",".join(f"{column}=?" for column in _INPUT_COLUMNS.split(","))
            query = f"""UPDATE bird_scan_jobs SET {assignments},status='completed',revision=revision+1,
                result_count=?,retained_previous=?,error=?,created_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP,
                started_at=NULL,completed_at=CURRENT_TIMESTAMP
                WHERE frigate_event=? AND revision=? AND generation=? AND status IN ('completed','failed') RETURNING frigate_event"""
            params = (
                *inputs,
                result_count,
                int(retained_previous),
                _safe_error(error),
                event_id,
                expected_revision,
                expected_generation,
            )
        async with self.db.execute(query, params) as cursor:
            changed = await cursor.fetchone() is not None
        if commit:
            await self.db.commit()
        return changed
