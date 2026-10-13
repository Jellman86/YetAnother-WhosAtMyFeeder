"""Motion work is opt-in, serial, preemptible, and private until published."""

import hashlib
import time
from unittest.mock import AsyncMock

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
