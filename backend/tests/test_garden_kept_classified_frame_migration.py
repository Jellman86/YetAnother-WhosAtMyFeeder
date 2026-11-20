"""Garden may keep YA-WAMF's own copy of a classified frame, and the change reverses cleanly."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

BEFORE = "b7d3e9f1a2c4"
REVISION = "f3a9c1d27b40"
CAPTURE = "a" * 32


def kept_row(db: sqlite3.Connection, source: str, state: str = "kept") -> None:
    checksum, size = ("c" * 64, 10) if state == "kept" else (None, None)
    db.execute(
        """INSERT INTO garden_kept_media(capture_id,photo_state,photo_source,photo_sha256,photo_bytes,
           clip_state,updated_at) VALUES (?,?,?,?,?,'missing','now')""",
        (CAPTURE, state, source, checksum, size),
    )


def test_classified_frame_source_migration_is_reversible_and_keeps_every_photo(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "garden.db"
    environment = {**os.environ, "DB_PATH": str(database)}

    def migrate(target: str, direction: str = "upgrade") -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target],
            cwd=backend,
            env=environment,
            check=True,
            capture_output=True,
        )

    migrate(BEFORE)
    with sqlite3.connect(database) as db:
        db.execute(
            """INSERT INTO garden_captures(id,event_key,camera,label,observed_at,status,has_snapshot)
               VALUES (?,?,'patio','bird','2026-11-20T09:15:56','confirmed',0)""",
            (CAPTURE, "b" * 64),
        )
        with pytest.raises(sqlite3.IntegrityError):
            kept_row(db, "classified_frame")
    migrate(REVISION)
    migrate(REVISION)
    with sqlite3.connect(database) as db:
        kept_row(db, "classified_frame")
        for source in ("elsewhere", None):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    "UPDATE garden_kept_media SET photo_source=? WHERE capture_id=?",
                    (source, CAPTURE),
                )
        before = db.execute("SELECT * FROM garden_captures").fetchall()
    migrate(BEFORE, "downgrade")
    with sqlite3.connect(database) as db:
        # Older versions know two sources; the photo stays kept and served under the Frigate one.
        assert db.execute("SELECT photo_state, photo_source, photo_sha256 FROM garden_kept_media").fetchall() == [
            ("kept", "frigate_snapshot", "c" * 64)
        ]
        assert db.execute("SELECT * FROM garden_captures").fetchall() == before
    migrate(REVISION)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT photo_state, photo_source FROM garden_kept_media").fetchall() == [
            ("kept", "frigate_snapshot")
        ]
        assert db.execute("SELECT * FROM garden_captures").fetchall() == before
