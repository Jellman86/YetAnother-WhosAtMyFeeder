"""The maintenance stats endpoint previews what a shorter history retention would delete."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.repositories.detection_repository import DetectionRepository


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def owner_keeping_everything():
    original = (
        settings.auth.enabled,
        settings.maintenance.retention_days,
        settings.media_cache.per_species_minimum,
        settings.maintenance.cleanup_enabled,
    )
    settings.auth.enabled = False
    settings.maintenance.retention_days = 0
    settings.media_cache.per_species_minimum = 0
    settings.maintenance.cleanup_enabled = True
    yield
    (
        settings.auth.enabled,
        settings.maintenance.retention_days,
        settings.media_cache.per_species_minimum,
        settings.maintenance.cleanup_enabled,
    ) = original


def _stamp(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")


@pytest_asyncio.fixture
async def history():
    """Ten-day-old robins (one favourite, one hidden), an old dunnock, and a robin from yesterday."""
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detection_favorites")
            await db.execute("DELETE FROM detections")
            rows = [
                ("robin_old_a", _stamp(10), "Robin", 0),
                ("robin_old_b", _stamp(11), "Robin", 0),
                ("robin_old_hidden", _stamp(12), "Robin", 1),
                ("robin_old_favourite", _stamp(13), "Robin", 0),
                ("dunnock_old", _stamp(20), "Dunnock", 0),
                ("robin_recent", _stamp(1), "Robin", 0),
            ]
            for event, when, name, hidden in rows:
                await db.execute(
                    """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score,
                       display_name, category_name, is_hidden)
                       VALUES (?, 'cam', ?, 1, 0.9, ?, 'bird', ?)""",
                    (event, when, name, hidden),
                )
            await db.commit()
            await DetectionRepository(db).favorite_detection("robin_old_favourite")
        yield
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detection_favorites")
            await db.execute("DELETE FROM detections")
            await db.commit()
        await close_db()


async def _detection_count() -> int:
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) FROM detections") as cursor:
            return (await cursor.fetchone())[0]


@pytest.mark.asyncio
async def test_stats_without_a_preview_report_only_the_saved_policy(client: httpx.AsyncClient, history):
    response = await client.get("/api/maintenance/stats")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["retention_days"] == 0
    assert payload["detections_to_cleanup"] == 0
    assert payload["preview_retention_days"] is None
    assert payload["preview_detections_to_cleanup"] is None
    assert payload["automatic_cleanup"] is True


@pytest.mark.asyncio
async def test_stats_say_when_automatic_cleanup_is_switched_off(client: httpx.AsyncClient, history):
    settings.maintenance.cleanup_enabled = False
    response = await client.get("/api/maintenance/stats", params={"retention_days": 7})
    assert response.status_code == 200, response.text
    assert response.json()["automatic_cleanup"] is False


@pytest.mark.asyncio
async def test_a_shorter_window_counts_old_rows_including_hidden_but_not_favourites(client: httpx.AsyncClient, history):
    response = await client.get("/api/maintenance/stats", params={"retention_days": 7})
    assert response.status_code == 200, response.text
    payload = response.json()
    # Saved policy still keeps everything: the preview never leaks into the saved figures.
    assert payload["retention_days"] == 0
    assert payload["detections_to_cleanup"] == 0
    assert payload["preview_retention_days"] == 7
    assert payload["preview_detections_to_cleanup"] == 4
    assert await _detection_count() == 6


@pytest.mark.asyncio
async def test_the_preview_keeps_the_newest_of_each_species_like_the_cleanup(client: httpx.AsyncClient, history):
    settings.media_cache.per_species_minimum = 2
    response = await client.get("/api/maintenance/stats", params={"retention_days": 7})
    assert response.status_code == 200, response.text
    payload = response.json()
    # The floor holds robin_recent and robin_old_a, and the lone dunnock.
    assert payload["preview_detections_to_cleanup"] == 2
    assert payload["kept_newest_per_species"] == 2


@pytest.mark.asyncio
async def test_a_preview_of_keep_everything_deletes_nothing(client: httpx.AsyncClient, history):
    settings.maintenance.retention_days = 7
    response = await client.get("/api/maintenance/stats", params={"retention_days": 0})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["detections_to_cleanup"] == 4
    assert payload["preview_retention_days"] == 0
    assert payload["preview_detections_to_cleanup"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [-1, 10_000_000])
async def test_an_impossible_preview_window_is_rejected(client: httpx.AsyncClient, history, days: int):
    response = await client.get("/api/maintenance/stats", params={"retention_days": days})
    assert response.status_code == 422
