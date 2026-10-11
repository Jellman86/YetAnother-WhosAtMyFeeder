"""The scan queue migration is repeatable and never removes detection history."""

import importlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


REVISION = "b91a6e2d4c80"
PARENT = "a6f491c8de20"


def test_bird_scan_migration_upgrade_downgrade_reupgrade(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / "scans.db"
    env = {**os.environ, "DB_PATH": str(path)}

    def migrate(target: str, direction: str = "upgrade") -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target], cwd=backend, env=env, check=True, capture_output=True
        )

    migrate(PARENT)
    with sqlite3.connect(path) as db:
        db.execute("""INSERT INTO detections(detection_time,detection_index,score,display_name,
            category_name,frigate_event,camera_name) VALUES ('2026-10-08',0,0.9,'Robin','Robin','event','feeder')""")
    migrate(REVISION)
    migration = importlib.import_module("migrations.versions.b91a6e2d4c80_add_bird_scan_jobs")
    engine = sa.create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
                migration.upgrade()
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute(
                """INSERT INTO bird_scan_jobs(frigate_event,generation,candidate_id,image_ref,content_sha256,
                media_version,clip_variant,frame_index,status) VALUES('event','generation-test','candidate','image',?,'v1','event',1,'queued')""",
                ("a" * 64,),
            )
            assert db.execute("SELECT revision FROM bird_scan_jobs").fetchone() == (1,)
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT frigate_event,revision FROM bird_scan_jobs").fetchall() == [("event", 1)]
        migrate(PARENT, "downgrade")
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT frigate_event FROM detections").fetchall() == [("event",)]
            assert db.execute("SELECT name FROM sqlite_master WHERE name='bird_scan_jobs'").fetchall() == []
        migrate(REVISION)
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT COUNT(*) FROM bird_scan_jobs").fetchone() == (0,)
            assert db.execute("SELECT frigate_event FROM detections").fetchall() == [("event",)]
            assert "ix_bird_scan_jobs_status_created" in {
                row[1] for row in db.execute("PRAGMA index_list(bird_scan_jobs)")
            }
    finally:
        engine.dispose()
