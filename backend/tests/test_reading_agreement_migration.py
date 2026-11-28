"""The reading-agreement column arrives and leaves without touching detection history (#804)."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

REVISION = "e8c3a51f9d24"
PARENT = "d4b8f2a6c1e3"


def _schema(db: sqlite3.Connection) -> list[tuple]:
    return db.execute("SELECT type, name, sql FROM sqlite_master ORDER BY type, name").fetchall()


def test_reading_agreement_migration_upgrade_downgrade_reupgrade(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / "agreement.db"
    env = {**os.environ, "DB_PATH": str(path)}

    def migrate(target: str, direction: str = "upgrade") -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target], cwd=backend, env=env, check=True, capture_output=True
        )

    migrate(PARENT)
    with sqlite3.connect(path) as db:
        db.execute("""INSERT INTO detections(detection_time,detection_index,score,display_name,
            category_name,frigate_event,camera_name,video_classification_status,video_classification_label)
            VALUES ('2026-11-20',0,0.98,'Carrion Crow','Corvus corone','before','feeder','completed','Pica pica')""")
        before = _schema(db)

    migrate(REVISION)
    with sqlite3.connect(path) as db:
        upgraded = _schema(db)
        # A finished video reading from before this release was never compared, so it says nothing.
        assert db.execute(
            "SELECT frigate_event, reading_agreement, video_classification_label FROM detections"
        ).fetchall() == [("before", None, "Pica pica")]
        for outcome in ("agree", "disagree", "cannot_compare"):
            db.execute("UPDATE detections SET reading_agreement = ? WHERE frigate_event = 'before'", (outcome,))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE detections SET reading_agreement = 'maybe' WHERE frigate_event = 'before'")

    # Re-running the head is a no-op.
    migrate(REVISION)
    with sqlite3.connect(path) as db:
        assert _schema(db) == upgraded
        assert db.execute("SELECT reading_agreement FROM detections").fetchall() == [("cannot_compare",)]

    migrate(PARENT, "downgrade")
    with sqlite3.connect(path) as db:
        assert _schema(db) == before
        assert db.execute("SELECT frigate_event, video_classification_label FROM detections").fetchall() == [
            ("before", "Pica pica")
        ]
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)

    migrate(REVISION)
    with sqlite3.connect(path) as db:
        assert _schema(db) == upgraded
        assert db.execute("SELECT frigate_event, reading_agreement FROM detections").fetchall() == [("before", None)]
        db.execute("PRAGMA foreign_keys=ON")
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
