import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from app.config import settings
from app.services import high_quality_snapshot_service as hq_module
from app.services import media_cache as media_cache_module


def _make_cache_service(tmp_path, monkeypatch):
    cache_base = tmp_path / "media_cache"
    snapshots = cache_base / "snapshots"
    clips = cache_base / "clips"
    previews = cache_base / "previews"
    snapshots.mkdir(parents=True, exist_ok=True)
    clips.mkdir(parents=True, exist_ok=True)
    previews.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(media_cache_module, "CACHE_BASE_DIR", cache_base)
    monkeypatch.setattr(media_cache_module, "SNAPSHOTS_DIR", snapshots)
    monkeypatch.setattr(media_cache_module, "CLIPS_DIR", clips)
    monkeypatch.setattr(media_cache_module, "PREVIEWS_DIR", previews)
    service = media_cache_module.MediaCacheService()
    monkeypatch.setattr(hq_module, "media_cache", service)
    return service


@pytest_asyncio.fixture(autouse=True)
async def reset_high_quality_snapshot_service_state():
    await hq_module.high_quality_snapshot_service.reset_state()
    yield
    await hq_module.high_quality_snapshot_service.reset_state()


@pytest.mark.asyncio
async def test_schedule_snapshot_replacement_skips_when_feature_disabled(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_disabled", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = False

    queued = hq_module.high_quality_snapshot_service.schedule_replacement("evt_disabled")

    assert queued is False
    assert await cache_service.get_snapshot("evt_disabled") == b"frigate-bytes"


@pytest.mark.asyncio
async def test_schedule_snapshot_replacement_accepts_recording_clip_only_mode(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_recording_only", b"frigate-bytes")
    monkeypatch.setattr(settings.media_cache, "high_quality_event_snapshots", True, raising=False)
    monkeypatch.setattr(settings.frigate, "clips_enabled", False, raising=False)
    monkeypatch.setattr(settings.frigate, "recording_clip_enabled", True, raising=False)

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)

    queued = hq_module.high_quality_snapshot_service.schedule_replacement("evt_recording_only")

    assert queued is True
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["enabled"] is True
    assert status["queue_size"] == 1


@pytest.mark.asyncio
async def test_process_event_replaces_cached_snapshot_with_clip_frame(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_replace", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_replace"
        return b"clip-bytes", None

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_wait_for_clip",
        fake_wait_for_clip,
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes: b"derived-bytes",
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_replace")

    assert result == "replaced"
    assert await cache_service.get_snapshot("evt_replace") == b"derived-bytes"


@pytest.mark.asyncio
async def test_process_event_falls_back_to_cached_recording_clip_when_event_clip_missing(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_recording_fallback", b"frigate-bytes")
    await cache_service.cache_recording_clip("evt_recording_fallback", b"r" * 1024)
    settings.media_cache.high_quality_event_snapshots = True
    settings.frigate.recording_clip_enabled = True

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_recording_fallback"
        return None, "clip_not_found"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_wait_for_clip",
        fake_wait_for_clip,
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes: b"derived-from-recording:" + clip_bytes,
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_recording_fallback")

    assert result == "replaced"
    assert await cache_service.get_snapshot("evt_recording_fallback") == b"derived-from-recording:" + (b"r" * 1024)


@pytest.mark.asyncio
async def test_schedule_snapshot_replacement_ignores_duplicates(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_duplicate", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_process_event(event_id: str):
        assert event_id == "evt_duplicate"
        started.set()
        await release.wait()
        return "replaced"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "process_event",
        fake_process_event,
    )

    first = hq_module.high_quality_snapshot_service.schedule_replacement("evt_duplicate")
    await asyncio.wait_for(started.wait(), timeout=1.0)
    second = hq_module.high_quality_snapshot_service.schedule_replacement("evt_duplicate")
    release.set()
    await hq_module.high_quality_snapshot_service.wait_for_idle()

    assert first is True
    assert second is False
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["scheduled_total"] == 1
    assert status["duplicate_requests"] == 1


@pytest.mark.asyncio
async def test_schedule_snapshot_replacement_defers_when_queue_full(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt-queue-1", b"frigate-bytes")
    await cache_service.cache_snapshot("evt-queue-2", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "MAX_PENDING_QUEUE", 1, raising=False)
    await hq_module.high_quality_snapshot_service.reset_state()
    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)

    first = hq_module.high_quality_snapshot_service.schedule_replacement("evt-queue-1")
    second = hq_module.high_quality_snapshot_service.schedule_replacement("evt-queue-2")

    assert first is True
    assert second is True
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["queue_size"] == 1
    assert status["deferred"] == 1
    assert status["queue_full_rejections"] == 0
    assert status["queue_full_deferrals"] == 1


@pytest.mark.asyncio
async def test_deferred_snapshot_replacements_drain_after_capacity_frees(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt-drain-1", b"frigate-bytes")
    await cache_service.cache_snapshot("evt-drain-2", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "MAX_PENDING_QUEUE", 1, raising=False)
    await hq_module.high_quality_snapshot_service.reset_state()
    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)

    processed: list[str] = []

    async def fake_process_event(event_id: str):
        processed.append(event_id)
        return "replaced"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "process_event",
        fake_process_event,
    )

    assert hq_module.high_quality_snapshot_service.schedule_replacement("evt-drain-1") is True
    assert hq_module.high_quality_snapshot_service.schedule_replacement("evt-drain-2") is True

    worker_task = asyncio.create_task(hq_module.high_quality_snapshot_service._worker_loop(0))
    await asyncio.wait_for(hq_module.high_quality_snapshot_service.wait_for_idle(), timeout=1.0)
    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert processed == ["evt-drain-1", "evt-drain-2"]
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["queue_size"] == 0
    assert status["deferred"] == 0
    assert status["queue_full_deferrals"] == 1


@pytest.mark.asyncio
async def test_high_quality_snapshot_service_status_tracks_outcomes(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_status", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    async def fake_wait_for_clip(event_id: str):
        assert event_id == "evt_status"
        return b"clip-bytes", None

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_wait_for_clip",
        fake_wait_for_clip,
    )
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes: b"derived-bytes",
    )

    result = await hq_module.high_quality_snapshot_service.process_event("evt_status")

    assert result == "replaced"
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["enabled"] is True
    assert status["active"] == 0
    assert status["outcomes"]["replaced"] == 1
    assert status["last_result"] == {"event_id": "evt_status", "result": "replaced"}


@pytest.mark.asyncio
async def test_replace_from_clip_bytes_replaces_cached_snapshot_when_enabled(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_bytes", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes: b"derived-bytes",
    )

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_bytes("evt_clip_bytes", b"clip-bytes")

    assert result == "replaced"
    assert await cache_service.get_snapshot("evt_clip_bytes") == b"derived-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_bytes_is_disabled_when_feature_flag_off(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_disabled", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = False

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes: b"derived-bytes",
    )

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_bytes("evt_clip_disabled", b"clip-bytes")

    assert result == "disabled"
    assert await cache_service.get_snapshot("evt_clip_disabled") == b"frigate-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_bytes_preserves_original_on_extraction_failure(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_failure", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    def _boom(_clip_bytes):
        raise ValueError("bad clip")

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        _boom,
    )

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_bytes("evt_clip_failure", b"clip-bytes")

    assert result == "frame_extract_failed"
    assert await cache_service.get_snapshot("evt_clip_failure") == b"frigate-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_bytes_satisfies_queued_event_without_duplicate_worker_processing(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_queued", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes: b"derived-bytes",
    )

    worker_processed = asyncio.Event()

    async def fake_process_event(event_id: str):
        worker_processed.set()
        return "replaced"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "process_event",
        fake_process_event,
    )

    queued = hq_module.high_quality_snapshot_service.schedule_replacement("evt_clip_queued")
    assert queued is True

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_bytes("evt_clip_queued", b"clip-bytes")
    assert result == "replaced"

    worker_task = asyncio.create_task(hq_module.high_quality_snapshot_service._worker_loop(0))
    await asyncio.sleep(0.05)
    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert worker_processed.is_set() is False
    assert await cache_service.get_snapshot("evt_clip_queued") == b"derived-bytes"


