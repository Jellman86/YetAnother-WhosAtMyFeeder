"""A crop-store upgrade/downgrade preserves animal history and enforces limits."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


def test_saved_crop_migration_is_reversible_bounded_and_preserves_history(tmp_path):
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

    migrate("c83d92a1f740")
    with sqlite3.connect(database) as db:
        db.execute(
            """INSERT INTO garden_captures(id,event_key,camera,label,observed_at,status,has_snapshot)
               VALUES (? ,?,'patio','animal','2026-10-26T00:00:00','confirmed',0)""",
            ("a" * 32, "b" * 64),
        )
        before = db.execute("SELECT * FROM garden_captures").fetchall()
    migrate("e026a10c26b1")
    migrate("e026a10c26b1")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM garden_captures").fetchall() == before
        for invalid in (b"", b"x" * 131073):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO garden_saved_crops VALUES (?,?,?,'available',NULL,'now')",
                    ("a" * 32, invalid, "{}"),
                )
        db.execute(
            "INSERT INTO garden_saved_crops VALUES (?,?,?,'available',NULL,'now')",
            ("a" * 32, b"crop", "{}"),
        )
    migrate("c83d92a1f740", "downgrade")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM garden_captures").fetchall() == before
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='garden_saved_crops'").fetchone()
    migrate("e026a10c26b1")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM garden_captures").fetchall() == before
        assert db.execute("SELECT COUNT(*) FROM garden_saved_crops").fetchone() == (0,)
