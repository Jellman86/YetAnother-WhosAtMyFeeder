"""Every path that deletes captures by age seals their days first, and nothing else can (#949)."""

import ast
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import aiosqlite
import pytest
import pytest_asyncio

from app import main as main_module
from app.config import settings
from app.repositories.daily_totals_repository import DailyTotalsRepository
from app.routers import settings as settings_router
from app.services.error_diagnostics import error_diagnostics_history

APP = Path(__file__).resolve().parents[1] / "app"


@pytest_asyncio.fixture
async def history(migrated_history_db, monkeypatch):
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
    monkeypatch.setattr(settings_router, "get_db", private_history)
    monkeypatch.delenv("TZ", raising=False)
    monkeypatch.setattr(settings.maintenance, "retention_days", 14)
    monkeypatch.setattr(settings.maintenance, "cleanup_enabled", True)
    monkeypatch.setattr(settings.media_cache, "retention_days", 0)
    monkeypatch.setattr(settings.media_cache, "per_species_minimum", 0)
    media_cleanup = AsyncMock(return_value={"snapshots_deleted": 0, "clips_deleted": 0})
    monkeypatch.setattr(main_module.media_cache, "cleanup_old_media", media_cleanup)
    from app.services.garden_media_cache import garden_media_cache

    monkeypatch.setattr(garden_media_cache, "apply_retention", AsyncMock())
    monkeypatch.setattr(main_module.archive_service, "orphan_sweep", AsyncMock(return_value={"removed": 0}))
    monkeypatch.setattr(main_module.proxy, "cleanup_expired_video_share_links", AsyncMock(return_value=0))
    monkeypatch.setattr(main_module, "_run_scheduled_unknown_analysis", AsyncMock(return_value=True))
    return migrated_history_db, media_cleanup


async def _state(path) -> tuple[int, list[tuple[int, int]]]:
    async with aiosqlite.connect(path) as db:
        async with db.execute("SELECT COUNT(*) FROM detections WHERE frigate_event LIKE 'aged-%'") as cursor:
            stored = (await cursor.fetchone())[0]
        async with db.execute("SELECT capture_count, visit_count FROM species_daily_totals") as cursor:
            totals = [tuple(row) for row in await cursor.fetchall()]
    return stored, totals


@pytest.mark.asyncio
async def test_scheduled_cleanup_keeps_the_count_of_every_capture_it_deletes(history):
    path, _media = history
    await main_module.run_cleanup()
    stored, totals = await _state(path)
    assert stored == 0
    assert sum(captures for captures, _visits in totals) == 3


@pytest.mark.asyncio
async def test_purge_old_records_keeps_the_count_of_every_capture_it_deletes(history):
    path, _media = history
    result = await settings_router.run_cleanup(auth=None)
    assert result["deleted_count"] == 3
    stored, totals = await _state(path)
    assert stored == 0
    assert sum(captures for captures, _visits in totals) == 3


@pytest.mark.asyncio
async def test_a_failed_seal_deletes_no_capture_but_the_rest_of_cleanup_runs_and_health_says_why(history, monkeypatch):
    path, media_cleanup = history
    monkeypatch.setattr(DailyTotalsRepository, "_write_day_totals", AsyncMock(side_effect=RuntimeError("disk full")))
    await main_module.run_cleanup()
    stored, totals = await _state(path)
    assert stored == 3
    assert totals == []
    media_cleanup.assert_awaited()
    reasons = [event["reason_code"] for event in error_diagnostics_history.snapshot(component="daily_totals")["events"]]
    assert "retention_paused_daily_totals" in reasons


def _calls(name: str) -> list[str]:
    found = []
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == name:
                receiver = ast.unparse(node.func.value)
                found.append(f"{path.relative_to(APP)}:{receiver}")
    return sorted(found)


def test_only_the_retention_function_deletes_captures_by_age():
    # Garden keeps its own history; every detection delete by age goes through sealing.
    assert [call for call in _calls("delete_older_than") if "Garden" not in call] == [
        "repositories/daily_totals_repository.py:self"
    ]


def test_only_the_owner_deletes_a_capture_without_keeping_its_count():
    # Deleting a capture by hand is a correction; anything automatic records the loss.
    assert {call.split(":")[0] for call in _calls("delete_by_frigate_event")} == {"routers/events.py"}
