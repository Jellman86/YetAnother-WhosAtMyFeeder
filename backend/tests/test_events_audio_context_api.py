from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.database import get_db, init_db, close_db
from app.config import settings
from app.repositories.detection_repository import DetectionRepository, Detection
from app.routers.audio import AUDIO_SUPPRESSED_BY_MAPPING_HEADER


def assert_audio_species_matches(actual: list[str], expected: list[str | set[str]]) -> None:
    assert len(actual) == len(expected)
    for actual_value, expected_value in zip(actual, expected):
        if isinstance(expected_value, set):
            assert actual_value in expected_value
        else:
            assert actual_value == expected_value


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def ensure_db_initialized():
    await init_db()
    try:
        yield
    finally:
        await close_db()


@pytest.fixture(autouse=True)
def reset_auth_and_mapping():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    original_mapping = dict(settings.frigate.camera_audio_mapping)
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.frigate.camera_audio_mapping = original_mapping


@pytest.mark.asyncio
async def test_events_include_audio_context_species_for_unmatched_audio(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"feeder-cam": "BirdCam"}

    target = datetime.now(timezone.utc).replace(microsecond=0)
    event_id = f"evt-audio-context-{int(target.timestamp())}"

    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.execute(
            "DELETE FROM audio_detections WHERE timestamp >= ? AND timestamp <= ?",
            (
                (target - timedelta(minutes=5)).isoformat(sep=" "),
                (target + timedelta(minutes=5)).isoformat(sep=" "),
            ),
        )
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged,
                audio_confirmed, audio_species, audio_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
            """,
            (
                target.isoformat(sep=" "),
                1,
                0.82,
                "Great Tit",
                "Great Tit",
                event_id,
                "feeder-cam",
                "Corvus corone",
                0.75,
            ),
        )

        audio_rows = [
            (
                (target - timedelta(seconds=20)).isoformat(sep=" "),
                "Corvus corone",
                0.75,
                "BirdCam",
                json.dumps({"nm": "BirdCam", "src": "rtsp_birdcam"}),
                "Corvus corone",
            ),
            (
                (target + timedelta(seconds=10)).isoformat(sep=" "),
                "Passer domesticus",
                0.66,
                "BirdCam",
                json.dumps({"nm": "BirdCam", "src": "rtsp_birdcam"}),
                "Passer domesticus",
            ),
            (
                (target + timedelta(seconds=5)).isoformat(sep=" "),
                "Turdus merula",
                0.7,
                "OtherMic",
                json.dumps({"nm": "OtherMic", "src": "rtsp_other"}),
                "Turdus merula",
            ),
        ]
        for row in audio_rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get("/api/events", params={"camera": "feeder-cam", "limit": 10})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload, "Expected at least one event row"

    event = next(item for item in payload if item["frigate_event"] == event_id)
    assert event["audio_confirmed"] is False
    assert event["audio_species"] == "Corvus corone"
    assert_audio_species_matches(
        event["audio_context_species"],
        ["Corvus corone", {"Passer domesticus", "House Sparrow"}],
    )


@pytest.mark.asyncio
async def test_event_audio_context_marks_late_species_match_as_visual_confirmation(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"feeder-cam": "BirdCam"}

    target = datetime.now(timezone.utc).replace(microsecond=0)
    event_id = f"evt-late-audio-match-{int(target.timestamp())}"
    async with get_db() as db:
        await db.execute(
            """INSERT INTO detections (
                   detection_time, detection_index, score, display_name, category_name,
                   frigate_event, camera_name, is_hidden, manual_tagged, audio_confirmed,
                   scientific_name, common_name
               ) VALUES (?, 1, 0.88, ?, ?, ?, 'feeder-cam', 0, 0, 0, ?, ?)""",
            (
                target.isoformat(sep=" "),
                "Blue Tit",
                "Cyanistes caeruleus",
                event_id,
                "Cyanistes caeruleus",
                "Blue Tit",
            ),
        )
        await db.execute(
            """INSERT INTO audio_detections
               (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                (target + timedelta(seconds=12)).isoformat(sep=" "),
                "Eurasian Blue Tit",
                0.79,
                "BirdCam",
                json.dumps({"nm": "BirdCam", "detectionId": 991122}),
                "Cyanistes caeruleus",
            ),
        )
        await db.commit()

    try:
        response = await client.get(f"/api/audio/context/event/{event_id}")
        assert response.status_code == 200, response.text
        payload = response.json()
        late_match = next(item for item in payload if item["scientific_name"] == "Cyanistes caeruleus")
        assert late_match["matches_visual"] is True
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
            await db.execute(
                "DELETE FROM audio_detections WHERE sensor_id = ? AND scientific_name = ?",
                ("BirdCam", "Cyanistes caeruleus"),
            )
            await db.commit()


