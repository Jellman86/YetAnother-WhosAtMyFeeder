"""Count qualification metadata must never disturb birds or owner corrections."""

import importlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa


REVISION = "c1d734b9e201"
PARENT = "b8230ca9d42c"


def test_count_region_migration_preserves_scan_and_owner_history_through_repeated_transitions(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / "counts.db"

    def migrate(target, direction="upgrade"):
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target],
            cwd=backend,
            env={**os.environ, "DB_PATH": str(path)},
            capture_output=True,
            check=True,
        )

    migrate(PARENT)
    with sqlite3.connect(path) as db:
        db.execute("""INSERT INTO detections(detection_time,detection_index,score,display_name,category_name,frigate_event,camera_name)
                   VALUES('2026-10-08',0,0.9,'Robin','Robin','event','feeder')""")
        db.execute(
            """INSERT INTO bird_scan_jobs(frigate_event,generation,candidate_id,image_ref,content_sha256,media_version,clip_variant,frame_index,status,result_count)
                   VALUES('event','generation','scene','image',?,'v1','event',1,'completed',1)""",
            ("a" * 64,),
        )
        db.execute("""INSERT INTO bird_observations(frigate_event,bird_index,candidate_id,clip_variant,frame_index,crop_box_json,detector_confidence,species,classifier_score,manual_species)
                   VALUES('event',0,'bird','event',1,'[1,1,10,10]',0.8,'Owner correction',0.9,1)""")
    migrate(REVISION)
    migration = importlib.import_module("migrations.versions.c1d734b9e201_bird_scan_count_regions")
    engine = sa.create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
                migration.upgrade()
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT count_status,count_regions_json FROM bird_scan_jobs").fetchone() == (
                "legacy",
                "[]",
            )
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("UPDATE bird_scan_jobs SET count_status='guessed'")
            with pytest.raises(sqlite3.IntegrityError):
                db.execute("UPDATE bird_scan_jobs SET count_regions_json='not-json'")
        migrate(PARENT, "downgrade")
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT result_count FROM bird_scan_jobs").fetchone() == (1,)
            assert db.execute("SELECT species,manual_species FROM bird_observations").fetchall() == [
                ("Owner correction", 1)
            ]
            assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        migrate(REVISION)
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT result_count,count_status FROM bird_scan_jobs").fetchone() == (1, "legacy")
            assert db.execute("SELECT species,manual_species FROM bird_observations").fetchall() == [
                ("Owner correction", 1)
            ]
    finally:
        engine.dispose()
