"""Audio removals preserve history through reversible schema upgrades."""

import os
from pathlib import Path
import sqlite3
import subprocess


def test_audio_visibility_migration_preserves_rows_and_is_reversible(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / "audio.db"
    env = {**os.environ, "DB_PATH": str(path)}

    def migrate(target, direction="upgrade"):
        subprocess.run(["alembic", direction, target], cwd=backend, env=env, check=True, capture_output=True)

    migrate("b8e1f2a3c4d5")
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO audio_detections (timestamp, species, confidence) VALUES ('2026-09-17', 'Robin', 0.9)")
    migrate("head")
    migrate("head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT species, is_hidden FROM audio_detections").fetchone() == ("Robin", 0)
        db.execute("UPDATE audio_detections SET is_hidden = 1")
    migrate("b8e1f2a3c4d5", "downgrade")
    migrate("head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT species, is_hidden FROM audio_detections").fetchone() == ("Robin", 0)