@pytest.mark.asyncio
async def test_unmapped_event_camera_suppresses_all_audio_context(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"other-camera": "OtherMic"}

    target = datetime.now(timezone.utc).replace(microsecond=0)
    event_id = f"evt-unmapped-audio-{int(target.timestamp())}"
    async with get_db() as db:
        await db.execute(
            """INSERT INTO detections (
                   detection_time, detection_index, score, display_name, category_name,
                   frigate_event, camera_name, is_hidden, manual_tagged
               ) VALUES (?, 1, 0.8, 'Blue Tit', 'Blue Tit', ?, 'unmapped-camera', 0, 0)""",
            (target.isoformat(sep=" "), event_id),
        )
        await db.execute(
            """INSERT INTO audio_detections
               (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
               VALUES (?, 'Blue Tit', 0.9, 'GardenMic', ?, 'Cyanistes caeruleus')""",
            (target.isoformat(sep=" "), json.dumps({"nm": "GardenMic"})),
        )
        await db.commit()

    try:
        response = await client.get(f"/api/audio/context/event/{event_id}")
        assert response.status_code == 200, response.text
        assert response.json() == []
        assert int(response.headers[AUDIO_SUPPRESSED_BY_MAPPING_HEADER]) >= 1
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
            await db.execute("DELETE FROM audio_detections WHERE sensor_id = 'GardenMic'")
            await db.commit()


@pytest.mark.asyncio
async def test_events_handles_mixed_naive_and_aware_timestamps_for_audio_context(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"feeder-cam": "BirdCam"}

    target_aware = datetime.now(timezone.utc).replace(microsecond=0)
    target_naive = target_aware.replace(tzinfo=None)
    event_id = f"evt-audio-mixed-ts-{int(target_aware.timestamp())}"

    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.execute(
            "DELETE FROM audio_detections WHERE timestamp >= ? AND timestamp <= ?",
            (
                (target_aware - timedelta(minutes=5)).isoformat(sep=" "),
                (target_aware + timedelta(minutes=5)).isoformat(sep=" "),
            ),
        )
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged,
                audio_confirmed, audio_species, audio_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
            """,
            (
                target_naive.isoformat(sep=" "),
                1,
                0.77,
                "Blue Tit",
                "Blue Tit",
                event_id,
                "feeder-cam",
                "Passer domesticus",
                0.61,
            ),
        )
        await db.execute(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                (target_aware + timedelta(seconds=8)).isoformat(sep=" "),
                "Passer domesticus",
                0.61,
                "BirdCam",
                json.dumps({"nm": "BirdCam", "src": "rtsp_birdcam"}),
                "Passer domesticus",
            ),
        )
        await db.commit()

    response = await client.get("/api/events", params={"camera": "feeder-cam", "limit": 10})
    assert response.status_code == 200, response.text
    payload = response.json()
    event = next(item for item in payload if item["frigate_event"] == event_id)
    assert_audio_species_matches(
        event["audio_context_species"],
        [{"Passer domesticus", "House Sparrow"}],
    )


@pytest.mark.asyncio
async def test_events_normalize_non_utc_audio_offsets_before_context_filtering(client: httpx.AsyncClient):
    """A local-offset BirdNET timestamp must match a naive-UTC visual event."""
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"feeder-cam": "OffsetBirdCam"}

    target_utc = datetime.now(timezone.utc).replace(microsecond=0)
    target_naive = target_utc.replace(tzinfo=None)
    event_id = f"evt-audio-offset-ts-{int(target_utc.timestamp())}"
    british_summer_time = timezone(timedelta(hours=1))
    heard_at = (target_utc + timedelta(seconds=8)).astimezone(british_summer_time)

    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden, manual_tagged
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)
            """,
            (
                target_naive.isoformat(sep=" "),
                1,
                0.77,
                "Blue Tit",
                "Blue Tit",
                event_id,
                "feeder-cam",
            ),
        )
        await DetectionRepository(db).insert_audio_detection(
            timestamp=heard_at,
            species="Passer domesticus",
            confidence=0.61,
            sensor_id="OffsetBirdCam",
            raw_data={"nm": "OffsetBirdCam", "src": "rtsp_offset_birdcam"},
            scientific_name="Passer domesticus",
        )

    response = await client.get(f"/api/audio/context/event/{event_id}")
    assert response.status_code == 200, response.text
    assert_audio_species_matches(
        [item["species"] for item in response.json()],
        [{"Passer domesticus", "House Sparrow"}],
    )


