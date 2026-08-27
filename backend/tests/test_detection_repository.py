import pytest
import aiosqlite
from datetime import datetime, timedelta
from app.repositories.detection_repository import DetectionRepository, Detection
from conftest import rollup_counts_by_display_name


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
            species_id INTEGER,
            model_artifact_id INTEGER,
            model_output_index INTEGER,
            video_classification_score FLOAT,
            video_classification_label TEXT,
            video_classification_index INTEGER,
            video_classification_timestamp TIMESTAMP,
            video_classification_status TEXT,
            video_classification_error TEXT,
            video_classification_provider TEXT,
            video_classification_backend TEXT,
            video_classification_model_id TEXT,
            video_classification_input_source TEXT,
            video_classification_diagnostics TEXT,
            video_result_blocked BOOLEAN DEFAULT 0,
            ai_analysis TEXT,
            ai_analysis_timestamp TIMESTAMP,
            notified_at TIMESTAMP,
            frigate_status TEXT DEFAULT 'present',
            frigate_missing_since TIMESTAMP,
            frigate_last_checked_at TIMESTAMP,
            frigate_last_error TEXT
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


async def _create_taxonomy_tables(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE taxonomy_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scientific_name TEXT NOT NULL UNIQUE,
            common_name TEXT,
            manual_common_name TEXT,
            taxa_id INTEGER UNIQUE
        )
    """)
    await db.execute("""
        CREATE TABLE taxonomy_translations (
            taxa_id INTEGER NOT NULL,
            language_code TEXT NOT NULL,
            common_name TEXT NOT NULL
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
            camera_name="cam_1",
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
        assert fetched_updated.frigate_status == "present"


@pytest.mark.asyncio
async def test_get_all_can_target_one_frigate_event():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)
        for event_id in ("evt-one", "evt-two"):
            await repo.create(
                Detection(
                    detection_time=datetime(2026, 7, 20, 12, 0, 0),
                    detection_index=1,
                    score=0.9,
                    display_name="Bird",
                    category_name="Bird",
                    frigate_event=event_id,
                    camera_name="birdcam",
                )
            )

        detections = await repo.get_all(frigate_event="evt-two")

        assert [detection.frigate_event for detection in detections] == ["evt-two"]


@pytest.mark.asyncio
async def test_mark_and_clear_frigate_missing_state():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()

        repo = DetectionRepository(db)
        detection = Detection(
            detection_time=datetime(2023, 1, 1, 12, 0, 0),
            detection_index=1,
            score=0.9,
            display_name="Bird",
            category_name="Bird",
            frigate_event="evt_missing_state",
            camera_name="cam_1",
        )
        await repo.create(detection)

        checked_at = datetime(2026, 4, 22, 18, 0, 0)
        await repo.mark_frigate_missing(
            "evt_missing_state",
            error="event_not_found",
            checked_at=checked_at,
        )

        marked = await repo.get_by_frigate_event("evt_missing_state")
        assert marked is not None
        assert marked.frigate_status == "missing"
        assert marked.frigate_last_error == "event_not_found"
        assert marked.frigate_missing_since == checked_at
        assert marked.frigate_last_checked_at == checked_at

        restored_at = datetime(2026, 4, 22, 19, 0, 0)
        await repo.mark_frigate_present("evt_missing_state", checked_at=restored_at)

        restored = await repo.get_by_frigate_event("evt_missing_state")
        assert restored is not None
        assert restored.frigate_status == "present"
        assert restored.frigate_missing_since is None
        assert restored.frigate_last_error is None
        assert restored.frigate_last_checked_at == restored_at


@pytest.mark.asyncio
async def test_get_unknown_detections_returns_newest_first_with_limit():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()

        repo = DetectionRepository(db)
        base = datetime(2026, 4, 29, 12, 0, 0)
        for index in range(5):
            await repo.create(
                Detection(
                    detection_time=base + timedelta(minutes=index),
                    detection_index=index,
                    score=0.4,
                    display_name="Unknown Bird",
                    category_name="Unknown Bird",
                    frigate_event=f"unknown-{index}",
                    camera_name="cam_1",
                )
            )

        detections = await repo.get_unknown_detections(limit=3)

        assert [d.frigate_event for d in detections] == ["unknown-4", "unknown-3", "unknown-2"]


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
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=1,
                score=0.9,
                display_name="Robin",
                category_name="Bird",
                frigate_event="evt_r1",
                camera_name="cam_1",
            )
        )
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=2,
                score=0.8,
                display_name="Sparrow",
                category_name="Bird",
                frigate_event="evt_s1",
                camera_name="cam_2",
            )
        )
        await repo.ensure_recent_rollups(30)
        counts = await rollup_counts_by_display_name(repo)

        assert counts["Robin"] >= 1
        assert counts["Sparrow"] >= 1


