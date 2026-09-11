"""The per-species floor (#178): the newest N of each species, and their cached photographs,
outlive the age window. Canonical-taxon based, so one bird under two names has one floor."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.config import Settings
from app.database import close_db, get_db, init_db
from app.repositories.detection_repository import DetectionRepository


def test_the_floor_is_configurable_from_the_environment(monkeypatch):
    monkeypatch.setenv("MEDIA_CACHE__PER_SPECIES_MINIMUM", "25")
    assert Settings.load().media_cache.per_species_minimum == 25


def test_the_floor_is_off_by_default():
    assert Settings.load().media_cache.per_species_minimum == 0


@pytest_asyncio.fixture
async def history():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM detection_favorites")
            await db.execute("DELETE FROM detections")
            rows = []
            # Six robins under two display names but one taxon: one species to the floor.
            for i in range(6):
                name = "Robin" if i % 2 else "European Robin"
                rows.append((f"robin_{i}", f"2026-01-0{i + 1} 10:00:00", name, 7999, 0))
            # Three dunnocks by name only, one of them hidden.
            # A robin the catalogue knows by name but that carries no taxa_id of its own: the same bird.
            rows.append(("robin_named", "2026-01-07 10:00:00", "Robin", None, 0))
            rows.append(("dunnock_0", "2026-01-01 09:00:00", "Dunnock", None, 0))
            rows.append(("dunnock_1", "2026-01-02 09:00:00", "Dunnock", None, 1))
            rows.append(("dunnock_2", "2026-01-03 09:00:00", "Dunnock", None, 0))
            await db.execute("DELETE FROM taxonomy_cache WHERE scientific_name = 'Erithacus rubecula'")
            await db.execute(
                "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES ('Erithacus rubecula', 'Robin', 7999)"
            )
            for event, when, name, taxa, hidden in rows:
                scientific = "Erithacus rubecula" if event == "robin_named" else None
                await db.execute(
                    """INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score,
                       display_name, category_name, taxa_id, scientific_name, is_hidden)
                       VALUES (?, 'cam', ?, 1, 0.9, ?, 'bird', ?, ?, ?)""",
                    (event, when, name, taxa, scientific, hidden),
                )
            await db.commit()
        yield
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_the_floor_partitions_by_taxon_and_ignores_hidden_rows(history):
    async with get_db() as db:
        floor = await DetectionRepository(db).get_species_floor_frigate_event_ids(2)
    # Newest two robins across both names and the catalogue-resolved one; newest two visible
    # dunnocks (the hidden one neither counts nor is kept).
    assert floor == {"robin_named", "robin_5", "dunnock_2", "dunnock_0"}
    async with get_db() as db:
        assert await DetectionRepository(db).get_species_floor_frigate_event_ids(0) == set()


@pytest.mark.asyncio
async def test_age_cleanup_keeps_the_floor_and_the_count_agrees(history):
    cutoff = datetime(2026, 2, 1, tzinfo=timezone.utc)  # everything is older than this
    async with get_db() as db:
        repo = DetectionRepository(db)
        expected = await repo.get_count(end_date=cutoff, include_hidden=True, exclude_species_floor=2)
        deleted = await repo.delete_older_than(cutoff, preserve_favorites=True, species_floor=2)
        remaining = {row[0] for row in await (await db.execute("SELECT frigate_event FROM detections")).fetchall()}
    assert deleted == expected == 6
    assert remaining == {"robin_named", "robin_5", "dunnock_2", "dunnock_0"}


@pytest.mark.asyncio
async def test_without_a_floor_only_favourites_survive(history):
    cutoff = datetime.now(timezone.utc) + timedelta(days=1)
    async with get_db() as db:
        repo = DetectionRepository(db)
        await repo.favorite_detection("dunnock_0")
        deleted = await repo.delete_older_than(cutoff, preserve_favorites=True, species_floor=0)
        remaining = {row[0] for row in await (await db.execute("SELECT frigate_event FROM detections")).fetchall()}
    assert deleted == 9
    assert remaining == {"dunnock_0"}
