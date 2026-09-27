from datetime import datetime
from types import SimpleNamespace

import pytest


class _FakeDbContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeMaintenanceCoordinator:
    def __init__(self):
        self.acquired = False
        self.released = False

    async def try_acquire(self, holder_id, *, kind):
        self.acquired = True
        return True

    async def release(self, holder_id):
        self.released = True


def _unknowns(count: int):
    return [
        SimpleNamespace(
            frigate_event=f"event-{idx}",
            camera_name="birdfeeder",
            detection_time=datetime(2026, 4, 29, 12, 0, 0),
        )
        for idx in range(count)
    ]


@pytest.mark.asyncio
async def test_run_analyze_unknowns_limits_candidate_scan_window(monkeypatch):
    from app.routers import settings as settings_router

    fake_coordinator = _FakeMaintenanceCoordinator()
    captured: dict[str, int | None] = {}

    class _FakeRepo:
        def __init__(self, db):
            pass

        async def get_unknown_detections(self, *, limit=None):
            captured["limit"] = limit
            return _unknowns(3)

        async def update_video_status(self, frigate_event, status, error=None):
            raise AssertionError("all fixture detections should be eligible")

    async def _get_config():
        return {}

    async def _get_event_with_error(event_id, timeout):
        return ({"has_clip": True}, None)

    async def _queue_classification(event_id, camera, **kwargs):
        return "queued"

    monkeypatch.setattr(settings_router, "get_db", lambda: _FakeDbContext())
    monkeypatch.setattr(settings_router, "DetectionRepository", _FakeRepo)
    monkeypatch.setattr(settings_router, "maintenance_coordinator", fake_coordinator)
    monkeypatch.setattr(
        settings_router, "_maintenance_guardrail_status", lambda: {"pending_maintenance": 0, "active_maintenance": 0}
    )
    monkeypatch.setattr(settings_router.frigate_client, "get_config", _get_config)
    monkeypatch.setattr(settings_router.frigate_client, "get_event_with_error", _get_event_with_error)
    monkeypatch.setattr(settings_router.auto_video_classifier, "queue_classification", _queue_classification)

    result = await settings_router._run_analyze_unknowns()

    assert captured["limit"] == 200
    assert result["scan_limit"] == 200
    assert result["scan_truncated"] is False


@pytest.mark.asyncio
async def test_run_analyze_unknowns_caps_queued_maintenance_jobs_per_run(monkeypatch):
    from app.routers import settings as settings_router

    queued: list[str] = []
    fake_coordinator = _FakeMaintenanceCoordinator()

    class _FakeRepo:
        def __init__(self, db):
            pass

        async def get_unknown_detections(self, *, limit=None):
            return _unknowns(60)

        async def update_video_status(self, frigate_event, status, error=None):
            raise AssertionError("all fixture detections should be eligible")

    async def _queue_classification(event_id, camera, **kwargs):
        queued.append(event_id)
        return "queued"

    async def _get_config():
        return {}

    async def _get_event_with_error(event_id, timeout):
        return ({"has_clip": True}, None)

    monkeypatch.setattr(settings_router, "get_db", lambda: _FakeDbContext())
    monkeypatch.setattr(settings_router, "DetectionRepository", _FakeRepo)
    monkeypatch.setattr(settings_router, "maintenance_coordinator", fake_coordinator)
    monkeypatch.setattr(
        settings_router, "_maintenance_guardrail_status", lambda: {"pending_maintenance": 0, "active_maintenance": 0}
    )
    monkeypatch.setattr(settings_router.frigate_client, "get_config", _get_config)
    monkeypatch.setattr(
        settings_router.frigate_client,
        "get_event_with_error",
        _get_event_with_error,
    )
    monkeypatch.setattr(settings_router.auto_video_classifier, "queue_classification", _queue_classification)

    result = await settings_router._run_analyze_unknowns()

    assert result["status"] == "queued"
    assert result["accepted"] == 50
    assert result["count"] == 50
    assert result["total_candidates"] == 60
    assert result["remaining_candidates"] == 10
    assert result["queue_limit"] == 50
    assert queued == [f"event-{idx}" for idx in range(50)]
    assert fake_coordinator.released is True


