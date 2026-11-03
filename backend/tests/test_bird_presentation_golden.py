"""Bird detections reach every surface exactly as they did before presentation moved out of the routers.

`fixtures/golden/bird_presentation.json` was captured from the routers before
the shared presenter existed, over the seeded history below: events, visits,
the daily summary and species detail, for the owner and for a guest with and
without shared audio, in English and German. Any change to a field, a redaction
or an ordering on any of them fails here.
"""

import json
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import aiosqlite
import httpx
import pytest
import pytest_asyncio

from app.auth import create_access_token
from app.config import settings

GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "bird_presentation.json"
START = datetime(2033, 6, 10, 8, 0, 0)

DETECTIONS = [
    # event, camera, minutes after START, display, category, scientific, common, taxa_id,
    # audio_species, audio_confirmed, audio_score, hidden, manual_tagged
    ("gp-robin", "garden", 0, "Robin", "Robin", "Erithacus rubecula", "European Robin", 12716, "Robin", 1, 0.81, 0, 0),
    ("gp-wren", "garden", 3, "Wren", "Wren", "Troglodytes troglodytes", "Eurasian Wren", 145300, "Wren", 0, 0.62, 0, 1),
    ("gp-unknown", "shed", 9, "background", "background", None, None, None, None, 0, None, 0, 0),
    ("gp-hidden", "garden", 12, "Robin", "Robin", "Erithacus rubecula", "European Robin", 12716, None, 0, None, 1, 0),
    (
        "manual_gp-upload",
        "garden",
        30,
        "Robin",
        "Robin",
        "Erithacus rubecula",
        "European Robin",
        12716,
        None,
        0,
        None,
        0,
        0,
    ),
]

AUDIO = [
    # timestamp offset seconds, species, scientific, confidence, sensor, payload
    (-20, "Robin", "Erithacus rubecula", 0.81, "garden-mic", {"detectionId": 501}),
    (170, "Wren", "Troglodytes troglodytes", 0.62, "garden-mic", {"detectionId": 502}),
    (200, "Dunnock", "Prunella modularis", 0.55, "garden-mic", {"detectionId": 503}),
    (210, "Blackbird", "Turdus merula", 0.51, "shed-mic", {"detectionId": 504}),
]


