"""Choosing which detections a scan re-checks.

The old scan read every `frigate_event` in the table and asked Frigate about
each one, every cycle. `frigate_last_checked_at` was written but never read, so
nothing could tell a row checked an hour ago from one checked never (#254).
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.repositories.detection_repository import DetectionRepository


@pytest_asyncio.fixture(autouse=True)
async def db_ready():
    await init_db()
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.commit()
    try:
        yield
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.commit()
        await close_db()


async def _insert(event_id: str, *, checked_at, status="present", camera="cam1"):
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, frigate_status, frigate_last_checked_at
            ) VALUES (?, 1, 0.9, 'Robin', 'Robin', ?, ?, 0, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(sep=" "),
                event_id,
                camera,
                status,
                checked_at.isoformat(sep=" ") if checked_at else None,
            ),
        )
        await db.commit()


def _ago(**kw):
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(**kw)


@pytest.mark.asyncio
async def test_only_rows_not_checked_recently_are_offered():
    """Re-asking Frigate about a row checked minutes ago is a wasted request."""
    await _insert("fresh", checked_at=_ago(hours=1))
    await _insert("stale", checked_at=_ago(days=9))

    async with get_db() as db:
        rows = await DetectionRepository(db).get_stale_frigate_check_candidates(limit=50, checked_before=_ago(days=1))

    assert [r["frigate_event"] for r in rows] == ["stale"]


@pytest.mark.asyncio
async def test_a_row_never_checked_is_offered_first():
    """A NULL is not "checked long ago", it is "no one has ever looked"."""
    await _insert("never", checked_at=None)
    await _insert("old", checked_at=_ago(days=30))

    async with get_db() as db:
        rows = await DetectionRepository(db).get_stale_frigate_check_candidates(limit=50, checked_before=_ago(days=1))

    assert [r["frigate_event"] for r in rows] == ["never", "old"]


@pytest.mark.asyncio
async def test_a_detection_already_known_missing_is_not_asked_about_again():
    """Frigate does not un-retire an event.

    Without this the scan re-asks about every row it has already resolved, and
    on a year of history against days of Frigate retention that is nearly the
    whole table, forever.
    """
    await _insert("gone", checked_at=_ago(days=30), status="missing")
    await _insert("here", checked_at=_ago(days=30), status="present")

    async with get_db() as db:
        rows = await DetectionRepository(db).get_stale_frigate_check_candidates(limit=50, checked_before=_ago(days=1))

    assert [r["frigate_event"] for r in rows] == ["here"]


@pytest.mark.asyncio
async def test_the_batch_is_capped_and_takes_the_oldest_first():
    """Bounded per run, and the least recently known truth goes first."""
    for i in range(6):
        await _insert(f"e{i}", checked_at=_ago(days=30 - i))

    async with get_db() as db:
        rows = await DetectionRepository(db).get_stale_frigate_check_candidates(limit=3, checked_before=_ago(days=1))

    assert [r["frigate_event"] for r in rows] == ["e0", "e1", "e2"]


@pytest.mark.asyncio
async def test_manual_observations_are_never_asked_about():
    """A manual observation has no Frigate event to ask about; asking would
    produce a 404 and mark an owner's own record missing."""
    await _insert("manual_abc", checked_at=_ago(days=30))
    await _insert("real", checked_at=_ago(days=30))

    async with get_db() as db:
        rows = await DetectionRepository(db).get_stale_frigate_check_candidates(limit=50, checked_before=_ago(days=1))

    assert [r["frigate_event"] for r in rows] == ["real"]


@pytest.mark.asyncio
async def test_the_remaining_backlog_is_countable():
    """An owner enabling this on a large history needs to see it draining."""
    for i in range(5):
        await _insert(f"p{i}", checked_at=_ago(days=10))
    await _insert("done", checked_at=_ago(days=10), status="missing")

    async with get_db() as db:
        pending = await DetectionRepository(db).count_stale_frigate_check_candidates(checked_before=_ago(days=1))

    assert pending == 5


@pytest.mark.asyncio
async def test_the_camera_is_returned_so_the_scan_need_not_re_read_the_row():
    async with get_db() as db:
        await db.execute("DELETE FROM detections")
        await db.commit()
    await _insert("withcam", checked_at=_ago(days=10), camera="backyard")

    async with get_db() as db:
        rows = await DetectionRepository(db).get_stale_frigate_check_candidates(limit=5, checked_before=_ago(days=1))

    assert rows[0]["camera_name"] == "backyard"


@pytest.mark.asyncio
async def test_confirming_a_present_detection_advances_its_check_time():
    """`mark_frigate_present` only touches rows that are not already cleanly
    present — it restores, it does not confirm. Without a way to record "I asked
    about this and it is fine", a healthy row stays permanently stale and every
    scan spends its whole batch re-asking about the same detections while the
    real backlog never moves.
    """
    stale = _ago(days=30)
    await _insert("confirmed", checked_at=stale, status="present")

    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.record_frigate_check("confirmed", checked_at=_ago(seconds=0))
        cur = await db.execute(
            "SELECT frigate_status, frigate_last_checked_at FROM detections WHERE frigate_event = ?",
            ("confirmed",),
        )
        status, checked = await cur.fetchone()

    assert status == "present", "Confirming must not disturb the status"
    assert checked > stale.isoformat(sep=" ")

    async with get_db() as db:
        remaining = await DetectionRepository(db).get_stale_frigate_check_candidates(
            limit=50, checked_before=_ago(days=1)
        )
    assert remaining == [], "A just-confirmed detection must drop out of the backlog"