@pytest.mark.asyncio
async def test_replace_from_clip_bytes_satisfies_deferred_event_without_later_worker_processing(tmp_path, monkeypatch):
    cache_service = _make_cache_service(tmp_path, monkeypatch)
    await cache_service.cache_snapshot("evt_clip_deferred_1", b"frigate-bytes")
    await cache_service.cache_snapshot("evt_clip_deferred_2", b"frigate-bytes")
    settings.media_cache.high_quality_event_snapshots = True

    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "MAX_PENDING_QUEUE", 1, raising=False)
    await hq_module.high_quality_snapshot_service.reset_state()
    monkeypatch.setattr(hq_module.high_quality_snapshot_service, "_ensure_workers_started", lambda: None)
    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "_extract_snapshot_from_clip",
        lambda clip_bytes: b"derived-bytes",
    )

    worker_processed: list[str] = []

    async def fake_process_event(event_id: str):
        worker_processed.append(event_id)
        return "replaced"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "process_event",
        fake_process_event,
    )

    assert hq_module.high_quality_snapshot_service.schedule_replacement("evt_clip_deferred_1") is True
    assert hq_module.high_quality_snapshot_service.schedule_replacement("evt_clip_deferred_2") is True

    result = await hq_module.high_quality_snapshot_service.replace_from_clip_bytes("evt_clip_deferred_2", b"clip-bytes")
    assert result == "replaced"

    worker_task = asyncio.create_task(hq_module.high_quality_snapshot_service._worker_loop(0))
    await asyncio.wait_for(hq_module.high_quality_snapshot_service.wait_for_idle(), timeout=1.0)
    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert worker_processed == ["evt_clip_deferred_1"]
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["duplicate_requests"] >= 1
    assert status["deferred"] == 0


