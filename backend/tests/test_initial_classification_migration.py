import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_initial_provenance_migration_never_invents_history_and_cleans_reused_ids(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / "initial-classification.db"
    env = {**os.environ, "DB_PATH": str(path)}

    def migrate(target, direction="upgrade"):
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target], cwd=backend, env=env, check=True, capture_output=True
        )

    def insert(db, event):
        db.execute(
            "INSERT INTO detections (id,frigate_event,camera_name,detection_time,detection_index,score,display_name,category_name) VALUES (7,?,'cam','2026-10-02',0,0.9,'Downy','Dryobates pubescens')",
            (event,),
        )

    migrate("f12b7340ac91")
    with sqlite3.connect(path) as db:
        insert(db, "legacy")
    migrate("head")
    migrate("head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM detection_initial_classifications").fetchone() == (0,)
        db.execute("DELETE FROM detections")
        insert(db, "fresh")
        db.execute("UPDATE detections SET category_name = 'Baeolophus bicolor'")
        assert db.execute("SELECT category_name FROM detection_initial_classifications").fetchone() == (
            "Dryobates pubescens",
        )
        # Plain SQLite maintenance connections may have foreign keys disabled.
        db.execute("DELETE FROM detections")
        assert db.execute("SELECT COUNT(*) FROM detection_initial_classifications").fetchone() == (0,)
        insert(db, "reused-id")
    migrate("f12b7340ac91", "downgrade")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT frigate_event FROM detections").fetchone() == ("reused-id",)
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='capture_initial_classification'").fetchone()
    migrate("head")
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert db.execute("SELECT COUNT(*) FROM detection_initial_classifications").fetchone() == (0,)


def test_classifier_input_migration_preserves_identity_and_trigger_through_rollback(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / "classifier-input.db"
    env = {**os.environ, "DB_PATH": str(path)}

    def migrate(target, direction="upgrade"):
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target], cwd=backend, env=env, check=True, capture_output=True
        )

    def insert(db, event, evidence=None):
        db.execute(
            """INSERT INTO detections (frigate_event,camera_name,detection_time,detection_index,
                   score,display_name,category_name,classification_input_json)
                   VALUES (?,'cam','2026-10-11',0,.99,'Robin','Robin',?)""",
            (event, evidence),
        )

    migrate("b91a6e2d4c80")
    migrate("head")
    migrate("head")
    with sqlite3.connect(path) as db:
        insert(db, "fresh", '{"source":"full_frame","is_cropped":false}')
        db.execute(
            "UPDATE detections SET category_name='Finch', manual_tagged=1, classification_input_json=?",
            ('{"source":"owner_species_choice"}',),
        )
        assert db.execute("SELECT classification_input_json FROM detection_initial_classifications").fetchone() == (
            '{"source":"full_frame","is_cropped":false}',
        )
    migrate("b91a6e2d4c80", "downgrade")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT category_name,manual_tagged FROM detections").fetchone() == ("Finch", 1)
        assert db.execute("SELECT category_name FROM detection_initial_classifications").fetchone() == ("Robin",)
    migrate("head")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT classification_input_json FROM detections").fetchone() == (None,)
        assert db.execute("SELECT classification_input_json FROM detection_initial_classifications").fetchone() == (
            None,
        )
        insert(db, "after-rollback", '{"source":"provided_crop","is_cropped":true}')
        assert db.execute(
            "SELECT classification_input_json FROM detection_initial_classifications ORDER BY detection_id DESC LIMIT 1"
        ).fetchone() == ('{"source":"provided_crop","is_cropped":true}',)
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
