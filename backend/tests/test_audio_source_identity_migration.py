"""Stored calls learn BirdNET-Go's source id from their own payload, and the change reverses cleanly (#1111)."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

BEFORE = "f3a9c1d27b40"
REVISION = "d4b8f2a6c1e3"


def test_source_identity_backfills_from_the_payload_and_is_reversible(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "audio.db"
    environment = {**os.environ, "DB_PATH": str(database)}

    def migrate(target: str, direction: str = "upgrade") -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target],
            cwd=backend,
            env=environment,
            check=True,
            capture_output=True,
        )

    payloads = [
        ("birdcam", {"SourceNode": "BirdNET-Go Quark", "sourceId": "rtsp_3af0d74c", "sourceName": "birdcam"}),
        ("Garden", {"Source": {"id": " rtsp_old ", "displayName": "Garden"}}),
        ("shed", {"src": "audio_card_22a9b331", "nm": "shed"}),
        ("legacy", {"sourceName": "legacy"}),
        ("string source", {"Source": "rtsp://camera/stream", "sourceId": ""}),
        # An older YA-WAMF stored BirdNET-Go's id as the sensor; the payload still has the name.
        ("rtsp_0d6c2ad3", {"sourceId": "rtsp_0d6c2ad3", "sourceName": "nestcam"}),
        # No name was sent: BirdNET-Go's id was stored as the sensor, which is no name.
        ("rtsp_noname", {"sourceId": "rtsp_noname"}),
        (None, None),
    ]
    migrate(BEFORE)
    with sqlite3.connect(database) as db:
        # More rows than one backfill batch, so the batching is exercised.
        for index in range(2_400):
            sensor, payload = payloads[index % len(payloads)]
            db.execute(
                "INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data) VALUES (?,?,?,?,?)",
                (
                    f"2026-11-01 08:00:{index % 60:02d}",
                    "Robin",
                    0.9,
                    sensor,
                    json.dumps(payload) if payload is not None else "not json",
                ),
            )
        before = db.execute("SELECT id, timestamp, sensor_id, raw_data FROM audio_detections ORDER BY id").fetchall()

    migrate(REVISION)
    migrate("head")
    with sqlite3.connect(database) as db:
        identities = db.execute(
            "SELECT sensor_id, source_node, source_id, source_name, COUNT(*) FROM audio_detections"
            " GROUP BY 1, 2, 3, 4 ORDER BY 1"
        ).fetchall()
        indexes = {row[1] for row in db.execute("PRAGMA index_list('audio_detections')")}
        unchanged = db.execute("SELECT id, timestamp, sensor_id, raw_data FROM audio_detections ORDER BY id").fetchall()
    assert identities == [
        (None, None, None, None, 300),
        ("Garden", None, "rtsp_old", "Garden", 300),
        ("birdcam", "BirdNET-Go Quark", "rtsp_3af0d74c", "birdcam", 300),
        ("legacy", None, None, "legacy", 300),
        ("rtsp_0d6c2ad3", None, "rtsp_0d6c2ad3", "nestcam", 300),
        ("rtsp_noname", None, "rtsp_noname", None, 300),
        ("shed", None, "audio_card_22a9b331", "shed", 300),
        ("string source", None, None, "string source", 300),
    ]
    assert "idx_audio_detections_source_identity" in indexes
    assert "idx_audio_detections_source_pending" in indexes
    assert unchanged == before
    with sqlite3.connect(database) as db:
        # Every stored call's source has been read, so none waits to be read at startup.
        assert db.execute("SELECT COUNT(*) FROM audio_detections WHERE source_resolved = 0").fetchone() == (0,)

    migrate(BEFORE, "downgrade")
    with sqlite3.connect(database) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info('audio_detections')")}
        indexes = {row[1] for row in db.execute("PRAGMA index_list('audio_detections')")}
        assert db.execute("SELECT id, timestamp, sensor_id, raw_data FROM audio_detections ORDER BY id").fetchall() == (
            before
        )
    assert not {"source_id", "source_node", "source_name", "source_resolved"} & columns
    assert not {"idx_audio_detections_source_identity", "idx_audio_detections_source_pending"} & indexes

    migrate("head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT COUNT(*) FROM audio_detections WHERE source_id = 'rtsp_3af0d74c'").fetchone() == (
            300,
        )


def test_hostile_stored_payloads_never_block_the_upgrade_and_store_only_clean_values(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "hostile.db"
    environment = {**os.environ, "DB_PATH": str(database)}

    def migrate(target: str, direction: str = "upgrade") -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", direction, target],
            cwd=backend,
            env=environment,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]

    long_text = "x" * 5_000
    rows = [
        # The previous ingest stored ASCII-escaped JSON, so a lone surrogate survived in the payload.
        ("surrogate", '{"SourceNode": "\\ud800", "sourceId": "rtsp_ok", "sourceName": "Feeder\\udfff"}'),
        ("deep", "[" * 200_000 + "]" * 200_000),
        ("deep-object", '{"a":' * 50_000 + "1" + "}" * 50_000),
        ("not json", "not json"),
        ("wrong types", json.dumps({"SourceNode": ["House"], "sourceId": 42, "sourceName": {"x": 1}})),
        ("huge", json.dumps({"SourceNode": long_text, "sourceId": "rtsp_" + long_text, "sourceName": long_text})),
        (
            "controls",
            json.dumps({"SourceNode": "Ho\x00use", "sourceId": "rtsp_\x07a", "sourceName": "Gar\x00den\nMic"}),
        ),
        ("nested non-object", json.dumps({"Source": ["rtsp_x"], "src": None})),
        ("separators", json.dumps({"SourceNode": "pi@shed, west", "sourceId": "rtsp_a, *", "sourceName": "x"})),
        # A refused id is never stored as a name, and the install is kept.
        ("rtsp shed", json.dumps({"SourceNode": "House", "sourceId": "rtsp shed"})),
    ]
    migrate(BEFORE)
    with sqlite3.connect(database) as db:
        for sensor, raw in rows:
            db.execute(
                "INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data) VALUES (?,?,?,?,?)",
                ("2026-11-01 08:00:00", "Robin", 0.9, sensor, raw),
            )
        before = db.execute("SELECT id, sensor_id, raw_data FROM audio_detections ORDER BY id").fetchall()

    migrate("head")
    with sqlite3.connect(database) as db:
        stored = {
            row[0]: row[1:]
            for row in db.execute("SELECT sensor_id, source_node, source_id, source_name FROM audio_detections")
        }
        assert db.execute("SELECT id, sensor_id, raw_data FROM audio_detections ORDER BY id").fetchall() == before
    assert stored == {
        "surrogate": (None, "rtsp_ok", "Feeder"),
        "deep": (None, None, "deep"),
        "deep-object": (None, None, "deep-object"),
        "not json": (None, None, "not json"),
        "wrong types": (None, None, None),
        "huge": (None, None, None),
        # Each of these sent an id that is refused, so it keeps no name to join a source by.
        "controls": (None, None, None),
        "nested non-object": (None, None, "nested non-object"),
        "separators": ("pi@shed, west", None, None),
        "rtsp shed": ("House", None, None),
    }
    migrate(BEFORE, "downgrade")
    migrate("head")