def test_extract_snapshot_from_clip_uses_configured_jpeg_quality(monkeypatch):
    original_quality = settings.media_cache.high_quality_event_snapshot_jpeg_quality
    settings.media_cache.high_quality_event_snapshot_jpeg_quality = 82

    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.get.return_value = 1
    cap.read.return_value = (True, object())
    encoded = MagicMock()
    encoded.tobytes.return_value = b"jpeg-bytes"
    imencode = MagicMock(return_value=(True, encoded))

    try:
        monkeypatch.setattr(hq_module.cv2, "VideoCapture", lambda _path: cap)
        monkeypatch.setattr(hq_module.cv2, "imencode", imencode)

        result = hq_module.high_quality_snapshot_service._extract_snapshot_from_clip_path(Path("/tmp/demo.mp4"))

        assert result == b"jpeg-bytes"
        imencode.assert_called_once_with(
            ".jpg",
            cap.read.return_value[1],
            [int(hq_module.cv2.IMWRITE_JPEG_QUALITY), 82],
        )
    finally:
        settings.media_cache.high_quality_event_snapshot_jpeg_quality = original_quality


@pytest.mark.asyncio
async def test_stop_ignores_worker_tasks_from_closed_event_loop(tmp_path, monkeypatch):
    _make_cache_service(tmp_path, monkeypatch)

    class _ClosedLoopTask:
        def __init__(self):
            self._loop = asyncio.new_event_loop()
            self._loop.close()

        def done(self):
            return False

        def get_loop(self):
            return self._loop

        def cancel(self):
            raise RuntimeError("cancel should not be called for closed-loop task")

    hq_module.high_quality_snapshot_service._worker_tasks = [_ClosedLoopTask()]  # type: ignore[list-item]

    await hq_module.high_quality_snapshot_service.stop()

    assert hq_module.high_quality_snapshot_service.get_status()["workers"] == 0


@pytest.mark.asyncio
async def test_worker_loop_tracks_task_done_against_original_queue_when_service_queue_replaced(tmp_path, monkeypatch):
    _make_cache_service(tmp_path, monkeypatch)
    settings.media_cache.high_quality_event_snapshots = True

    original_queue = asyncio.Queue()
    await original_queue.put("evt_queue_swap")
    hq_module.high_quality_snapshot_service._pending_queue = original_queue

    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_process_event(event_id: str):
        assert event_id == "evt_queue_swap"
        started.set()
        await release.wait()
        return "replaced"

    monkeypatch.setattr(
        hq_module.high_quality_snapshot_service,
        "process_event",
        fake_process_event,
    )

    worker_task = asyncio.create_task(hq_module.high_quality_snapshot_service._worker_loop(0))
    await asyncio.wait_for(started.wait(), timeout=1.0)

    replacement_queue = asyncio.Queue()
    hq_module.high_quality_snapshot_service._pending_queue = replacement_queue

    worker_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await worker_task

    assert original_queue.qsize() == 0
    assert original_queue._unfinished_tasks == 0
    assert replacement_queue.qsize() == 0
    assert replacement_queue._unfinished_tasks == 0
