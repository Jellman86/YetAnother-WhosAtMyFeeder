"""A species new to this feeder asks for one human confirmation (#310).

A 34% Hadeda Ibis in Ohio is almost certainly a misread, but the only way
to notice was stumbling over it in the Explorer. The endpoint under test
surfaces each species with no confirmed history — recently arrived, few
sightings, never manually tagged — so the review queue can offer it for a
confirm, a correction, or a block.
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
                INSERT INTO detections (frigate_event, camera_name, detection_time, detection_index, score, display_name, category_name, scientific_name, is_hidden, manual_tagged)
                VALUES
                -- One recent sighting, never confirmed: the #310 case.
                ('new_1', 'cam1', datetime('now', '-1 day'), 1, 0.34, 'Hadeda Ibis', 'Hadeda Ibis', 'Bostrychia hagedash', 0, 0),
                -- A second recent sighting of another newcomer, latest wins as the face of the queue row.
                ('new_2a', 'cam1', datetime('now', '-2 days'), 1, 0.41, 'Painted Bunting', 'Painted Bunting', 'Passerina ciris', 0, 0),
                ('new_2b', 'cam2', datetime('now', '-1 hour'), 1, 0.52, 'Painted Bunting', 'Painted Bunting', 'Passerina ciris', 0, 0),
                -- A regular: too many sightings to be new.
                ('reg_1', 'cam1', datetime('now', '-5 days'), 1, 0.9, 'American Robin', 'American Robin', 'Turdus migratorius', 0, 0),
                ('reg_2', 'cam1', datetime('now', '-4 days'), 1, 0.9, 'American Robin', 'American Robin', 'Turdus migratorius', 0, 0),
                ('reg_3', 'cam1', datetime('now', '-3 days'), 1, 0.9, 'American Robin', 'American Robin', 'Turdus migratorius', 0, 0),
                ('reg_4', 'cam1', datetime('now', '-2 days'), 1, 0.9, 'American Robin', 'American Robin', 'Turdus migratorius', 0, 0),
                -- Rare but already confirmed by a person: the question is answered.
                ('conf_1', 'cam1', datetime('now', '-1 day'), 1, 0.4, 'Snowy Owl', 'Snowy Owl', 'Bubo scandiacus', 0, 1),
                -- First seen long ago: stale, not an arrival worth interrupting for.
                ('old_1', 'cam1', datetime('now', '-60 days'), 1, 0.5, 'Gray Catbird', 'Gray Catbird', 'Dumetella carolinensis', 0, 0),
                -- Hidden-only species never asks for anything.
                ('hid_1', 'cam1', datetime('now', '-1 day'), 1, 0.5, 'House Sparrow', 'House Sparrow', 'Passer domesticus', 1, 0),
                -- The unknown label is a different queue's problem.
                ('unk_1', 'cam1', datetime('now', '-1 day'), 1, 0.2, 'Unknown Bird', 'Unknown Bird', NULL, 0, 0)
            """)
            await db.commit()
        yield
    finally:
        await close_db()


@pytest.mark.asyncio
async def test_new_species_queue_lists_unconfirmed_newcomers_only():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/events/new-species")
        assert res.status_code == 200
        data = res.json()
        by_species = {item["display_name"]: item for item in data["items"]}
        assert set(by_species) == {"Hadeda Ibis", "Painted Bunting"}


@pytest.mark.asyncio
async def test_new_species_row_is_the_latest_sighting_and_counts_all():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/events/new-species")
        data = res.json()
        bunting = next(item for item in data["items"] if item["display_name"] == "Painted Bunting")
        assert bunting["frigate_event"] == "new_2b"
        assert bunting["species_sightings"] == 2
        assert bunting["scientific_name"] == "Passerina ciris"
        assert bunting["manual_tagged"] is False


@pytest.mark.asyncio
async def test_new_species_thresholds_are_honoured():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Widen the sighting cap: the Robin's four visits now qualify.
        res = await client.get("/api/events/new-species?max_sightings=10")
        names = {item["display_name"] for item in res.json()["items"]}
        assert "American Robin" in names

        # Widen the window: the long-ago Catbird arrival shows again.
        res = await client.get("/api/events/new-species?window_days=90")
        names = {item["display_name"] for item in res.json()["items"]}
        assert "Gray Catbird" in names
