from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from app.repositories.processing_job_repository import ProcessingJobRepository


async def _create_table(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE processing_job_state (
            pipeline TEXT NOT NULL,
            event_id TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            retry_after TIMESTAMP,
            last_error TEXT,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (pipeline, event_id)
        )
        """
    )
    await db.commit()


@pytest.mark.asyncio
async def test_processing_job_retry_state_becomes_terminal_after_bounded_attempts():
    now = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    async with aiosqlite.connect(":memory:") as db:
        await _create_table(db)
        repo = ProcessingJobRepository(db)

        first = await repo.record_failure(
            "high_quality_snapshot",
            "evt-1",
            error="clip_unavailable",
            retry_delays_seconds=(300.0, 900.0, 2700.0),
            now=now,
        )
        assert first.status == "retryable"
        assert first.attempt_count == 1
        assert first.retry_after == now + timedelta(seconds=300)
        assert first.can_attempt(now + timedelta(seconds=299)) is False
        assert first.can_attempt(now + timedelta(seconds=300)) is True

        await repo.record_failure(
            "high_quality_snapshot",
            "evt-1",
            error="clip_unavailable",
            retry_delays_seconds=(300.0, 900.0, 2700.0),
            now=now,
        )
        await repo.record_failure(
            "high_quality_snapshot",
            "evt-1",
            error="clip_unavailable",
            retry_delays_seconds=(300.0, 900.0, 2700.0),
            now=now,
        )
        terminal = await repo.record_failure(
            "high_quality_snapshot",
            "evt-1",
            error="clip_unavailable",
            retry_delays_seconds=(300.0, 900.0, 2700.0),
            now=now,
        )

        assert terminal.status == "terminal"
        assert terminal.attempt_count == 4
        assert terminal.retry_after is None
        assert terminal.can_attempt(now + timedelta(days=1)) is False


@pytest.mark.asyncio
async def test_processing_job_success_clears_failure_and_retry_deadline():
    now = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    async with aiosqlite.connect(":memory:") as db:
        await _create_table(db)
        repo = ProcessingJobRepository(db)
        await repo.record_failure(
            "high_quality_snapshot",
            "evt-2",
            error="frame_extract_failed",
            retry_delays_seconds=(300.0,),
            now=now,
        )

        await repo.record_success("high_quality_snapshot", "evt-2")
        state = await repo.get("high_quality_snapshot", "evt-2")

        assert state is not None
        assert state.status == "succeeded"
        assert state.attempt_count == 1
        assert state.retry_after is None
        assert state.last_error is None
