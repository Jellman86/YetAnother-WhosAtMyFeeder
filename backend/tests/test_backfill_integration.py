"""Exercise backfill orchestration and real repository writes together.

Only external media, model inference, taxonomy and outbound reporting are
substituted. Each case owns a database built by the production migrations.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from io import BytesIO
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
import pytest_asyncio
from PIL import Image
from starlette.requests import Request

from app.repositories.detection_repository import DetectionRepository
from app.routers import backfill as router
from app.services import backfill_service as backfill_module
from app.services import detection_service as detection_module
from app.services.backfill_service import BackfillService
from app.services.maintenance_coordinator import MaintenanceCoordinator
from app.services.species_catalog_resolver import ShadowResolution


@pytest.fixture(scope="module")
def migrated_backfill_template(tmp_path_factory):
    path = tmp_path_factory.mktemp("backfill-schema") / "template.db"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "DB_PATH": str(path)},
        check=True,
        capture_output=True,
    )
    return path


@pytest_asyncio.fixture
async def replay(monkeypatch, tmp_path, migrated_backfill_template):
    path = tmp_path / "backfill.db"
    shutil.copyfile(migrated_backfill_template, path)

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as connection:
            await connection.execute("PRAGMA foreign_keys=ON")
            yield connection

    classifier = MagicMock()
    classifier.model_loaded = True
    classifier.get_admission_status.return_value = {}
    classifier.classify_async_background = AsyncMock(
        return_value=[{"label": "Prunella modularis", "score": 0.85, "index": 2}]
    )
    image = BytesIO()
    Image.new("RGB", (32, 32), "green").save(image, "JPEG")
    snapshot = AsyncMock(return_value=image.getvalue())
    monkeypatch.setattr(backfill_module.frigate_client, "get_snapshot", snapshot)
    monkeypatch.setattr(detection_module, "get_db", database)
    monkeypatch.setattr(router, "get_db", database)
    monkeypatch.setattr(detection_module.taxonomy_service, "get_names", AsyncMock(return_value={}))
    monkeypatch.setattr(
        detection_module, "_catalog_shadow_resolution", AsyncMock(return_value=ShadowResolution(verdict="unavailable"))
    )
    monkeypatch.setattr(detection_module.birdweather_service, "report_detection", AsyncMock(return_value=False))
    monkeypatch.setattr(router.broadcaster, "broadcast", AsyncMock())
    for key, value in {
        "threshold": 0.6,
        "min_confidence": 0.6,
        "trust_frigate_sublabel": False,
        "blocked_labels": [],
        "blocked_species": [],
    }.items():
        monkeypatch.setattr(backfill_module.settings.classification, key, value)
    monkeypatch.setattr(backfill_module.settings.media_cache, "enabled", False)
    service = BackfillService(classifier)
    monkeypatch.setattr(router, "backfill_service", service)
    monkeypatch.setattr(router, "_JOB_STORE", {})
    monkeypatch.setattr(router, "_JOB_TASKS", {})
    monkeypatch.setattr(router, "_LATEST_JOB_BY_KIND", {})
    monkeypatch.setattr(router, "_JOB_LOCK", asyncio.Lock())
    monkeypatch.setattr(router, "_RESET_IN_PROGRESS", False)
    monkeypatch.setattr(router, "_maintenance_guardrail_status", lambda: {})
    monkeypatch.setattr(router.canonical_identity_repair_service, "get_status", lambda: {})
    coordinator = MaintenanceCoordinator()
    monkeypatch.setattr(router, "maintenance_coordinator", coordinator)
    monkeypatch.setattr(router, "_schedule_weather_followup", MagicMock())
    event = {"id": "replay-event", "camera": "test-camera", "start_time": 1700000000, "top_score": 0.95}
    try:
        yield SimpleNamespace(
            service=service,
            classifier=classifier,
            database=database,
            event=event,
            snapshot=snapshot,
            coordinator=coordinator,
        )
    finally:
        tasks = list(router._JOB_TASKS.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def stored(replay):
    async with replay.database() as db:
        return await DetectionRepository(db).get_by_frigate_event(replay.event["id"])


@pytest.mark.asyncio
async def test_replay_is_idempotent_and_only_improves_automatic_identity(replay):
    assert await replay.service.process_historical_event(replay.event) == ("new", None)
    initial = await stored(replay)
    assert initial.score == pytest.approx(0.85)
    assert await replay.service.process_historical_event(replay.event) == ("skipped", "already_exists")
    replay.classifier.classify_async_background.return_value[0]["score"] = 0.7
    assert await replay.service.process_historical_event(replay.event) == ("skipped", "already_exists")
    replay.classifier.classify_async_background.return_value[0]["score"] = 0.95
    assert await replay.service.process_historical_event(replay.event) == ("new", None)
    updated = await stored(replay)
    assert updated.id == initial.id
    assert updated.score == pytest.approx(0.95)
    async with replay.database() as db:
        assert (await (await db.execute("SELECT count(*) FROM detections")).fetchone())[0] == 1
        assert (await (await db.execute("PRAGMA integrity_check")).fetchone())[0] == "ok"


@pytest.mark.asyncio
async def test_replay_preserves_manual_identity_favorite_hidden_and_enrichment(replay):
    await replay.service.process_historical_event(replay.event)
    async with replay.database() as db:
        await db.execute(
            "UPDATE detections SET manual_tagged=1, is_hidden=1, temperature=12.5, ai_analysis='owner notes'"
        )
        await db.commit()
        await DetectionRepository(db).favorite_detection(replay.event["id"])
    replay.classifier.classify_async_background.return_value = [{"label": "Parus major", "score": 0.99, "index": 3}]
    assert await replay.service.process_historical_event(replay.event) == ("skipped", "already_exists")
    row = await stored(replay)
    assert row.category_name == "Prunella modularis"
    assert row.manual_tagged and row.is_hidden and row.is_favorite
    assert row.temperature == 12.5
    assert row.ai_analysis == "owner notes"


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1, 0.1])
async def test_unusable_classifier_scores_never_reach_database(replay, score):
    replay.classifier.classify_async_background.return_value[0]["score"] = score
    status, _ = await replay.service.process_historical_event(replay.event)
    assert status == "skipped"
    assert await stored(replay) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("snapshot", [None, b"not a jpeg"])
async def test_missing_or_corrupt_media_never_classifies_or_writes(replay, snapshot):
    replay.snapshot.return_value = snapshot
    assert (await replay.service.process_historical_event(replay.event))[0] == "error"
    replay.classifier.classify_async_background.assert_not_awaited()
    assert await stored(replay) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["lookup", "write", "upgrade"])
async def test_media_failure_after_commit_does_not_misreport_saved_detection(replay, monkeypatch, failure):
    monkeypatch.setattr(backfill_module.settings.media_cache, "enabled", True)
    monkeypatch.setattr(backfill_module.settings.media_cache, "cache_snapshots", True)
    monkeypatch.setattr(backfill_module.settings.media_cache, "high_quality_event_snapshots", True)
    cache = MagicMock(has_snapshot=MagicMock(return_value=False), cache_snapshot=AsyncMock(return_value="test.jpg"))
    upgrade = MagicMock(return_value=True)
    {"lookup": cache.has_snapshot, "write": cache.cache_snapshot, "upgrade": upgrade}[failure].side_effect = OSError(
        "cache unavailable"
    )
    monkeypatch.setattr(backfill_module, "media_cache", cache)
    monkeypatch.setattr(backfill_module.high_quality_snapshot_service, "schedule_replacement", upgrade)
    assert await replay.service.process_historical_event(replay.event) == ("new", None)
    assert (await stored(replay)).score == pytest.approx(0.85)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_detection_jobs_account_for_saved_filtered_and_missing_events(replay, mode):
    events = [{**replay.event, "id": f"replay-{i}"} for i in range(3)]
    replay.service.fetch_frigate_events = AsyncMock(return_value=events)
    jpeg = replay.snapshot.return_value
    replay.snapshot.side_effect = [jpeg, jpeg, None]
    replay.classifier.classify_async_background.side_effect = [
        [{"label": "Prunella modularis", "score": 0.85, "index": 2}],
        [{"label": "Prunella modularis", "score": 0.1, "index": 2}],
    ]
    request = Request({"type": "http", "headers": []})
    if mode == "sync":
        result = await router.backfill_detections(router.BackfillRequest(date_range="day"), request)
    else:
        result = await router.backfill_detections_async(router.BackfillRequest(date_range="day"), request)
        await router._JOB_TASKS[result.id]
        router._schedule_weather_followup.assert_called_once()
        assert router.broadcaster.broadcast.await_args.args[0]["type"] == "backfill_complete"
    assert result.status == "completed"
    assert result.processed == 3
    assert result.new_detections == result.skipped == result.errors == 1
    assert result.skipped_reasons == {"low_confidence": 1}
    assert result.error_reasons == {"fetch_snapshot_failed": 1}
    assert not replay.coordinator._holders


@pytest.mark.asyncio
async def test_cancelled_detection_job_releases_capacity_and_does_not_chain_weather(replay):
    started = asyncio.Event()

    async def blocked_fetch(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    replay.service.fetch_frigate_events = blocked_fetch
    job = await router.backfill_detections_async(
        router.BackfillRequest(date_range="day"), Request({"type": "http", "headers": []})
    )
    task = router._JOB_TASKS[job.id]
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert job.status == "failed" and job.finished_at
    assert job.processed == 0
    assert not replay.coordinator._holders
    router._schedule_weather_followup.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["detections", "weather"])
async def test_task_creation_failure_cannot_leave_phantom_running_job(replay, monkeypatch, kind):
    def cannot_schedule(coro, **kwargs):
        coro.close()
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(router, "create_background_task", cannot_schedule)
    with pytest.raises(RuntimeError, match="scheduler unavailable"):
        if kind == "detections":
            await router.backfill_detections_async(
                router.BackfillRequest(date_range="day"), Request({"type": "http", "headers": []})
            )
        else:
            await router._start_weather_backfill_async(router.WeatherBackfillRequest(date_range="day"), "en")
    assert not replay.coordinator._holders
    assert await router._get_running_job(kind) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("archive", ["available", "missing", "error"])
async def test_weather_backfill_real_repository_and_job_accounting(replay, monkeypatch, mode, archive):
    await replay.service.process_historical_event(replay.event)
    start = datetime.fromtimestamp(replay.event["start_time"], timezone.utc)
    hour = start.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:00")
    weather = AsyncMock(
        return_value={hour: {"temperature": 12.5, "condition_text": "Cloudy"}} if archive == "available" else {}
    )
    if archive == "error":
        weather.side_effect = OSError("archive offline")
    monkeypatch.setattr(router.weather_service, "get_hourly_weather", weather)
    request = router.WeatherBackfillRequest(date_range="custom", start_date="2023-11-14", end_date="2023-11-14")
    if mode == "sync":
        if archive == "error":
            with pytest.raises(router.HTTPException) as exc:
                await router.backfill_weather(request, Request({"type": "http", "headers": []}))
            assert exc.value.status_code == 500
            assert not replay.coordinator._holders
            return
        job = await router.backfill_weather(request, Request({"type": "http", "headers": []}))
    else:
        job = await router._start_weather_backfill_async(request, "en")
        await router._JOB_TASKS[job.id]
    assert not replay.coordinator._holders
    if archive == "error":
        assert job.status == "failed"
        assert (await stored(replay)).temperature is None
    else:
        assert job.status == "completed"
        assert job.processed == 1
        assert job.updated == (archive == "available")
        assert job.skipped == (archive == "missing")
        assert (await stored(replay)).temperature == (12.5 if archive == "available" else None)


@pytest.mark.asyncio
async def test_cancelled_weather_write_is_not_counted_as_processed(replay, monkeypatch):
    await replay.service.process_historical_event(replay.event)
    monkeypatch.setattr(
        router.weather_service,
        "get_hourly_weather",
        AsyncMock(return_value={"2023-11-14T22:00": {"temperature": 12.5}}),
    )
    started = asyncio.Event()

    async def blocked_write(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(DetectionRepository, "update_weather_fields", blocked_write)
    job = await router._start_weather_backfill_async(
        router.WeatherBackfillRequest(date_range="custom", start_date="2023-11-14", end_date="2023-11-14"), "en"
    )
    task = router._JOB_TASKS[job.id]
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert job.status == "failed"
    assert job.processed == job.updated + job.skipped + job.errors == 0
    assert not replay.coordinator._holders
    assert (await stored(replay)).temperature is None


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1])
async def test_direct_save_rejects_invalid_probability_before_any_write(replay, score):
    changed, inserted = await replay.service.detection_service.save_detection(
        frigate_event=replay.event["id"],
        camera="test-camera",
        start_time=1700000000,
        classification={"label": "Prunella modularis", "score": score, "index": 2},
    )
    assert (changed, inserted) == (False, False)
    assert await stored(replay) is None