@pytest.mark.asyncio
async def test_audio_context_reports_detections_suppressed_by_camera_mapping(client: httpx.AsyncClient):
    """An empty result must say whether audio was absent or excluded by the mapping.

    A camera mapped to its own microphone hides audio heard on a different one.
    Reporting that as plainly "no nearby audio" is indistinguishable from a silent
    window, so the caller cannot tell a quiet garden from a filtered one.
    """
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"feeder-cam": "BirdCam"}

    target = datetime.now(timezone.utc).replace(microsecond=0)

    async with get_db() as db:
        await db.execute(
            "DELETE FROM audio_detections WHERE timestamp >= ? AND timestamp <= ?",
            (
                (target - timedelta(minutes=5)).isoformat(sep=" "),
                (target + timedelta(minutes=5)).isoformat(sep=" "),
            ),
        )
        # Heard on a different microphone than the one this camera maps to.
        await db.execute(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                (target - timedelta(seconds=30)).isoformat(sep=" "),
                "Common Wood-Pigeon",
                0.53,
                "PatioMic",
                json.dumps({"nm": "PatioMic", "src": "rtsp_patio"}),
                "Columba palumbus",
            ),
        )
        await db.commit()

    response = await client.get(
        "/api/audio/context",
        params={"timestamp": target.isoformat(), "camera": "feeder-cam", "window_seconds": 300},
    )
    assert response.status_code == 200, response.text
    assert response.json() == []
    assert response.headers[AUDIO_SUPPRESSED_BY_MAPPING_HEADER] == "1"


@pytest.mark.asyncio
async def test_audio_context_reports_no_suppression_for_a_genuinely_silent_window(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"feeder-cam": "BirdCam"}

    target = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=400)

    async with get_db() as db:
        await db.execute(
            "DELETE FROM audio_detections WHERE timestamp >= ? AND timestamp <= ?",
            (
                (target - timedelta(minutes=5)).isoformat(sep=" "),
                (target + timedelta(minutes=5)).isoformat(sep=" "),
            ),
        )
        await db.commit()

    response = await client.get(
        "/api/audio/context",
        params={"timestamp": target.isoformat(), "camera": "feeder-cam", "window_seconds": 300},
    )
    assert response.status_code == 200, response.text
    assert response.json() == []
    assert response.headers[AUDIO_SUPPRESSED_BY_MAPPING_HEADER] == "0"


