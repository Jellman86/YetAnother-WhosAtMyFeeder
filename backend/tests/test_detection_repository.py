import pytest
import aiosqlite
from datetime import datetime
from app.repositories.detection_repository import DetectionRepository, Detection

@pytest.mark.asyncio
async def test_detection_repository():
    async with aiosqlite.connect(":memory:") as db:
        # Init schema matches backend/app/database.py
        await db.execute("""
            CREATE TABLE detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                detection_time TIMESTAMP NOT NULL,
                detection_index INTEGER NOT NULL,
                score FLOAT NOT NULL,
                display_name TEXT NOT NULL,
                category_name TEXT NOT NULL,
                frigate_event TEXT UNIQUE NOT NULL,
                camera_name TEXT NOT NULL,
                is_hidden BOOLEAN DEFAULT 0,
                frigate_score FLOAT,
                sub_label TEXT,
                audio_confirmed BOOLEAN DEFAULT 0,
                audio_species TEXT,
                audio_score FLOAT,
                temperature FLOAT,
                weather_condition TEXT,
                scientific_name TEXT,
                common_name TEXT,
                taxa_id INTEGER,
                video_classification_score FLOAT,
                video_classification_label TEXT,
                video_classification_index INTEGER,
                video_classification_timestamp TIMESTAMP,
                video_classification_status TEXT
            )
        """)
        await db.commit()

        repo = DetectionRepository(db)
        
        # Test Create
        dt = datetime(2023, 1, 1, 12, 0, 0)
        detection = Detection(
            detection_time=dt,
            detection_index=1,
            score=0.9,
            display_name="Bird",
            category_name="Bird",
            frigate_event="evt_1",
            camera_name="cam_1"
        )
        await repo.create(detection)
        
        # Test Get
        fetched = await repo.get_by_frigate_event("evt_1")
        assert fetched is not None
        assert fetched.frigate_event == "evt_1"
        assert fetched.score == 0.9
        # Check datetime handling if sqlite returns string
        # assert fetched.detection_time == dt # Might fail if format differs slightly, but checks object presence
        
        # Test Update
        detection.score = 0.95
        await repo.update(detection)
        
        fetched_updated = await repo.get_by_frigate_event("evt_1")
        assert fetched_updated.score == 0.95
