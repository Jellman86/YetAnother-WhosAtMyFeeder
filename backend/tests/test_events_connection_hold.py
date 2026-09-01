"""A pooled connection must not be held across a network round trip (#300).

The events list asks Frigate about every event on the page, and it did so
inside the block holding one of five pooled database connections. On a busy
history that hold reached 27 seconds on a real install, and everything else
needing the database queued behind it, which is what the owner experienced as
the whole interface being slow. Resetting the database appeared to fix it
because a small history asks Frigate about fewer events.
"""

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import close_db, get_db, init_db
from app.main import app

FRIGATE_DELAY_SECONDS = 0.4


@pytest_asyncio.fixture(autouse=True)
async def seeded_db():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            for index in range(6):
                await db.execute(
                    """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index,
                       score, display_name, category_name, is_hidden)
                       VALUES (?, 'cam1', ?, 1, 0.9, 'Robin', 'Robin', 0)""",
                    (f"evt_{index}", f"2026-08-31 10:0{index}:00"),
                )
            await db.commit()
        yield
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_frigate_round_trips_do_not_happen_while_a_connection_is_held(monkeypatch):
    from app.routers import events as events_router

    async def slow_frigate(event_id, timeout=None):
        await asyncio.sleep(FRIGATE_DELAY_SECONDS)
        return None, "event_not_found"

    monkeypatch.setattr(events_router.frigate_client, "get_event_with_error", slow_frigate)

    from app.database import get_db_pool_status

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/events?limit=6")
        assert res.status_code == 200

    hold_max_ms = get_db_pool_status()["hold_ms_max"]
    assert hold_max_ms < FRIGATE_DELAY_SECONDS * 1000 * 0.5, (
        f"a connection was held for {hold_max_ms} ms while Frigate took "
        f"{FRIGATE_DELAY_SECONDS * 1000} ms, so the wait was inside the hold"
    )
