"""Motion work is opt-in, serial, preemptible, and private until published."""

import hashlib
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.config_models import FrigateSettings
from app.database import init_db, get_db, close_db
from app.repositories.garden_repository import GardenRepository
from app.services import garden_motion_privacy
from app.services.garden_identification import garden_identification_service
from app.services.garden_motion import GardenMotionService
from app.services.garden_motion_decode import MotionDecoder


def test_motion_cameras_default_off_and_reject_path_names():
    assert FrigateSettings(frigate_url="http://frigate").garden_motion_cameras == []
    with pytest.raises(ValueError):
        FrigateSettings(frigate_url="http://frigate", garden_motion_cameras=["../patio"])


@pytest_asyncio.fixture
async def collector(monkeypatch, tmp_path):
    await init_db()
    async with get_db() as db:
        for table in ("garden_identifications", "garden_motion_sources", "garden_motion_cursors", "garden_captures"):
            await db.execute(f"DELETE FROM {table}")
        await db.commit()
    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio"])
    monkeypatch.setattr(settings.frigate, "garden_motion_cameras", ["patio"])
    monkeypatch.setattr(garden_identification_service, "busy", False)
    monkeypatch.setattr(garden_identification_service, "error", None)
    monkeypatch.setattr("app.services.garden_motion.garden_inference_pressure", lambda: {"live": {}, "background": {}})
    service = GardenMotionService()
    # A developer machine may have a GPU; tests decide the decoder explicitly.
    service.decoder = MotionDecoder("not_packaged")
    service.path = tmp_path / "detector.onnx"
    service.path.write_bytes(b"model")
    bundle = dict(
        model_sha256=hashlib.sha256(b"model").hexdigest(), model_bytes=5, names=["animal", "person", "vehicle"]
    )
    monkeypatch.setattr(service.catalog, "load", lambda: bundle)

    async def get(path, **kwargs):
        if path == "api/stats":
            payload = {"cameras": {"patio": {"camera_fps": 10, "process_fps": 10, "skipped_fps": 0}}}
        else:
            payload = [{"start_time": time.time() - 50, "end_time": time.time() - 40, "motion": 10}]
        return httpx.Response(200, json=payload, request=httpx.Request("GET", "http://frigate/"))

    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", get)
    monkeypatch.setattr("app.services.garden_motion.frigate_client.list_events", AsyncMock(return_value=[]))

    async def download(camera, start, end, path):
        path.write_bytes(b"clip")

    monkeypatch.setattr("app.services.garden_motion.frigate_client.download_motion_recording", download)

    async def native(payload, blocked):
        from pathlib import Path

        Path(payload["photo"]).write_bytes(b"photo")
        return dict(
            outcome="candidate",
            frame_index=10,
            frame_offset=1.0,
            detector_score=0.8,
            box_xywh=[0.1, 0.1, 0.2, 0.2],
            image_sha256=hashlib.sha256(b"photo").hexdigest(),
            detector_input_sha256="d" * 64,
            sampled_frame_sha256="e" * 64,
            devices=["CPUExecutionProvider"],
        )

    monkeypatch.setattr(service, "_native", native)
    yield service
    assert not garden_identification_service.busy
    await close_db()


@pytest.mark.asyncio
async def test_one_real_recording_scan_publishes_review_without_bird_writes(collector):
    async with get_db() as db:
        before = await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone()
    await collector.scan_once()
    async with get_db() as db:
        repo = GardenRepository(db)
        rows = await repo.list("pending", 20, 0)
        assert len(rows) == 1 and rows[0].motion_source
        assert rows[0].frigate_event is None
        assert await repo.motion_photo(rows[0].id) == b"photo"
        assert await (await db.execute("SELECT COUNT(*) FROM detections")).fetchone() == before
    assert collector.last_outcome == "candidate"
    await collector.scan_once()
    async with get_db() as db:
        assert await GardenRepository(db).count("pending") == 1


@pytest.mark.asyncio
async def test_motion_capture_refreshes_the_explorer_after_commit_without_waiting_for_identification(
    collector, monkeypatch
):
    from app.services.broadcaster import broadcaster

    async def refresh(message):
        assert message == {"type": "garden_history_changed"}
        assert not garden_motion_privacy.lock.locked()
        async with get_db() as db:
            assert await GardenRepository(db).count("pending") == 1

    update = AsyncMock(side_effect=refresh)
    monkeypatch.setattr(broadcaster, "broadcast", update)
    await collector.scan_once()
    update.assert_awaited_once_with({"type": "garden_history_changed"})


@pytest.mark.asyncio
async def test_bird_work_and_disabled_camera_prevent_native_launch(collector, monkeypatch):
    native = AsyncMock()
    monkeypatch.setattr(collector, "_native", native)
    monkeypatch.setattr("app.services.garden_motion.garden_inference_pressure", lambda: None)
    await collector.scan_once()
    native.assert_not_awaited()
    monkeypatch.setattr(settings.frigate, "garden_motion_cameras", [])
    await collector.scan_once()
    native.assert_not_awaited()


@pytest.mark.asyncio
async def test_late_privacy_generation_cancels_publication(collector, monkeypatch):
    native = collector._native

    async def veto(payload, blocked):
        result = await native(payload, blocked)
        garden_motion_privacy.invalidate()
        return result

    monkeypatch.setattr(collector, "_native", veto)
    await collector.scan_once()
    async with get_db() as db:
        assert await GardenRepository(db).count("pending") == 0


