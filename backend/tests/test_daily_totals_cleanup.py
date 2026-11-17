"""The scheduled cleanup seals each day's totals before it deletes, and deletes nothing if it cannot (#949)."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

from app import main as main_module
from app.config import settings
from app.repositories.daily_totals_repository import DailyTotalsRepository


@pytest_asyncio.fixture
async def cleanup(migrated_history_db, monkeypatch):
    old = (datetime.now(timezone.utc) - timedelta(days=40)).replace(tzinfo=None, microsecond=0)
    async with aiosqlite.connect(migrated_history_db) as db:
        for number in range(3):
            await db.execute(
                """INSERT INTO detections (detection_time, detection_index, score, display_name, category_name,
                    frigate_event, camera_name, scientific_name, is_hidden)
                VALUES (?, 0, 0.9, 'Turdus merula', 'Turdus merula', ?, 'birdcam', 'Turdus merula', 0)""",
                ((old + timedelta(hours=number)).isoformat(sep=" "), f"aged-{number}"),
            )
        await db.commit()

    @asynccontextmanager
    async def private_history():
        async with aiosqlite.connect(migrated_history_db) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            yield connection

    monkeypatch.setattr(main_module, "get_db", private_history)
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(settings.maintenance, "retention_days", 14)
    monkeypatch.setattr(settings.maintenance, "cleanup_enabled", True)
    monkeypatch.setattr(settings.media_cache, "retention_days", 0)
    monkeypatch.setattr(settings.media_cache, "per_species_minimum", 0)
    monkeypatch.setattr(
        main_module.media_cache,
        "cleanup_old_media",
        AsyncMock(return_value={"snapshots_deleted": 0, "clips_deleted": 0}),
    )
    from app.services.garden_media_cache import garden_media_cache

    monkeypatch.setattr(garden_media_cache, "apply_retention", AsyncMock())
    monkeypatch.setattr(main_module.archive_service, "orphan_sweep", AsyncMock(return_value={"removed": 0}))
    monkeypatch.setattr(main_module.proxy, "cleanup_expired_video_share_links", AsyncMock(return_value=0))
    monkeypatch.setattr(main_module, "_run_scheduled_unknown_analysis", AsyncMock(return_value=True))
    return migrated_history_db


async def _state(path) -> tuple[int, list[tuple[int, int]]]:
    async with aiosqlite.connect(path) as db:
        async with db.execute("SELECT COUNT(*) FROM detections WHERE frigate_event LIKE 'aged-%'") as cursor:
            stored = (await cursor.fetchone())[0]
        async with db.execute("SELECT capture_count, visit_count FROM species_daily_totals") as cursor:
            totals = [tuple(row) for row in await cursor.fetchall()]
    return stored, totals


@pytest.mark.asyncio
async def test_cleanup_keeps_the_count_of_every_capture_it_deletes(cleanup):
    await main_module.run_cleanup()
    stored, totals = await _state(cleanup)
    assert stored == 0
    assert sum(captures for captures, _visits in totals) == 3


@pytest.mark.asyncio
async def test_cleanup_deletes_nothing_when_it_cannot_seal_first(cleanup, monkeypatch):
    monkeypatch.setattr(DailyTotalsRepository, "seal_before", AsyncMock(side_effect=RuntimeError("disk full")))
    await main_module.run_cleanup()
    stored, totals = await _state(cleanup)
    assert stored == 3
    assert totals == []
