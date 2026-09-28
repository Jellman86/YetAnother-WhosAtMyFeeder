"""Counted birds live beneath their original detection without changing its identity."""

import os
from pathlib import Path
import sqlite3
import subprocess


def test_bird_observation_migration_is_reversible_and_preserves_detection(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / "bird-observations.db"
    env = {**os.environ, "DB_PATH": str(path)}

    def migrate(target: str, direction: str = "upgrade") -> None:
        subprocess.run(["alembic", direction, target], cwd=backend, env=env, check=True, capture_output=True)

    migrate("c1d2e3f4a5b6")
    with sqlite3.connect(path) as db:
        db.execute(
            """INSERT INTO detections
               (detection_time, detection_index, score, display_name, category_name, frigate_event, camera_name)
               VALUES ('2026-09-28 12:00:00', 0, 0.9, 'House Finch', 'House Finch', 'evt-1', 'feeder')"""
        )
    migrate("head")
    migrate("head")
    with sqlite3.connect(path) as db:
        columns = {row[1] for row in db.execute("PRAGMA table_info(bird_observations)")}
        assert {"frigate_event", "bird_index", "species", "crop_box_json"} <= columns
        db.execute(
            """INSERT INTO bird_observations
               (frigate_event, bird_index, candidate_id, clip_variant, frame_index,
                crop_box_json, species, classifier_score)
               VALUES ('evt-1', 0, 'bird-1', 'event', 1, '[1,2,3,4]', 'House Finch', 0.9)"""
        )
    migrate("c1d2e3f4a5b6", "downgrade")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT frigate_event FROM detections").fetchone() == ("evt-1",)
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='bird_observations'").fetchone()
    migrate("head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM bird_observations").fetchone() == (0,)
