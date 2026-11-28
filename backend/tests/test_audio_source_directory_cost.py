"""Naming Audio history's sources costs the same however long the history is (#1111).

A request reads the sources a window's calls came from, not every call ever stored: the work to
name them grows with the number of sources, never with the number of calls.
"""

import json
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest

from app.repositories.audio_history_repository import AudioHistoryRepository, load_audio_source_directory

DAY = datetime(2026, 11, 27, tzinfo=timezone.utc)


async def _seed(db: aiosqlite.Connection, old_calls: int) -> None:
    """``old_calls`` calls long before the day asked for, then one renamed source heard that day."""
    await db.execute("DELETE FROM audio_detections")
    rows = []
    for index in range(old_calls):
        stamp = (DAY - timedelta(days=30, seconds=index)).strftime("%Y-%m-%d %H:%M:%S")
        if index % 2:
            # An old call whose payload names no source: the upgrade left its source columns empty.
            rows.append((stamp, None, '{"comName": "Robin", "score": 0.9}', None, None, None))
        else:
            name = ("patiocam", "birdcam", "nestcam")[index % 3]
            payload = json.dumps({"sourceId": f"rtsp_{index % 3}", "sourceName": name, "SourceNode": "Quark"})
            rows.append((stamp, name, payload, "Quark", f"rtsp_{index % 3}", name))
    rows.append(
        (
            (DAY + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
            "Feeder",
            json.dumps({"sourceId": "rtsp_0", "sourceName": "Feeder", "SourceNode": "Quark"}),
            "Quark",
            "rtsp_0",
            "Feeder",
        )
    )
    await db.executemany(
        """INSERT INTO audio_detections
           (timestamp, species, confidence, sensor_id, raw_data, source_node, source_id, source_name, source_resolved)
           VALUES (?, 'Robin', 0.9, ?, ?, ?, ?, ?, 1)""",
        rows,
    )
    await db.commit()


async def _steps(db: aiosqlite.Connection, work) -> tuple[int, object]:
    """How many SQLite virtual machine steps ``work`` took, in thousands: the rows it read."""
    steps = 0

    def count() -> int:
        nonlocal steps
        steps += 1
        return 0

    await db.set_progress_handler(count, 1_000)
    try:
        result = await work()
    finally:
        await db.set_progress_handler(None, 1_000)
    return steps, result


async def _day_cost(path, old_calls: int) -> dict[str, int]:
    async with aiosqlite.connect(path) as db:
        await _seed(db, old_calls)
        repo = AudioHistoryRepository(db)
        costs = {}
        for name, kwargs in {
            "owner": {"owner_evidence": True},
            "hidden": {"owner_evidence": True, "hidden": True},
            "guest": {"minimum_start": DAY, "maximum_end": DAY + timedelta(days=1)},
        }.items():
            costs[name], _ = await _steps(db, lambda kwargs=kwargs: load_audio_source_directory(db, **kwargs))
        costs["summary"], summary = await _steps(
            db, lambda: repo.get_audio_history_summary(start_date=DAY, end_date=DAY + timedelta(days=1))
        )
        assert [(item["source_name"], item["count"]) for item in summary["sources"]] == [("Feeder", 1)]
        return costs


@pytest.mark.asyncio
async def test_naming_a_days_sources_reads_the_same_whatever_the_history_holds(migrated_history_db):
    small = await _day_cost(migrated_history_db, 2_000)
    large = await _day_cost(migrated_history_db, 20_000)
    # Ten times the calls: the same work, give or take the index's depth.
    for name in small:
        assert large[name] <= small[name] + 2, (name, small, large)


@pytest.mark.asyncio
async def test_every_statement_reading_sources_seeks_an_index(migrated_history_db):
    async with aiosqlite.connect(migrated_history_db) as db:
        await _seed(db, 3_000)
        statements: list[str] = []
        await db.set_trace_callback(statements.append)
        await load_audio_source_directory(db, owner_evidence=True)
        await load_audio_source_directory(db, minimum_start=DAY, maximum_end=DAY + timedelta(days=1))
        await db.set_trace_callback(None)
        assert statements
        for statement in statements:
            async with db.execute(f"EXPLAIN QUERY PLAN {statement}") as cursor:
                plan = " ".join(str(row[3]) for row in await cursor.fetchall())
            assert "SCAN audio_detections" not in plan, (statement, plan)


@pytest.mark.asyncio
async def test_a_start_with_no_call_to_read_costs_one_empty_seek(migrated_history_db):
    async with aiosqlite.connect(migrated_history_db) as db:
        await _seed(db, 20_000)
        repo = AudioHistoryRepository(db)
        statements: list[str] = []
        await db.set_trace_callback(statements.append)
        steps, resolved = await _steps(db, lambda: repo.resolve_pending_sources(500))
        await db.set_trace_callback(None)
        assert (resolved, steps) == (0, 0)
        [statement] = statements
        async with db.execute(f"EXPLAIN QUERY PLAN {statement}") as cursor:
            plan = " ".join(str(row[3]) for row in await cursor.fetchall())
        assert "idx_audio_detections_source_pending" in plan, plan


async def _link_reads(path, old_calls: int) -> tuple[list[str], list[str], list]:
    async with aiosqlite.connect(path) as db:
        await _seed(db, old_calls)
        statements: list[str] = []
        await db.set_trace_callback(statements.append)
        links = await AudioHistoryRepository(db).load_audio_source_links()
        await db.set_trace_callback(None)
        plans = []
        for statement in statements:
            async with db.execute(f"EXPLAIN QUERY PLAN {statement}") as cursor:
                plans.append(" ".join(str(row[3]) for row in await cursor.fetchall()))
        return statements, plans, links


@pytest.mark.asyncio
async def test_listing_sources_to_link_reads_the_identity_index_alone(migrated_history_db):
    """Settings' list takes one statement per stored name, whatever the history holds, and never a payload."""
    small, _, small_links = await _link_reads(migrated_history_db, 2_000)
    large, plans, large_links = await _link_reads(migrated_history_db, 20_000)
    assert len(large) == len(small)
    for plan in plans:
        assert "SCAN audio_detections" not in plan, plan
        assert "COVERING INDEX" in plan, plan
    assert [(link.mapping_value, link.source_name) for link in large_links] == [
        ("rtsp_0", "Feeder"),
        ("rtsp_2", "nestcam"),
        ("rtsp_1", "birdcam"),
    ]
    assert [name.name for name in large_links[0].earlier_names] == ["patiocam"]
    assert sum(link.seen_count for link in large_links) == 10_001
    assert [link.mapping_value for link in small_links] == [link.mapping_value for link in large_links]