@pytest.mark.asyncio
async def test_known_person_prevents_download_and_worker(collector, monkeypatch):
    from app.services.garden_motion import frigate_client

    monkeypatch.setattr(frigate_client, "list_events", AsyncMock(return_value=[{"start_time": 1.0, "end_time": None}]))
    native = AsyncMock()
    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    native.assert_not_awaited()
    assert collector.last_outcome == "person_rejected"


@pytest.mark.asyncio
async def test_full_photo_budget_prevents_repeated_native_work(collector, monkeypatch):
    monkeypatch.setattr("app.repositories.garden_repository.MOTION_PHOTO_LIMIT", 0)
    native = AsyncMock()
    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    native.assert_not_awaited()
    assert collector.last_outcome == "storage_full"


@pytest.mark.asyncio
async def test_verified_install_is_idempotent_and_returns_unlocked_status(collector):
    status = await collector.install()
    assert status.installed and not status.busy


@pytest.mark.asyncio
async def test_person_history_check_includes_bounded_keyframe_padding(collector, monkeypatch):
    from app.services.garden_motion import frigate_client

    people = AsyncMock(return_value=[{"start_time": 96.0, "end_time": 98.0}])
    monkeypatch.setattr(frigate_client, "list_events", people)
    assert await collector._person_overlap("patio", 100.0, 110.0)
    assert people.call_args.kwargs["before"] == 115.0


@pytest.mark.asyncio
async def test_camera_pressure_or_cleanup_quarantine_stops_collection(collector, monkeypatch):
    native = AsyncMock()
    monkeypatch.setattr(collector, "_native", native)
    monkeypatch.setattr(
        "app.services.garden_motion.frigate_client.get", AsyncMock(return_value=httpx.Response(200, json={}))
    )
    await collector.scan_once()
    native.assert_not_awaited()
    monkeypatch.setattr(garden_identification_service, "error", "Garden worker did not stop")
    await collector.scan_once()
    native.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_service_drains_worker_before_returning(collector, monkeypatch):
    import asyncio

    entered, cleaned = asyncio.Event(), asyncio.Event()

    async def native(payload, blocked):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cleaned.set()

    monkeypatch.setattr(collector, "_native", native)
    await collector.start()
    await asyncio.wait_for(entered.wait(), 3)
    await collector.stop()
    assert cleaned.is_set()
    assert not garden_identification_service.busy


@pytest.mark.asyncio
async def test_queue_drains_long_recording_and_restart_resumes_durable_cursor(collector, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 2000.0)
    requests = []

    async def get(path, **kwargs):
        if path == "api/stats":
            payload = {"cameras": {"patio": {"camera_fps": 10, "process_fps": 10, "skipped_fps": 0}}}
        else:
            requests.append(kwargs["params"])
            payload = [{"start_time": 1900, "end_time": 1930, "motion": 10}]
        return httpx.Response(200, json=payload, request=httpx.Request("GET", "http://frigate/"))

    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", get)
    native = AsyncMock(return_value={"outcome": "no_candidate"})
    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    assert collector.next_scan == 105
    assert (await collector.status()).queued_windows == 2
    await collector.scan_once()
    assert native.await_count == 1
    clock[0] = 111
    await collector.scan_once()
    assert native.await_count == 2
    # Restart loses ephemeral scheduling state, but not the recording cursor.
    restarted = GardenMotionService()
    restarted.path = collector.path
    restarted.catalog = collector.catalog
    monkeypatch.setattr(restarted, "_native", native)
    await restarted.scan_once()
    assert native.await_count == 3
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("patio") == 1930
        assert await GardenRepository(db).count("pending") == 0
    assert requests == [
        {"after": 1400, "before": 1980},
        {"after": 1910, "before": 1980},
        {"after": 1920, "before": 1980},
    ]


@pytest.mark.asyncio
async def test_successful_scan_processing_time_does_not_add_to_the_minimum_start_interval(collector, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: clock[0])

    async def native(payload, blocked):
        clock[0] += 1.5
        return {"outcome": "no_candidate"}

    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    assert collector.last_outcome == "no_candidate"
    assert collector.next_scan == 110
    clock[0] = 109.9
    collector.last_outcome = "unchanged"
    await collector.scan_once()
    assert collector.last_outcome == "unchanged"
    clock[0] = 110
    await collector.scan_once()
    assert collector.last_outcome == "no_recording"
    assert collector.next_scan == 120


@pytest.mark.asyncio
@pytest.mark.parametrize("processing_seconds", [1.5, 12])
@pytest.mark.parametrize("interval", [5, 10])
async def test_collector_loop_preserves_start_cadence_and_leaves_rest_after_slow_scans(
    collector, monkeypatch, processing_seconds, interval
):
    import asyncio

    clock, starts, sleeps = [100.0], [], []
    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: clock[0])

    async def scan():
        starts.append(clock[0])
        clock[0] += processing_seconds
        collector.interval_seconds = interval
        collector.next_scan = max(starts[-1] + interval, clock[0])

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay
        if len(sleeps) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(collector, "scan_once", scan)
    monkeypatch.setattr(
        "app.services.garden_motion.asyncio", SimpleNamespace(sleep=sleep, CancelledError=asyncio.CancelledError)
    )
    with pytest.raises(asyncio.CancelledError):
        await collector._run()
    rest = max(1, interval - processing_seconds)
    spacing = processing_seconds + rest
    assert starts == [100, 100 + spacing, 100 + 2 * spacing]
    assert sleeps == [rest] * 3


