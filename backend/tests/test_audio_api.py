from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.database import get_db, init_db, close_db
from app.config import settings


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
def reset_auth_config():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    original_show_camera_names = settings.public_access.show_camera_names
    original_camera_audio_mapping = dict(settings.frigate.camera_audio_mapping)
    original_correlation_window = settings.frigate.audio_correlation_window_seconds
    yield
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled
    settings.public_access.show_camera_names = original_show_camera_names
    settings.frigate.camera_audio_mapping = original_camera_audio_mapping
    settings.frigate.audio_correlation_window_seconds = original_correlation_window


@pytest.mark.asyncio
async def test_audio_sources_returns_recent_distinct_source_names(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = datetime.now(timezone.utc)
    rows = [
        (
            (now - timedelta(minutes=1)).isoformat(sep=" "),
            "Dunnock",
            0.9,
            "BirdCam",
            json.dumps({"nm": "BirdCam", "src": "rtsp_new", "Source": {"id": "rtsp_new", "displayName": "BirdCam"}}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(minutes=5)).isoformat(sep=" "),
            "Woodpigeon",
            0.8,
            "BirdCam",
            json.dumps({"nm": "BirdCam", "src": "rtsp_old", "Source": {"id": "rtsp_old", "displayName": "BirdCam"}}),
            "Columba palumbus",
        ),
        (
            (now - timedelta(minutes=2)).isoformat(sep=" "),
            "Blue Tit",
            0.85,
            "Garden Mic",
            json.dumps({"Source": {"id": "rtsp_garden", "displayName": "Garden Mic"}}),
            "Cyanistes caeruleus",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get("/api/audio/sources?limit=10")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert [item["source_name"] for item in payload] == ["BirdCam", "Garden Mic"]

    birdcam = payload[0]
    assert birdcam["mapping_value"] == "BirdCam"
    assert birdcam["sample_source_id"] == "rtsp_new"
    assert birdcam["seen_count"] == 2
    assert birdcam["last_seen"].startswith(now.strftime("%Y-%m-%d"))


@pytest.mark.asyncio
async def test_audio_sources_falls_back_to_source_id_when_name_missing(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = datetime.now(timezone.utc)
    row = (
        now.isoformat(sep=" "),
        "House Sparrow",
        0.91,
        None,
        json.dumps({"sourceId": "rtsp_livepayload", "CommonName": "House Sparrow"}),
        "Passer domesticus",
    )

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            row,
        )
        await db.commit()

    response = await client.get("/api/audio/sources?limit=10")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert len(payload) == 1
    assert payload[0]["source_name"] == "rtsp_livepayload"
    assert payload[0]["mapping_value"] == "rtsp_livepayload"
    assert payload[0]["sample_source_id"] == "rtsp_livepayload"


@pytest.mark.asyncio
async def test_audio_sources_uses_birdnet_source_name(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = datetime.now(timezone.utc)
    row = (
        now.isoformat(sep=" "),
        "House Sparrow",
        0.91,
        "rtsp_livepayload",
        json.dumps({"sourceName": "Patio Mic", "sourceId": "rtsp_livepayload"}),
        "Passer domesticus",
    )

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            row,
        )
        await db.commit()

    response = await client.get("/api/audio/sources?limit=10")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert len(payload) == 1
    assert payload[0]["source_name"] == "Patio Mic"
    assert payload[0]["mapping_value"] == "Patio Mic"
    assert payload[0]["sample_source_id"] == "rtsp_livepayload"


@pytest.mark.asyncio
async def test_audio_history_filters_persisted_birdnet_detections(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        (
            (now - timedelta(hours=1)).isoformat(sep=" "),
            "Dunnock",
            0.92,
            "BirdCam",
            json.dumps({"detectionId": 101, "nm": "BirdCam", "src": "rtsp_birdcam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(hours=2)).isoformat(sep=" "),
            "Blue Tit",
            0.88,
            "Garden Mic",
            json.dumps({"detectionId": 102, "nm": "Garden Mic", "src": "rtsp_garden"}),
            "Cyanistes caeruleus",
        ),
        (
            (now - timedelta(days=10)).isoformat(sep=" "),
            "Dunnock",
            0.7,
            "BirdCam",
            json.dumps({"detectionId": 103, "nm": "BirdCam", "src": "rtsp_birdcam"}),
            "Prunella modularis",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get(
        "/api/audio/history",
        params={
            "days": 2,
            "species": "dun",
            "source": "BirdCam",
            "min_confidence": 0.8,
            "limit": 10,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["total"] == 1
    assert payload["limit"] == 10
    assert payload["offset"] == 0
    assert len(payload["items"]) == 1
    assert payload["items"][0]["species"] == "Dunnock"
    assert payload["items"][0]["source_name"] == "BirdCam"
    assert payload["items"][0]["birdnet_id"] == 101
    assert "scientific_name" not in payload["items"][0]


@pytest.mark.asyncio
async def test_audio_history_links_only_matching_automatic_video_classifications(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"birdcam": "BirdCam", "nestcam": "NestCam"}
    settings.frigate.audio_correlation_window_seconds = 300

    now = datetime.now(timezone.utc).replace(microsecond=0)
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute("DELETE FROM detections")
        await db.executemany(
            """INSERT INTO audio_detections
                   (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    now.isoformat(sep=" "),
                    "Woodpigeon",
                    0.92,
                    "BirdCam",
                    json.dumps({"detectionId": 201, "nm": "BirdCam"}),
                    "Columba palumbus",
                ),
                (
                    (now - timedelta(seconds=10)).isoformat(sep=" "),
                    "Woodpigeon",
                    0.89,
                    "NestCam",
                    json.dumps({"detectionId": 202, "nm": "NestCam"}),
                    "Columba palumbus",
                ),
            ],
        )
        detection_rows = [
            ("auto-match", "birdcam", 40, 0, 0, "completed", "Columba palumbus", 0.82),
            ("manual-closer", "birdcam", 5, 1, 0, "completed", "Columba palumbus", 0.99),
            ("hidden-closer", "birdcam", 8, 0, 1, "completed", "Columba palumbus", 0.99),
            ("wrong-camera", "nestcam", 3, 0, 0, "completed", "Columba palumbus", 0.98),
            ("wrong-species", "birdcam", 2, 0, 0, "completed", "Pica pica", 0.99),
            ("failed-video", "birdcam", 1, 0, 0, "failed", "Columba palumbus", 0.99),
        ]
        for event_id, camera, delta, manual, hidden, status, label, score in detection_rows:
            await db.execute(
                """INSERT INTO detections
                       (detection_time, detection_index, score, display_name, category_name,
                        frigate_event, camera_name, manual_tagged, is_hidden,
                        video_classification_status, video_classification_label,
                        video_classification_score)
                       VALUES (?, 1, 0.8, 'Bird', 'Bird', ?, ?, ?, ?, ?, ?, ?)""",
                (
                    (now + timedelta(seconds=delta)).isoformat(sep=" "),
                    event_id,
                    camera,
                    manual,
                    hidden,
                    status,
                    label,
                    score,
                ),
            )
        await db.commit()

    response = await client.get("/api/audio/history", params={"days": 1, "limit": 10})
    assert response.status_code == 200, response.text
    items = {item["birdnet_id"]: item for item in response.json()["items"]}

    assert items[201]["matched_visual_event_id"] == "auto-match"
    assert items[202]["matched_visual_event_id"] == "wrong-camera"


@pytest.mark.asyncio
async def test_audio_summary_rolls_up_persisted_history(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=12,
        minute=0,
        second=0,
        microsecond=0,
    )
    rows = [
        (
            (now - timedelta(hours=1)).isoformat(sep=" "),
            "Dunnock",
            0.92,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(hours=2)).isoformat(sep=" "),
            "Dunnock",
            0.82,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(days=1)).isoformat(sep=" "),
            "Blue Tit",
            0.88,
            "Garden Mic",
            json.dumps({"Source": {"displayName": "Garden Mic"}}),
            "Cyanistes caeruleus",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get("/api/audio/summary", params={"days": 7})
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["total"] == 3
    assert payload["species_count"] == 2
    assert payload["source_count"] == 2
    assert payload["top_species"][0]["species"] == "Dunnock"
    assert payload["top_species"][0]["count"] == 2
    assert "scientific_name" not in payload["top_species"][0]
    assert {item["date"] for item in payload["daily_counts"]} == {
        now.strftime("%Y-%m-%d"),
        (now - timedelta(days=1)).strftime("%Y-%m-%d"),
    }
    assert any(item["hour"] == 11 and item["count"] == 1 for item in payload["hourly_counts"])
    assert [item["source_name"] for item in payload["sources"]] == ["BirdCam", "Garden Mic"]


@pytest.mark.asyncio
async def test_audio_species_leaderboard_counts_window_and_prev(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        # Dunnock: two in the current 7-day window, one in the prior window.
        (
            (now - timedelta(hours=1)).isoformat(sep=" "),
            "Dunnock",
            0.92,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(hours=2)).isoformat(sep=" "),
            "Dunnock",
            0.82,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(days=10)).isoformat(sep=" "),
            "Dunnock",
            0.71,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        # Blue Tit: one in the current window, none prior.
        (
            (now - timedelta(hours=3)).isoformat(sep=" "),
            "Blue Tit",
            0.88,
            "Garden Mic",
            json.dumps({"nm": "Garden Mic"}),
            "Cyanistes caeruleus",
        ),
        # Robin: outside both windows — must be excluded.
        (
            (now - timedelta(days=20)).isoformat(sep=" "),
            "Robin",
            0.9,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Erithacus rubecula",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute("DELETE FROM taxonomy_cache")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get("/api/audio/species", params={"span": "week"})
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["span"] == "week"
    species = payload["species"]
    names = [item["species"] for item in species]
    assert names == ["Dunnock", "Blue Tit"]  # sorted by heard_count desc, Robin excluded

    dunnock = species[0]
    assert dunnock["heard_count"] == 2
    assert dunnock["heard_prev_count"] == 1
    assert dunnock["heard_delta"] == 1
    assert dunnock["heard_percent"] == 100.0
    assert dunnock["scientific_name"] == "Prunella modularis"
    assert dunnock["last_heard"] is not None

    blue_tit = species[1]
    assert blue_tit["heard_count"] == 1
    assert blue_tit["heard_prev_count"] == 0
    assert blue_tit["heard_percent"] == 0.0


@pytest.mark.asyncio
async def test_audio_species_leaderboard_all_span_counts_everything(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    now = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        (
            (now - timedelta(hours=1)).isoformat(sep=" "),
            "Dunnock",
            0.9,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(days=40)).isoformat(sep=" "),
            "Dunnock",
            0.7,
            "BirdCam",
            json.dumps({"nm": "BirdCam"}),
            "Prunella modularis",
        ),
        (
            (now - timedelta(hours=2)).isoformat(sep=" "),
            "Blue Tit",
            0.85,
            "Garden Mic",
            json.dumps({"nm": "Garden Mic"}),
            "Cyanistes caeruleus",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute("DELETE FROM taxonomy_cache")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get("/api/audio/species", params={"span": "all"})
    assert response.status_code == 200, response.text
    payload = response.json()

    by_name = {item["species"]: item for item in payload["species"]}
    assert by_name["Dunnock"]["heard_count"] == 2  # includes the 40-day-old row
    assert by_name["Dunnock"]["heard_prev_count"] == 0
    assert by_name["Dunnock"]["heard_delta"] == 2
    assert by_name["Blue Tit"]["heard_count"] == 1


@pytest.mark.asyncio
async def test_audio_context_supports_multi_source_camera_mapping(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"front": "BirdCam, Garden Mic"}

    target = datetime.now(timezone.utc).replace(microsecond=0)
    rows = [
        (
            (target - timedelta(seconds=15)).isoformat(sep=" "),
            "Dunnock",
            0.81,
            "BirdCam",
            json.dumps({"nm": "BirdCam", "src": "rtsp_birdcam"}),
            "Prunella modularis",
        ),
        (
            (target + timedelta(seconds=12)).isoformat(sep=" "),
            "Blue Tit",
            0.74,
            "Garden Mic",
            json.dumps({"nm": "Garden Mic", "src": "rtsp_garden"}),
            "Cyanistes caeruleus",
        ),
        (
            (target + timedelta(seconds=8)).isoformat(sep=" "),
            "Woodpigeon",
            0.7,
            "Other Mic",
            json.dumps({"nm": "Other Mic", "src": "rtsp_other"}),
            "Columba palumbus",
        ),
    ]

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        for row in rows:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                row,
            )
        await db.commit()

    response = await client.get(
        "/api/audio/context",
        params={
            "timestamp": target.isoformat(),
            "camera": "front",
            "window_seconds": 60,
            "limit": 10,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    species = [item["species"] for item in payload]
    assert "Dunnock" in species
    assert "Blue Tit" in species
    assert "Woodpigeon" not in species


@pytest.mark.asyncio
async def test_audio_context_matches_birdnet_source_name(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera_audio_mapping = {"front": "Patio Mic"}

    target = datetime.now(timezone.utc).replace(microsecond=0)
    row = (
        target.isoformat(sep=" "),
        "Dunnock",
        0.81,
        "rtsp_livepayload",
        json.dumps({"sourceName": "Patio Mic", "sourceId": "rtsp_livepayload"}),
        "Prunella modularis",
    )

    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        await db.execute(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            row,
        )
        await db.commit()

    response = await client.get(
        "/api/audio/context",
        params={
            "timestamp": target.isoformat(),
            "camera": "front",
            "window_seconds": 60,
            "limit": 10,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["species"] for item in payload] == ["Dunnock"]


@pytest.mark.asyncio
async def test_audio_recent_replaces_locale_species_with_canonical_english(client: httpx.AsyncClient):
    """Regression for issue #46 — Dashboard 'Recent audio' must show the user's locale,
    not whatever language BirdNET-Go publishes in ``comName``. Mirrors the response-time
    transform already deployed for the species/leaderboard endpoints."""
    settings.auth.enabled = False
    settings.public_access.enabled = False

    from app.services.audio.audio_service import audio_service, AudioDetection
    from datetime import datetime, timezone

    async with get_db() as db:
        await db.execute("DELETE FROM taxonomy_cache")
        await db.execute(
            """INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found, last_updated)
               VALUES (?, ?, ?, 0, ?)""",
            ("Passer domesticus", "House Sparrow", 12345, datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()

    async with audio_service._lock:
        audio_service._buffer.clear()
        audio_service._buffer.append(
            AudioDetection(
                timestamp=datetime.now(timezone.utc),
                species="Домовый воробей",
                confidence=0.9,
                sensor_id="BirdCam",
                raw_data={},
                scientific_name="Passer domesticus",
            )
        )

    try:
        response = await client.get("/api/audio/recent", params={"limit": 5})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["species"] == "House Sparrow"
        assert "scientific_name" not in payload[0]
    finally:
        async with audio_service._lock:
            audio_service._buffer.clear()


@pytest.mark.asyncio
async def test_audio_recent_falls_back_when_taxa_id_missing(client: httpx.AsyncClient):
    """A detection with no ``scientific_name`` (or no matching taxonomy_cache row)
    must fall back to the stored species string — graceful degradation."""
    settings.auth.enabled = False
    settings.public_access.enabled = False

    from app.services.audio.audio_service import audio_service, AudioDetection
    from datetime import datetime, timezone

    async with audio_service._lock:
        audio_service._buffer.clear()
        audio_service._buffer.append(
            AudioDetection(
                timestamp=datetime.now(timezone.utc),
                species="Dunnock",
                confidence=0.8,
                sensor_id="BirdCam",
                raw_data={},
                scientific_name=None,
            )
        )

    try:
        response = await client.get("/api/audio/recent", params={"limit": 5})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload[0]["species"] == "Dunnock"
    finally:
        async with audio_service._lock:
            audio_service._buffer.clear()


@pytest.mark.asyncio
async def test_audio_recent_resolves_via_translation_when_scientific_name_missing(client: httpx.AsyncClient):
    """Issue #46 follow-up — when BirdNET-Go publishes a non-English ``comName`` and
    no ``ScientificName``, the audio service stores ``scientific_name = None`` (or the
    raw locale string with no taxa_id). The localizer must still recover the canonical
    English name by matching the stored species text against ``taxonomy_translations``.
    """
    settings.auth.enabled = False
    settings.public_access.enabled = False

    from app.services.audio.audio_service import audio_service, AudioDetection
    from datetime import datetime, timezone

    async with get_db() as db:
        await db.execute("DELETE FROM taxonomy_cache")
        await db.execute("DELETE FROM taxonomy_translations")
        await db.execute(
            """INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found, last_updated)
               VALUES (?, ?, ?, 0, ?)""",
            ("Passer domesticus", "House Sparrow", 12345, datetime.now(timezone.utc).isoformat()),
        )
        await db.execute(
            """INSERT INTO taxonomy_translations (taxa_id, language_code, common_name)
               VALUES (?, ?, ?)""",
            (12345, "ru", "Домовый воробей"),
        )
        await db.commit()

    async with audio_service._lock:
        audio_service._buffer.clear()
        audio_service._buffer.append(
            AudioDetection(
                timestamp=datetime.now(timezone.utc),
                species="Домовый воробей",
                confidence=0.9,
                sensor_id="BirdCam",
                raw_data={},
                scientific_name=None,
            )
        )

    try:
        response = await client.get("/api/audio/recent", params={"limit": 5})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["species"] == "House Sparrow"
    finally:
        async with audio_service._lock:
            audio_service._buffer.clear()


@pytest.mark.asyncio
async def test_audio_recent_resolves_via_common_name_when_scientific_name_is_locale_text(client: httpx.AsyncClient):
    """Issue #46 follow-up — when ``add_detection`` stored a non-Latin string as
    ``scientific_name`` (because iNaturalist couldn't resolve the BirdNET-Go locale
    comName), the cache row keyed by that string has ``taxa_id = NULL``. The
    localizer must still recover by matching the species text against
    ``taxonomy_cache.common_name`` for any row that *does* have a taxa_id.
    """
    settings.auth.enabled = False
    settings.public_access.enabled = False

    from app.services.audio.audio_service import audio_service, AudioDetection
    from datetime import datetime, timezone

    async with get_db() as db:
        await db.execute("DELETE FROM taxonomy_cache")
        await db.execute(
            """INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found, last_updated)
               VALUES (?, ?, ?, 0, ?)""",
            ("Passer domesticus", "House Sparrow", 12345, datetime.now(timezone.utc).isoformat()),
        )
        # Poisoned row: the locale comName got saved as scientific_name with no taxa_id.
        await db.execute(
            """INSERT INTO taxonomy_cache (scientific_name, common_name, taxa_id, is_not_found, last_updated)
               VALUES (?, NULL, NULL, 1, ?)""",
            ("Домовый воробей", datetime.now(timezone.utc).isoformat()),
        )
        await db.commit()

    async with audio_service._lock:
        audio_service._buffer.clear()
        audio_service._buffer.append(
            AudioDetection(
                timestamp=datetime.now(timezone.utc),
                species="House Sparrow",
                confidence=0.9,
                sensor_id="BirdCam",
                raw_data={},
                scientific_name="Домовый воробей",  # poisoned by ingest pre-fix
            )
        )

    try:
        response = await client.get("/api/audio/recent", params={"limit": 5})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["species"] == "House Sparrow"
    finally:
        async with audio_service._lock:
            audio_service._buffer.clear()