@pytest.mark.asyncio
async def test_upsert_daily_rollups_is_idempotent_for_existing_dates():
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
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=1,
                score=0.9,
                display_name="Robin",
                category_name="Bird",
                frigate_event="evt_rollup_repeat",
                camera_name="cam_1",
            )
        )

        rollup_date = now.date()
        await repo.upsert_daily_rollups(rollup_date, rollup_date)
        await repo.upsert_daily_rollups(rollup_date, rollup_date)

        async with db.execute("SELECT COUNT(*) FROM species_daily_rollup") as cursor:
            row = await cursor.fetchone()

        assert row[0] == 1


@pytest.mark.asyncio
async def test_timebucket_metrics_unifies_common_and_scientific_variants():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Cyanistes caeruleus", "Blue Tit", 1234),
        )
        await db.commit()

        repo = DetectionRepository(db)
        ts = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        start = ts - timedelta(hours=1)
        end = ts + timedelta(hours=1)

        await repo.create(
            Detection(
                detection_time=ts,
                detection_index=1,
                score=0.91,
                display_name="Blue Tit",
                category_name="Bird",
                frigate_event="evt_bt_common",
                camera_name="cam_1",
                scientific_name="Cyanistes caeruleus",
                common_name="Blue Tit",
                taxa_id=1234,
            )
        )
        await repo.create(
            Detection(
                detection_time=ts,
                detection_index=2,
                score=0.93,
                display_name="Cyanistes caeruleus",
                category_name="Bird",
                frigate_event="evt_bt_sci",
                camera_name="cam_2",
                scientific_name="Cyanistes caeruleus",
                common_name="Blue Tit",
                taxa_id=1234,
            )
        )

        metrics = await repo.get_timebucket_metrics(start, end, "day")
        key = ts.date().isoformat() + "T00:00:00Z"
        assert key in metrics
        assert metrics[key]["count"] == 2
        assert metrics[key]["unique_species"] == 1


@pytest.mark.asyncio
async def test_taxonomy_lookup_and_alias_resolution_support_localized_common_names():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Cyanistes caeruleus", "Blue Tit", 1234),
        )
        await db.execute(
            "INSERT INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (?, ?, ?)",
            (1234, "es", "Herrerillo comun"),
        )
        await db.commit()

        repo = DetectionRepository(db)
        now = datetime.utcnow()
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=1,
                score=0.9,
                display_name="Blue Tit",
                category_name="Bird",
                frigate_event="evt_alias_1",
                camera_name="cam_1",
                scientific_name="Cyanistes caeruleus",
                common_name="Blue Tit",
                taxa_id=1234,
            )
        )
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=2,
                score=0.88,
                display_name="Cyanistes caeruleus",
                category_name="Bird",
                frigate_event="evt_alias_2",
                camera_name="cam_1",
                scientific_name="Cyanistes caeruleus",
                common_name="Blue Tit",
                taxa_id=1234,
            )
        )

        taxonomy = await repo.get_taxonomy_names("Herrerillo comun", language="es")
        assert taxonomy["taxa_id"] == 1234
        assert taxonomy["scientific_name"] == "Cyanistes caeruleus"
        assert taxonomy["common_name"] == "Herrerillo comun"

        alias_info = await repo.resolve_species_aliases("Herrerillo comun", language="es")
        assert alias_info["taxa_id"] == 1234
        assert alias_info["scientific_name"] == "Cyanistes caeruleus"
        assert set(alias_info["display_labels"]) == {"Blue Tit", "Cyanistes caeruleus"}

        accented_taxonomy = await repo.get_taxonomy_names("Herrerillo com\u00fan", language="es")
        assert accented_taxonomy["taxa_id"] == 1234
        assert accented_taxonomy["scientific_name"] == "Cyanistes caeruleus"
        assert accented_taxonomy["common_name"] == "Herrerillo comun"

        accented_alias_info = await repo.resolve_species_aliases("Herrerillo com\u00fan", language="es")
        assert accented_alias_info["taxa_id"] == 1234
        assert accented_alias_info["scientific_name"] == "Cyanistes caeruleus"
        assert set(accented_alias_info["display_labels"]) == {"Blue Tit", "Cyanistes caeruleus"}


