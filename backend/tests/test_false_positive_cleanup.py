"""Cleaning up a detection Frigate has withdrawn as a false positive.

`_handle_false_positive` called `repo.delete(...)`, which has never existed on
`DetectionRepository` — the repository has had `delete_by_frigate_event` since
before the handler was written. So every false positive raised AttributeError
into the handler's own `except Exception`, was logged as a cleanup failure, and
left the detection in place.

The cached media is deleted first and that line worked, so the visible result
was a detection that survived with its images gone.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.repositories.detection_repository import DetectionRepository
from app.services.event_processor import EventProcessor


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
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


async def _insert(event_id: str, *, manual_tagged=0):
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged
            ) VALUES (?, 1, 0.9, 'Robin', 'Robin', ?, 'cam1', 0, ?)
            """,
            (datetime.now(timezone.utc).isoformat(sep=" "), event_id, manual_tagged),
        )
        await db.commit()


async def _row(event_id: str):
    async with get_db() as db:
        cur = await db.execute(
            "SELECT is_hidden, display_name, score FROM detections WHERE frigate_event = ?", (event_id,)
        )
        return await cur.fetchone()


def _processor():
    return EventProcessor.__new__(EventProcessor)


@pytest.mark.asyncio
async def test_a_false_positive_is_removed_from_view():
    """The bug: this did nothing at all, silently, for seven months."""
    await _insert("evt-fp")

    with (
        patch("app.services.event_processor.media_cache.delete_cached_media", new=AsyncMock()),
        patch("app.services.broadcaster.broadcaster.broadcast", new=AsyncMock()),
    ):
        await EventProcessor._handle_false_positive(_processor(), "evt-fp")

    row = await _row("evt-fp")
    assert row is not None, "The detection must be kept, not destroyed"
    assert row[0] == 1, "A false positive must not remain visible"


@pytest.mark.asyncio
async def test_the_detection_is_hidden_rather_than_destroyed():
    """§1 prefers soft deletion, and this path has no confirmation in front of
    it: it fires automatically from an MQTT message. Frigate withdrawing its
    claim is good reason to stop showing a detection, and a poor reason to
    destroy an owner's record of it irreversibly. Hidden rows are already
    excluded from the events list and from the daily rollups, so the visible
    result matches a delete while staying recoverable.
    """
    await _insert("evt-keep")

    with (
        patch("app.services.event_processor.media_cache.delete_cached_media", new=AsyncMock()),
        patch("app.services.broadcaster.broadcaster.broadcast", new=AsyncMock()),
    ):
        await EventProcessor._handle_false_positive(_processor(), "evt-keep")

    is_hidden, display_name, score = await _row("evt-keep")
    assert is_hidden == 1
    assert display_name == "Robin", "The species must survive"
    assert score == pytest.approx(0.9), "The score must survive"


@pytest.mark.asyncio
async def test_a_detection_the_owner_tagged_themselves_is_left_alone():
    """A manual tag is the owner asserting this was a real bird. Frigate later
    withdrawing the event is not grounds to overrule them."""
    await _insert("evt-mine", manual_tagged=1)

    with (
        patch("app.services.event_processor.media_cache.delete_cached_media", new=AsyncMock()),
        patch("app.services.broadcaster.broadcaster.broadcast", new=AsyncMock()),
    ):
        await EventProcessor._handle_false_positive(_processor(), "evt-mine")

    assert (await _row("evt-mine"))[0] == 0, "A manually tagged detection must stay visible"


@pytest.mark.asyncio
async def test_the_frontend_is_told_so_an_open_page_stops_showing_it():
    """The broadcast never fired either, because it sat after the failing call."""
    await _insert("evt-sse")

    with (
        patch("app.services.event_processor.media_cache.delete_cached_media", new=AsyncMock()),
        patch("app.services.broadcaster.broadcaster.broadcast", new=AsyncMock()) as broadcast,
    ):
        await EventProcessor._handle_false_positive(_processor(), "evt-sse")

    broadcast.assert_awaited_once()
    payload = broadcast.await_args.args[0]
    assert payload["type"] == "detection_deleted"
    assert payload["data"]["frigate_event"] == "evt-sse"


@pytest.mark.asyncio
async def test_an_unknown_event_is_not_an_error():
    """Frigate can withdraw an event YA-WAMF never stored."""
    with (
        patch("app.services.event_processor.media_cache.delete_cached_media", new=AsyncMock()),
        patch("app.services.broadcaster.broadcaster.broadcast", new=AsyncMock()) as broadcast,
    ):
        await EventProcessor._handle_false_positive(_processor(), "evt-never-seen")

    broadcast.assert_not_awaited()


@pytest.mark.asyncio
async def test_hiding_a_detection_keeps_it_out_of_the_events_list():
    """The property that makes hiding an acceptable stand-in for deleting."""
    await _insert("evt-listed")

    with (
        patch("app.services.event_processor.media_cache.delete_cached_media", new=AsyncMock()),
        patch("app.services.broadcaster.broadcaster.broadcast", new=AsyncMock()),
    ):
        await EventProcessor._handle_false_positive(_processor(), "evt-listed")

    async with get_db() as db:
        visible = await DetectionRepository(db).get_all(limit=50, offset=0)
    assert all(d.frigate_event != "evt-listed" for d in visible)


@pytest.mark.asyncio
async def test_a_repeated_withdrawal_does_not_re_announce_it():
    """Frigate sends several updates per event. Hiding is idempotent, and the
    frontend is told once — a toggle here would have put the detection back on
    show with the second message."""
    await _insert("evt-twice")

    with (
        patch("app.services.event_processor.media_cache.delete_cached_media", new=AsyncMock()),
        patch("app.services.broadcaster.broadcaster.broadcast", new=AsyncMock()) as broadcast,
    ):
        await EventProcessor._handle_false_positive(_processor(), "evt-twice")
        await EventProcessor._handle_false_positive(_processor(), "evt-twice")

    assert broadcast.await_count == 1
    assert (await _row("evt-twice"))[0] == 1, "It must stay hidden, not toggle back"
