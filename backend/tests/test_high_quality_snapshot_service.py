import asyncio

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
async def test_schedule_snapshot_replacement_rejects_when_queue_full(tmp_path, monkeypatch):
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
    assert second is False
    status = hq_module.high_quality_snapshot_service.get_status()
    assert status["queue_size"] == 1
    assert status["queue_full_rejections"] == 1


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
