"""Source summaries retain their semantics without loading every raw payload at once."""

import asyncio
from datetime import datetime, timedelta
import json

import aiosqlite
import pytest
import pytest_asyncio

from app.database import close_db, get_db, init_db
from app.repositories.detection_repository import DetectionRepository


@pytest_asyncio.fixture
async def audio_db():
    await init_db()
    try:
        async with get_db() as db:
            await db.execute("DELETE FROM audio_detections")
            await db.commit()
            yield db
    finally:
        await close_db()


def is_source_cursor(cursor):
    return [column[0] for column in cursor.description or ()] == ["timestamp", "sensor_id", "raw_data"]


def instrument_source_cursor(monkeypatch, *, cancel_after_first=False):
    fetchall = aiosqlite.Cursor.fetchall
    fetchmany = aiosqlite.Cursor.fetchmany
    close = aiosqlite.Cursor.close
    batches = []
    closed = []

    async def bounded_fetchall(cursor):
        assert not is_source_cursor(cursor), "Source payloads must be fetched in bounded batches"
        return await fetchall(cursor)

    async def bounded_fetchmany(cursor, size=None):
        if is_source_cursor(cursor):
            assert size is not None and 0 < size <= 512
            if cancel_after_first and batches:
                raise asyncio.CancelledError
            rows = await fetchmany(cursor, size)
            batches.append(len(rows))
            return rows
        return await fetchmany(cursor, size)

    async def record_close(cursor):
        if is_source_cursor(cursor):
            closed.append(cursor)
        return await close(cursor)

    monkeypatch.setattr(aiosqlite.Cursor, "fetchall", bounded_fetchall)
    monkeypatch.setattr(aiosqlite.Cursor, "fetchmany", bounded_fetchmany)
    monkeypatch.setattr(aiosqlite.Cursor, "close", record_close)
    return batches, closed


async def insert_rows(db, rows):
    await db.executemany(
        """INSERT INTO audio_detections
           (timestamp, species, confidence, sensor_id, raw_data, scientific_name, is_hidden)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    await db.commit()


@pytest.mark.asyncio
async def test_source_summary_streams_all_batches_with_legacy_label_priority(audio_db, monkeypatch):
    cases = [
        ("sensor", {"nm": " Alpha ", "sourceName": "wrong"}, "Alpha"),
        ("sensor", {"nm": 1, "sourceName": "beta", "Source": {"displayName": "wrong"}}, "beta"),
        ("sensor", {"sourceName": " ", "Source": {"displayName": "Gamma"}}, "Gamma"),
        (" Sensor ", {"sourceId": "wrong"}, "Sensor"),
        (None, {"sourceId": "delta", "src": "wrong"}, "delta"),
        (" ", {"sourceId": [], "src": "epsilon", "Source": {"id": "wrong"}}, "epsilon"),
        (None, {"Source": {"displayName": False, "id": "zeta"}}, "zeta"),
        (" fallback ", "malformed", "fallback"),
        (None, ["nonobject"], "Unknown source"),
    ]
    start = datetime(2026, 1, 1)
    rows = []
    expected = {}
    for index in range(1200):
        sensor, payload, name = cases[index % len(cases)]
        timestamp = start + timedelta(seconds=index)
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        rows.append((timestamp.isoformat(sep=" "), "Robin", 0.9, sensor, raw, "Erithacus rubecula", 0))
        item = expected.setdefault(name, {"source_name": name, "count": 0, "last_heard": None})
        item["count"] += 1
        item["last_heard"] = timestamp.isoformat() + "Z"
    await insert_rows(audio_db, rows[::2] + rows[1::2])
    batches, closed = instrument_source_cursor(monkeypatch)
    result = await DetectionRepository(audio_db).get_audio_history_summary()
    assert result["total"] == 1200
    assert result["source_count"] == len(cases)
    assert result["sources"] == sorted(
        expected.values(), key=lambda item: (-item["count"], item["source_name"].casefold())
    )
    assert sum(batches) == 1200
    assert len([size for size in batches if size]) >= 3
    assert len(closed) == 1


@pytest.mark.asyncio
async def test_streamed_summary_keeps_filters_public_boundary_and_live_visibility(audio_db, monkeypatch):
    start = datetime(2026, 1, 1)
    end = start + timedelta(seconds=1100)
    maximum_end = start + timedelta(seconds=1050)
    rows = [
        (
            (start + timedelta(seconds=i)).isoformat(sep=" "),
            "Robin",
            0.9,
            "mic",
            '{"nm":"Garden","token":"needle"}',
            "Erithacus rubecula",
            0,
        )
        for i in range(1200)
    ]
    rows += [
        (start.isoformat(sep=" "), "Robin", 0.9, "mic", '{"nm":"Hidden","token":"needle"}', None, 1),
        (start.isoformat(sep=" "), "Robin", 0.1, "mic", '{"token":"needle"}', None, 0),
        (start.isoformat(sep=" "), "Other", 0.9, "mic", '{"token":"needle"}', None, 0),
        (start.isoformat(sep=" "), "Robin", 0.9, "mic", "{}", None, 0),
        ((start - timedelta(seconds=1)).isoformat(sep=" "), "Robin", 0.9, "mic", '{"token":"needle"}', None, 0),
    ]
    await insert_rows(audio_db, rows)
    instrument_source_cursor(monkeypatch)
    repo = DetectionRepository(audio_db)
    filters = dict(start_date=start, end_date=end, species="obi", source="needle", min_confidence=0.8)
    result = await repo.get_audio_history_summary(**filters, maximum_end=maximum_end)
    assert result["total"] == 1050
    assert result["sources"] == [{"source_name": "Garden", "count": 1050, "last_heard": "2026-01-01T00:17:29Z"}]
    assert (await repo.get_audio_history_summary(**filters))["total"] == 1101
    await audio_db.execute("UPDATE audio_detections SET is_hidden=1 WHERE scientific_name='Erithacus rubecula'")
    await audio_db.commit()
    assert (await repo.get_audio_history_summary(**filters))["sources"] == []
    await audio_db.execute("UPDATE audio_detections SET is_hidden=0 WHERE scientific_name='Erithacus rubecula'")
    await audio_db.commit()
    assert (await repo.get_audio_history_summary(**filters, maximum_end=maximum_end))["sources"] == result["sources"]


@pytest.mark.asyncio
async def test_streamed_summary_closes_source_cursor_when_cancelled(audio_db, monkeypatch):
    await insert_rows(audio_db, [("2026-01-01 00:00:00", "Robin", 0.9, "mic", "{}", None, 0)] * 600)
    batches, closed = instrument_source_cursor(monkeypatch, cancel_after_first=True)
    with pytest.raises(asyncio.CancelledError):
        await DetectionRepository(audio_db).get_audio_history_summary()
    assert batches == [512]
    assert len(closed) == 1
    async with audio_db.execute("SELECT COUNT(*) FROM audio_detections") as cursor:
        assert (await cursor.fetchone())[0] == 600