@pytest.mark.asyncio
async def test_run_analyze_unknowns_defers_when_maintenance_queue_has_work(monkeypatch):
    from app.routers import settings as settings_router

    fake_coordinator = _FakeMaintenanceCoordinator()
    monkeypatch.setattr(settings_router, "maintenance_coordinator", fake_coordinator)
    monkeypatch.setattr(
        settings_router,
        "_maintenance_guardrail_status",
        lambda: {
            "pending_maintenance": 7,
            "active_maintenance": 0,
            "maintenance_status_message": "Maintenance work is queued",
        },
    )

    result = await settings_router._run_analyze_unknowns()

    assert result["status"] == "deferred"
    assert result["accepted"] == 0
    assert result["pending_maintenance"] == 7
    assert result["retry_after_seconds"] > 0
    assert fake_coordinator.acquired is False


@pytest.mark.asyncio
async def test_run_analyze_unknowns_defers_before_scanning_when_frigate_is_unavailable(monkeypatch):
    from app.routers import settings as settings_router

    fake_coordinator = _FakeMaintenanceCoordinator()

    async def _get_config():
        return None

    monkeypatch.setattr(settings_router, "maintenance_coordinator", fake_coordinator)
    monkeypatch.setattr(
        settings_router, "_maintenance_guardrail_status", lambda: {"pending_maintenance": 0, "active_maintenance": 0}
    )
    monkeypatch.setattr(settings_router.frigate_client, "get_config", _get_config)
    monkeypatch.setattr(settings_router, "get_db", lambda: (_ for _ in ()).throw(AssertionError("database scanned")))

    result = await settings_router._run_analyze_unknowns()

    assert result["status"] == "deferred"
    assert result["reason"] == "frigate_unavailable"
    assert result["accepted"] == 0
    assert fake_coordinator.released is True


@pytest.mark.asyncio
async def test_run_analyze_unknowns_stops_after_frigate_precheck_outage(monkeypatch):
    from app.routers import settings as settings_router

    requested: list[str] = []
    queued: list[str] = []
    fake_coordinator = _FakeMaintenanceCoordinator()

    class _FakeRepo:
        def __init__(self, db):
            pass

        async def get_unknown_detections(self, *, limit=None):
            return _unknowns(60)

    async def _get_config():
        return {}

    async def _get_event_with_error(event_id, timeout):
        requested.append(event_id)
        return None, "event_http_500"

    async def _queue_classification(event_id, camera, **kwargs):
        queued.append(event_id)
        return "queued"

    monkeypatch.setattr(settings_router, "get_db", lambda: _FakeDbContext())
    monkeypatch.setattr(settings_router, "DetectionRepository", _FakeRepo)
    monkeypatch.setattr(settings_router, "maintenance_coordinator", fake_coordinator)
    monkeypatch.setattr(
        settings_router, "_maintenance_guardrail_status", lambda: {"pending_maintenance": 0, "active_maintenance": 0}
    )
    monkeypatch.setattr(settings_router.frigate_client, "get_config", _get_config)
    monkeypatch.setattr(settings_router.frigate_client, "get_event_with_error", _get_event_with_error)
    monkeypatch.setattr(settings_router.auto_video_classifier, "queue_classification", _queue_classification)

    result = await settings_router._run_analyze_unknowns()

    assert result["status"] == "deferred"
    assert result["reason"] == "frigate_unavailable"
    assert len(requested) == settings_router.BATCH_ANALYSIS_CHECK_CONCURRENCY
    assert queued == []
    assert result["precheck_errors"] == len(requested)
    assert fake_coordinator.released is True
