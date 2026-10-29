"""Owner corrections upgrade independently and leave original history intact."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


def test_owner_correction_migration_roundtrip_and_constraints(tmp_path):
    path = tmp_path / "history.db"
    backend = Path(__file__).parents[1]

    def migrate(target, direction="upgrade"):
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target],
            cwd=backend,
            env={**os.environ, "DB_PATH": str(path)},
            capture_output=True,
            check=True,
        )

    migrate("e026a10c26b1")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO garden_captures(id,event_key,camera,label,observed_at,status,has_snapshot) VALUES ('capture','event','patio','dog','2026-10-29','confirmed',0)"
        )
        before = db.execute("SELECT * FROM garden_captures").fetchall()
    migrate("f17d29a0c631")
    migrate("f17d29a0c631")
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        for species, name in ((0, "Fox"), (1, "")):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO garden_owner_identifications VALUES ('capture',?,?,'Vulpes vulpes','now')",
                    (species, name),
                )
        db.execute("INSERT INTO garden_owner_identifications VALUES ('capture',1,'Fox','Vulpes vulpes','now')")
        assert db.execute("SELECT * FROM garden_captures").fetchall() == before
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO garden_owner_identifications VALUES ('missing',1,'Fox','Vulpes vulpes','now')")
    migrate("e026a10c26b1", "downgrade")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM garden_captures").fetchall() == before
    migrate("f17d29a0c631")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM garden_owner_identifications").fetchone() == (0,)
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("INSERT INTO garden_owner_identifications VALUES ('capture',1,'Fox','Vulpes vulpes','now')")
        db.execute("DELETE FROM garden_captures")
        assert db.execute("SELECT COUNT(*) FROM garden_owner_identifications").fetchone() == (0,)