@pytest.mark.asyncio
async def test_failed_scan_backoff_starts_after_processing_finishes(collector, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: clock[0])

    async def native(payload, blocked):
        clock[0] += 1.5
        raise ValueError("Invalid clip")

    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    assert collector.last_outcome == "failed"
    assert collector.next_scan == 131.5


@pytest.mark.asyncio
async def test_preemption_keeps_window_for_retry_and_camera_round_robin_is_fair(collector, monkeypatch):
    from app.services.garden_worker_supervisor import GardenBusy

    monkeypatch.setattr(settings.frigate, "garden_cameras", ["patio", "side"])
    monkeypatch.setattr(settings.frigate, "garden_motion_cameras", ["patio", "side"])
    monkeypatch.setattr(collector, "_camera_clear", AsyncMock(return_value=True))
    calls = []
    original = collector._native

    async def native(payload, blocked):
        calls.append(payload["duration"])
        if len(calls) == 1:
            raise GardenBusy("Bird work arrived")
        return await original(payload, blocked)

    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    assert collector.last_outcome == "paused"
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("patio") is None
    collector.next_scan = 0
    await collector.scan_once()
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("side") is not None
        assert await GardenRepository(db).motion_cursor("patio") is None
    collector.next_scan = 0
    await collector.scan_once()
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("patio") is not None


@pytest.mark.asyncio
async def test_failed_window_backs_off_without_advancing_recording_cursor(collector, monkeypatch):
    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: 100.0)
    monkeypatch.setattr(collector, "_native", AsyncMock(side_effect=ValueError("Invalid clip")))
    await collector.scan_once()
    assert collector.last_outcome == "failed"
    assert collector.next_scan == 130.0
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("patio") is None


@pytest.mark.asyncio
async def test_bounded_queue_refills_without_duplicates_and_bird_arrival_preserves_cursor(collector, monkeypatch):
    from app.services.garden_motion import frigate_client

    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 2000.0)
    monkeypatch.setattr(collector, "_camera_clear", AsyncMock(return_value=True))
    monkeypatch.setattr(
        frigate_client,
        "get",
        AsyncMock(
            return_value=httpx.Response(
                200,
                json=[{"start_time": 1400.0, "end_time": 1700.0, "motion": 20}],
                request=httpx.Request("GET", "http://frigate/"),
            )
        ),
    )
    downloads = []

    async def download(camera, start, end, path):
        downloads.append((start, end))
        path.write_bytes(b"clip")

    monkeypatch.setattr(frigate_client, "download_motion_recording", download)
    native = AsyncMock(return_value={"outcome": "no_candidate"})
    monkeypatch.setattr(collector, "_native", native)
    for index in range(30):
        collector.next_scan = 0
        if index == 4:
            monkeypatch.setattr(
                "app.services.garden_motion.garden_inference_pressure",
                lambda: {"live": {"queued": 7}, "background": {}},
            )
            await collector.scan_once()
            assert native.await_count == 4
            async with get_db() as db:
                assert await GardenRepository(db).motion_cursor("patio") == 1440
            monkeypatch.setattr(
                "app.services.garden_motion.garden_inference_pressure", lambda: {"live": {}, "background": {}}
            )
        await collector.scan_once()
        status = await collector.status()
        assert 0 <= status.queued_windows <= 24
    assert downloads == [(1400 + index * 10, 1410 + index * 10) for index in range(30)]
    assert native.await_count == 30
    assert status.queued_windows == 0
    assert status.queue_camera == "patio"


@pytest.mark.asyncio
async def test_selected_animal_confidence_reaches_worker_and_saved_provenance(collector, monkeypatch):
    monkeypatch.setattr(settings.frigate, "garden_motion_confidence", 0.6)
    original = collector._native
    seen = []

    async def native(payload, blocked):
        seen.append(payload["animal_confidence"])
        return await original(payload, blocked)

    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    assert seen == [0.6]
    assert (await collector.status()).animal_confidence == 0.6
    async with get_db() as db:
        capture = (await GardenRepository(db).list("pending", 10, 0))[0]
        assert capture.motion_source.animal_confidence == 0.6


@pytest.mark.asyncio
async def test_threshold_change_during_scan_prevents_stale_proposal_or_cursor_write(collector, monkeypatch):
    monkeypatch.setattr(settings.frigate, "garden_motion_confidence", 0.5)
    original = collector._native

    async def native(payload, blocked):
        result = await original(payload, blocked)
        settings.frigate.garden_motion_confidence = 0.6
        assert blocked()
        return result

    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    assert collector.last_outcome == "paused"
    async with get_db() as db:
        repo = GardenRepository(db)
        assert await repo.count("pending") == 0
        assert await repo.motion_cursor("patio") is None


