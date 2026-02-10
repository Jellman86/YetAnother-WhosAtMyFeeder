import os
import sqlite3
import subprocess
import sys


def test_taxonomy_translations_no_fk_and_writable(tmp_path):
    """
    Regression test for upgraded DBs failing with:
      sqlite3.OperationalError: foreign key mismatch - "taxonomy_translations" referencing "taxonomy_cache"

    This runs migrations on a fresh DB, enables FK enforcement, and asserts:
    - taxonomy_translations has no FK constraints
    - inserting into taxonomy_translations works with PRAGMA foreign_keys=ON
    """
    db_path = tmp_path / "schema_sanity.db"
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