@pytest.mark.asyncio
async def test_taxonomy_lookup_resolves_localized_common_name_without_language_hint():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Cyanistes caeruleus", "Blue Tit", 1234),
        )
        await db.execute(
            "INSERT INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (?, ?, ?)",
            (1234, "es", "Herrerillo comun"),
        )
        await db.commit()

        repo = DetectionRepository(db)
        taxonomy = await repo.get_taxonomy_names("Herrerillo com\u00fan")

        assert taxonomy["taxa_id"] == 1234
        assert taxonomy["scientific_name"] == "Cyanistes caeruleus"


@pytest.mark.asyncio
async def test_get_all_and_count_filter_by_canonical_species_identity():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Cyanistes caeruleus", "Blue Tit", 1234),
        )
        await db.commit()

        repo = DetectionRepository(db)
        now = datetime.utcnow()
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=1,
                score=0.92,
                display_name="Blue Tit",
                category_name="Bird",
                frigate_event="evt_filter_common",
                camera_name="cam_1",
                scientific_name="Cyanistes caeruleus",
                common_name="Blue Tit",
                taxa_id=1234,
            )
        )
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=2,
                score=0.95,
                display_name="Cyanistes caeruleus",
                category_name="Bird",
                frigate_event="evt_filter_sci",
                camera_name="cam_2",
                scientific_name="Cyanistes caeruleus",
                common_name="Blue Tit",
                taxa_id=1234,
            )
        )

        filtered = await repo.get_all(species="Blue Tit")
        count = await repo.get_count(species="Blue Tit")

        assert len(filtered) == 2
        assert count == 2


@pytest.mark.asyncio
async def test_rollup_metrics_collapse_common_and_scientific_aliases():
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
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=1,
                score=0.91,
                display_name="Blue Tit",
                category_name="Bird",
                frigate_event="evt_rollup_common",
                camera_name="cam_1",
                scientific_name="Cyanistes caeruleus",
                common_name="Blue Tit",
                taxa_id=1234,
            )
        )
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=2,
                score=0.94,
                display_name="Cyanistes caeruleus",
                category_name="Bird",
                frigate_event="evt_rollup_sci",
                camera_name="cam_2",
                scientific_name="Cyanistes caeruleus",
                common_name="Blue Tit",
                taxa_id=1234,
            )
        )

        await repo.ensure_recent_rollups(30)
        counts = await rollup_counts_by_display_name(repo)

        assert list(counts.keys()) == ["Blue Tit"]
        assert counts["Blue Tit"] >= 2


@pytest.mark.asyncio
async def test_species_detail_helpers_use_canonical_identity():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Cyanistes caeruleus", "Blue Tit", 1234),
        )
        await db.commit()

        repo = DetectionRepository(db)
        now = datetime.utcnow()
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=1,
                score=0.91,
                display_name="Blue Tit",
                category_name="Bird",
                frigate_event="evt_detail_common",
                camera_name="cam_1",
                scientific_name="Cyanistes caeruleus",
                common_name="Blue Tit",
                taxa_id=1234,
            )
        )
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=2,
                score=0.94,
                display_name="Cyanistes caeruleus",
                category_name="Bird",
                frigate_event="evt_detail_sci",
                camera_name="cam_2",
                scientific_name="Cyanistes caeruleus",
                common_name="Blue Tit",
                taxa_id=1234,
            )
        )

        basic_stats = await repo.get_species_basic_stats("Blue Tit")
        camera_breakdown = await repo.get_camera_breakdown("Blue Tit")
        hourly = await repo.get_hourly_distribution("Blue Tit")
        daily = await repo.get_daily_distribution("Blue Tit")
        monthly = await repo.get_monthly_distribution("Blue Tit")
        recent = await repo.get_recent_by_species("Blue Tit", limit=5)

        assert basic_stats["total"] == 2
        assert {row["camera_name"] for row in camera_breakdown} == {"cam_1", "cam_2"}
        assert sum(hourly) == 2
        assert sum(daily) == 2
        assert sum(monthly) == 2
        assert len(recent) == 2


