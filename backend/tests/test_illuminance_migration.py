"""The light-level column arrives and leaves without touching detection history (#945)."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

REVISION = "d4a7c1e92b36"
PARENT = "c1d734b9e201"


def _schema(db: sqlite3.Connection) -> list[tuple]:
    return db.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()


def test_illuminance_migration_upgrade_downgrade_reupgrade(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / "lux.db"
    env = {**os.environ, "DB_PATH": str(path)}

    def migrate(target: str, direction: str = "upgrade") -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target], cwd=backend, env=env, check=True, capture_output=True
        )

    migrate(PARENT)
    with sqlite3.connect(path) as db:
        db.execute("""INSERT INTO detections(detection_time,detection_index,score,display_name,
            category_name,frigate_event,camera_name,weather_cloud_cover)
            VALUES ('2026-10-08',0,0.9,'Robin','Robin','before','feeder',40)""")
        before = _schema(db)

    migrate(REVISION)
    with sqlite3.connect(path) as db:
        upgraded = _schema(db)
        # History that predates the sensor has no light level, not a guessed one.
        assert db.execute("SELECT frigate_event, illuminance_lux, weather_cloud_cover FROM detections").fetchall() == [
            ("before", None, 40.0)
        ]
        db.execute("UPDATE detections SET illuminance_lux = 1240.5 WHERE frigate_event = 'before'")
        for impossible in (-1, 200001, "bright"):
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("UPDATE detections SET illuminance_lux = ? WHERE frigate_event = 'before'", (impossible,))

    # Re-running the head is a no-op.
    migrate(REVISION)
    with sqlite3.connect(path) as db:
        assert _schema(db) == upgraded
        assert db.execute("SELECT illuminance_lux FROM detections").fetchall() == [(1240.5,)]

    migrate(PARENT, "downgrade")
    with sqlite3.connect(path) as db:
        assert _schema(db) == before
        assert db.execute("SELECT frigate_event, weather_cloud_cover FROM detections").fetchall() == [("before", 40.0)]
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    migrate(REVISION)
    with sqlite3.connect(path) as db:
        assert _schema(db) == upgraded
        assert db.execute("SELECT frigate_event, illuminance_lux FROM detections").fetchall() == [("before", None)]
        db.execute("PRAGMA foreign_keys=ON")
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
