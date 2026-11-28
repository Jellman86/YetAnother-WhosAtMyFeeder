"""The feeder refills table is added beside the history without touching it, and reverses cleanly (#946)."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BEFORE = "d4b8f2a6c1e3"
REVISION = "e5c1a9f3b7d2"


def test_feeder_refills_table_is_additive_and_reversible(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "refills.db"
    environment = {**os.environ, "DB_PATH": str(database)}

    def migrate(target: str, direction: str = "upgrade") -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target],
            cwd=backend,
            env=environment,
            check=True,
            capture_output=True,
        )

    def tables(db: sqlite3.Connection) -> set[str]:
        return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    migrate(BEFORE)
    with sqlite3.connect(database) as db:
        before_tables = tables(db)
        detections_sql = db.execute("SELECT sql FROM sqlite_master WHERE name='detections'").fetchone()

    migrate(REVISION)
    with sqlite3.connect(database) as db:
        assert tables(db) == before_tables | {"feeder_refills"}
        assert db.execute("SELECT sql FROM sqlite_master WHERE name='detections'").fetchone() == detections_sql
        indexes = {row[1]: row[2] for row in db.execute("PRAGMA index_list('feeder_refills')")}
        assert "idx_feeder_refills_refilled_at" in indexes
        assert any(unique for name, unique in indexes.items() if name != "idx_feeder_refills_refilled_at")
        db.execute(
            "INSERT INTO feeder_refills (refilled_at, camera_name, source, created_at)"
            " VALUES ('2026-11-28 09:00:00', 'birdcam', 'manual', '2026-11-28 09:00:01')"
        )

    migrate(BEFORE, "downgrade")
    with sqlite3.connect(database) as db:
        assert tables(db) == before_tables

    migrate(REVISION)
    migrate(REVISION)
    with sqlite3.connect(database) as db:
        assert tables(db) == before_tables | {"feeder_refills"}
        assert db.execute("SELECT COUNT(*) FROM feeder_refills").fetchone() == (0,)