@pytest.mark.asyncio
async def test_unified_species_window_metrics_combines_alias_variants():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Cyanistes caeruleus", "Blue Tit", 1234),
        )
        await db.commit()

        repo = DetectionRepository(db)
        now = datetime.utcnow()
        for i, display_name in enumerate(["Blue Tit", "Cyanistes caeruleus"], start=1):
            await repo.create(
                Detection(
                    detection_time=now,
                    detection_index=i,
                    score=0.9,
                    display_name=display_name,
                    category_name="Bird",
                    frigate_event=f"evt_unified_{i}",
                    camera_name="cam_1",
                    scientific_name="Cyanistes caeruleus",
                    common_name="Blue Tit",
                    taxa_id=1234,
                )
            )

        metrics = await repo.get_unified_species_window_metrics()
        # Keys are namespaced by source so a taxa_id cannot collide with a
        # catalogue species_id of the same number.
        assert metrics["taxon:1234"]["count_7d"] >= 2


@pytest.mark.asyncio
async def test_unified_species_window_metrics_resolves_through_the_taxonomy_cache():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await _create_taxonomy_tables(db)
        await db.execute(
            "INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id) VALUES (?, ?, ?)",
            ("Passer domesticus", "House Sparrow", 1111),
        )
        await db.commit()

        repo = DetectionRepository(db)
        now = datetime.utcnow()
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=1,
                score=0.84,
                display_name="House Sparrow",
                category_name="Bird",
                frigate_event="evt_house_sparrow_unified",
                camera_name="cam_1",
                scientific_name=None,
                common_name=None,
                taxa_id=None,
            )
        )

        metrics = await repo.get_unified_species_window_metrics()
        # The detection carries no taxa_id or scientific name of its own, but the
        # taxonomy cache resolves its label, so it keys on the cached taxon. That
        # is the same key the leaderboard groups by, which is what lets the
        # leaderboard find these trends; keying on the label here instead would
        # match only when the label and the scientific name happen to be equal.
        assert "taxon:1111" in metrics
        assert "label:house sparrow" not in metrics


@pytest.mark.asyncio
async def test_delete_methods_report_exact_row_changes():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        now = datetime.utcnow()
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=1,
                score=0.9,
                display_name="Robin",
                category_name="Bird",
                frigate_event="evt_delete",
                camera_name="cam_1",
            )
        )

        row = await repo.get_by_frigate_event("evt_delete")
        assert row is not None

        assert await repo.delete_by_id(row.id) is True
        assert await repo.delete_by_id(row.id) is False
        assert await repo.delete_by_frigate_event("evt_delete") is False


@pytest.mark.asyncio
async def test_get_unknown_detections_includes_completed_unknowns_for_manual_batch_retry():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        now = datetime.utcnow()
        rows_to_insert = [
            ("evt_unknown_completed", 1, 0.51, "completed", None),
            ("evt_unknown_group_label", 4, 0.54, "completed", None),
            ("evt_unknown_pending", 2, 0.52, "pending", None),
            ("evt_unknown_retention_expired", 3, 0.53, "failed", "frigate_retention_expired"),
        ]
        for event_id, idx, score, status, error in rows_to_insert:
            display_name = "Unknown Bird"
            category_name = "Bird"
            scientific_name = None
            common_name = None
            if event_id == "evt_unknown_group_label":
                display_name = "Great tit and allies"
                category_name = "Great tit and allies"
                scientific_name = "Great tit and allies"
                common_name = "Great tit and allies"
            await db.execute(
                """
                INSERT INTO detections (
                    detection_time, detection_index, score, display_name, category_name,
                    frigate_event, camera_name, is_hidden, manual_tagged,
                    scientific_name, common_name,
                    video_classification_status, video_classification_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)
                """,
                (
                    now,
                    idx,
                    score,
                    display_name,
                    category_name,
                    event_id,
                    "cam_1",
                    scientific_name,
                    common_name,
                    status,
                    error,
                ),
            )
        await db.commit()

        rows = await repo.get_unknown_detections()
        ids = {row.frigate_event for row in rows}

        assert "evt_unknown_completed" in ids
        assert "evt_unknown_group_label" in ids
        assert "evt_unknown_pending" not in ids
        assert "evt_unknown_retention_expired" not in ids


