"""The media migration keeps history and prevents late orphaned references."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


def test_media_job_migration_round_trip_keeps_visits_and_guards_parents(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / "media-jobs.db"
    env = {**os.environ, "DB_PATH": str(path)}

    def migrate(target: str, direction: str = "upgrade") -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target], cwd=backend, env=env, check=True, capture_output=True
        )

    migrate("d7a9b1c2e3f4")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO detections (frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES ('retained','cam','2026-01-01',0,0.9,'Robin','bird')"
        )
        columns = {row[1]: row for row in db.execute("PRAGMA table_info(snapshot_candidates)")}
        assert "frigate_event" in columns
        # An old orphaned derived reference must be pruned without removing a visit.
        db.execute(
            "INSERT INTO snapshot_candidates (frigate_event,candidate_id,source_mode,clip_variant,frame_index,ranking_score) VALUES ('orphan','old','full_frame','event',1,0.9)"
        )
    migrate("head")
    migrate("head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM detections").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM snapshot_candidates").fetchone()[0] == 0
        with pytest.raises(sqlite3.IntegrityError, match="media visit does not exist"):
            db.execute(
                "INSERT INTO snapshot_candidates (frigate_event,candidate_id,source_mode,clip_variant,frame_index,ranking_score) VALUES ('orphan','late','full_frame','event',1,0.9)"
            )
        db.execute(
            "INSERT INTO snapshot_candidates (frigate_event,candidate_id,source_mode,clip_variant,frame_index,ranking_score) VALUES ('retained','valid','full_frame','event',1,0.9)"
        )
        db.execute("DELETE FROM detections WHERE frigate_event='retained'")
        assert db.execute("SELECT COUNT(*) FROM snapshot_candidates").fetchone()[0] == 0
        db.rollback()
    migrate("d7a9b1c2e3f4", "downgrade")
    migrate("head")
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("SELECT frigate_event FROM detections").fetchone() == ("retained",)