@pytest.mark.asyncio
async def test_fifty_overlapping_owner_audio_contexts_use_one_read(client, monkeypatch):
    import aiosqlite

    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"batch-context-cam": "batch-microphone"}
    target = datetime(2025, 1, 1, tzinfo=timezone.utc)
    event_ids = [f"batched-audio-{index}" for index in range(50)]
    async with get_db() as db:
        for index, event_id in enumerate(event_ids):
            await db.execute(
                """INSERT INTO detections (detection_time, detection_index, score, display_name,
                category_name, frigate_event, camera_name, audio_confirmed, audio_species)
                VALUES (?, 1, 0.8, 'Great Tit', 'Great Tit', ?, 'batch-context-cam', 0, 'Corvus corone')""",
                ((target + timedelta(seconds=index)).isoformat(sep=" "), event_id),
            )
        await db.execute(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
            VALUES (?, 'Passer domesticus', 0.9, 'batch-microphone', '{}', 'Passer domesticus')""",
            (target.isoformat(sep=" "),),
        )
        await db.commit()
    reads = []
    execute = aiosqlite.Connection.execute

    def counted_execute(connection, sql, parameters=None):
        normalized = " ".join(sql.split()).casefold()
        if normalized.startswith("select timestamp, species, confidence, sensor_id, scientific_name, raw_data"):
            reads.append(sql)
        return execute(connection, sql, parameters or [])

    monkeypatch.setattr(aiosqlite.Connection, "execute", counted_execute)
    try:
        response = await client.get("/api/events", params={"camera": "batch-context-cam", "limit": 50})
        assert response.status_code == 200, response.text
        events = response.json()
        assert len(events) == 50
        assert len(reads) == 1
        for event in events:
            assert_audio_species_matches(
                event["audio_context_species"], ["Corvus corone", {"Passer domesticus", "House Sparrow"}]
            )
    finally:
        async with get_db() as db:
            await db.execute("DELETE FROM detections WHERE camera_name = 'batch-context-cam'")
            await db.execute("DELETE FROM audio_detections WHERE sensor_id = 'batch-microphone'")
            await db.commit()


@pytest.mark.asyncio
async def test_batched_owner_contexts_match_single_reads_across_mapping_windows_and_chunks():
    import aiosqlite

    target = datetime(2024, 1, 1, tzinfo=timezone.utc)
    cameras = {"mapped": "mic", "wildcard": "*", "unmapped": "", "payload": "payload-mic"}
    events = [
        Detection(target + timedelta(seconds=offset), 1, 0.8, "bird", "bird", f"context-{camera}-{offset}", camera)
        for camera in cameras
        for offset in (0, 20, 1000)
    ]
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""CREATE TABLE audio_detections (timestamp TEXT, species TEXT, confidence REAL,
                           sensor_id TEXT, scientific_name TEXT, raw_data TEXT, is_hidden INT DEFAULT 0)""")
        # More than a chunk, including hidden rows and exact timestamp boundaries.
        for index in range(620):
            stamp = target + timedelta(seconds=(index % 61) - 30)
            await db.execute(
                "INSERT INTO audio_detections VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    stamp.isoformat(sep=" "),
                    f"species-{index}",
                    (index % 10) / 10,
                    "mic" if index % 3 == 0 else "other",
                    None,
                    json.dumps({"nm": "payload-mic", "detectionId": index}),
                    int(index % 13 == 0),
                ),
            )
        await db.commit()
        repo = DetectionRepository(db)
        expected = {
            event.frigate_event: await repo.get_audio_context(event.detection_time, 30, cameras[event.camera_name], 8)
            for event in events
        }
        actual = await repo.get_audio_contexts_for_detections(events, cameras, 30)
        assert actual == expected
        assert actual["context-unmapped-0"][0] == []
        assert actual["context-unmapped-0"][1] > 0
        assert len(actual["context-wildcard-0"][0]) == 8
        assert actual["context-mapped-1000"] == ([], 0)
        assert await repo.get_audio_contexts_for_detections([], cameras, 30) == {}
