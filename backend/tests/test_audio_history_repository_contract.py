"""Audio history reads and writes return exactly what they returned before audio left the detection repository.

The expected values in `fixtures/golden/audio_history_repository.json` were
captured from `DetectionRepository` before its audio methods moved, over the
seeded history below. Each method is called through the facade every caller
uses today and through the audio repository directly; both must reproduce the
capture exactly, including ordering, suppression counts and which rows a write
touched.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import aiosqlite
import pytest

from app.repositories.audio_history_repository import AudioHistoryRepository
from app.repositories.detection_repository import DetectionRepository

GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "audio_history_repository.json"
NOW = datetime(2033, 6, 10, 12, 0, 0)

AUDIO_ROWS = [
    # timestamp, species, confidence, sensor_id, raw_data, scientific_name, source_event_id, is_hidden
    (
        "2033-06-10 08:00:00",
        "Robin",
        0.91,
        "garden-mic",
        {"detectionId": 101, "nm": "Garden Mic"},
        "Erithacus rubecula",
        "garden-mic:101",
        0,
    ),
    (
        "2033-06-10 08:00:20",
        "Wren",
        0.72,
        "garden-mic",
        {"detection_id": "102", "Source": {"displayName": "Garden Mic", "id": "dev-1"}},
        "Troglodytes troglodytes",
        "garden-mic:102",
        0,
    ),
    (
        "2033-06-10 08:00:40",
        "Blackbird",
        0.65,
        "shed-mic",
        {"id": 103, "sourceName": "Shed"},
        "Turdus merula",
        "shed-mic:103",
        0,
    ),
    (
        "2033-06-10 08:01:30",
        "Robin",
        0.55,
        "garden-mic",
        {"detectionId": 104, "src": "dev-1"},
        "Erithacus rubecula",
        "garden-mic:104",
        1,
    ),
    (
        "2033-06-09 19:00:00",
        "Robin",
        0.81,
        "garden-mic",
        {"detectionId": 105},
        "Erithacus rubecula",
        "garden-mic:105",
        0,
    ),
    ("2033-06-08 06:30:00", "Song Thrush", 0.77, None, "not json", "Turdus philomelos", None, 0),
    (
        "2033-06-03 06:30:00",
        "Wren",
        0.68,
        "shed-mic",
        {"detectionId": 107, "sourceId": "shed"},
        "Troglodytes troglodytes",
        "shed-mic:107",
        0,
    ),
]

DETECTIONS = [
    # frigate_event, camera, detection_time, display_name, audio_species, audio_confirmed
    ("evt-robin", "garden", "2033-06-10 08:00:10", "Robin", "Robin", 1),
    ("evt-wren", "garden", "2033-06-10 08:00:30", "Robin", "Wren", 0),
    ("evt-shed", "shed", "2033-06-10 08:00:45", "Blackbird", "Blackbird", 0),
    ("evt-quiet", "garden", "2033-06-07 12:00:00", "Dunnock", None, 0),
]


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


async def _seed(db: aiosqlite.Connection) -> None:
    for timestamp, species, confidence, sensor, raw, scientific, source_event, hidden in AUDIO_ROWS:
        await db.execute(
            """INSERT INTO audio_detections
               (timestamp, species, confidence, sensor_id, raw_data, scientific_name, source_event_id, is_hidden)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp,
                species,
                confidence,
                sensor,
                raw if isinstance(raw, str) else json.dumps(raw),
                scientific,
                source_event,
                hidden,
            ),
        )
    for index, (event, camera, when, name, audio_species, confirmed) in enumerate(DETECTIONS):
        await db.execute(
            """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                   frigate_event, camera_name, audio_species, audio_confirmed)
               VALUES (?, ?, 0.9, ?, ?, ?, ?, ?, ?)""",
            (when, index, name, name, event, camera, audio_species, confirmed),
        )
    await db.commit()


def _detection(event: str, camera: str, when: str, audio_species: str | None, confirmed: int) -> SimpleNamespace:
    return SimpleNamespace(
        frigate_event=event,
        camera_name=camera,
        detection_time=datetime.fromisoformat(when),
        audio_species=audio_species,
        audio_confirmed=bool(confirmed),
    )


@pytest.fixture
def audio_settings(monkeypatch):
    from app.config import settings
    from app.utils import public_access

    monkeypatch.setattr(settings.frigate, "camera_audio_mapping", {"garden": "garden mic, dev-1", "shed": "*"})
    monkeypatch.setattr(settings.frigate, "audio_correlation_window_seconds", 60)
    monkeypatch.setattr(public_access, "public_events_window", lambda now=None: (datetime(2033, 6, 9), None))


