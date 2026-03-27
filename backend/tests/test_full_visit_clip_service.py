import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.full_visit_clip_service import FullVisitClipService


@pytest.mark.asyncio
async def test_trigger_for_event_noops_when_recording_clips_disabled():
    service = FullVisitClipService()

    with patch("app.services.full_visit_clip_service.settings.frigate.clips_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.frigate.recording_clip_enabled", False, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.cache_clips", True, create=True), \
         patch.object(service, "_fetch_once", new=AsyncMock(return_value=True)) as mock_fetch:
        ready = await service.trigger_for_event("evt-disabled", "cam1")

    assert ready is False
    mock_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_for_event_noops_when_recording_clip_already_cached():
    service = FullVisitClipService()

    with patch("app.services.full_visit_clip_service.settings.frigate.clips_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.frigate.recording_clip_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.cache_clips", True, create=True), \
         patch("app.services.full_visit_clip_service.media_cache.get_recording_clip_path", return_value=Path("/tmp/existing_recording.mp4")), \
         patch.object(service, "_fetch_once", new=AsyncMock(return_value=True)) as mock_fetch:
        ready = await service.trigger_for_event("evt-cached", "cam1")

    assert ready is True
    mock_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_for_event_fetches_and_persists_recording_clip():
    service = FullVisitClipService()

    async def async_iter_bytes():
        yield b"0" * 1024

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "video/mp4", "content-length": "1024"}
    mock_response.aiter_bytes = async_iter_bytes
    mock_response.aclose = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.build_request = MagicMock()
    mock_client.send = AsyncMock(return_value=mock_response)
    mock_client.aclose = AsyncMock()

    with patch("app.services.full_visit_clip_service.settings.frigate.clips_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.frigate.recording_clip_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.cache_clips", True, create=True), \
         patch("app.services.full_visit_clip_service.media_cache.get_recording_clip_path", return_value=None), \
         patch("app.services.full_visit_clip_service.media_cache.cache_recording_clip_streaming", new=AsyncMock(return_value=Path("/tmp/evt-ready_recording.mp4"))) as mock_cache, \
         patch("app.services.full_visit_clip_service._get_recording_clip_context", new=AsyncMock(return_value=("front_feeder", 1700000000, 1700000120))), \
         patch("app.services.full_visit_clip_service.httpx.AsyncClient", return_value=mock_client), \
         patch("app.services.full_visit_clip_service.frigate_client") as mock_frigate:
        mock_frigate.get_camera_recording_clip_url = MagicMock(
            return_value="http://frigate/api/front_feeder/start/1700000000/end/1700000120/clip.mp4"
        )
        mock_frigate._get_headers = MagicMock(return_value={})

        ready = await service.trigger_for_event("evt-ready", "cam1")

    assert ready is True
    mock_cache.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_for_event_persists_recording_clip_even_when_regular_clip_caching_disabled():
    service = FullVisitClipService()

    async def async_iter_bytes():
        yield b"0" * 1024

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "video/mp4", "content-length": "1024"}
    mock_response.aiter_bytes = async_iter_bytes
    mock_response.aclose = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.build_request = MagicMock()
    mock_client.send = AsyncMock(return_value=mock_response)
    mock_client.aclose = AsyncMock()

    with patch("app.services.full_visit_clip_service.settings.frigate.clips_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.frigate.recording_clip_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.cache_clips", False, create=True), \
         patch("app.services.full_visit_clip_service.media_cache.get_recording_clip_path", return_value=None), \
         patch("app.services.full_visit_clip_service.media_cache.cache_recording_clip_streaming", new=AsyncMock(return_value=Path("/tmp/evt-ready_recording.mp4"))) as mock_cache, \
         patch("app.services.full_visit_clip_service._get_recording_clip_context", new=AsyncMock(return_value=("front_feeder", 1700000000, 1700000120))), \
         patch("app.services.full_visit_clip_service.httpx.AsyncClient", return_value=mock_client), \
         patch("app.services.full_visit_clip_service.frigate_client") as mock_frigate:
        mock_frigate.get_camera_recording_clip_url = MagicMock(
            return_value="http://frigate/api/front_feeder/start/1700000000/end/1700000120/clip.mp4"
        )
        mock_frigate._get_headers = MagicMock(return_value={})

        ready = await service.trigger_for_event("evt-ready", "cam1")

    assert ready is True
    mock_cache.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_for_event_retries_temporary_unavailability():
    service = FullVisitClipService()

    with patch("app.services.full_visit_clip_service.settings.frigate.clips_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.frigate.recording_clip_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.cache_clips", True, create=True), \
         patch("app.services.full_visit_clip_service.media_cache.get_recording_clip_path", return_value=None), \
         patch.object(service, "_fetch_once", new=AsyncMock(side_effect=[False, True])) as mock_fetch, \
         patch("app.services.full_visit_clip_service.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        ready = await service.trigger_for_event("evt-retry", "cam1")

    assert ready is True
    assert mock_fetch.await_count == 2
    mock_sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_for_event_throttles_repeat_failures_until_cooldown_expires():
    service = FullVisitClipService()

    with patch("app.services.full_visit_clip_service.settings.frigate.clips_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.frigate.recording_clip_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.cache_clips", True, create=True), \
         patch("app.services.full_visit_clip_service.media_cache.get_recording_clip_path", return_value=None), \
         patch.object(service, "_fetch_once", new=AsyncMock(return_value=False)) as mock_fetch, \
         patch("app.services.full_visit_clip_service.time.time", side_effect=[100.0, 100.0, 100.0, 101.0, 101.0, 4000.0, 4000.0]), \
         patch("app.services.full_visit_clip_service.asyncio.sleep", new=AsyncMock()):
        first = await service.trigger_for_event("evt-cooldown", "cam1", source="reconcile")
        second = await service.trigger_for_event("evt-cooldown", "cam1", source="reconcile")

    assert first is False
    assert second is False
    assert mock_fetch.await_count == 2


@pytest.mark.asyncio
async def test_trigger_for_event_uses_single_flight_lock_per_event():
    service = FullVisitClipService()
    state = {"ready": False}

    def get_recording_clip_path(_event_id: str):
        return Path("/tmp/evt-lock_recording.mp4") if state["ready"] else None

    async def fetch_once(_event_id: str, _lang: str) -> bool:
        await asyncio.sleep(0.01)
        state["ready"] = True
        return True

    with patch("app.services.full_visit_clip_service.settings.frigate.clips_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.frigate.recording_clip_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.cache_clips", True, create=True), \
         patch("app.services.full_visit_clip_service.media_cache.get_recording_clip_path", side_effect=get_recording_clip_path), \
         patch.object(service, "_fetch_once", new=AsyncMock(side_effect=fetch_once)) as mock_fetch:
        results = await asyncio.gather(
            service.trigger_for_event("evt-lock", "cam1"),
            service.trigger_for_event("evt-lock", "cam1"),
        )

    assert results == [True, True]
    assert mock_fetch.await_count == 1


@pytest.mark.asyncio
async def test_reconcile_recent_detections_triggers_missing_recent_candidates():
    service = FullVisitClipService()
    candidate = SimpleNamespace(frigate_event="evt-reconcile-1", camera_name="cam1")

    db_ctx = AsyncMock()
    db_ctx.__aenter__.return_value = object()
    db_ctx.__aexit__.return_value = False

    with patch("app.services.full_visit_clip_service.settings.frigate.clips_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.frigate.recording_clip_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.frigate.recording_clip_after_seconds", 90, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.cache_clips", True, create=True), \
         patch("app.services.full_visit_clip_service.get_db", return_value=db_ctx), \
         patch("app.services.full_visit_clip_service.DetectionRepository") as MockRepo, \
         patch("app.services.full_visit_clip_service.media_cache.get_recording_clip_path", return_value=None), \
         patch.object(service, "trigger_for_event", new=AsyncMock(return_value=True)) as mock_trigger:
        MockRepo.return_value.get_recent_full_visit_candidates = AsyncMock(return_value=[candidate])

        generated = await service.reconcile_recent_detections()

    assert generated == 1
    mock_trigger.assert_awaited_once_with("evt-reconcile-1", "cam1", source="reconcile", lang="en")


@pytest.mark.asyncio
async def test_reconcile_recent_detections_skips_candidates_with_persisted_recording_clip():
    service = FullVisitClipService()
    candidate = SimpleNamespace(frigate_event="evt-reconcile-skip", camera_name="cam1")

    db_ctx = AsyncMock()
    db_ctx.__aenter__.return_value = object()
    db_ctx.__aexit__.return_value = False

    with patch("app.services.full_visit_clip_service.settings.frigate.clips_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.frigate.recording_clip_enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.frigate.recording_clip_after_seconds", 90, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.enabled", True, create=True), \
         patch("app.services.full_visit_clip_service.settings.media_cache.cache_clips", True, create=True), \
         patch("app.services.full_visit_clip_service.get_db", return_value=db_ctx), \
         patch("app.services.full_visit_clip_service.DetectionRepository") as MockRepo, \
         patch("app.services.full_visit_clip_service.media_cache.get_recording_clip_path", return_value=Path("/tmp/already_recording.mp4")), \
         patch.object(service, "trigger_for_event", new=AsyncMock(return_value=True)) as mock_trigger:
        MockRepo.return_value.get_recent_full_visit_candidates = AsyncMock(return_value=[candidate])

        generated = await service.reconcile_recent_detections()

    assert generated == 0
    mock_trigger.assert_not_awaited()
