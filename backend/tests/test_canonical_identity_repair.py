from datetime import datetime
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

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
            taxa_id INTEGER
        )
    """)


async def _create_taxonomy_tables(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE taxonomy_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scientific_name TEXT NOT NULL UNIQUE,
            common_name TEXT,
            taxa_id INTEGER UNIQUE
        )
    """)


async def _create_rollup_table(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE species_daily_rollup (
            rollup_date DATE NOT NULL,
            canonical_key TEXT NOT NULL,
            display_name TEXT NOT NULL,
            scientific_name TEXT,
            common_name TEXT,
            taxa_id INTEGER,
            detection_count INTEGER NOT NULL,
            camera_count INTEGER NOT NULL,
            avg_confidence FLOAT,
            max_confidence FLOAT,
            min_confidence FLOAT,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            PRIMARY KEY (rollup_date, canonical_key)
        )
    """)


@pytest.mark.asyncio
async def test_canonical_identity_repair_service_repairs_missing_taxonomy_and_rebuilds_rollups():
    try:
        from app.services.canonical_identity_repair_service import CanonicalIdentityRepairService
    except ImportError as exc:  # pragma: no cover - red phase guard
        pytest.fail(f"Canonical repair service missing: {exc}")

    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await _create_rollup_table(db)
        await db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Cyanistes caeruleus", "Blue Tit", 1234),
        )
        await db.commit()

        repo = DetectionRepository(db)
        now = datetime.utcnow()
        await repo.create(Detection(
            detection_time=now,
            detection_index=1,
            score=0.90,
            display_name="Blue Tit",
            category_name="Blue Tit",
            frigate_event="evt_repair_missing",
            camera_name="cam_1",
            scientific_name=None,
            common_name=None,
            taxa_id=None,
        ))
        await repo.create(Detection(
            detection_time=now,
            detection_index=2,
            score=0.93,
            display_name="Cyanistes caeruleus",
            category_name="Cyanistes caeruleus",
            frigate_event="evt_repair_existing",
            camera_name="cam_2",
            scientific_name="Cyanistes caeruleus",
            common_name="Blue Tit",
            taxa_id=1234,
        ))

        service = CanonicalIdentityRepairService()
        with patch(
            "app.services.canonical_identity_repair_service.taxonomy_service.get_names",
            new=AsyncMock(return_value={"scientific_name": "Cyanistes caeruleus", "common_name": "Blue Tit", "taxa_id": 1234}),
        ):
            first_run = await service.run(db=db, batch_size=100)
            second_run = await service.run(db=db, batch_size=100)

        async with db.execute(
            "SELECT scientific_name, common_name, taxa_id FROM detections WHERE frigate_event = ?",
            ("evt_repair_missing",),
        ) as cursor:
            repaired_row = await cursor.fetchone()

        assert repaired_row == ("Cyanistes caeruleus", "Blue Tit", 1234)
        assert first_run["updated"] >= 1
        assert second_run["updated"] == 0

        metrics = await repo.get_rollup_metrics()
        assert list(metrics.keys()) == ["Blue Tit"]
        assert metrics["Blue Tit"]["count_7d"] >= 2


@pytest.mark.asyncio
async def test_canonical_identity_repair_service_preserves_localized_common_names():
    from app.services.canonical_identity_repair_service import CanonicalIdentityRepairService

    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await _create_rollup_table(db)
        await db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Cyanistes caeruleus", "Blue Tit", 1234),
        )
        await db.execute(
            "CREATE TABLE taxonomy_translations (taxa_id INTEGER NOT NULL, language_code TEXT NOT NULL, common_name TEXT NOT NULL)"
        )
        await db.execute(
            "INSERT INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (?, ?, ?)",
            (1234, "ru", "Лазоревка"),
        )
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name,
                scientific_name, common_name, taxa_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow(),
                1,
                0.91,
                "Лазоревка",
                "Cyanistes caeruleus",
                "evt_preserve_localized",
                "cam_1",
                "Cyanistes caeruleus",
                "Лазоревка",
                1234,
            ),
        )
        await db.commit()

        service = CanonicalIdentityRepairService()
        with patch(
            "app.services.canonical_identity_repair_service.taxonomy_service.get_names",
            new=AsyncMock(return_value={"scientific_name": "Cyanistes caeruleus", "common_name": "Blue Tit", "taxa_id": 1234}),
        ) as mock_get_names:
            result = await service.run(db=db, batch_size=100)

        async with db.execute(
            "SELECT scientific_name, common_name, taxa_id FROM detections WHERE frigate_event = ?",
            ("evt_preserve_localized",),
        ) as cursor:
            preserved_row = await cursor.fetchone()

        assert preserved_row == ("Cyanistes caeruleus", "Лазоревка", 1234)
        assert result["updated"] == 0
        mock_get_names.assert_not_awaited()


@pytest.mark.asyncio
async def test_canonical_identity_repair_service_preserves_rollups_when_rebuild_fails():
    from app.services.canonical_identity_repair_service import CanonicalIdentityRepairService

    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await _create_rollup_table(db)
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name,
                scientific_name, common_name, taxa_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow(),
                1,
                0.9,
                "Blue Tit",
                "Cyanistes caeruleus",
                "evt_rollup_source",
                "cam_1",
                "Cyanistes caeruleus",
                "Blue Tit",
                1234,
            ),
        )
        await db.execute(
            """
            INSERT INTO species_daily_rollup (
                rollup_date, canonical_key, display_name, scientific_name, common_name, taxa_id,
                detection_count, camera_count, avg_confidence, max_confidence, min_confidence, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-03-28",
                "1234",
                "Blue Tit",
                "Cyanistes caeruleus",
                "Blue Tit",
                1234,
                2,
                1,
                0.9,
                0.9,
                0.9,
                "2026-03-28 10:00:00",
                "2026-03-28 10:00:00",
            ),
        )
        await db.commit()

        service = CanonicalIdentityRepairService()
        with patch.object(DetectionRepository, "rebuild_all_rollups", new=AsyncMock(side_effect=RuntimeError("boom"))):
            with pytest.raises(RuntimeError, match="boom"):
                await service.run(db=db, batch_size=100)

        async with db.execute("SELECT COUNT(*) FROM species_daily_rollup") as cursor:
            row = await cursor.fetchone()

        assert row[0] == 1


def test_canonical_identity_repair_status_reports_stalled_progress():
    from app.services.canonical_identity_repair_service import CanonicalIdentityRepairService

    service = CanonicalIdentityRepairService()
    service._status = {
        "is_running": True,
        "processed": 10,
        "total": 200,
        "current_item": "Blue Tit",
        "error": None,
        "last_progress_at": "2026-04-09T08:00:00+00:00",
    }

    with patch("app.services.canonical_identity_repair_service.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime.fromisoformat("2026-04-09T08:02:30+00:00")
        mock_datetime.fromisoformat = datetime.fromisoformat
        status = service.get_status()

    assert status["progress_state"] == "stalled"
    assert status["seconds_since_progress"] == 150.0
    assert "stalled" in str(status["message"]).lower()
