import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.routers import backfill as backfill_router
from app.routers.backfill import (
    BackfillJobStatus,
    _build_error_message,
    _build_running_message,
    _build_skipped_message,
    _check_stale_backfill_jobs,
    _resolve_date_range,
)


def test_build_skipped_message_without_reasons():
    assert _build_skipped_message(0, None) == ""
    assert _build_skipped_message(3, None) == "3 skipped"


def test_build_skipped_message_already_exists_only():
    assert _build_skipped_message(4, {"already_exists": 4}) == "4 already existed"


def test_build_skipped_message_reports_invalid_scores():
    assert _build_skipped_message(2, {"invalid_score": 2}) == "2 had invalid classifier scores"


def test_build_skipped_message_reports_low_confidence_results():
    assert _build_skipped_message(93, {"low_confidence": 93}) == "93 were below the confidence threshold"


def test_build_skipped_message_mixed_reasons():
    msg = _build_skipped_message(
        17,
        {
            "already_exists": 5,
            "invalid_score": 2,
            "low_confidence": 7,
            "blocked_label": 3,
        },
    )
    assert msg == (
        "5 already existed, 2 had invalid classifier scores, "
        "7 were below the confidence threshold, 3 skipped by filters/validation"
    )


def test_build_error_message_without_reasons():
    assert _build_error_message(0, None) == ""
    assert _build_error_message(3, None) == "3 error(s)"


def test_build_error_message_reports_known_detection_failures():
    msg = _build_error_message(
        7,
        {
            "fetch_snapshot_failed": 2,
            "background_image_worker_unavailable": 1,
            "timeout": 3,
            "exception": 1,
        },
    )
    assert msg == "2 missing snapshots, 1 classifier worker unavailable, 3 timed out, 1 processing exception"


def test_build_error_message_reports_model_unavailable_reason():
    msg = _build_error_message(
        3,
        {
            "background_image_model_unavailable": 2,
            "classification_failed": 1,
        },
    )
    assert msg == "2 classifier model unavailable, 1 empty classifier result"


def test_build_running_message_reports_scanning_when_total_unknown():
    job = BackfillJobStatus(id="job-1", kind="detections", status="running")
    assert _build_running_message(job, {}) == "Scanning historical events"


def test_build_running_message_reports_live_pressure_pause():
    job = BackfillJobStatus(
        id="job-2",
        kind="detections",
        status="running",
        processed=0,
        total=200,
    )
    assert (
        _build_running_message(job, {"background_throttled": True})
        == "Paused while live detections use classifier capacity"
    )


def test_build_running_message_reports_classifier_recovery_pause():
    job = BackfillJobStatus(
        id="job-3",
        kind="detections",
        status="running",
        processed=0,
        total=200,
    )
    assert (
        _build_running_message(
            job,
            {
                "background_throttled": True,
                "worker_pools": {
                    "live": {"circuit_open": True},
                    "background": {"circuit_open": False},
                },
            },
        )
        == "Paused while classifier workers recover"
    )


def test_build_running_message_reports_classifier_recovery_mid_run():
    job = BackfillJobStatus(
        id="job-4",
        kind="detections",
        status="running",
        processed=48,
        total=200,
    )
    assert (
        _build_running_message(
            job,
            {
                "worker_pools": {
                    "live": {"circuit_open": False},
                    "background": {"circuit_open": True},
                },
            },
        )
        == "Waiting for classifier workers to recover"
    )


def test_build_running_message_reports_deprioritized_queue():
    job = BackfillJobStatus(
        id="job-5",
        kind="detections",
        status="running",
        processed=0,
        total=200,
    )
    assert (
        _build_running_message(
            job,
            {
                "background_throttled": True,
                "background": {"queued": 12, "oldest_queued_age_seconds": 22.0},
                "background_starvation_relief_active": False,
            },
        )
        == "Deprioritized while live detections keep classifier capacity"
    )


def test_build_running_message_reports_stalled_queue():
    job = BackfillJobStatus(
        id="job-6",
        kind="detections",
        status="running",
        processed=0,
        total=200,
    )
    assert (
        _build_running_message(
            job,
            {
                "background_throttled": True,
                "background": {"queued": 24, "oldest_queued_age_seconds": 95.0},
                "background_starvation_relief_active": True,
            },
        )
        == "Stalled while waiting for maintenance classifier capacity"
    )


