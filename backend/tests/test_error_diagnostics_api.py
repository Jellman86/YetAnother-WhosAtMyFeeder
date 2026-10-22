import httpx
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

from app.main import app
from app.config import settings
from app.services.error_diagnostics import error_diagnostics_history
from app.routers import classifier as classifier_router
from app.routers import settings as settings_router


@pytest.fixture(autouse=True)
def unavailable_media_sample(monkeypatch):
    probe = AsyncMock(
        return_value={
            "available": False,
            "codec_tag": None,
            "safari_compatible": None,
            "note": "No clip available in this fixture",
        }
    )
    monkeypatch.setattr("app.routers.diagnostics.collect_video_sample_diagnostic", probe)
    return probe


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
async def test_workspace_payload_includes_focused_video_classifier_diagnostics(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    error_diagnostics_history.record(
        source="video_classifier",
        component="auto_video_classifier",
        reason_code="video_timeout",
        message="Video classification exceeded the configured timeout",
        severity="error",
        event_id="evt-video-1",
        correlation_key="video:evt-video-1",
        worker_pool="video",
        context={"timeout_seconds": 30},
        timestamp="2026-04-01T20:27:00Z",
    )
    error_diagnostics_history.record(
        source="video_classifier",
        component="auto_video_classifier",
        reason_code="video_circuit_opened",
        message="Video classification circuit opened after repeated failures",
        severity="error",
        event_id="evt-video-1",
        correlation_key="video:circuit_open",
        worker_pool="video",
        context={"failure_count": 5, "cooldown_minutes": 15, "last_error": "video_timeout"},
        timestamp="2026-04-01T20:28:00Z",
    )

    import app.main as main_module

    original_build_health_payload = main_module.build_health_payload
    original_get_status = classifier_router.classifier_service.get_status
    try:

        def fake_build_health_payload() -> dict[str, object]:
            return {
                "status": "degraded",
                "service": "ya-wamf-backend",
                "version": "2.9.1-dev",
                "startup_warnings": [],
                "video_classifier": {
                    "status": "unknown",
                    "pending": 69,
                    "active": 1,
                    "completed": 0,
                    "failed": 0,
                    "circuit_open": True,
                    "open_until": "2026-04-01T20:42:13.797562+00:00",
                    "failure_count": 5,
                },
            }

        main_module.build_health_payload = fake_build_health_payload
        classifier_router.classifier_service.get_status = lambda: {"active_provider": "intel_gpu"}

        response = await client.get("/api/diagnostics/workspace")
        assert response.status_code == 200, response.text
        payload = response.json()

        focus = payload["focused_diagnostics"]["video_classifier"]
        assert focus["circuit_open"] is True
        assert focus["failure_count"] == 5
        assert focus["pending"] == 69
        assert focus["latest_circuit_opened"]["reason_code"] == "video_circuit_opened"
        assert focus["latest_circuit_opened"]["context"]["last_error"] == "video_timeout"
        assert [event["reason_code"] for event in focus["recent_events"]] == [
            "video_circuit_opened",
            "video_timeout",
        ]
        assert payload["backend_diagnostics"]["events"][0]["reason_code"] == "video_circuit_opened"
    finally:
        main_module.build_health_payload = original_build_health_payload
        classifier_router.classifier_service.get_status = original_get_status


@pytest.mark.asyncio
async def test_owner_can_fetch_diagnostics_bundle(client: httpx.AsyncClient, unavailable_media_sample):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    error_diagnostics_history.record(
        source="event_pipeline",
        component="event_processor",
        reason_code="stage_timeout",
        message="Classification timed out",
        severity="error",
        event_id="evt-owner-bundle-1",
        correlation_key="event_pipeline:stage_timeout",
        snapshot_ref="health-bundle-1",
    )

    original_get_status = classifier_router.classifier_service.get_status
    try:
        classifier_router.classifier_service.get_status = lambda: {
            "active_provider": "intel_cpu",
            "inference_backend": "openvino",
        }

        response = await client.get("/api/diagnostics/bundle")
        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload["schema_version"] == "2026-08-15.owner-diagnostics-bundle.v2"
        assert payload["summary"]["diagnostic_events"] == 1
        assert payload["summary"]["health_status"] == payload["health"]["status"]
        assert payload["server"]["service"] == payload["health"]["service"]
        assert payload["workspace"]["backend_diagnostics"]["events"][0]["event_id"] == "evt-owner-bundle-1"
        assert payload["classifier"]["active_provider"] == "intel_cpu"
        assert payload["backend_diagnostics"]["events"][0]["correlation_key"] == "event_pipeline:stage_timeout"
        assert isinstance(payload["focused_diagnostics"], dict)
        # Answers "why does Safari refuse my clip" without a round trip for
        # ffprobe output. The unavailable-media boundary is explicit: a reachable
        # Frigate beside the test container must not change the test's outcome.
        assert payload["media_sample"]["available"] is False
        assert payload["media_sample"]["codec_tag"] is None
        assert payload["media_sample"]["safari_compatible"] is None
        assert payload["media_sample"]["note"]
        assert payload["summary"]["video_sample_format"] == "unknown"
        unavailable_media_sample.assert_awaited_once()
    finally:
        classifier_router.classifier_service.get_status = original_get_status


@pytest.mark.asyncio
async def test_diagnostics_bundle_includes_taxonomy_and_maintenance_status(client: httpx.AsyncClient):
    settings.auth.enabled = False
    settings.public_access.enabled = False

    original_get_status = classifier_router.classifier_service.get_status
    original_taxonomy_status = settings_router.canonical_identity_repair_service.get_status
    try:
        classifier_router.classifier_service.get_status = lambda: {"active_provider": "intel_cpu"}
        settings_router.canonical_identity_repair_service.get_status = lambda: {
            "is_running": False,
            "processed": 48,
            "total": 120,
            "current_item": "Blue Tit",
            "error": "taxonomy_lookup_failed",
            "progress_state": "failed",
            "message": "taxonomy_lookup_failed",
        }

        response = await client.get("/api/diagnostics/bundle")
        assert response.status_code == 200, response.text
        payload = response.json()

        assert payload["taxonomy_repair"]["error"] == "taxonomy_lookup_failed"
        assert payload["workspace"]["taxonomy_repair"]["progress_state"] == "failed"
        assert payload["maintenance_coordinator"]["capacity"] >= 1
        assert payload["workspace"]["maintenance_coordinator"]["capacity"] >= 1
    finally:
        classifier_router.classifier_service.get_status = original_get_status
        settings_router.canonical_identity_repair_service.get_status = original_taxonomy_status


@pytest.mark.asyncio
async def test_guest_cannot_fetch_diagnostics_bundle(client: httpx.AsyncClient):
    settings.auth.enabled = True
    settings.public_access.enabled = True

    response = await client.get("/api/diagnostics/bundle")
    assert response.status_code == 403


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


def test_successful_video_photo_and_cache_events_are_not_reported_as_failures():
    from app.routers.diagnostics import _build_video_classifier_focus

    events = [
        {"component": "auto_video_classifier", "severity": "info", "reason_code": reason}
        for reason in ("video_photo_update", "precheck_cache_bypass", "video_result_not_promotable")
    ]
    focus = _build_video_classifier_focus({"events": events}, {})

    assert focus["likely_last_error"] is None
    assert focus["candidate_failure_events"] == []
    assert focus["recent_events"] == events


def test_video_failure_evidence_is_not_hidden_by_eight_newer_progress_events():
    from app.routers.diagnostics import _build_video_classifier_focus

    progress = {"component": "auto_video_classifier", "severity": "info", "reason_code": "video_photo_update"}
    failure = {"component": "auto_video_classifier", "severity": "error", "reason_code": "video_timeout"}
    focus = _build_video_classifier_focus({"events": [dict(progress) for _ in range(9)] + [failure]}, {})

    assert focus["likely_last_error"] == "video_timeout"
    assert focus["candidate_failure_events"] == [failure]
    assert len(focus["recent_events"]) == 8


@pytest.mark.parametrize("severity", ["warning", "error", "critical"])
def test_video_failure_focus_keeps_actionable_severities(severity):
    from app.routers.diagnostics import _build_video_classifier_focus

    failure = {"worker_pool": "video", "severity": severity, "reason_code": "video_timeout"}
    focus = _build_video_classifier_focus({"events": [failure]}, {})

    assert focus["likely_last_error"] == "video_timeout"
    assert focus["candidate_failure_events"] == [failure]


def test_successful_cpu_video_recovery_is_degraded_status_not_a_failed_inference():
    from app.routers.diagnostics import _build_video_classifier_focus

    recovery = {"worker_pool": "video", "severity": "warning", "reason_code": "native_cpu_recovery_degraded"}
    focus = _build_video_classifier_focus({"events": [recovery]}, {})

    assert focus["likely_last_error"] is None
    assert focus["candidate_failure_events"] == []
    assert focus["recent_events"] == [recovery]


def test_video_circuit_cause_remains_available_beyond_the_recent_activity_cap():
    from app.routers.diagnostics import _build_video_classifier_focus

    progress = {"worker_pool": "video", "severity": "info", "reason_code": "video_photo_update"}
    circuit = {
        "worker_pool": "video",
        "severity": "error",
        "reason_code": "video_circuit_opened",
        "context": {"last_error": "video_worker_timed_out"},
    }
    focus = _build_video_classifier_focus({"events": [dict(progress) for _ in range(9)] + [circuit]}, {})

    assert focus["likely_last_error"] == "video_worker_timed_out"
    assert focus["latest_circuit_opened"] == circuit
    assert focus["candidate_failure_events"] == []
    assert len(focus["recent_events"]) == 8


def test_newer_video_failure_takes_precedence_over_an_older_circuit_cause():
    from app.routers.diagnostics import _build_video_classifier_focus

    failure = {"worker_pool": "video", "severity": "error", "reason_code": "video_timeout"}
    progress = {"worker_pool": "video", "severity": "info", "reason_code": "video_photo_update"}
    circuit = {
        "worker_pool": "video",
        "severity": "error",
        "reason_code": "video_circuit_opened",
        "context": {"last_error": "old_worker_failure"},
    }
    focus = _build_video_classifier_focus({"events": [failure] + [dict(progress) for _ in range(20)] + [circuit]}, {})
    assert focus["likely_last_error"] == "video_timeout"
    assert focus["latest_circuit_opened"] == circuit


@pytest.mark.parametrize("status", ["degraded", "failed"])
def test_real_cpu_video_recovery_producer_reaches_focused_diagnostics(tmp_path, status):
    from app.routers.diagnostics import _build_video_classifier_focus
    from app.services.native_cpu_recovery import NativeCpuRecovery
    from app.services.native_crash_quarantine import NativeCrashQuarantine

    policy = NativeCrashQuarantine(lambda: {}, root=tmp_path)
    runner = NativeCpuRecovery(lambda: {}, policy)
    runner._state("video", status, {"active_provider": "cpu"})
    snapshot = error_diagnostics_history.snapshot(limit=20)
    focus = _build_video_classifier_focus(snapshot, {})
    assert len(focus["recent_events"]) == 1
    assert focus["recent_events"][0]["worker_pool"] == "video"
    assert focus["likely_last_error"] == ("native_cpu_recovery_failed" if status == "failed" else None)
    assert len(focus["candidate_failure_events"]) == (1 if status == "failed" else 0)


def test_successful_snapshot_fallback_is_activity_rather_than_failure():
    from app.routers.diagnostics import _build_video_classifier_focus

    event = {
        "component": "auto_video_classifier",
        "severity": "warning",
        "reason_code": "video_worker_timed_out",
        "context": {"snapshot_fallback_attempted": True, "snapshot_fallback_recovered": True},
    }
    focus = _build_video_classifier_focus({"events": [event]}, {})
    assert focus["likely_last_error"] is None
    assert focus["candidate_failure_events"] == []
    assert focus["recent_events"] == [event]


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["errors", "workspace", "bundle"])
async def test_diagnostic_exports_do_not_disclose_configured_credentials(client, monkeypatch, endpoint):
    settings.auth.enabled = False
    settings.public_access.enabled = False
    token = "DUMMY-EXPORT-DIAGNOSTIC-CREDENTIAL"
    monkeypatch.setattr(settings.notifications.telegram, "bot_token", token)
    error_diagnostics_history.record(
        source="fixture",
        component="fixture",
        reason_code="fixture_failure",
        message=f"Unstructured provider text {token}",
        context={"nested": {"api_key": token}},
    )
    response = await client.get(f"/api/diagnostics/{endpoint}")
    assert response.status_code == 200
    assert token not in response.text
    assert "fixture_failure" in response.text
    assert "REDACTED" in response.text
