"""The kept-media record upgrades, downgrades and upgrades again without touching Garden history."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

BEFORE = "7fa03c365538"
REVISION = "db260f76fda3"


def test_kept_media_migration_is_reversible_constrained_and_preserves_history(tmp_path):
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
               VALUES (?,?,'patio','animal','2026-10-26T00:00:00','confirmed',1)""",
            ("a" * 32, "b" * 64),
        )
        before = db.execute("SELECT * FROM garden_captures").fetchall()
    migrate(REVISION)
    migrate(REVISION)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM garden_captures").fetchall() == before
        invalid = [
            # A kept photo needs its checksum, size and source.
            ("kept", "frigate_snapshot", None, 10, None, None, None),
            ("kept", "frigate_snapshot", "c" * 64, 0, None, None, None),
            ("kept", "elsewhere", "c" * 64, 10, None, None, None),
            ("kept", None, "c" * 64, 10, None, None, None),
            # Anything not kept carries no checksum.
            ("missing", None, "c" * 64, 10, None, None, None),
            ("lost", None, None, None, None, None, None),
            ("kept", "motion_photo", "c" * 64, 10, "kept", None, 10),
            ("kept", "motion_photo", "c" * 64, 10, "missing", "d" * 64, None),
        ]
        for values in invalid:
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    """INSERT INTO garden_kept_media(capture_id,photo_state,photo_source,photo_sha256,photo_bytes,
                       clip_state,clip_sha256,clip_bytes,updated_at) VALUES (?,?,?,?,?,?,?,?,'now')""",
                    ("a" * 32, *values),
                )
        db.execute(
            """INSERT INTO garden_kept_media(capture_id,photo_state,photo_source,photo_sha256,photo_bytes,
               clip_state,clip_sha256,clip_bytes,updated_at) VALUES (?,?,?,?,?,?,?,?,'now')""",
            ("a" * 32, "kept", "frigate_snapshot", "c" * 64, 10, "kept", "d" * 64, 20),
        )
    migrate(BEFORE, "downgrade")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM garden_captures").fetchall() == before
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='garden_kept_media'").fetchone()
    migrate(REVISION)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM garden_captures").fetchall() == before
        assert db.execute("SELECT COUNT(*) FROM garden_kept_media").fetchone() == (0,)
