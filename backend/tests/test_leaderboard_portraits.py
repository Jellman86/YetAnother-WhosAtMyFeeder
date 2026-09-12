"""The leaderboard shows this feeder's own photograph of each leading species: the newest
stored crop, and nothing when there is none, so a reference image can stand in honestly."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database import close_db, get_db, init_db
from app.main import app
from app.routers.species import clear_portraits_cache

SOURCES = {
    "dunnock_new": "high_quality_snapshot",  # whole scene: skipped
    "dunnock_old": "hq_candidate_model_crop",  # the crop that stands in
    "robin_new": "frigate_snapshot_cropped",
    "sparrow_only": "hq_candidate_full_frame",  # no crop at all: left out
}


async def _meta(event_id: str) -> dict | None:
    source = SOURCES.get(event_id)
    return {"source": source} if source else None


@pytest_asyncio.fixture
async def seeded_db():
    await init_db()
    clear_portraits_cache()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detection_favorites")
            await db.execute("DELETE FROM detections")
            await db.execute(
                """
                INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name, is_hidden)
                VALUES
                ('dunnock_new', 'cam1', datetime('now', '-1 hour'), 1, 0.9, 'Dunnock', 'bird', 0),
                ('dunnock_old', 'cam1', datetime('now', '-2 days'), 1, 0.8, 'Dunnock', 'bird', 0),
                ('dunnock_older', 'cam1', datetime('now', '-3 days'), 1, 0.8, 'Dunnock', 'bird', 0),
                ('robin_new', 'cam1', datetime('now', '-5 hours'), 1, 0.9, 'European Robin', 'bird', 0),
                ('sparrow_only', 'cam1', datetime('now', '-6 hours'), 1, 0.7, 'House Sparrow', 'bird', 0),
                ('sparrow_more', 'cam1', datetime('now', '-7 hours'), 1, 0.7, 'House Sparrow', 'bird', 0)
                """
            )
            await db.commit()
        yield
    finally:
        clear_portraits_cache()
        await close_db()


@pytest.fixture
def media_cache_on():
    original = (settings.media_cache.enabled, settings.media_cache.cache_snapshots)
    settings.media_cache.enabled = True
    settings.media_cache.cache_snapshots = True
    yield
    settings.media_cache.enabled, settings.media_cache.cache_snapshots = original


@pytest.mark.asyncio
async def test_each_leading_species_gets_its_newest_crop_or_nothing(seeded_db, media_cache_on):
    with patch("app.services.media_cache.media_cache.get_snapshot_metadata", new=AsyncMock(side_effect=_meta)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/leaderboard/portraits?span=week")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["span"] == "week"
    by_species = {p["species"]: p for p in body["portraits"]}
    # Dunnock leads with three visits; its newest frame is a whole scene, so the older crop stands in.
    assert by_species["Dunnock"]["frigate_event"] == "dunnock_old"
    assert by_species["Dunnock"]["image_url"] == "/api/about/showcase/dunnock_old.jpg"
    assert by_species["European Robin"]["frigate_event"] == "robin_new"
    # A species with no stored crop is left out rather than shown as a whole scene.
    assert "House Sparrow" not in by_species


@pytest.mark.asyncio
async def test_the_limit_ranks_by_the_window_and_the_result_is_cached(seeded_db, media_cache_on):
    reads = AsyncMock(side_effect=_meta)
    with patch("app.services.media_cache.media_cache.get_snapshot_metadata", new=reads):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            first = await client.get("/api/leaderboard/portraits?span=month&limit=1")
            second = await client.get("/api/leaderboard/portraits?span=month&limit=1")
    assert [p["species"] for p in first.json()["portraits"]] == ["Dunnock"]
    assert second.json() == first.json()
    assert reads.await_count == 2  # the second request came from the cache


@pytest.mark.asyncio
async def test_no_media_cache_means_no_portraits(seeded_db):
    original = settings.media_cache.enabled
    settings.media_cache.enabled = False
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.get("/api/leaderboard/portraits?span=all")
    finally:
        settings.media_cache.enabled = original
    assert res.json() == {"span": "all", "portraits": []}