def test_custom_backfill_range_uses_browser_timezone_and_an_exclusive_next_day_boundary():
    start, end = _resolve_date_range(
        "custom",
        "2026-07-01",
        "2026-07-01",
        "en",
        user_timezone=ZoneInfo("Europe/London"),
    )

    assert start == datetime(2026, 6, 30, 23, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 7, 1, 23, 0, tzinfo=timezone.utc)
    assert end - start == timedelta(days=1)


def test_custom_backfill_range_before_start_produces_an_empty_or_reversed_interval():
    start, end = _resolve_date_range(
        "custom",
        "2026-07-03",
        "2026-07-02",
        "en",
        user_timezone=timezone.utc,
    )

    assert start >= end


def test_backfill_watchdog_uses_last_progress_instead_of_total_runtime(monkeypatch):
    now = datetime.now(timezone.utc)
    job = BackfillJobStatus(
        id="job-progressing",
        kind="detections",
        status="running",
        started_at=(now - timedelta(hours=2)).isoformat(),
        last_progress_at=now.isoformat(),
        processed=500,
        total=1000,
    )
    backfill_router._JOB_STORE.clear()
    backfill_router._JOB_STORE[job.id] = job
    backfill_router._stale_job_ids_reported.clear()
    recorded: list[dict] = []
    monkeypatch.setattr(backfill_router.error_diagnostics_history, "record", lambda **kwargs: recorded.append(kwargs))

    _check_stale_backfill_jobs()

    assert recorded == []
    assert job.id not in backfill_router._stale_job_ids_reported
    backfill_router._JOB_STORE.clear()


def test_weather_followup_waits_and_retries_instead_of_being_dropped(monkeypatch):
    attempts: list[int] = []

    async def fake_start(*_args, **_kwargs):
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            return None
        return BackfillJobStatus(id="weather-followup", kind="weather", status="running")

    monkeypatch.setattr(backfill_router, "_start_weather_backfill_async", fake_start)
    monkeypatch.setattr(backfill_router, "WEATHER_FOLLOWUP_RETRY_SECONDS", 0.001)
    backfill_router._JOB_TASKS.clear()

    async def exercise() -> None:
        backfill_router._schedule_weather_followup(
            backfill_router.WeatherBackfillRequest(date_range="day", only_missing=True),
            "en",
            timezone.utc,
            detection_job_id="detection-1",
        )
        task = backfill_router._JOB_TASKS["weather_followup:detection-1"]
        await asyncio.wait_for(task, timeout=1.0)

    asyncio.run(exercise())

    assert attempts == [1, 2, 3]
    assert "weather_followup:detection-1" not in backfill_router._JOB_TASKS


def test_terminal_backfill_history_is_bounded_without_dropping_running_or_latest_jobs(monkeypatch):
    monkeypatch.setattr(backfill_router, "BACKFILL_JOB_HISTORY_LIMIT", 2)
    backfill_router._JOB_STORE.clear()
    backfill_router._LATEST_JOB_BY_KIND.clear()

    for index in range(4):
        job = BackfillJobStatus(
            id=f"done-{index}",
            kind="detections",
            status="completed",
            started_at=f"2026-07-22T10:0{index}:00+00:00",
            finished_at=f"2026-07-22T10:0{index}:30+00:00",
        )
        backfill_router._JOB_STORE[job.id] = job
    running = BackfillJobStatus(id="running", kind="weather", status="running")
    backfill_router._JOB_STORE[running.id] = running
    backfill_router._LATEST_JOB_BY_KIND.update({"detections": "done-0", "weather": running.id})

    backfill_router._prune_terminal_jobs()

    assert set(backfill_router._JOB_STORE) == {"done-0", "done-2", "done-3", "running"}
    backfill_router._JOB_STORE.clear()
    backfill_router._LATEST_JOB_BY_KIND.clear()


def test_request_task_registration_fails_closed_during_reset():
    async def exercise() -> None:
        backfill_router._JOB_TASKS.clear()
        backfill_router._RESET_IN_PROGRESS = True
        try:
            assert await backfill_router._register_request_task("sync-request") is False
            assert "sync-request" not in backfill_router._JOB_TASKS
        finally:
            backfill_router._RESET_IN_PROGRESS = False

    asyncio.run(exercise())