@pytest.mark.asyncio
async def test_loop_reduces_continuous_recording_backlog_and_returns_to_normal_polling(collector, monkeypatch):
    import asyncio

    clock, starts, sleeps = [100.0], [], []
    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 1900 + clock[0])
    monkeypatch.setattr(collector, "_camera_clear", AsyncMock(return_value=True))
    monkeypatch.setattr(collector, "_person_overlap", AsyncMock(return_value=True))
    monkeypatch.setattr(collector, "_native", AsyncMock(return_value={"outcome": "no_candidate"}))

    async def get(path, **kwargs):
        return httpx.Response(
            200,
            json=[{"start_time": 1950, "end_time": 1880 + clock[0], "motion": 10}],
            request=httpx.Request("GET", "http://frigate/"),
        )

    async def sleep(delay):
        starts.append(clock[0])
        sleeps.append(delay)
        clock[0] += delay
        if len(sleeps) == 7:
            raise asyncio.CancelledError

    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", get)
    monkeypatch.setattr("app.services.garden_motion.asyncio", SimpleNamespace(**{**vars(asyncio), "sleep": sleep}))
    with pytest.raises(asyncio.CancelledError):
        await collector._run()
    assert starts[:5] == [100, 105, 110, 115, 120]
    assert sleeps == [5, 5, 5, 5, 10, 10, 10]
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("patio") == 2020
        assert await GardenRepository(db).count("pending") == 0
    assert (await collector.status()).interval_seconds == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_by", ["birds", "camera", "storage"])
async def test_backlog_waits_for_pressure_without_fast_polling_or_cursor_advance(collector, monkeypatch, blocked_by):
    clock = [100.0]
    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 2000)
    monkeypatch.setattr(collector, "_camera_clear", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "app.services.garden_motion.frigate_client.get",
        AsyncMock(
            return_value=httpx.Response(
                200,
                json=[{"start_time": 1900, "end_time": 1930, "motion": 10}],
                request=httpx.Request("GET", "http://frigate/"),
            )
        ),
    )
    native = AsyncMock(return_value={"outcome": "no_candidate"})
    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    assert collector.next_scan == 105
    assert (await collector.status()).interval_seconds == 5
    clock[0] = 105
    if blocked_by == "birds":
        monkeypatch.setattr(
            "app.services.garden_motion.garden_inference_pressure", lambda: {"live": {"queued": 7}, "background": {}}
        )
    elif blocked_by == "camera":
        monkeypatch.setattr(collector, "_camera_clear", AsyncMock(return_value=False))
    else:
        monkeypatch.setattr("app.repositories.garden_repository.MOTION_PHOTO_LIMIT", 0)
    await collector.scan_once()
    native.assert_awaited_once()
    assert (await collector.status()).interval_seconds == 10
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("patio") == 1910


@pytest.mark.asyncio
async def test_housekeeping_preserves_the_selected_catchup_interval(collector, monkeypatch):
    import asyncio
    from contextlib import suppress

    collector.last_outcome = "no_candidate"
    collector.queue_camera = "patio"
    collector.queued_windows = 2
    collector.interval_seconds = 5
    entered = asyncio.Event()

    async def expire(repo):
        entered.set()
        await asyncio.Future()

    monkeypatch.setattr(GardenRepository, "expire_motion_photos", expire)
    task = asyncio.create_task(collector._run())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert (await collector.status()).interval_seconds == 5
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_scanning_more_backlog_keeps_the_selected_interval_until_the_outcome(collector, monkeypatch):
    import asyncio

    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 2000)
    monkeypatch.setattr(collector, "_camera_clear", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "app.services.garden_motion.frigate_client.get",
        AsyncMock(
            return_value=httpx.Response(
                200,
                json=[{"start_time": 1900, "end_time": 1930, "motion": 10}],
                request=httpx.Request("GET", "http://frigate/"),
            )
        ),
    )
    monkeypatch.setattr(collector, "_native", AsyncMock(return_value={"outcome": "no_candidate"}))
    await collector.scan_once()
    assert (await collector.status()).interval_seconds == 5
    collector.next_scan = 0
    entered, release = asyncio.Event(), asyncio.Event()

    async def native(payload, blocked):
        entered.set()
        await release.wait()
        return {"outcome": "no_candidate"}

    monkeypatch.setattr(collector, "_native", native)
    task = asyncio.create_task(collector.scan_once())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        status = await collector.status()
        assert status.state == "scanning"
        assert status.interval_seconds == 5
    finally:
        release.set()
        await task
    assert (await collector.status()).interval_seconds == 5


@pytest.mark.asyncio
async def test_a_still_proposal_is_recorded_as_scanned_and_stores_nothing(collector, monkeypatch):
    native = AsyncMock(return_value={"outcome": "still_rejected", "detector_score": 0.7, "motion_ratio": 0.8})
    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    assert native.await_count == 1
    assert collector.last_outcome == "still_rejected"
    assert "did not move" in collector.message
    async with get_db() as db:
        assert await GardenRepository(db).count("pending") == 0


@pytest.mark.asyncio
async def test_unreadable_recording_is_skipped_counted_and_never_retried(collector, monkeypatch):
    native = AsyncMock(return_value={"outcome": "unusable_recording", "reason": "duration_limit"})
    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    assert collector.last_outcome == "unusable_recording"
    assert "could not be read" in collector.message
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("patio") is not None
        assert await GardenRepository(db).count("pending") == 0
    status = await collector.status()
    assert [(item.camera, item.count, item.last_reason) for item in status.unreadable_recordings] == [
        ("patio", 1, "duration_limit")
    ]


@pytest.mark.asyncio
async def test_unknown_unreadable_reason_is_a_failure_not_a_skip(collector, monkeypatch):
    from app.services import garden_motion

    monkeypatch.setattr(
        collector.worker, "request", AsyncMock(return_value={"outcome": "unusable_recording", "reason": "secret"})
    )
    payload = {"model": "cedar.onnx", "model_sha256": "e" * 64}
    with pytest.raises(ValueError, match="unknown"):
        await garden_motion.GardenMotionService._native(collector, payload, lambda: False)
    assert collector.worker.request.await_args.args[0] == ("cedar.onnx", "e" * 64)