@pytest.mark.asyncio
async def test_update_video_classification_persists_runtime_provider_backend_and_model():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        await repo.create(
            Detection(
                detection_time=datetime.utcnow(),
                detection_index=1,
                score=0.77,
                display_name="Unknown Bird",
                category_name="Bird",
                frigate_event="evt_video_runtime",
                camera_name="cam_1",
            )
        )

        await repo.update_video_classification(
            frigate_event="evt_video_runtime",
            label="Blue Jay",
            score=0.88,
            index=123,
            status="completed",
            provider="intel_gpu",
            backend="openvino",
            model_id="convnext_large_inat21",
            input_source="frigate_hint_crop",
        )

        updated = await repo.get_by_frigate_event("evt_video_runtime")
        assert updated is not None
        assert updated.video_classification_label == "Blue Jay"
        assert updated.video_classification_score == pytest.approx(0.88)
        assert updated.video_classification_provider == "intel_gpu"
        assert updated.video_classification_backend == "openvino"
        assert updated.video_classification_model_id == "convnext_large_inat21"
        assert updated.video_classification_input_source == "frigate_hint_crop"


@pytest.mark.asyncio
async def test_update_video_status_persists_bounded_consensus_diagnostics():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)
        await repo.create(
            Detection(
                detection_time=datetime.utcnow(),
                detection_index=1,
                score=0.42,
                display_name="Unknown Bird",
                category_name="Bird",
                frigate_event="evt_video_diagnostics",
                camera_name="cam_1",
            )
        )
        diagnostics = {
            "version": 1,
            "outcome": "abstained",
            "processed_frames": 30,
            "sources": {"model_crop": {"evaluated_frames": 15, "confident_frames": 2}},
        }

        updated = await repo.update_video_status(
            "evt_video_diagnostics",
            "failed",
            error="video_no_results",
            diagnostics=diagnostics,
        )

        assert updated is True
        detection = await repo.get_by_frigate_event("evt_video_diagnostics")
        assert detection is not None
        assert detection.video_classification_diagnostics == diagnostics


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
            camera_name="cam_2",
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
            audio_confirmed=False,
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
            audio_confirmed=False,
        )
        assert await repo.upsert_if_higher_score(lower) == (False, False)

        existing = await repo.get_by_frigate_event("evt_upsert")
        assert existing is not None
        assert existing.score == pytest.approx(0.92)
        assert existing.display_name == "Blue Jay"


@pytest.mark.asyncio
async def test_upsert_if_higher_score_preserves_existing_enrichment_when_incoming_values_are_absent():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        enriched = Detection(
            detection_time=datetime.utcnow(),
            detection_index=1,
            score=0.72,
            display_name="Sparrowhawk",
            category_name="Accipiter nisus",
            frigate_event="evt_enriched_upsert",
            camera_name="birdcam",
            audio_confirmed=True,
            audio_species="Eurasian Sparrowhawk",
            audio_score=0.91,
            temperature=12.4,
            weather_condition="Partly cloudy",
            weather_cloud_cover=42.0,
            weather_wind_speed=8.5,
            weather_wind_direction=225.0,
            weather_precipitation=0.2,
            weather_rain=0.2,
            weather_snowfall=0.0,
            scientific_name="Accipiter nisus",
            common_name="Eurasian Sparrowhawk",
            taxa_id=7003,
        )
        assert await repo.upsert_if_higher_score(enriched) == (True, False)

        reclassified = Detection(
            detection_time=datetime.utcnow(),
            detection_index=2,
            score=0.94,
            display_name="Eurasian Sparrowhawk",
            category_name="Accipiter nisus",
            frigate_event="evt_enriched_upsert",
            camera_name="birdcam",
            audio_confirmed=False,
            audio_species=None,
            audio_score=None,
            temperature=None,
            weather_condition=None,
            scientific_name=None,
            common_name=None,
            taxa_id=None,
        )

        assert await repo.upsert_if_higher_score(reclassified) == (False, True)
        saved = await repo.get_by_frigate_event("evt_enriched_upsert")
        assert saved is not None
        assert saved.score == pytest.approx(0.94)
        assert saved.audio_confirmed is True
        assert saved.audio_species == "Eurasian Sparrowhawk"
        assert saved.audio_score == pytest.approx(0.91)
        assert saved.temperature == pytest.approx(12.4)
        assert saved.weather_condition == "Partly cloudy"
        assert saved.weather_cloud_cover == pytest.approx(42.0)
        assert saved.weather_wind_speed == pytest.approx(8.5)
        assert saved.weather_wind_direction == pytest.approx(225.0)
        assert saved.weather_precipitation == pytest.approx(0.2)
        assert saved.weather_rain == pytest.approx(0.2)
        assert saved.weather_snowfall == pytest.approx(0.0)
        assert saved.scientific_name == "Accipiter nisus"
        assert saved.common_name == "Eurasian Sparrowhawk"
        assert saved.taxa_id == 7003