async def _capture(repo, db: aiosqlite.Connection, monkeypatch) -> dict:
    from app.services import audio_identity

    detections = [_detection(*row[:3], row[4], row[5]) for row in DETECTIONS]
    mapping = {"garden": "garden mic, dev-1", "shed": "*"}
    window_start, window_end = datetime(2033, 6, 9), datetime(2033, 6, 11)
    captured = {
        "history": await repo.get_audio_history(limit=4),
        "history_page_two": await repo.get_audio_history(limit=4, offset=4),
        "history_filtered": await repo.get_audio_history(
            start_date=window_start, end_date=window_end, species="ro", source="garden", min_confidence=0.6
        ),
        "history_bounded": await repo.get_audio_history(maximum_end=datetime(2033, 6, 10, 8, 0, 30)),
        "summary": await repo.get_audio_history_summary(),
        "summary_filtered": await repo.get_audio_history_summary(start_date=window_start, source="shed"),
        "context_garden": await repo.get_audio_context(datetime(2033, 6, 10, 8, 0, 10), 60, mapping["garden"], 8),
        "context_unmapped": await repo.get_audio_context(datetime(2033, 6, 10, 8, 0, 10), 60, None, 8),
        "context_bounded": await repo.get_audio_context(
            datetime(2033, 6, 10, 8, 0, 10, tzinfo=timezone.utc),
            60,
            "*",
            2,
            minimum_start=datetime(2033, 6, 10, 8, 0, 5, tzinfo=timezone.utc),
            maximum_end=datetime(2033, 6, 10, 8, 0, 41, tzinfo=timezone.utc),
        ),
        "contexts": await repo.get_audio_contexts_for_detections(detections, mapping, 60, limit=2),
        "public_audio": await repo.get_public_audio_for_detections(detections),
        "recent_sources": await repo.get_recent_audio_source_observations(limit=3),
        "recent_sources_bounded": await repo.get_recent_audio_source_observations(
            start_date=datetime(2033, 6, 8), end_date=datetime(2033, 6, 10, 8, 0, 30)
        ),
        "history_start": await repo.get_audio_history_start(),
        "history_start_bounded": await repo.get_audio_history_start(
            minimum_start=datetime(2033, 6, 9), maximum_end=datetime(2033, 6, 11)
        ),
        "media_visible": {
            str(birdnet_id): await repo.public_birdnet_media_visible(birdnet_id, datetime(2033, 6, 9), None)
            for birdnet_id in (101, 102, 103, 104, 105, 107, 999)
        },
        "species_counts": sorted(
            await repo.get_audio_species_counts(
                datetime(2033, 6, 9), datetime(2033, 6, 11), datetime(2033, 6, 1), datetime(2033, 6, 9)
            ),
            key=lambda row: str(row["species"]),
        ),
        "correlation": [await repo.get_audio_detection_for_correlation(row_id) for row_id in (1, 4, 99)],
        "visible": [await repo.audio_detection_is_visible(row_id) for row_id in (1, 4, 99)],
        "pending_names": sorted(await repo.pending_audio_scientific_names()),
    }

    identities = {"Erithacus rubecula": 9001, "Turdus merula": 9002}
    monkeypatch.setattr(audio_identity, "resolve_audio_identity", lambda name, resolver=None: identities.get(name))
    captured["insert_new"] = await repo.insert_audio_detection_idempotent(
        datetime(2033, 6, 10, 9, 0, tzinfo=timezone.utc),
        "Robin",
        0.88,
        "garden-mic",
        {"detectionId": 108},
        scientific_name="Erithacus rubecula",
        source_event_id="garden-mic:108",
    )
    captured["insert_repeat"] = await repo.insert_audio_detection_idempotent(
        datetime(2033, 6, 10, 9, 0, tzinfo=timezone.utc),
        "Robin",
        0.88,
        "garden-mic",
        {"detectionId": 108},
        scientific_name="Erithacus rubecula",
        source_event_id="garden-mic:108",
    )
    captured["insert_plain"] = await repo.insert_audio_detection(
        datetime(2033, 6, 10, 9, 5), "Wren", 0.5, None, None, scientific_name="Troglodytes troglodytes"
    )
    captured["hide"] = [await repo.set_audio_hidden(2, True), await repo.set_audio_hidden(99, True)]
    captured["delete"] = [await repo.delete_audio_detection(3), await repo.delete_audio_detection(99)]
    captured["backfill"] = await repo.backfill_audio_species_ids(resolver=object())
    async with db.execute(
        "SELECT id, timestamp, species, sensor_id, raw_data, source_event_id, species_id, is_hidden"
        " FROM audio_detections ORDER BY id"
    ) as cursor:
        captured["rows_after_writes"] = [list(row) for row in await cursor.fetchall()]
    return _jsonable(captured)


@pytest.mark.asyncio
@pytest.mark.parametrize("repository", [DetectionRepository, AudioHistoryRepository], ids=["facade", "audio"])
async def test_audio_history_methods_reproduce_the_captured_results(
    migrated_history_db, audio_settings, monkeypatch, repository
):
    async with aiosqlite.connect(migrated_history_db) as db:
        await _seed(db)
        captured = await _capture(repository(db), db, monkeypatch)

    assert captured == json.loads(GOLDEN.read_text(encoding="utf-8"))