@pytest.mark.asyncio
@pytest.mark.parametrize(("exit_code", "signal_name"), [(1, None), (-11, "SIGSEGV")])
async def test_worker_failure_logs_camera_window_exit_code_and_signal(collector, monkeypatch, exit_code, signal_name):
    from app.services import garden_motion
    from app.services.garden_worker_supervisor import GardenNativeWorkerFailed

    monkeypatch.setattr(collector, "_native", AsyncMock(side_effect=GardenNativeWorkerFailed(exit_code, None)))
    warning = Mock()
    monkeypatch.setattr(garden_motion.log, "warning", warning)
    await collector.scan_once()
    assert collector.last_outcome == "failed"
    event, fields = warning.call_args.args[0], warning.call_args.kwargs
    assert event == "garden_motion_scan_failed"
    assert fields["camera"] == "patio" and fields["clip_start"] < fields["clip_end"]
    assert fields["exit_code"] == exit_code and fields["signal"] == signal_name
    assert ("SIGSEGV" in collector.message) == (signal_name is not None)
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("patio") is None


def test_unreadable_summary_counts_only_the_last_hour_on_collecting_cameras():
    from app.services.garden_motion import unreadable_summary

    skipped = [(50.0, "patio", "decode_failed"), (3000.0, "patio", "duration_limit"), (3000.0, "old", "pixel_limit")]
    summary = unreadable_summary(skipped, now=3700.0, cameras=["patio"])
    assert [(item.camera, item.count, item.last_reason) for item in summary] == [("patio", 1, "duration_limit")]


@pytest.mark.asyncio
async def test_an_oversize_recording_is_skipped_and_counted_instead_of_failing_every_retry(collector, monkeypatch):
    from app.services.frigate_client import MotionRecordingTooLarge

    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: 100.0)
    download = AsyncMock(side_effect=MotionRecordingTooLarge("Motion recording exceeds its byte limit"))
    monkeypatch.setattr("app.services.garden_motion.frigate_client.download_motion_recording", download)
    native = AsyncMock()
    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    native.assert_not_awaited()
    assert collector.last_outcome == "unusable_recording"
    # The window is skipped, not retried in thirty seconds as a failure.
    assert collector.next_scan < 130.0
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("patio") is not None
    status = await collector.status()
    assert [(item.camera, item.count, item.last_reason) for item in status.unreadable_recordings] == [
        ("patio", 1, "size_limit")
    ]


def _records_get(records, queries):
    async def get(path, **kwargs):
        if path == "api/stats":
            payload = {"cameras": {"patio": {"camera_fps": 10, "process_fps": 10, "skipped_fps": 0}}}
        else:
            queries.append(kwargs["params"])
            payload = records
        return httpx.Response(200, json=payload, request=httpx.Request("GET", "http://frigate/"))

    return get


@pytest.mark.asyncio
async def test_a_restart_skips_backlog_older_than_the_window_with_one_log_line(collector, monkeypatch):
    from app.services import garden_motion

    clock, wall = [100.0], [5000.0]
    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: wall[0])
    # Continuous motion since well before the outage; the saved cursor is at 1000.
    records = [{"start_time": float(start), "end_time": start + 10.0, "motion": 5} for start in range(1000, 4980, 10)]
    queries = []
    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", _records_get(records, queries))
    native = AsyncMock(return_value={"outcome": "no_candidate"})
    monkeypatch.setattr(collector, "_native", native)
    info = Mock()
    monkeypatch.setattr(garden_motion.log, "info", info)
    async with get_db() as db:
        await GardenRepository(db).advance_motion_cursor("patio", 1000.0)
    await collector.scan_once()
    skipped = [call for call in info.call_args_list if call.args[0] == "garden_motion_backlog_skipped"]
    assert len(skipped) == 1
    # Counted from the lookback, so one bounded request covers it.
    assert queries[0]["after"] == 1000
    assert skipped[0].kwargs["camera"] == "patio"
    assert skipped[0].kwargs["skipped_windows"] == (4400 - 1000) // 10
    assert native.await_args.args[0]["duration"] == 10
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("patio") == 4410
    # The window keeps moving while the scanner rests; a creeping skip is not logged again soon.
    clock[0], wall[0] = 160.0, 5100.0
    collector.next_scan = 0
    await collector.scan_once()
    assert len([call for call in info.call_args_list if call.args[0] == "garden_motion_backlog_skipped"]) == 1
    clock[0], wall[0] = 800.0, 5800.0
    collector.next_scan = 0
    await collector.scan_once()
    skipped = [call for call in info.call_args_list if call.args[0] == "garden_motion_backlog_skipped"]
    assert len(skipped) == 2
    assert skipped[1].kwargs["skipped_windows"] > 0


@pytest.mark.asyncio
async def test_a_first_enable_starts_at_the_window_without_reporting_skipped_footage(collector, monkeypatch):
    from app.services import garden_motion

    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 5000.0)
    records = [{"start_time": float(start), "end_time": start + 10.0, "motion": 5} for start in range(1000, 4980, 10)]
    queries = []
    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", _records_get(records, queries))
    native = AsyncMock(return_value={"outcome": "no_candidate"})
    monkeypatch.setattr(collector, "_native", native)
    info = Mock()
    monkeypatch.setattr(garden_motion.log, "info", info)
    await collector.scan_once()
    assert queries[0]["after"] == 4400
    assert not [call for call in info.call_args_list if call.args[0] == "garden_motion_backlog_skipped"]