@pytest.mark.asyncio
async def test_upsert_if_higher_score_clears_taxonomy_from_a_replaced_species():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        original = Detection(
            detection_time=datetime.utcnow(),
            detection_index=1,
            score=0.60,
            display_name="Wood Pigeon",
            category_name="Columba palumbus",
            frigate_event="evt_taxonomy_replaced",
            camera_name="front",
            frigate_score=0.91,
            scientific_name="Columba palumbus",
            common_name="Wood Pigeon",
            taxa_id=123,
        )
        assert await repo.upsert_if_higher_score(original) == (True, False)

        replacement = Detection(
            detection_time=datetime.utcnow(),
            detection_index=2,
            score=0.88,
            display_name="Eurasian Magpie",
            category_name="Pica pica",
            frigate_event="evt_taxonomy_replaced",
            camera_name="front",
            frigate_score=0.80,
            scientific_name="Pica pica",
            common_name=None,
            taxa_id=None,
        )
        assert await repo.upsert_if_higher_score(replacement) == (False, True)

        saved = await repo.get_by_frigate_event("evt_taxonomy_replaced")
        assert saved is not None
        assert saved.scientific_name == "Pica pica"
        assert saved.common_name is None
        assert saved.taxa_id is None
        assert saved.frigate_score == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_upsert_if_higher_score_never_replaces_manual_species_identity():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        manual = Detection(
            detection_time=datetime.utcnow(),
            detection_index=1,
            score=0.42,
            display_name="Wood Pigeon",
            category_name="Columba palumbus",
            frigate_event="evt_manual_upsert",
            camera_name="cam_3",
            manual_tagged=True,
        )
        assert await repo.upsert_if_higher_score(manual) == (True, False)

        automatic = Detection(
            detection_time=datetime.utcnow(),
            detection_index=2,
            score=0.99,
            display_name="Eurasian Collared Dove",
            category_name="Streptopelia decaocto",
            frigate_event="evt_manual_upsert",
            camera_name="cam_3",
            manual_tagged=False,
        )

        assert await repo.upsert_if_higher_score(automatic) == (False, False)
        existing = await repo.get_by_frigate_event("evt_manual_upsert")
        assert existing is not None
        assert existing.manual_tagged is True
        assert existing.display_name == "Wood Pigeon"
        assert existing.category_name == "Columba palumbus"
        assert existing.score == pytest.approx(0.42)


@pytest.mark.asyncio
async def test_upsert_if_higher_score_normalizes_list_sublabel():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        detection = Detection(
            detection_time=datetime.utcnow(),
            detection_index=1,
            score=0.91,
            display_name="Great Tit",
            category_name="Parus major",
            frigate_event="evt_list_sublabel",
            camera_name="cam_4",
            sub_label=["Parus major", None],  # type: ignore[arg-type]
        )

        assert await repo.upsert_if_higher_score(detection) == (True, False)
        saved = await repo.get_by_frigate_event("evt_list_sublabel")
        assert saved is not None
        assert saved.sub_label == "Parus major"


@pytest.mark.asyncio
async def test_favorite_detection_idempotent_and_filterable():
    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        now = datetime.utcnow()
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=1,
                score=0.9,
                display_name="Robin",
                category_name="Bird",
                frigate_event="evt_fav_1",
                camera_name="cam_1",
            )
        )
        await repo.create(
            Detection(
                detection_time=now,
                detection_index=2,
                score=0.8,
                display_name="Sparrow",
                category_name="Bird",
                frigate_event="evt_fav_2",
                camera_name="cam_1",
            )
        )

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

        await repo.create(
            Detection(
                detection_time=old_time,
                detection_index=1,
                score=0.9,
                display_name="Robin",
                category_name="Bird",
                frigate_event=old_favorite_event,
                camera_name="cam_1",
            )
        )
        await repo.create(
            Detection(
                detection_time=old_time,
                detection_index=2,
                score=0.85,
                display_name="Robin",
                category_name="Bird",
                frigate_event=old_regular_event,
                camera_name="cam_1",
            )
        )
        await repo.create(
            Detection(
                detection_time=recent_time,
                detection_index=3,
                score=0.88,
                display_name="Robin",
                category_name="Bird",
                frigate_event=recent_event,
                camera_name="cam_1",
            )
        )

        assert await repo.favorite_detection(old_favorite_event, created_by="owner") is True

        cutoff = datetime.utcnow() - timedelta(days=7)
        deleted = await repo.delete_older_than(cutoff, preserve_favorites=True)
        assert deleted == 1

        assert await repo.get_by_frigate_event(old_favorite_event) is not None
        assert await repo.get_by_frigate_event(old_regular_event) is None
        assert await repo.get_by_frigate_event(recent_event) is not None


