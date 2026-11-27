"""Species and camera options for the Explorer filter bar; their counts are tested with the route."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.database import get_db, init_db, close_db
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
        await close_db()


async def _insert(**overrides):
    row = {
        "detection_time": datetime.now(timezone.utc) - timedelta(hours=1),
        "detection_index": 0,
        "score": 0.9,
        "display_name": "Eurasian Blackbird",
        "category_name": "bird",
        "frigate_event": f"evt-{overrides.get('frigate_event', id(overrides))}",
        "camera_name": "birdcam",
        "is_hidden": 0,
        "audio_confirmed": 0,
        "scientific_name": "Turdus merula",
        "common_name": "Eurasian Blackbird",
        "taxa_id": 12716,
    }
    row.update(overrides)
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    async with get_db() as db:
        await db.execute(f"INSERT INTO detections ({columns}) VALUES ({placeholders})", tuple(row.values()))
        await db.commit()


@pytest.mark.asyncio
async def test_species_options_follow_the_canonical_grouping():
    # Two spellings of one species must be one option, not two.
    await _insert(frigate_event="a", display_name="Eurasian Blackbird")
    await _insert(frigate_event="b", display_name="Blackbird")
    await _insert(
        frigate_event="c",
        display_name="Dunnock",
        scientific_name="Prunella modularis",
        common_name="Dunnock",
        taxa_id=13858,
    )

    async with get_db() as db:
        rows = await DetectionRepository(db).get_unique_species_with_taxonomy()

    assert sorted(row[3] for row in rows) == [12716, 13858]


@pytest.mark.asyncio
async def test_hidden_records_are_offered_only_in_the_hidden_view():
    await _insert(frigate_event="visible")
    await _insert(
        frigate_event="hidden",
        is_hidden=1,
        display_name="Dunnock",
        scientific_name="Prunella modularis",
        taxa_id=13858,
        camera_name="shed",
    )

    async with get_db() as db:
        repo = DetectionRepository(db)
        visible = await repo.get_unique_species_with_taxonomy()
        hidden = await repo.get_unique_species_with_taxonomy(hidden=True)
        assert await repo.get_unique_cameras() == ["birdcam"]
        assert await repo.get_unique_cameras(hidden=True) == ["shed"]
        assert await repo.has_hidden_detections()

    assert [row[3] for row in visible] == [12716]
    assert [row[3] for row in hidden] == [13858]


@pytest.mark.asyncio
async def test_an_empty_history_offers_nothing_and_holds_nothing_hidden():
    async with get_db() as db:
        repo = DetectionRepository(db)
        assert await repo.get_unique_species_with_taxonomy() == []
        assert await repo.get_unique_cameras() == []
        assert not await repo.has_hidden_detections()