@pytest.mark.asyncio
async def test_fast_catchup_returns_to_the_normal_interval_once_the_cycle_budget_is_spent(collector, monkeypatch):
    from app.models.garden_motion import MOTION_CATCHUP_BUDGET

    clock = [100.0]
    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 5000.0)
    records = [{"start_time": 4400.0, "end_time": 4970.0, "motion": 5}]
    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", _records_get(records, []))
    monkeypatch.setattr(collector, "_native", AsyncMock(return_value={"outcome": "no_candidate"}))
    intervals = []
    for _ in range(MOTION_CATCHUP_BUDGET + 2):
        await collector.scan_once()
        intervals.append(collector.interval_seconds)
        clock[0] = collector.next_scan
    assert intervals[: MOTION_CATCHUP_BUDGET - 1] == [5] * (MOTION_CATCHUP_BUDGET - 1)
    assert intervals[MOTION_CATCHUP_BUDGET - 1 :] == [10, 10, 10]


@pytest.mark.asyncio
async def test_a_proven_gpu_decoder_reaches_the_worker_and_software_images_send_none(collector, monkeypatch):
    seen = []
    original = collector._native

    async def native(payload, blocked):
        seen.append(payload["decode_device"])
        return await original(payload, blocked)

    monkeypatch.setattr(collector, "_native", native)
    await collector.scan_once()
    collector.decoder = MotionDecoder("vaapi", "/dev/dri/renderD128")
    collector.next_scan = 0
    async with get_db() as db:
        for table in ("garden_motion_sources", "garden_motion_cursors", "garden_captures"):
            await db.execute(f"DELETE FROM {table}")
        await db.commit()
    await collector.scan_once()
    assert seen == [None, "/dev/dri/renderD128"]


@pytest.mark.asyncio
async def test_the_decoder_is_probed_once_and_reported_when_collection_first_runs(collector, monkeypatch):
    from app.services import garden_motion

    collector.decoder = None
    probe = AsyncMock(return_value=MotionDecoder("no_render_node"))
    monkeypatch.setattr(garden_motion, "probe_motion_decoder", probe)
    warning, record = Mock(), Mock()
    monkeypatch.setattr(garden_motion.log, "warning", warning)
    monkeypatch.setattr(garden_motion.error_diagnostics_history, "record", record)
    monkeypatch.setattr(collector, "_native", AsyncMock(return_value={"outcome": "no_candidate"}))
    await collector.scan_once()
    collector.next_scan = 0
    await collector.scan_once()
    probe.assert_awaited_once()
    events = [call.args[0] for call in warning.call_args_list]
    assert events.count("garden_motion_software_decode") == 1
    assert warning.call_args_list[events.index("garden_motion_software_decode")].kwargs["state"] == "no_render_node"
    record.assert_called_once()
    assert record.call_args.kwargs["reason_code"] == "hardware_decode_no_render_node"
    assert collector.decode_health()["state"] == "no_render_node"
    assert collector.decode_health()["decoder"] == "software"


@pytest.mark.asyncio
async def test_an_image_without_the_gpu_decoder_warns_without_a_diagnostics_fault(collector, monkeypatch):
    from app.services import garden_motion

    collector.decoder = None
    monkeypatch.setattr(garden_motion, "probe_motion_decoder", AsyncMock(return_value=MotionDecoder("not_packaged")))
    warning, record = Mock(), Mock()
    monkeypatch.setattr(garden_motion.log, "warning", warning)
    monkeypatch.setattr(garden_motion.error_diagnostics_history, "record", record)
    await collector.scan_once()
    assert [call.args[0] for call in warning.call_args_list].count("garden_motion_software_decode") == 1
    record.assert_not_called()


@pytest.mark.asyncio
async def test_repeated_gpu_failures_switch_collection_to_cpu_decode_until_restart(collector, monkeypatch):
    from app.services import garden_motion
    from app.services.garden_motion import MOTION_HARDWARE_FALLBACK_LIMIT

    collector.decoder = MotionDecoder("vaapi", "/dev/dri/renderD128")
    collector.decoder_reported = True
    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 5000.0)
    records = [{"start_time": 4400.0, "end_time": 4970.0, "motion": 5}]
    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", _records_get(records, []))
    devices = []

    async def native(payload, blocked):
        devices.append(payload["decode_device"])
        # Like the worker: a result names its decoder only when the GPU was requested.
        return {"outcome": "no_candidate", **({"decoder": "software_fallback"} if payload["decode_device"] else {})}

    monkeypatch.setattr(collector, "_native", native)
    warning, record = Mock(), Mock()
    monkeypatch.setattr(garden_motion.log, "warning", warning)
    monkeypatch.setattr(garden_motion.error_diagnostics_history, "record", record)
    for _ in range(MOTION_HARDWARE_FALLBACK_LIMIT + 1):
        collector.next_scan = 0
        await collector.scan_once()
    assert devices == ["/dev/dri/renderD128"] * MOTION_HARDWARE_FALLBACK_LIMIT + [None]
    events = [call.args[0] for call in warning.call_args_list]
    # The first fallback is information; each one after it in a row is a warning.
    assert events.count("garden_motion_hardware_decode_fallback") == MOTION_HARDWARE_FALLBACK_LIMIT - 1
    assert collector.decode_health()["state"] == "decode_failed"
    assert record.call_args.kwargs["reason_code"] == "hardware_decode_decode_failed"


