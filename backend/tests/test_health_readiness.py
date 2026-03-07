import httpx
import pytest
import pytest_asyncio
from types import SimpleNamespace

import app.main as main_module
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_degraded_when_startup_warnings_present(client: httpx.AsyncClient):
    app.state.startup_warnings = [{"phase": "telemetry_start", "error": "boom"}]
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["startup_warnings"]


@pytest.mark.asyncio
async def test_ready_503_when_startup_warnings_present(client: httpx.AsyncClient):
    app.state.startup_warnings = [{"phase": "telemetry_start", "error": "boom"}]
    response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert body["startup_warnings"]


@pytest.mark.asyncio
async def test_ready_ok_in_test_mode_without_warnings(client: httpx.AsyncClient):
    app.state.startup_warnings = []
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True


@pytest.mark.asyncio
async def test_ready_503_when_not_testing_and_db_pool_not_initialized(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    app.state.startup_warnings = []
    monkeypatch.setattr(main_module, "_is_testing", lambda: False)
    monkeypatch.setattr(main_module, "is_db_pool_initialized", lambda: False)

    response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert body["db_pool_initialized"] is False


@pytest.mark.asyncio
async def test_health_degraded_when_notification_dispatcher_has_drops(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    app.state.startup_warnings = []
    monkeypatch.setattr(
        main_module,
        "notification_dispatcher",
        SimpleNamespace(
            get_status=lambda: {
                "running": True,
                "workers": 2,
                "queue_size": 0,
                "queue_max": 100,
                "dropped_jobs": 3,
                "timeout_seconds": 30.0,
            }
        ),
        raising=False,
    )

    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["notification_dispatcher"]["dropped_jobs"] == 3


@pytest.mark.asyncio
async def test_health_includes_event_pipeline_status(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    app.state.startup_warnings = []
    monkeypatch.setattr(
        main_module,
        "event_processor",
        SimpleNamespace(
            get_status=lambda: {
                "status": "ok",
                "started_events": 42,
                "completed_events": 40,
                "dropped_events": 2,
                "incomplete_events": 0,
                "critical_failures": 0,
                "stage_timeouts": {"classify_snapshot": 1},
                "stage_failures": {},
                "stage_fallbacks": {"gather_context": 1},
                "drop_reasons": {"filter_low_confidence": 2},
                "last_stage_timeout": None,
                "last_stage_failure": None,
                "last_drop": None,
                "last_completed": None,
                "recent_outcomes": [],
            }
        ),
        raising=False,
    )

    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["event_pipeline"]["started_events"] == 42
    assert body["event_pipeline"]["drop_reasons"]["filter_low_confidence"] == 2


@pytest.mark.asyncio
async def test_health_includes_high_quality_snapshot_status(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    app.state.startup_warnings = []
    monkeypatch.setattr(
        main_module,
        "high_quality_snapshot_service",
        SimpleNamespace(
            get_status=lambda: {
                "enabled": True,
                "active": 1,
                "scheduled_total": 3,
                "duplicate_requests": 1,
                "disabled_requests": 0,
                "outcomes": {"replaced": 2, "clip_not_found": 1},
                "last_result": {"event_id": "evt-1", "result": "replaced"},
            }
        ),
        raising=False,
    )

    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["high_quality_snapshots"]["scheduled_total"] == 3
    assert body["high_quality_snapshots"]["outcomes"]["replaced"] == 2


@pytest.mark.asyncio
async def test_health_degraded_when_event_pipeline_reports_critical_failures(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    app.state.startup_warnings = []
    monkeypatch.setattr(
        main_module,
        "event_processor",
        SimpleNamespace(
            get_status=lambda: {
                "status": "degraded",
                "started_events": 10,
                "completed_events": 8,
                "dropped_events": 2,
                "incomplete_events": 0,
                "critical_failures": 1,
                "stage_timeouts": {"classify_snapshot": 1},
                "stage_failures": {},
                "stage_fallbacks": {},
                "drop_reasons": {"classify_snapshot_unavailable": 1},
                "last_stage_timeout": None,
                "last_stage_failure": None,
                "last_drop": None,
                "last_completed": None,
                "recent_outcomes": [],
            }
        ),
        raising=False,
    )

    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["event_pipeline"]["critical_failures"] == 1


@pytest.mark.asyncio
async def test_health_degraded_when_db_pool_acquire_wait_is_extreme(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    app.state.startup_warnings = []
    monkeypatch.setattr(
        main_module,
        "get_db_pool_status",
        lambda: {
            "initialized": True,
            "pool_size": 5,
            "available_connections": 0,
            "acquire_count": 10,
            "slow_acquire_count": 10,
            "acquire_wait_avg_ms": 1200.0,
            "acquire_wait_max_ms": 6000.0,
            "slow_acquire_warn_ms": 250.0,
        },
        raising=False,
    )

    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db_pool"]["acquire_wait_max_ms"] == 6000.0