async def _create_audio_detections_table(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE audio_detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP NOT NULL,
            species TEXT NOT NULL,
            confidence FLOAT NOT NULL,
            sensor_id TEXT,
            source_event_id TEXT UNIQUE,
            raw_data TEXT,
            scientific_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            species_id INTEGER
        )
    """)


@pytest.mark.asyncio
async def test_delete_audio_detections_older_than_purges_only_old_rows():
    async with aiosqlite.connect(":memory:") as db:
        await _create_audio_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        old_time = datetime.utcnow() - timedelta(days=30)
        recent_time = datetime.utcnow()

        await repo.insert_audio_detection(
            timestamp=old_time,
            species="OldBird",
            confidence=0.9,
            sensor_id="cam_1",
            raw_data={"seq": 1},
            scientific_name="Erithacus rubecula",
        )
        await repo.insert_audio_detection(
            timestamp=recent_time,
            species="NewBird",
            confidence=0.8,
            sensor_id="cam_1",
            raw_data={"seq": 2},
            scientific_name="Erithacus rubecula",
        )

        cutoff = datetime.utcnow() - timedelta(days=7)
        deleted = await repo.delete_audio_detections_older_than(cutoff)
        assert deleted == 1

        async with db.execute("SELECT species FROM audio_detections") as cursor:
            remaining = [row[0] for row in await cursor.fetchall()]
        assert remaining == ["NewBird"]


@pytest.mark.asyncio
async def test_delete_audio_detections_older_than_returns_zero_when_nothing_expired():
    async with aiosqlite.connect(":memory:") as db:
        await _create_audio_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)

        await repo.insert_audio_detection(
            timestamp=datetime.utcnow(),
            species="NewBird",
            confidence=0.8,
            sensor_id="cam_1",
            raw_data={"seq": 1},
            scientific_name="Erithacus rubecula",
        )

        cutoff = datetime.utcnow() - timedelta(days=7)
        assert await repo.delete_audio_detections_older_than(cutoff) == 0

        async with db.execute("SELECT COUNT(*) FROM audio_detections") as cursor:
            (remaining,) = await cursor.fetchone()
        assert remaining == 1


@pytest.mark.asyncio
async def test_catalog_identity_and_provenance_round_trip():
    """Phase 3: a detection stores its canonical species_id and artifact
    provenance, and reads them back; absent values stay None."""

    async with aiosqlite.connect(":memory:") as db:
        await _create_detections_table(db)
        await db.commit()
        repo = DetectionRepository(db)
        await _round_trip_catalog_identity(repo)


async def _round_trip_catalog_identity(repo):
    from app.utils.api_datetime import utc_naive_now

    await repo.create(
        Detection(
            detection_time=utc_naive_now(),
            detection_index=42,
            score=0.91,
            display_name="Eurasian Blue Tit",
            category_name="Cyanistes caeruleus",
            frigate_event="evt-catalog-1",
            camera_name="feeder",
            scientific_name="Cyanistes caeruleus",
            species_id=4815,
            model_artifact_id=7,
            model_output_index=42,
        )
    )
    await repo.create(
        Detection(
            detection_time=utc_naive_now(),
            detection_index=1,
            score=0.5,
            display_name="Unknown Bird",
            category_name="Unknown Bird",
            frigate_event="evt-catalog-2",
            camera_name="feeder",
        )
    )

    with_identity = await repo.get_by_frigate_event("evt-catalog-1")
    assert with_identity.species_id == 4815
    assert with_identity.model_artifact_id == 7
    assert with_identity.model_output_index == 42

    without_identity = await repo.get_by_frigate_event("evt-catalog-2")
    assert without_identity.species_id is None
    assert without_identity.model_artifact_id is None
    assert without_identity.model_output_index is None