@pytest.mark.asyncio
async def test_a_successful_gpu_scan_clears_earlier_fallbacks(collector, monkeypatch):
    collector.decoder = MotionDecoder("vaapi", "/dev/dri/renderD128")
    collector.decoder_reported = True
    collector.hardware_fallbacks = 2
    monkeypatch.setattr(collector, "_native", AsyncMock(return_value={"outcome": "no_candidate", "decoder": "vaapi"}))
    await collector.scan_once()
    assert collector.hardware_fallbacks == 0
    assert collector.decode_health() == {
        "state": "vaapi",
        "decoder": "vaapi",
        "device": "/dev/dri/renderD128",
        "message": "Motion recordings decode on the Intel GPU (/dev/dri/renderD128).",
        "consecutive_fallbacks": 0,
        "software_cameras": [],
    }


def test_decode_health_says_when_the_decoder_has_not_been_checked():
    service = GardenMotionService()
    assert service.decode_health()["state"] == "not_checked"
    assert service.decode_health()["decoder"] is None


@pytest.mark.asyncio
async def test_an_unknown_decoder_in_a_worker_result_is_a_failure(collector, monkeypatch):
    from app.services import garden_motion

    monkeypatch.setattr(
        collector.worker, "request", AsyncMock(return_value={"outcome": "no_candidate", "decoder": "magic"})
    )
    with pytest.raises(ValueError, match="decoder"):
        await garden_motion.GardenMotionService._native(
            collector, {"model": "m", "model_sha256": "e" * 64}, lambda: False
        )


@pytest.mark.asyncio
async def test_an_unusable_recording_from_a_gpu_scan_is_skipped_not_retried(collector, monkeypatch):
    from app.services import garden_motion

    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: 100.0)
    collector.decoder = MotionDecoder("vaapi", "/dev/dri/renderD128")
    collector.decoder_reported = True
    # The worker reports an unreadable recording before decoding anything, so it names no decoder.
    monkeypatch.setattr(
        collector.worker,
        "request",
        AsyncMock(return_value={"outcome": "unusable_recording", "reason": "invalid_metadata"}),
    )
    monkeypatch.setattr(collector, "_native", garden_motion.GardenMotionService._native.__get__(collector))
    await collector.scan_once()
    assert collector.last_outcome == "unusable_recording"
    assert collector.next_scan < 130.0
    async with get_db() as db:
        assert await GardenRepository(db).motion_cursor("patio") is not None
    status = await collector.status()
    assert [(item.camera, item.count, item.last_reason) for item in status.unreadable_recordings] == [
        ("patio", 1, "invalid_metadata")
    ]


@pytest.mark.asyncio
async def test_gpu_fallbacks_that_recover_on_the_next_recording_are_counted_as_information(collector, monkeypatch):
    from app.services import garden_motion
    from app.services.error_diagnostics import ErrorDiagnosticsHistory

    history = ErrorDiagnosticsHistory()
    monkeypatch.setattr(garden_motion, "error_diagnostics_history", history)
    collector.decoder = MotionDecoder("vaapi", "/dev/dri/renderD128")
    collector.decoder_reported = True
    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 5000.0)
    records = [{"start_time": 4400.0, "end_time": 4970.0, "motion": 5}]
    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", _records_get(records, []))
    # Intermittent: never three in a row, so the decoder is never switched off.
    decoders = iter(["software_fallback", "vaapi", "software_fallback", "vaapi"])
    monkeypatch.setattr(
        collector,
        "_native",
        AsyncMock(side_effect=lambda *args: {"outcome": "no_candidate", "decoder": next(decoders)}),
    )
    for _ in range(4):
        collector.next_scan = 0
        await collector.scan_once()
    events = history.snapshot(source="garden_motion")["events"]
    fallbacks = [event for event in events if event["reason_code"] == "hardware_decode_fallback"]
    assert len(fallbacks) == 1 and fallbacks[0]["count"] == 2
    assert fallbacks[0]["severity"] == "info"
    assert fallbacks[0]["context"] == {"camera": "patio"}
    assert [event for event in events if event["severity"] != "info"] == []
    assert collector.decode_health()["state"] == "vaapi"


@pytest.mark.asyncio
async def test_a_gpu_that_falls_back_on_every_other_recording_is_a_warning(collector, monkeypatch):
    """Never two in a row, so the consecutive rule never fires, but half the recordings fail."""
    from app.services import garden_motion
    from app.services.error_diagnostics import ErrorDiagnosticsHistory
    from app.services.garden_motion import MOTION_HARDWARE_FALLBACK_RATE_COUNT

    history = ErrorDiagnosticsHistory()
    monkeypatch.setattr(garden_motion, "error_diagnostics_history", history)
    collector.decoder = MotionDecoder("vaapi", "/dev/dri/renderD128")
    collector.decoder_reported = True
    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 5000.0)
    records = [{"start_time": 4400.0, "end_time": 4970.0, "motion": 5}]
    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", _records_get(records, []))
    scans = 2 * MOTION_HARDWARE_FALLBACK_RATE_COUNT - 1
    decoders = iter(["software_fallback", "vaapi"] * MOTION_HARDWARE_FALLBACK_RATE_COUNT)
    monkeypatch.setattr(
        collector,
        "_native",
        AsyncMock(side_effect=lambda *args: {"outcome": "no_candidate", "decoder": next(decoders)}),
    )
    for _ in range(scans):
        collector.next_scan = 0
        await collector.scan_once()
    warnings = [event for event in history.snapshot(source="garden_motion")["events"] if event["severity"] != "info"]
    assert [(event["reason_code"], event["severity"]) for event in warnings] == [
        ("hardware_decode_fallback_frequent", "warning")
    ]
    assert warnings[0]["context"]["fallbacks"] == MOTION_HARDWARE_FALLBACK_RATE_COUNT
    # The consecutive rule never fired, so GPU decode stays on; Health's CPU state is unchanged.
    assert collector.decode_health()["state"] == "vaapi"


