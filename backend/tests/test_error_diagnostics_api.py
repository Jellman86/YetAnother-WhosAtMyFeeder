import httpx
import pytest
import pytest_asyncio

from app.main import app
from app.config import settings
from app.services.error_diagnostics import error_diagnostics_history
from app.routers import classifier as classifier_router


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def reset_state():
    original_auth_enabled = settings.auth.enabled
    original_public_enabled = settings.public_access.enabled
    error_diagnostics_history.clear()
    yield
    error_diagnostics_history.clear()
    settings.auth.enabled = original_auth_enabled
    settings.public_access.enabled = original_public_enabled


@pytest.mark.asyncio
async def test_owner_can_fetch_diagnostics_history(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    error_diagnostics_history.record(
        source="event_pipeline",
        component="event_processor",
        reason_code="stage_timeout",
        message="Classification timed out",
        severity="error",
        event_id="evt-owner-1",
    )

    response = await client.get("/api/diagnostics/errors")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["total_events"] == 1
    assert payload["returned_events"] == 1
    assert payload["severity_counts"] == {"error": 1}
    assert len(payload["events"]) == 1
    assert payload["events"][0]["event_id"] == "evt-owner-1"


@pytest.mark.asyncio
async def test_guest_cannot_fetch_diagnostics_history(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.public_access.enabled = True

    response = await client.get("/api/diagnostics/errors")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_diagnostics_history_supports_limit_and_filters(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    error_diagnostics_history.record(
        source="event_pipeline",
        component="event_processor",
        reason_code="drop_reason",
        message="Dropped",
        severity="warning",
    )
    error_diagnostics_history.record(
        source="notification_dispatcher",
        component="notification_dispatcher",
        reason_code="queue_full",
        message="Queue full",
        severity="error",
    )
    error_diagnostics_history.record(
        source="event_pipeline",
        component="event_processor",
        reason_code="stage_failure",
        message="Stage failure",
        severity="critical",
    )

    response = await client.get(
        "/api/diagnostics/errors",
        params={"component": "event_processor", "severity": "critical", "limit": 1},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["total_events"] == 3
    assert payload["returned_events"] == 1
    assert payload["severity_counts"] == {"critical": 1}
    assert payload["events"][0]["component"] == "event_processor"
    assert payload["events"][0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_owner_can_fetch_workspace_diagnostics_payload(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    error_diagnostics_history.record(
        source="event_pipeline",
        component="event_processor",
        reason_code="stage_timeout",
        message="Classification timed out",
        severity="error",
        event_id="evt-owner-2",
        correlation_key="event_pipeline:stage_timeout",
        snapshot_ref="health-abc",
    )

    original_get_status = classifier_router.classifier_service.get_status
    try:
        classifier_router.classifier_service.get_status = lambda: {
            "active_provider": "intel_gpu",
            "inference_backend": "openvino",
            "openvino_runtime": {
                "selected_provider": "intel_gpu",
                "active_provider": "intel_gpu",
                "inference_backend": "openvino",
                "model": {
                    "model_path": "/models/bird.onnx",
                    "input_size": 384,
                },
            },
        }

        response = await client.get("/api/diagnostics/workspace")
        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload["workspace_schema_version"]
        assert payload["backend_diagnostics"]["returned_events"] == 1
        assert payload["backend_diagnostics"]["events"][0]["correlation_key"] == "event_pipeline:stage_timeout"
        assert payload["health"]["service"] == "ya-wamf-backend"
        assert "ml" in payload["health"]
        assert "startup_warnings" in payload
        assert payload["classifier"]["active_provider"] == "intel_gpu"
        assert payload["classifier"]["openvino_runtime"]["model"]["model_path"] == "/models/bird.onnx"
    finally:
        classifier_router.classifier_service.get_status = original_get_status


@pytest.mark.asyncio
async def test_owner_can_clear_diagnostics_history(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    error_diagnostics_history.record(
        source="event_pipeline",
        component="event_processor",
        reason_code="stage_timeout",
        message="Classification timed out",
        severity="error",
        event_id="evt-owner-clear-1",
    )
    error_diagnostics_history.record(
        source="auto_video_classifier",
        component="video_classifier",
        reason_code="circuit_open",
        message="Video classification queue paused by circuit breaker",
        severity="warning",
    )

    response = await client.post("/api/diagnostics/clear")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["cleared_events"] == 2
    assert payload["remaining_events"] == 0

    snapshot = error_diagnostics_history.snapshot(limit=20)
    assert snapshot["total_events"] == 0
    assert snapshot["returned_events"] == 0
