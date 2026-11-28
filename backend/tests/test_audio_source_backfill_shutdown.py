"""Stopping YA-WAMF while it reads older calls' sources leaves no batch half written and no
connection open after the database closes; the next start reads what is left (#1111)."""

import ast
import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from app import database
from app.database import close_db, get_db, init_db
from app.repositories.audio_history_repository import AudioHistoryRepository
from app.services.audio.source_backfill import (
    BATCH_SIZE,
    resolve_pending_audio_sources,
    start_background_audio_source_backfill,
    stop_audio_source_backfill,
)

MAIN = Path(__file__).resolve().parents[1] / "app" / "main.py"
CALLS = BATCH_SIZE * 2 + 200


def test_shutdown_stops_the_backfill_before_it_closes_the_database():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    lifespan = next(
        node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan"
    )
    kept = [
        node
        for node in ast.walk(lifespan)
        if isinstance(node, ast.Assign)
        and [ast.unparse(target) for target in node.targets] == ["audio_source_backfill_task"]
        and "start_background_audio_source_backfill()" in ast.unparse(node.value)
    ]
    assert kept, "the lifespan must keep the backfill task to stop it"
    stops = [
        node.lineno
        for node in ast.walk(lifespan)
        if isinstance(node, ast.Await)
        and ast.unparse(node.value) == "stop_audio_source_backfill(audio_source_backfill_task)"
    ]
    closes = [
        node.lineno
        for node in ast.walk(lifespan)
        if isinstance(node, ast.Await) and ast.unparse(node.value) == "close_db()"
    ]
    assert stops and closes
    assert max(stops) < min(closes)


def _pending(path: str) -> int:
    with sqlite3.connect(path) as db:
        return db.execute("SELECT COUNT(*) FROM audio_detections WHERE source_resolved = 0").fetchone()[0]


@pytest.mark.asyncio
async def test_a_stop_mid_batch_rolls_the_batch_back_and_opens_nothing_after_the_database_closes(
    history_pool, monkeypatch
):
    async with get_db() as db:
        await db.execute("DELETE FROM audio_detections")
        # Stored by a release from before source tracking, after a rollback: no source columns.
        await db.executemany(
            """INSERT INTO audio_detections (timestamp, species, confidence, sensor_id, raw_data)
               VALUES ('2026-11-01 08:00:00', 'Robin', 0.9, 'Feeder', ?)""",
            [
                (json.dumps({"detectionId": index, "sourceId": "rtsp_x", "sourceName": "Feeder"}),)
                for index in range(CALLS)
            ],
        )
        await db.commit()
    path = database._get_db_path()

    original = AudioHistoryRepository.resolve_pending_sources
    batches = 0
    mid_batch = asyncio.Event()

    async def stopped_mid_batch(self, limit):
        nonlocal batches
        batches += 1
        if batches == 1:
            return await original(self, limit)
        # The second batch is written but not committed when the stop arrives.
        await self.db.execute(
            """UPDATE audio_detections SET source_resolved = 1
               WHERE id IN (SELECT id FROM audio_detections WHERE source_resolved = 0 LIMIT ?)""",
            (limit,),
        )
        mid_batch.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(AudioHistoryRepository, "resolve_pending_sources", stopped_mid_batch)
    task = asyncio.create_task(start_background_audio_source_backfill())
    await asyncio.wait_for(mid_batch.wait(), timeout=10)

    await stop_audio_source_backfill(task)
    assert task.cancelled()

    opened_after_close: list[str] = []
    real_connect = database.aiosqlite.connect

    def counted_connect(*args, **kwargs):
        opened_after_close.append(str(args[0]) if args else "")
        return real_connect(*args, **kwargs)

    await close_db()
    monkeypatch.setattr(database.aiosqlite, "connect", counted_connect)
    for _ in range(20):
        await asyncio.sleep(0)
    assert opened_after_close == []
    # The first batch was committed; the one cut short was rolled back and still waits.
    assert _pending(path) == CALLS - BATCH_SIZE

    monkeypatch.setattr(database.aiosqlite, "connect", real_connect)
    monkeypatch.setattr(AudioHistoryRepository, "resolve_pending_sources", original)
    await init_db()
    # The next start reads what is left, and only that.
    assert await resolve_pending_audio_sources() == CALLS - BATCH_SIZE
    assert _pending(path) == 0


@pytest.mark.asyncio
async def test_stopping_a_finished_or_absent_backfill_does_nothing():
    await stop_audio_source_backfill(None)

    async def finished() -> None:
        return None

    task = asyncio.create_task(finished())
    await task
    await stop_audio_source_backfill(task)
    assert task.done() and not task.cancelled()
