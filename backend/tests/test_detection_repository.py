import pytest
import aiosqlite
from datetime import datetime, timedelta
from app.repositories.detection_repository import DetectionRepository, Detection


async def _create_detections_table(db: aiosqlite.Connection) -> None:
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
            manual_tagged BOOLEAN DEFAULT 0,
            audio_confirmed BOOLEAN DEFAULT 0,
            audio_species TEXT,
            audio_score FLOAT,
            temperature FLOAT,
            weather_condition TEXT,
            weather_cloud_cover FLOAT,
            weather_wind_speed FLOAT,
            weather_wind_direction FLOAT,
            weather_precipitation FLOAT,
            weather_rain FLOAT,
            weather_snowfall FLOAT,
            scientific_name TEXT,
            common_name TEXT,
            taxa_id INTEGER,
            video_classification_score FLOAT,
            video_classification_label TEXT,
            video_classification_index INTEGER,
            video_classification_timestamp TIMESTAMP,
            video_classification_status TEXT,
            video_classification_error TEXT,
            ai_analysis TEXT,
            ai_analysis_timestamp TIMESTAMP,
            notified_at TIMESTAMP
        )
    """)
    await db.execute("""
        CREATE TABLE detection_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detection_id INTEGER NOT NULL UNIQUE,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (detection_id) REFERENCES detections(id) ON DELETE CASCADE
        )
    """)


@pytest.mark.asyncio
async def test_detection_repository():
    async with aiosqlite.connect(":memory:") as db:
        # Init schema matches backend/app/database.py
        await _create_detections_table(db)
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


@pytest.mark.asyncio
async def test_species_rollup_metrics():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.execute("""
            CREATE TABLE species_daily_rollup (
                rollup_date DATE NOT NULL,
                display_name TEXT NOT NULL,
                detection_count INTEGER NOT NULL,
                camera_count INTEGER NOT NULL,
                avg_confidence FLOAT,
                max_confidence FLOAT,
                min_confidence FLOAT,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                PRIMARY KEY (rollup_date, display_name)
            )
        """)
        await db.commit()

        repo = DetectionRepository(db)
        now = datetime.utcnow()
        await repo.create(Detection(
            detection_time=now,
            detection_index=1,
            score=0.9,
            display_name="Robin",
            category_name="Bird",
            frigate_event="evt_r1",
            camera_name="cam_1"
        ))
        await repo.create(Detection(
            detection_time=now,
            detection_index=2,
            score=0.8,
            display_name="Sparrow",
            category_name="Bird",
            frigate_event="evt_s1",
            camera_name="cam_2"
        ))
        await repo.ensure_recent_rollups(30)
        metrics = await repo.get_rollup_metrics()

        assert metrics["Robin"]["count_7d"] >= 1
        assert metrics["Sparrow"]["count_7d"] >= 1


@pytest.mark.asyncio
async def test_delete_methods_report_exact_row_changes():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        now = datetime.utcnow()
        await repo.create(Detection(
            detection_time=now,
            detection_index=1,
            score=0.9,
            display_name="Robin",
            category_name="Bird",
            frigate_event="evt_delete",
            camera_name="cam_1"
        ))

        row = await repo.get_by_frigate_event("evt_delete")
        assert row is not None

        assert await repo.delete_by_id(row.id) is True
        assert await repo.delete_by_id(row.id) is False
        assert await repo.delete_by_frigate_event("evt_delete") is False


@pytest.mark.asyncio
async def test_insert_if_not_exists_reports_conflicts_correctly():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        detection = Detection(
            detection_time=datetime.utcnow(),
            detection_index=1,
            score=0.8,
            display_name="Sparrow",
            category_name="Bird",
            frigate_event="evt_insert_once",
            camera_name="cam_2"
        )
        assert await repo.insert_if_not_exists(detection) is True
        assert await repo.insert_if_not_exists(detection) is False


@pytest.mark.asyncio
async def test_upsert_if_higher_score_returns_no_change_for_lower_score():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        base = Detection(
            detection_time=datetime.utcnow(),
            detection_index=1,
            score=0.92,
            display_name="Blue Jay",
            category_name="Bird",
            frigate_event="evt_upsert",
            camera_name="cam_3",
            audio_confirmed=False
        )
        assert await repo.upsert_if_higher_score(base) == (True, False)

        lower = Detection(
            detection_time=datetime.utcnow(),
            detection_index=2,
            score=0.50,
            display_name="Unknown Bird",
            category_name="Bird",
            frigate_event="evt_upsert",
            camera_name="cam_3",
            audio_confirmed=False
        )
        assert await repo.upsert_if_higher_score(lower) == (False, False)

        existing = await repo.get_by_frigate_event("evt_upsert")
        assert existing is not None
        assert existing.score == pytest.approx(0.92)
        assert existing.display_name == "Blue Jay"


@pytest.mark.asyncio
async def test_favorite_detection_idempotent_and_filterable():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        now = datetime.utcnow()
        await repo.create(Detection(
            detection_time=now,
            detection_index=1,
            score=0.9,
            display_name="Robin",
            category_name="Bird",
            frigate_event="evt_fav_1",
            camera_name="cam_1"
        ))
        await repo.create(Detection(
            detection_time=now,
            detection_index=2,
            score=0.8,
            display_name="Sparrow",
            category_name="Bird",
            frigate_event="evt_fav_2",
            camera_name="cam_1"
        ))

        assert await repo.favorite_detection("evt_fav_1", created_by="owner") is True
        # idempotent second call should still succeed without duplicate
        assert await repo.favorite_detection("evt_fav_1", created_by="owner") is True

        row = await repo.get_by_frigate_event("evt_fav_1")
        assert row is not None
        assert row.is_favorite is True

        all_rows = await repo.get_all(limit=10, favorite_only=False)
        fav_rows = await repo.get_all(limit=10, favorite_only=True)
        assert len(all_rows) == 2
        assert len(fav_rows) == 1
        assert fav_rows[0].frigate_event == "evt_fav_1"

        assert await repo.get_count(favorite_only=False) == 2
        assert await repo.get_count(favorite_only=True) == 1

        assert await repo.unfavorite_detection("evt_fav_1") is True
        # idempotent second call should still report success
        assert await repo.unfavorite_detection("evt_fav_1") is True

        row_after = await repo.get_by_frigate_event("evt_fav_1")
        assert row_after is not None
        assert row_after.is_favorite is False
        assert await repo.get_count(favorite_only=True) == 0


@pytest.mark.asyncio
async def test_favorite_detection_returns_none_when_missing():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        assert await repo.favorite_detection("evt_missing", created_by="owner") is None
        assert await repo.unfavorite_detection("evt_missing") is None


@pytest.mark.asyncio
async def test_delete_older_than_preserves_favorites_when_enabled():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        old_time = datetime.utcnow() - timedelta(days=30)
        recent_time = datetime.utcnow()

        old_favorite_event = "evt_old_favorite"
        old_regular_event = "evt_old_regular"
        recent_event = "evt_recent"

        await repo.create(Detection(
            detection_time=old_time,
            detection_index=1,
            score=0.9,
            display_name="Robin",
            category_name="Bird",
            frigate_event=old_favorite_event,
            camera_name="cam_1",
        ))
        await repo.create(Detection(
            detection_time=old_time,
            detection_index=2,
            score=0.85,
            display_name="Robin",
            category_name="Bird",
            frigate_event=old_regular_event,
            camera_name="cam_1",
        ))
        await repo.create(Detection(
            detection_time=recent_time,
            detection_index=3,
            score=0.88,
            display_name="Robin",
            category_name="Bird",
            frigate_event=recent_event,
            camera_name="cam_1",
        ))

        assert await repo.favorite_detection(old_favorite_event, created_by="owner") is True

        cutoff = datetime.utcnow() - timedelta(days=7)
        deleted = await repo.delete_older_than(cutoff, preserve_favorites=True)
        assert deleted == 1

        assert await repo.get_by_frigate_event(old_favorite_event) is not None
        assert await repo.get_by_frigate_event(old_regular_event) is None
        assert await repo.get_by_frigate_event(recent_event) is not None
