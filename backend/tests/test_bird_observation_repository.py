from datetime import datetime

import aiosqlite
import pytest

from app.repositories.bird_observation_repository import BirdObservationRepository
from app.services.bird_observation_selection import BirdObservation, BirdObservationSelection


@pytest.mark.asyncio
async def test_bird_observations_replace_atomically_and_count_visible_birds():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "CREATE TABLE detections (frigate_event TEXT PRIMARY KEY, detection_time TEXT NOT NULL, is_hidden BOOLEAN DEFAULT 0)"
        )
        await db.execute(
            """CREATE TABLE bird_observations (
                id INTEGER PRIMARY KEY, frigate_event TEXT NOT NULL REFERENCES detections(frigate_event) ON DELETE CASCADE,
                bird_index INTEGER NOT NULL, candidate_id TEXT NOT NULL, clip_variant TEXT NOT NULL,
                frame_index INTEGER NOT NULL, crop_box_json TEXT NOT NULL, detector_confidence FLOAT,
                species TEXT NOT NULL, classifier_label TEXT, classifier_score FLOAT NOT NULL,
                manual_species BOOLEAN NOT NULL DEFAULT 0, is_hidden BOOLEAN NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(frigate_event, bird_index)
            )"""
        )
        await db.execute(
            "INSERT INTO detections(frigate_event, detection_time) VALUES ('evt-1', '2026-09-28 12:00:00')"
        )
        repo = BirdObservationRepository(db)
        selection = BirdObservationSelection(
            "frigate_snapshot",
            0,
            "whole",
            (
                BirdObservation("bird-1", (10, 10, 60, 60), 0.9, "House Finch", "House Finch", 0.91),
                BirdObservation("bird-2", (90, 10, 140, 60), 0.8, "Northern Cardinal", "Northern Cardinal", 0.84),
            ),
        )

        await repo.replace_generated("evt-1", selection)
        await repo.replace_generated("evt-1", selection)
        birds = await repo.list_for_event("evt-1")
        assert [bird["species"] for bird in birds] == ["House Finch", "Northern Cardinal"]
        assert birds[1]["crop_box"] == [90, 10, 140, 60]
        assert await repo.set_species("evt-1", birds[1]["id"], "Blue Jay") is True
        await repo.replace_generated("evt-1", selection)
        corrected = await repo.list_for_event("evt-1")
        assert corrected[1]["species"] == "Blue Jay"
        assert corrected[1]["manual_species"] is True
        reranked = BirdObservationSelection(
            "frigate_snapshot",
            0,
            "whole",
            (
                BirdObservation("bird-2", (10, 10, 60, 60), 0.9, "House Finch", "House Finch", 0.91),
                BirdObservation("bird-1", (90, 10, 140, 60), 0.8, "Northern Cardinal", "Northern Cardinal", 0.84),
            ),
        )
        await repo.replace_generated("evt-1", reranked)
        corrected = await repo.list_for_event("evt-1")
        assert [bird["species"] for bird in corrected] == ["House Finch", "Blue Jay"]
        assert await repo.count_visible_between(datetime(2026, 9, 28), datetime(2026, 9, 29)) == {
            "birds": 2,
            "captures": 1,
        }

        assert await repo.set_hidden("evt-1", corrected[1]["id"], True) is True
        assert await repo.count_visible_between(datetime(2026, 9, 28), datetime(2026, 9, 29)) == {
            "birds": 1,
            "captures": 1,
        }
        assert await repo.set_hidden("evt-1", corrected[0]["id"], True) is True
        assert await repo.count_visible_between(datetime(2026, 9, 28), datetime(2026, 9, 29)) == {
            "birds": 0,
            "captures": 1,
        }
        await db.execute("DELETE FROM detections WHERE frigate_event = 'evt-1'")
        await db.commit()
        assert await repo.list_for_event("evt-1") == []


@pytest.mark.asyncio
async def test_empty_regeneration_keeps_existing_bird_count():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute(
            """CREATE TABLE bird_observations (
                id INTEGER PRIMARY KEY, frigate_event TEXT NOT NULL, bird_index INTEGER NOT NULL,
                candidate_id TEXT NOT NULL, clip_variant TEXT NOT NULL, frame_index INTEGER NOT NULL,
                crop_box_json TEXT NOT NULL, detector_confidence FLOAT, species TEXT NOT NULL,
                classifier_label TEXT, classifier_score FLOAT NOT NULL,
                manual_species BOOLEAN DEFAULT 0, is_hidden BOOLEAN DEFAULT 0
            )"""
        )
        await db.execute(
            """INSERT INTO bird_observations
               (frigate_event,bird_index,candidate_id,clip_variant,frame_index,crop_box_json,species,classifier_score)
               VALUES ('evt',0,'bird','event',1,'[10,10,60,60]','Robin',0.8)"""
        )
        repo = BirdObservationRepository(db)

        await repo.replace_generated("evt", BirdObservationSelection(None, None, None, ()))

        assert len(await repo.list_for_event("evt")) == 1