async def _seed(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        for index, row in enumerate(DETECTIONS):
            (
                event,
                camera,
                minutes,
                display,
                category,
                scientific,
                common,
                taxa,
                audio,
                confirmed,
                score,
                hidden,
                manual,
            ) = row
            await db.execute(
                """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                       frigate_event, camera_name, scientific_name, common_name, taxa_id, audio_species,
                       audio_confirmed, audio_score, is_hidden, manual_tagged, frigate_score, sub_label,
                       temperature, weather_condition, weather_wind_speed, ai_analysis, ai_analysis_timestamp,
                       video_classification_score, video_classification_label, video_classification_status,
                       video_classification_timestamp, video_classification_error, video_classification_provider,
                       video_classification_backend, video_classification_model_id,
                       video_classification_input_source, video_classification_diagnostics, frigate_last_error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0.7, NULL, 14.5, 'Cloudy', 3.2, ?, ?,
                       0.88, ?, 'completed', ?, 'none', 'cpu', 'onnxruntime', 'model-a', 'recording',
                       '{"frames": 4}', 'missing clip')""",
                (
                    (START + timedelta(minutes=minutes)).isoformat(sep=" "),
                    index,
                    0.9 - index * 0.05,
                    display,
                    category,
                    event,
                    camera,
                    scientific,
                    common,
                    taxa,
                    audio,
                    confirmed,
                    score,
                    hidden,
                    manual,
                    f"analysis of {event}",
                    (START + timedelta(minutes=minutes, seconds=30)).isoformat(sep=" "),
                    display,
                    (START + timedelta(minutes=minutes, seconds=20)).isoformat(sep=" "),
                ),
            )
        await db.execute(
            "INSERT INTO detection_favorites (detection_id, archive_snapshot_state, archive_clip_state)"
            " SELECT id, 'durable', 'unavailable' FROM detections WHERE frigate_event = 'gp-robin'"
        )
        await db.execute(
            """INSERT INTO manual_observation_drafts (id, status, media_type, original_filename, content_type,
                   content_sha256, size_bytes, source_filename, saved_event_id, notes, latitude, longitude,
                   location_source)
               VALUES ('draft-1', 'saved', 'image', 'robin.jpg', 'image/jpeg', 'abc', 10, 'robin.jpg',
                   'manual_gp-upload', 'By the pond', 51.501234, -0.141567, 'exif')"""
        )
        for offset, species, scientific, confidence, sensor, payload in AUDIO:
            await db.execute(
                """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data, scientific_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    (START + timedelta(seconds=offset)).isoformat(sep=" "),
                    species,
                    confidence,
                    sensor,
                    json.dumps(payload),
                    scientific,
                ),
            )
        await db.commit()


@pytest_asyncio.fixture
async def presentation_history(migrated_history_db, monkeypatch):
    import app.database as database_module
    from app.main import app
    from app.routers import events, stats
    from app.services.taxonomy.taxonomy_service import taxonomy_service

    await _seed(migrated_history_db)

    @asynccontextmanager
    async def private_history():
        async with aiosqlite.connect(migrated_history_db) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    shared_history = database_module.get_db
    for name, module in list(sys.modules.items()):
        if name.startswith("app.") and getattr(module, "get_db", None) is shared_history:
            monkeypatch.setattr(module, "get_db", private_history)

    async def localized(taxa_id, lang, db=None):
        return f"{lang} name {taxa_id}"

    async def canonical(taxa_id, db=None):
        return {12716: "Canonical Robin", 145300: "Canonical Wren"}.get(taxa_id)

    monkeypatch.setattr(taxonomy_service, "get_localized_common_name", localized)
    monkeypatch.setattr(taxonomy_service, "get_canonical_english_name", canonical)
    monkeypatch.setattr(stats, "utc_naive_now", lambda: START + timedelta(hours=2))
    monkeypatch.setattr(
        events,
        "batch_check_clips",
        AsyncMock(
            side_effect=lambda ids: {
                event: {"has_clip": event == "gp-robin", "has_snapshot": True, "has_frigate_event": True}
                for event in ids
            }
        ),
    )
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "initial_setup_complete", True)
    monkeypatch.setattr(settings.auth, "username", "owner")
    monkeypatch.setattr(settings.public_access, "enabled", True)
    monkeypatch.setattr(settings.public_access, "show_camera_names", False)
    monkeypatch.setattr(settings.public_access, "show_ai_conversation", False)
    monkeypatch.setattr(settings.public_access, "location_precision", "approximate")
    monkeypatch.setattr(settings.public_access, "historical_days_mode", "custom")
    monkeypatch.setattr(settings.public_access, "show_historical_days", 3650)
    monkeypatch.setattr(settings.frigate, "camera_audio_mapping", {"garden": "garden-mic", "shed": "shed-mic"})
    monkeypatch.setattr(settings.frigate, "audio_correlation_window_seconds", 300)
    monkeypatch.setattr(settings.classification, "unknown_bird_labels", ["background"])
    return app


VIEWERS = {
    "owner": {"show_audio": True, "owner": True},
    "guest_with_audio": {"show_audio": True, "owner": False},
    "guest_without_audio": {"show_audio": False, "owner": False},
}

ROUTES = [
    "/api/events?start_date=2033-06-01&end_date=2033-06-30",
    "/api/events?start_date=2033-06-01&end_date=2033-06-30&include_hidden=true&sort=oldest",
    "/api/events?start_date=2033-06-01&end_date=2033-06-30&fields=list",
    "/api/events?start_date=2033-06-01&end_date=2033-06-30&fields=camera_name,audio_species,video_classification_error",
    "/api/visits?start_date=2033-06-01&end_date=2033-06-30",
    "/api/stats/daily-summary",
    "/api/species/Robin/stats",
    "/api/species/Unknown%20Bird/stats",
]


async def _responses(app, monkeypatch) -> dict:
    captured: dict = {}
    for viewer, options in VIEWERS.items():
        monkeypatch.setattr(settings.public_access, "show_audio", options["show_audio"])
        headers = {"Authorization": f"Bearer {create_access_token('owner')}"} if options["owner"] else {}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            for language in ("en", "de"):
                for route in ROUTES:
                    response = await client.get(route, headers={**headers, "Accept-Language": language})
                    captured[f"{viewer} {language} {route}"] = {
                        "status": response.status_code,
                        "body": response.json(),
                    }
                visits = captured[f"{viewer} en {ROUTES[4]}"]["body"].get("visits", [])
                for visit in visits:
                    route = f"/api/visits/{visit['visit_id']}/captures"
                    response = await client.get(route, headers={**headers, "Accept-Language": language})
                    captured[f"{viewer} {language} {route}"] = {
                        "status": response.status_code,
                        "body": response.json(),
                    }
    return captured


@pytest.mark.asyncio
async def test_bird_surfaces_return_the_captured_responses(presentation_history, monkeypatch):
    captured = await _responses(presentation_history, monkeypatch)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert sorted(captured) == sorted(golden)
    for request in golden:
        assert captured[request] == golden[request], request
