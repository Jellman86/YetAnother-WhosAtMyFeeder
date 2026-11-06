"""Automatic review migrates without revisiting or losing owner history."""

import importlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


def test_automatic_review_migration_preserves_old_reviews_and_rolls_back_only_automatic_dismissals(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    path = tmp_path / "garden.db"
    env = {**os.environ, "DB_PATH": str(path)}

    def migrate(target, direction="upgrade"):
        subprocess.run(
            [sys.executable, "-m", "alembic", direction, target], cwd=backend, env=env, check=True, capture_output=True
        )

    migrate("a21e40b5c610")
    with sqlite3.connect(path) as db:
        for capture_id, status in [
            ("old-pending", "pending"),
            ("old-confirmed", "confirmed"),
            ("old-dismissed", "dismissed"),
        ]:
            db.execute(
                "INSERT INTO garden_captures(id,event_key,camera,label,observed_at,status,has_snapshot) VALUES (?,?,'patio','animal','2026-10-20',?,1)",
                (capture_id, capture_id, status),
            )
    migrate("b72d91a4e630")
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT automation_overridden FROM garden_captures").fetchall() == [(1,), (1,), (1,)]
        for capture_id, override in [("automatic", 0), ("owner-overrode", 1)]:
            db.execute(
                "INSERT INTO garden_captures(id,event_key,camera,label,observed_at,status,has_snapshot,automation_overridden) VALUES (?,?,'patio','animal','2026-10-20','dismissed',1,?)",
                (capture_id, capture_id, override),
            )
            db.execute("INSERT INTO garden_automatic_checks VALUES (?,?)", (capture_id, '{"outcome":"non_animal"}'))
        before = db.execute("SELECT * FROM garden_captures ORDER BY id").fetchall()
    migration = importlib.import_module("migrations.versions.b72d91a4e630_garden_automatic_checks")
    engine = sa.create_engine(f"sqlite:///{path}")
    try:
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
            migration.upgrade()
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT * FROM garden_captures ORDER BY id").fetchall() == before
        migrate("a21e40b5c610", "downgrade")
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        with sqlite3.connect(path) as db:
            assert dict(db.execute("SELECT id,status FROM garden_captures")) == {
                "old-pending": "pending",
                "old-confirmed": "confirmed",
                "old-dismissed": "dismissed",
                "automatic": "pending",
                "owner-overrode": "dismissed",
            }
            assert db.execute("PRAGMA quick_check").fetchone() == ("ok",)
        migrate("b72d91a4e630")
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT COUNT(*) FROM garden_captures").fetchone() == (5,)
            assert db.execute("SELECT COUNT(*) FROM garden_automatic_checks").fetchone() == (0,)
    finally:
        engine.dispose()
