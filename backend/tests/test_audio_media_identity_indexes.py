"""Retained-identity authorization stays indexed and migration preserves history."""

from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import aiosqlite
import pytest

from app.repositories.detection_repository import DetectionRepository

INDEX_NAMES = {"idx_audio_birdnet_detectionId", "idx_audio_birdnet_detection_id", "idx_audio_birdnet_id"}
BACKEND = Path(__file__).resolve().parents[1]
REVISION = "e98a7230bd14"
PREVIOUS = "e8b2c4d6f0a1"


@pytest.fixture
def indexed_history(tmp_path):
    path = tmp_path / "history.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as db:
        source.backup(db)
        db.execute("DELETE FROM audio_detections")
        for raw in [
            "broken-json",
            json.dumps({"detectionId": 101}),
            json.dumps({"detection_id": "102"}),
            json.dumps({"id": 103}),
        ]:
            db.execute(
                "INSERT INTO audio_detections(timestamp,species,confidence,sensor_id,raw_data) VALUES('2026-09-30 00:00:01','Robin',.9,'mic',?)",
                (raw,),
            )
        db.commit()
    return path


async def actual_media_query(path):
    statements = []
    async with aiosqlite.connect(path) as db:
        await db.set_trace_callback(statements.append)
        assert await DetectionRepository(db).public_birdnet_media_visible(
            101, datetime(2026, 9, 30, tzinfo=timezone.utc)
        )
    return next(sql for sql in statements if sql.startswith("SELECT raw_data, is_hidden, sensor_id, timestamp"))


@pytest.mark.asyncio
async def test_actual_media_identity_query_uses_three_guarded_indexes(indexed_history):
    query = await actual_media_query(indexed_history)
    with closing(sqlite3.connect(indexed_history)) as db:
        plan = [row[3] for row in db.execute("EXPLAIN QUERY PLAN " + query)]
    assert any("MULTI-INDEX OR" in row for row in plan), plan
    assert not any("SCAN audio_detections" in row for row in plan), plan
    for name in INDEX_NAMES:
        assert any(name in row for row in plan), plan


@pytest.mark.asyncio
async def test_identity_index_upgrade_downgrade_upgrade_is_idempotent_and_preserves_malformed_history(indexed_history):
    query = await actual_media_query(indexed_history)
    with closing(sqlite3.connect(indexed_history)) as db:
        before = db.execute("SELECT * FROM audio_detections ORDER BY id").fetchall()
    env = os.environ.copy()
    env.update(DB_PATH=str(indexed_history), PYTHONPATH=str(BACKEND))

    def migrate(target, direction="upgrade"):
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", direction, target],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr

    migrate(PREVIOUS, "downgrade")
    with closing(sqlite3.connect(indexed_history)) as db:
        assert any("SCAN audio_detections" in row[3] for row in db.execute("EXPLAIN QUERY PLAN " + query))
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert not names.intersection(INDEX_NAMES)
    migrate(REVISION)
    migrate(REVISION)
    with closing(sqlite3.connect(indexed_history)) as db:
        assert db.execute("SELECT * FROM audio_detections ORDER BY id").fetchall() == before
        plan = [row[3] for row in db.execute("EXPLAIN QUERY PLAN " + query)]
        assert any("MULTI-INDEX OR" in row for row in plan), plan
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert INDEX_NAMES <= names
    # Explicitly rerun the revision's operations, not only Alembic's no-op head check.
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    import importlib.util
    import sqlalchemy as sa

    spec = importlib.util.spec_from_file_location(
        "identity_indexes", BACKEND / "migrations/versions/e98a7230bd14_add_audio_upstream_id_lookup_indexes.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine(f"sqlite:///{indexed_history}")
    try:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
                module.upgrade()
                module.downgrade()
                module.downgrade()
                module.upgrade()
        with closing(sqlite3.connect(indexed_history)) as db:
            assert db.execute("SELECT * FROM audio_detections ORDER BY id").fetchall() == before
    finally:
        engine.dispose()
