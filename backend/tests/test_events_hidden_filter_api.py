"""The Explorer's Hidden facet promises "only hidden" and must deliver it.

Upstream #347: hiding an event and selecting the Hidden facet changed
nothing, because the UI's toggle mapped to include_hidden — which adds
hidden rows to the full list instead of filtering to them. These tests
pin the only_hidden contract end to end.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import close_db, get_db, init_db
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detections")
            await db.execute("""
                INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name, is_hidden)
                VALUES
                ('event_visible_1', 'cam1', '2026-01-01 10:00:00', 1, 0.9, 'Robin', 'Robin', 0),
                ('event_visible_2', 'cam1', '2026-01-01 10:05:00', 1, 0.9, 'Blue Jay', 'Blue Jay', 0),
                ('event_hidden', 'cam1', '2026-01-01 10:10:00', 1, 0.9, 'House Sparrow', 'House Sparrow', 1)
            """)
            await db.commit()
        yield
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_events_only_hidden_returns_just_the_hidden_rows():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/events?only_hidden=true")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["frigate_event"] == "event_hidden"
        assert data[0]["is_hidden"] is True


@pytest.mark.asyncio
async def test_events_default_still_excludes_hidden():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/events")
        assert res.status_code == 200
        assert {d["frigate_event"] for d in res.json()} == {"event_visible_1", "event_visible_2"}


@pytest.mark.asyncio
async def test_events_include_hidden_still_returns_everything():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/events?include_hidden=true")
        assert res.status_code == 200
        assert len(res.json()) == 3


@pytest.mark.asyncio
async def test_events_count_only_hidden_counts_just_the_hidden_rows():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/events/count?only_hidden=true")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] == 1
        assert data["filtered"] is True


@pytest.mark.asyncio
async def test_events_only_hidden_composes_with_other_filters():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/events?only_hidden=true&species=Robin")
        assert res.status_code == 200
        assert res.json() == []

        res = await client.get("/api/events?only_hidden=true&species=House%20Sparrow")
        assert res.status_code == 200
        assert [d["frigate_event"] for d in res.json()] == ["event_hidden"]
