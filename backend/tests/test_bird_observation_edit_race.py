"""Per-bird owner edits must survive concurrent regeneration."""

import asyncio
from contextlib import closing
from datetime import datetime
import os
import sqlite3

import aiosqlite
import pytest
import pytest_asyncio

from app.repositories.bird_observation_repository import BirdObservationRepository
from app.repositories.detection_repository import DetectionRepository, Detection
from app.services.bird_observation_selection import BirdObservation, BirdObservationSelection


SELECTION = BirdObservationSelection(
    "frigate_snapshot", 0, "whole", (BirdObservation("bird-1", (10, 10, 60, 60), 0.9, "Robin", "Robin", 0.91),)
)


@pytest_asyncio.fixture
async def fixture_birds(tmp_path):
    path = tmp_path / "history.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
        target.execute("DELETE FROM detections")
        target.commit()
    async with aiosqlite.connect(path) as regeneration, aiosqlite.connect(path) as owner:
        for db in (regeneration, owner):
            await db.execute("PRAGMA foreign_keys=ON")
        detections = DetectionRepository(regeneration)
        await detections.create(Detection(datetime.now(), 1, 0.9, "Robin", "Robin", "edit-race", "camera"))
        repo = BirdObservationRepository(regeneration)
        await repo.replace_generated("edit-race", SELECTION)
        # Another capture makes deletion/reinsertion churn identifiers in SQLite.
        await detections.create(Detection(datetime.now(), 1, 0.9, "Robin", "Robin", "other-capture", "camera"))
        await repo.replace_generated("other-capture", SELECTION)
        yield repo, BirdObservationRepository(owner)


@pytest.mark.asyncio
@pytest.mark.parametrize("edit", ["species", "exclude"])
async def test_owner_edit_during_regeneration_keeps_the_same_bird_and_owner_decision(fixture_birds, monkeypatch, edit):
    repo, owner = fixture_birds
    original_bird = (await owner.list_for_event("edit-race"))[0]
    read_finished, resume = asyncio.Event(), asyncio.Event()
    original_read = repo.list_for_event

    async def pause_after_read(event_id):
        birds = await original_read(event_id)
        read_finished.set()
        await resume.wait()
        return birds

    monkeypatch.setattr(repo, "list_for_event", pause_after_read)
    regeneration = asyncio.create_task(repo.replace_generated("edit-race", SELECTION))
    await asyncio.wait_for(read_finished.wait(), timeout=2)
    owner_edit = asyncio.create_task(
        owner.set_species("edit-race", original_bird["id"], "Blue Jay")
        if edit == "species"
        else owner.set_hidden("edit-race", original_bird["id"], True)
    )
    try:
        # Old code accepts and loses the edit; write-reserved regeneration makes
        # it wait, then the stable observation ID accepts it after the commit.
        await asyncio.wait({owner_edit}, timeout=0.1)
        resume.set()
        assert await asyncio.wait_for(regeneration, timeout=2) is True
        assert await asyncio.wait_for(owner_edit, timeout=2) is True
    finally:
        resume.set()
        for task in (regeneration, owner_edit):
            if not task.done():
                task.cancel()
        await asyncio.gather(regeneration, owner_edit, return_exceptions=True)
    after = (await owner.list_for_event("edit-race"))[0]
    assert after["id"] == original_bird["id"]
    if edit == "species":
        assert after["species"] == "Blue Jay" and after["manual_species"]
    else:
        assert after["is_hidden"]


@pytest.mark.asyncio
async def test_cancelled_regeneration_releases_write_reservation_without_erasing_birds(fixture_birds, monkeypatch):
    repo, owner = fixture_birds
    original_bird = (await owner.list_for_event("edit-race"))[0]

    async def cancelled_read(_event_id):
        raise asyncio.CancelledError

    monkeypatch.setattr(repo, "list_for_event", cancelled_read)
    with pytest.raises(asyncio.CancelledError):
        await repo.replace_generated("edit-race", SELECTION)
    assert not repo.db.in_transaction
    assert await asyncio.wait_for(owner.set_species("edit-race", original_bird["id"], "Blue Jay"), timeout=2)
    assert (await owner.list_for_event("edit-race"))[0]["species"] == "Blue Jay"


@pytest.mark.asyncio
async def test_reranked_generated_boxes_keep_observation_ids(fixture_birds):
    repo, owner = fixture_birds
    original = (await owner.list_for_event("edit-race"))[0]
    reranked = BirdObservationSelection(
        "frigate_snapshot", 0, "whole", (BirdObservation("bird-9", (11, 11, 61, 61), 0.95, "Robin", "Robin", 0.94),)
    )
    assert await repo.replace_generated("edit-race", reranked)
    after = (await owner.list_for_event("edit-race"))[0]
    assert after["id"] == original["id"]
    assert after["candidate_id"] == "bird-9"


@pytest.mark.asyncio
async def test_failed_regeneration_restores_indices_ids_and_owner_decisions(fixture_birds, monkeypatch):
    repo, owner = fixture_birds
    original = (await owner.list_for_event("edit-race"))[0]
    assert await owner.set_species("edit-race", original["id"], "Blue Jay")
    before = await owner.list_for_event("edit-race")
    original_write = repo.db.executemany

    async def fail_new_rows(sql, rows):
        if "INSERT INTO bird_observations" in sql:
            raise sqlite3.IntegrityError("fixture insertion failure")
        return await original_write(sql, rows)

    monkeypatch.setattr(repo.db, "executemany", fail_new_rows)
    with pytest.raises(sqlite3.IntegrityError):
        await repo.replace_generated("edit-race", SELECTION)
    assert not repo.db.in_transaction
    assert await owner.list_for_event("edit-race") == before
