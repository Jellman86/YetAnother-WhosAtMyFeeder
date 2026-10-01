"""Per-bird owner edits must survive concurrent regeneration."""

import asyncio
from contextlib import closing
from itertools import product
import random
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


@pytest.mark.asyncio
@pytest.mark.parametrize("edit", ["species", "exclude"])
@pytest.mark.parametrize("reverse", [False, True])
async def test_overlapping_reranked_birds_keep_owner_edits_on_the_best_spatial_match(fixture_birds, edit, reverse):
    repo, owner = fixture_birds
    birds = (
        BirdObservation("a", (0, 0, 50, 50), 0.9, "Robin", "Robin", 0.9),
        BirdObservation("b", (30, 0, 80, 50), 0.9, "Cardinal", "Cardinal", 0.9),
    )
    first = BirdObservationSelection("frigate_snapshot", 0, "whole", birds)
    await repo.replace_generated("edit-race", first)
    original = await owner.list_for_event("edit-race")
    corrected = original[0]
    if edit == "species":
        await owner.set_species("edit-race", corrected["id"], "Blue Jay")
    else:
        await owner.set_hidden("edit-race", corrected["id"], True)
    reordered = BirdObservationSelection("frigate_snapshot", 0, "whole", tuple(reversed(birds)) if reverse else birds)
    assert await repo.replace_generated("edit-race", reordered)
    after = await owner.list_for_event("edit-race")
    by_box = {tuple(bird["crop_box"]): bird for bird in after}
    for old in original:
        assert by_box[tuple(old["crop_box"])]["id"] == old["id"]
    reviewed = by_box[(0, 0, 50, 50)]
    other = by_box[(30, 0, 80, 50)]
    assert not other["manual_species"] and not other["is_hidden"]
    if edit == "species":
        assert reviewed["species"] == "Blue Jay" and reviewed["manual_species"]
    else:
        assert reviewed["is_hidden"]


def test_spatial_assignment_optimizes_all_pairs_instead_of_consuming_the_first_best_edge():
    assert BirdObservationRepository._maximum_weight_assignment([[0.9, 0.8], [0.8, 0]]) == [1, 0]


@pytest.mark.asyncio
async def test_ambiguous_owner_association_preserves_the_entire_reviewed_frame(fixture_birds):
    repo, owner = fixture_birds
    original = (await owner.list_for_event("edit-race"))[0]
    await owner.set_species("edit-race", original["id"], "Blue Jay")
    before = await owner.list_for_event("edit-race")
    ambiguous = BirdObservationSelection(
        "frigate_snapshot",
        0,
        "whole",
        (
            BirdObservation("left", (5, 10, 55, 60), 0.9, "Robin", "Robin", 0.9),
            BirdObservation("right", (15, 10, 65, 60), 0.9, "Robin", "Robin", 0.9),
        ),
    )
    assert await repo.replace_generated("edit-race", ambiguous) is False
    assert await owner.list_for_event("edit-race") == before


def test_global_spatial_assignment_matches_exhaustive_optimum_with_unmatched_slots():
    randomizer = random.Random(42)
    for row_count in range(1, 5):
        for old_count in range(0, 4):
            for _ in range(5):
                weights = [[randomizer.randrange(0, 11) / 10 for _ in range(old_count)] for _ in range(row_count)]
                assignment = BirdObservationRepository._maximum_weight_assignment(weights)
                assigned = [old for old in assignment if old is not None]
                assert len(assigned) == len(set(assigned))
                actual = sum(weights[new][old] for new, old in enumerate(assignment) if old is not None)
                optimum = max(
                    sum(weights[new][old] for new, old in enumerate(candidate) if old is not None)
                    for candidate in product([None, *range(old_count)], repeat=row_count)
                    if len([old for old in candidate if old is not None])
                    == len(set(old for old in candidate if old is not None))
                )
                assert actual == pytest.approx(optimum)
