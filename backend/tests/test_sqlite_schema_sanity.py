import os
import sqlite3
import subprocess
import sys


def _upgrade_db(db_path):
    env = os.environ.copy()
    env["DB_PATH"] = str(db_path)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=os.path.join(os.path.dirname(__file__), ".."),
        env=env,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_taxonomy_translations_no_fk_and_writable(tmp_path):
    """
    Regression test for upgraded DBs failing with:
      sqlite3.OperationalError: foreign key mismatch - "taxonomy_translations" referencing "taxonomy_cache"

    This runs migrations on a fresh DB, enables FK enforcement, and asserts:
    - taxonomy_translations has no FK constraints
    - inserting into taxonomy_translations works with PRAGMA foreign_keys=ON
    """
    db_path = tmp_path / "schema_sanity.db"
    _upgrade_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        fk_list = conn.execute("PRAGMA foreign_key_list(taxonomy_translations);").fetchall()
        assert fk_list == []

        # Smoke-write: would throw OperationalError with the old FK mismatch.
        conn.execute(
            "INSERT OR REPLACE INTO taxonomy_translations (taxa_id, language_code, common_name) VALUES (?, ?, ?)",
            (123456, "ru", "test-name"),
        )
        conn.commit()
    finally:
        conn.close()


def test_classification_feedback_schema_exists(tmp_path):
    db_path = tmp_path / "schema_feedback.db"
    _upgrade_db(db_path)

    conn = sqlite3.connect(str(db_path))
    try:
        cols = conn.execute("PRAGMA table_info(classification_feedback);").fetchall()
        col_names = [c[1] for c in cols]
        assert col_names == [
            "id",
            "created_at",
            "frigate_event",
            "camera_name",
            "model_id",
            "predicted_label",
            "corrected_label",
            "predicted_score",
            "source",
        ]

        indexes = conn.execute("PRAGMA index_list(classification_feedback);").fetchall()
        index_names = {row[1] for row in indexes}
        assert "idx_classification_feedback_camera_model_time" in index_names
        assert "idx_classification_feedback_camera_model_predicted_time" in index_names
    finally:
        conn.close()
