"""Facet counts for the Explorer filter bar."""

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


async def _favourite(frigate_event: str) -> None:
    async with get_db() as db:
        cursor = await db.execute("SELECT id FROM detections WHERE frigate_event = ?", (frigate_event,))
        row = await cursor.fetchone()
        await cursor.close()
        await db.execute("INSERT INTO detection_favorites (detection_id) VALUES (?)", (row[0],))
        await db.commit()


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
async def test_species_counts_follow_the_canonical_grouping():
    # Two spellings of one species must count as one row, not two.
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

    counts = {row[0]: row[4] for row in rows}
    assert sum(counts.values()) == 3
    assert max(counts.values()) == 2


@pytest.mark.asyncio
async def test_hidden_detections_are_not_counted():
    await _insert(frigate_event="visible")
    await _insert(frigate_event="hidden", is_hidden=1)

    async with get_db() as db:
        repo = DetectionRepository(db)
        species = await repo.get_unique_species_with_taxonomy()
        cameras = await repo.get_camera_counts()
        totals = await repo.get_facet_totals()

    assert sum(row[4] for row in species) == 1
    assert cameras == {"birdcam": 1}
    assert totals["total"] == 1


@pytest.mark.asyncio
async def test_camera_counts_are_per_camera():
    await _insert(frigate_event="one", camera_name="birdcam")
    await _insert(frigate_event="two", camera_name="birdcam")
    await _insert(frigate_event="three", camera_name="nestcam")

    async with get_db() as db:
        cameras = await DetectionRepository(db).get_camera_counts()

    assert cameras == {"birdcam": 2, "nestcam": 1}


@pytest.mark.asyncio
async def test_totals_cover_the_only_facets():
    await _insert(frigate_event="plain")
    await _insert(frigate_event="fav")
    await _favourite("fav")
    await _insert(frigate_event="audio", audio_confirmed=1)
    await _insert(frigate_event="clip", video_classification_status="completed")

    async with get_db() as db:
        totals = await DetectionRepository(db).get_facet_totals()

    assert totals == {"total": 4, "favorites": 1, "audio_matched": 1, "video_analysed": 1}


@pytest.mark.asyncio
async def test_empty_database_reports_zeroes_rather_than_failing():
    async with get_db() as db:
        repo = DetectionRepository(db)
        assert await repo.get_camera_counts() == {}
        assert await repo.get_facet_totals() == {
            "total": 0,
            "favorites": 0,
            "audio_matched": 0,
            "video_analysed": 0,
        }