@pytest.mark.asyncio
async def test_a_gpu_fallback_that_repeats_on_the_next_recording_is_a_warning(collector, monkeypatch):
    from app.services import garden_motion
    from app.services.error_diagnostics import ErrorDiagnosticsHistory
    from app.services.garden_motion import MOTION_HARDWARE_FALLBACK_WARN_AFTER

    history = ErrorDiagnosticsHistory()
    monkeypatch.setattr(garden_motion, "error_diagnostics_history", history)
    collector.decoder = MotionDecoder("vaapi", "/dev/dri/renderD128")
    collector.decoder_reported = True
    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 5000.0)
    records = [{"start_time": 4400.0, "end_time": 4970.0, "motion": 5}]
    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", _records_get(records, []))
    monkeypatch.setattr(
        collector, "_native", AsyncMock(return_value={"outcome": "no_candidate", "decoder": "software_fallback"})
    )
    for _ in range(MOTION_HARDWARE_FALLBACK_WARN_AFTER):
        collector.next_scan = 0
        await collector.scan_once()
    warnings = [event for event in history.snapshot(source="garden_motion")["events"] if event["severity"] != "info"]
    assert [(event["reason_code"], event["severity"]) for event in warnings] == [
        ("hardware_decode_fallback_repeated", "warning")
    ]
    assert warnings[0]["context"] == {"camera": "patio", "consecutive": MOTION_HARDWARE_FALLBACK_WARN_AFTER}
    # Still on the GPU until the switch-off limit; the Health card keeps saying so.
    assert collector.decode_health()["state"] == "vaapi"


@pytest.mark.asyncio
async def test_person_rejected_windows_spend_the_catchup_budget_too(collector, monkeypatch):
    from app.models.garden_motion import MOTION_CATCHUP_BUDGET
    from app.services.garden_motion import frigate_client

    clock = [100.0]
    monkeypatch.setattr("app.services.garden_motion.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 5000.0)
    records = [{"start_time": 4400.0, "end_time": 4970.0, "motion": 5}]
    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", _records_get(records, []))
    monkeypatch.setattr(frigate_client, "list_events", AsyncMock(return_value=[{"start_time": 1.0, "end_time": None}]))
    native = AsyncMock()
    monkeypatch.setattr(collector, "_native", native)
    intervals = []
    for _ in range(MOTION_CATCHUP_BUDGET + 2):
        await collector.scan_once()
        assert collector.last_outcome == "person_rejected"
        intervals.append(collector.interval_seconds)
        clock[0] = collector.next_scan
    native.assert_not_awaited()
    assert intervals[: MOTION_CATCHUP_BUDGET - 1] == [5] * (MOTION_CATCHUP_BUDGET - 1)
    assert intervals[MOTION_CATCHUP_BUDGET - 1 :] == [10, 10, 10]


@pytest.mark.asyncio
async def test_a_recording_decoded_in_software_by_design_does_not_count_against_the_gpu(collector, monkeypatch):
    from app.services import garden_motion

    collector.decoder = MotionDecoder("vaapi", "/dev/dri/renderD128")
    collector.decoder_reported = True
    collector.hardware_fallbacks = 2
    record = Mock()
    monkeypatch.setattr(garden_motion.error_diagnostics_history, "record", record)
    monkeypatch.setattr(
        collector.worker, "request", AsyncMock(return_value={"outcome": "no_candidate", "decoder": "software"})
    )
    monkeypatch.setattr(collector, "_native", garden_motion.GardenMotionService._native.__get__(collector))
    await collector.scan_once()
    assert collector.last_outcome == "no_candidate"
    assert collector.hardware_fallbacks == 2 and collector.decode_health()["state"] == "vaapi"
    record.assert_not_called()


@pytest.mark.asyncio
async def test_a_camera_that_always_decodes_in_software_is_said_once_and_shown_in_health(collector, monkeypatch):
    from app.services import garden_motion

    collector.decoder = MotionDecoder("vaapi", "/dev/dri/renderD128")
    collector.decoder_reported = True
    monkeypatch.setattr("app.services.garden_motion.time.time", lambda: 5000.0)
    records = [{"start_time": 4400.0, "end_time": 4970.0, "motion": 5}]
    monkeypatch.setattr("app.services.garden_motion.frigate_client.get", _records_get(records, []))
    monkeypatch.setattr(
        collector, "_native", AsyncMock(return_value={"outcome": "no_candidate", "decoder": "software"})
    )
    info = Mock()
    monkeypatch.setattr(garden_motion.log, "info", info)
    for _ in range(3):
        collector.next_scan = 0
        await collector.scan_once()
    lines = [call for call in info.call_args_list if call.args[0] == "garden_motion_camera_decodes_in_software"]
    assert len(lines) == 1 and lines[0].kwargs["camera"] == "patio"
    health = collector.decode_health()
    assert health["state"] == "vaapi" and health["software_cameras"] == ["patio"]
