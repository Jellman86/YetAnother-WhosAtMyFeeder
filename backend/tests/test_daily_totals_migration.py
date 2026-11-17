"""Durable daily totals arrive and leave without touching detection history (#949)."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

REVISION = "b7d3e9f1a2c4"
PARENT = "e6b2f4a8c9d1"


def _schema(db: sqlite3.Connection) -> list[tuple]:
    return db.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()


def test_daily_totals_migration_round_trips_without_touching_history(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / "totals.db"
    env = {**os.environ, "DB_PATH": str(path)}

    def migrate(target: str, direction: str = "upgrade") -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target], cwd=backend, env=env, check=True, capture_output=True
        )

    migrate(PARENT)
    with sqlite3.connect(path) as db:
        db.execute("""INSERT INTO detections(detection_time,detection_index,score,display_name,
            category_name,frigate_event,camera_name) VALUES ('2026-01-02 08:00:00',0,0.9,'Robin','Robin','kept','feeder')""")
        before = _schema(db)

    migrate(REVISION)
    with sqlite3.connect(path) as db:
        upgraded = _schema(db)
        # Every stored row is still there to read; no day is sealed until cleanup would remove rows.
        assert db.execute("SELECT COUNT(*) FROM daily_totals_days").fetchone() == (0,)
        assert db.execute("SELECT COUNT(*) FROM species_daily_totals").fetchone() == (0,)
        db.execute("PRAGMA foreign_keys=ON")
        # The schema refuses totals that could not have been counted.
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO species_daily_totals(day,species_key,display_name,capture_count,visit_count)
                VALUES ('2026-01-02','label:robin','Robin',1,1)"""
            )
        db.execute("INSERT INTO daily_totals_days(day,sealed_at,complete) VALUES ('2026-01-02','2026-02-01',1)")
        for captures, visits in ((0, 0), (1, 2), (2, -1)):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    """INSERT INTO species_daily_totals(day,species_key,display_name,capture_count,visit_count)
                    VALUES ('2026-01-02','label:robin','Robin',?,?)""",
                    (captures, visits),
                )
        db.execute(
            """INSERT INTO species_daily_totals(day,species_key,display_name,capture_count,visit_count)
            VALUES ('2026-01-02','label:robin','Robin',3,2)"""
        )

    # Re-running the head is a no-op and keeps what it holds.
    migrate(REVISION)
    with sqlite3.connect(path) as db:
        assert _schema(db) == upgraded
        assert db.execute("SELECT capture_count, visit_count FROM species_daily_totals").fetchall() == [(3, 2)]

    migrate(PARENT, "downgrade")
    with sqlite3.connect(path) as db:
        assert _schema(db) == before
        assert db.execute("SELECT frigate_event FROM detections").fetchall() == [("kept",)]
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    migrate(REVISION)
    with sqlite3.connect(path) as db:
        assert _schema(db) == upgraded
        assert db.execute("SELECT COUNT(*) FROM daily_totals_days").fetchone() == (0,)
