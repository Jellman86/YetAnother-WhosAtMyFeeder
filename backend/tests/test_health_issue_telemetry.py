import asyncio

import pytest

from app.config import settings
from app.services import telemetry_service as telemetry_module
from app.services.error_diagnostics import error_diagnostics_history
from app.services.telemetry_service import TelemetryService, build_health_issue_report, build_runtime_telemetry_payload


def _diagnostic_event(
    event_id: str,
    *,
    timestamp: str = "2026-07-25T12:00:00+00:00",
    reason_code: str = "video_timeout",
) -> dict:
    return {
        "id": event_id,
        "timestamp": timestamp,
        "source": "backend",
        "component": "video_classifier",
        "stage": "classify",
        "reason_code": reason_code,
        "message": "Timed out",
        "severity": "error",
        "context": {"timeout_seconds": 180},
    }


def _diagnostic_snapshot(*events: dict) -> dict:
    return {
        "captured_at": "2026-07-25T12:05:00+00:00",
        "total_events": len(events),
        "returned_events": len(events),
        "severity_counts": {"error": len(events)},
        "component_counts": {"video_classifier": len(events)},
        "events": list(events),
    }


class _RecordingAsyncClient:
    payloads: list[dict] = []
    statuses: list[int] = []
    delay_seconds = 0.0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, _url: str, *, json: dict):
        self.payloads.append(json)
        await asyncio.sleep(self.delay_seconds)
        status_code = self.statuses.pop(0) if self.statuses else 200
        return type("Response", (), {"status_code": status_code})()


@pytest.fixture
def health_sender(monkeypatch):
    _RecordingAsyncClient.payloads = []
    _RecordingAsyncClient.statuses = []
    _RecordingAsyncClient.delay_seconds = 0.0
    monkeypatch.setattr(telemetry_module.httpx, "AsyncClient", _RecordingAsyncClient)
    monkeypatch.setattr(settings.telemetry, "installation_id", "00000000-0000-0000-0000-000000000000")
    monkeypatch.setattr(settings.telemetry, "health_url", "https://telemetry.example/health-issues")
    return TelemetryService()


@pytest.mark.asyncio
async def test_health_report_does_not_repeat_successfully_sent_event(monkeypatch, health_sender):
    snapshot = _diagnostic_snapshot(_diagnostic_event("diag:1"))
    monkeypatch.setattr(error_diagnostics_history, "snapshot", lambda **_kwargs: snapshot)

    await health_sender._send_health_report()
    await health_sender._send_health_report()

    assert len(_RecordingAsyncClient.payloads) == 1


@pytest.mark.asyncio
async def test_health_report_retry_uses_stable_report_id(monkeypatch, health_sender):
    snapshot = _diagnostic_snapshot(_diagnostic_event("diag:retry"))
    monkeypatch.setattr(error_diagnostics_history, "snapshot", lambda **_kwargs: snapshot)
    _RecordingAsyncClient.statuses = [500, 200]

    await health_sender._send_health_report()
    await health_sender._send_health_report()

    assert len(_RecordingAsyncClient.payloads) == 2
    first_id = _RecordingAsyncClient.payloads[0]["report_id"]
    assert first_id == _RecordingAsyncClient.payloads[1]["report_id"]
    assert len(first_id) == 64
    assert _RecordingAsyncClient.payloads[0]["schema_version"] == "2026-07-25.health-issues.v3"
    assert len(_RecordingAsyncClient.payloads[0]["issues"][0]["event_ids"]) == 1
    assert len(_RecordingAsyncClient.payloads[0]["issues"][0]["event_ids"][0]) == 64


@pytest.mark.asyncio
async def test_health_report_retries_exact_inflight_batch_before_new_events(monkeypatch, health_sender):
    current = {"snapshot": _diagnostic_snapshot(_diagnostic_event("diag:inflight"))}
    monkeypatch.setattr(error_diagnostics_history, "snapshot", lambda **_kwargs: current["snapshot"])
    _RecordingAsyncClient.statuses = [500, 200, 200]

    await health_sender._send_health_report()
    current["snapshot"] = _diagnostic_snapshot(
        _diagnostic_event("diag:inflight"),
        _diagnostic_event("diag:new", timestamp="2026-07-25T12:10:00+00:00"),
    )
    await health_sender._send_health_report()
    await health_sender._send_health_report()

    assert len(_RecordingAsyncClient.payloads) == 3
    assert _RecordingAsyncClient.payloads[1] == _RecordingAsyncClient.payloads[0]
    assert _RecordingAsyncClient.payloads[2]["report_id"] != _RecordingAsyncClient.payloads[0]["report_id"]
    assert _RecordingAsyncClient.payloads[0]["issues"][0]["count"] == 1
    assert _RecordingAsyncClient.payloads[2]["issues"][0]["count"] == 1


@pytest.mark.asyncio
async def test_health_report_leaves_truncated_issue_groups_for_next_batch(monkeypatch, health_sender):
    events = [_diagnostic_event(f"diag:{index}", reason_code=f"reason_{index:02d}") for index in range(26)]
    snapshot = _diagnostic_snapshot(*events)
    monkeypatch.setattr(error_diagnostics_history, "snapshot", lambda **_kwargs: snapshot)

    await health_sender._send_health_report()
    await health_sender._send_health_report()

    assert len(_RecordingAsyncClient.payloads) == 2
    assert len(_RecordingAsyncClient.payloads[0]["issues"]) == 25
    assert len(_RecordingAsyncClient.payloads[1]["issues"]) == 1
    fingerprints = {
        issue["fingerprint"] for payload in _RecordingAsyncClient.payloads for issue in payload["issues"]
    }
    assert len(fingerprints) == 26


@pytest.mark.asyncio
async def test_health_report_sends_only_new_events_from_persistent_history(monkeypatch, health_sender):
    current = {"snapshot": _diagnostic_snapshot(_diagnostic_event("diag:old"))}
    monkeypatch.setattr(error_diagnostics_history, "snapshot", lambda **_kwargs: current["snapshot"])

    await health_sender._send_health_report()
    current["snapshot"] = _diagnostic_snapshot(
        _diagnostic_event("diag:new", timestamp="2026-07-25T12:10:00+00:00"),
        _diagnostic_event("diag:old"),
    )
    await health_sender._send_health_report()

    assert len(_RecordingAsyncClient.payloads) == 2
    assert _RecordingAsyncClient.payloads[0]["issues"][0]["count"] == 1
    assert _RecordingAsyncClient.payloads[1]["issues"][0]["count"] == 1
    assert _RecordingAsyncClient.payloads[0]["report_id"] != _RecordingAsyncClient.payloads[1]["report_id"]


@pytest.mark.asyncio
async def test_concurrent_health_reports_do_not_upload_same_event_twice(monkeypatch, health_sender):
    snapshot = _diagnostic_snapshot(_diagnostic_event("diag:concurrent"))
    monkeypatch.setattr(error_diagnostics_history, "snapshot", lambda **_kwargs: snapshot)
    _RecordingAsyncClient.delay_seconds = 0.01

    await asyncio.gather(
        health_sender._send_health_report(),
        health_sender._send_health_report(),
    )

    assert len(_RecordingAsyncClient.payloads) == 1


def test_health_issue_report_groups_and_sanitizes_diagnostics():
    snapshot = {
        "captured_at": "2026-05-03T18:00:00+00:00",
        "total_events": 3,
        "returned_events": 3,
        "severity_counts": {"error": 2, "info": 1},
        "component_counts": {"video_classifier": 2, "startup": 1},
        "events": [
            {
                "timestamp": "2026-05-03T17:55:00+00:00",
                "source": "backend",
                "component": "video_classifier",
                "stage": "classify",
                "reason_code": "video_timeout",
                "message": "Timed out on /media/frigate/front/event-123.mp4",
                "severity": "error",
                "event_id": "event-123",
                "context": {
                    "event_id": "event-123",
                    "clip_path": "/media/frigate/front/event-123.mp4",
                    "camera": "front",
                    "configured_provider": "intel_gpu",
                    "active_provider": "cpu",
                    "timeout_seconds": 180,
                    "queue_depth": 4,
                    "freeform_error": "contains raw path /config/media/file.jpg",
                },
            },
            {
                "timestamp": "2026-05-03T17:56:00+00:00",
                "source": "backend",
                "component": "video_classifier",
                "stage": "classify",
                "reason_code": "video_timeout",
                "message": "Timed out on another event",
                "severity": "warning",
                "context": {
                    "configured_provider": "intel_gpu",
                    "active_provider": "cpu",
                    "timeout_seconds": 180,
                },
            },
            {
                "timestamp": "2026-05-03T17:57:00+00:00",
                "source": "backend",
                "component": "startup",
                "reason_code": "startup_note",
                "message": "informational",
                "severity": "info",
                "context": {"status": "ok"},
            },
        ],
    }

    report = build_health_issue_report(
        installation_id="00000000-0000-0000-0000-000000000000",
        app_version="2.9.14-dev+abc1234",
        diagnostics_snapshot=snapshot,
    )

    assert report is not None
    assert report["schema_version"] == "2026-07-25.health-issues.v3"
    assert len(report["issues"]) == 1

    issue = report["issues"][0]
    assert issue["component"] == "video_classifier"
    assert issue["reason_code"] == "video_timeout"
    assert issue["severity"] == "error"
    assert issue["count"] == 2
    assert len(issue["event_ids"]) == 2
    assert all(len(event_id) == 64 for event_id in issue["event_ids"])
    assert issue["fingerprint"]
    assert issue["sample_context"] == {
        "configured_provider": "intel_gpu",
        "active_provider": "cpu",
        "timeout_seconds": 180,
        "queue_depth": 4,
    }

    rendered = str(report)
    assert "event-123" not in rendered
    assert "front" not in rendered
    assert "/media" not in rendered
    assert "/config" not in rendered


def test_health_issue_report_keeps_error_type_for_critical_stage_failures():
    # A critical classify_snapshot stage failure used to report an empty sample_context
    # (its only context key, "error", is free text and is stripped). It now also carries the
    # exception type and stage, which are allow-listed, so the fleet data is diagnosable.
    snapshot = {
        "captured_at": "2026-07-11T00:00:00+00:00",
        "total_events": 1,
        "returned_events": 1,
        "severity_counts": {"critical": 1},
        "component_counts": {"event_processor": 1},
        "events": [
            {
                "timestamp": "2026-07-11T00:00:00+00:00",
                "source": "event_pipeline",
                "component": "event_processor",
                "stage": "classify_snapshot",
                "reason_code": "stage_failure",
                "message": "Stage classify_snapshot failed: boom reading /config/media/x.jpg",
                "severity": "critical",
                "event_id": "evt-77",
                "context": {
                    "error": "boom while reading /config/media/x.jpg",
                    "error_type": "ValueError",
                    "stage": "classify_snapshot",
                },
            },
        ],
    }

    report = build_health_issue_report(
        installation_id="00000000-0000-0000-0000-000000000000",
        app_version="2.13.0-dev+abc1234",
        diagnostics_snapshot=snapshot,
    )

    assert report is not None
    issue = report["issues"][0]
    assert issue["severity"] == "critical"
    assert issue["reason_code"] == "stage_failure"
    assert issue["sample_context"] == {"error_type": "ValueError", "stage": "classify_snapshot"}

    rendered = str(report)
    assert "boom" not in rendered
    assert "/config" not in rendered
    assert "evt-77" not in rendered


def test_runtime_telemetry_payload_exposes_device_and_runtime_capabilities():
    payload = build_runtime_telemetry_payload(
        model_type="birdnet_v2",
        model_runtime="onnx",
        classifier_status={
            "selected_provider": "intel_gpu",
            "active_provider": "intel_cpu",
            "inference_backend": "openvino",
            "image_execution_mode": "subprocess",
            "cuda_available": False,
            "cuda_hardware_available": True,
            "openvino_available": True,
            "intel_gpu_available": True,
            "intel_npu_available": True,
            "openvino_model_compile_ok": False,
            "openvino_model_compile_device": "GPU",
            "live_image_gpu_fallback_active": True,
        },
        app_version="2.9.14-dev+abc1234",
        platform_system="Linux",
        platform_release="6.8.0",
        platform_machine="x86_64",
        deployment_env={
            "APP_BRANCH": "dev",
            "GIT_HASH": "abc1234",
            "YAWAMF_IMAGE_TAG": "dev",
            "YAWAMF_DEPLOYMENT_MODE": "monolith",
        },
    )

    assert payload["configuration"]["model_type"] == "birdnet_v2"
    assert payload["runtime"] == {
        "model_runtime": "onnx",
        "inference_provider_configured": "intel_gpu",
        "inference_provider_active": "intel_cpu",
        "inference_backend_active": "openvino",
        "image_execution_mode": "subprocess",
        "bird_crop_detector_tier": "fast",
        "inference_health_status": None,
        "inference_health_unhealthy_runtimes": 0,
        "inference_health_degraded_runtimes": 0,
        "inference_health_total_runtimes": 0,
        "last_recovery_reason": None,
        "last_recovery_status": None,
    }
    assert payload["hardware"] == {
        "cuda_available": False,
        "nvidia_gpu_detected": True,
        "openvino_available": True,
        "intel_gpu_available": True,
        "intel_npu_available": True,
        "openvino_gpu_compile_ok": False,
        "openvino_gpu_compile_device": "GPU",
        "openvino_gpu_fallback_active": True,
    }
    assert payload["deployment"] == {
        "mode": "monolith",
        "image_flavor": "dev",
        "image_arch": "x86_64",
        "app_branch": "dev",
        "git_hash": "abc1234",
    }


def test_runtime_telemetry_payload_does_not_treat_unrelated_recovery_as_gpu_fallback():
    payload = build_runtime_telemetry_payload(
        model_type="birdnet_v2",
        model_runtime="onnx",
        classifier_status={
            "selected_provider": "auto",
            "active_provider": "intel_gpu",
            "inference_backend": "openvino",
            "cuda_available": False,
            "cuda_hardware_available": False,
            "openvino_available": True,
            "intel_gpu_available": True,
            "openvino_model_compile_ok": True,
            "openvino_model_compile_device": "GPU",
            "last_runtime_recovery": {"reason": "non_finite_output"},
            "live_image_gpu_fallback_active": False,
        },
        app_version="2.9.14-dev+abc1234",
        platform_system="Linux",
        platform_release="6.8.0",
        platform_machine="x86_64",
        deployment_env={},
    )

    assert payload["hardware"]["openvino_gpu_fallback_active"] is False


def test_runtime_telemetry_payload_prefers_inference_health_recovery_over_legacy_flags():
    payload = build_runtime_telemetry_payload(
        model_type="birdnet_v2",
        model_runtime="onnx",
        classifier_status={
            "selected_provider": "intel_gpu",
            "active_provider": "intel_cpu",
            "inference_backend": "openvino",
            "image_execution_mode": "subprocess",
            "cuda_available": False,
            "cuda_hardware_available": False,
            "openvino_available": True,
            "intel_gpu_available": True,
            "openvino_model_compile_ok": True,
            "openvino_model_compile_device": "GPU",
            "inference_health": {
                "status": "degraded",
                "runtimes": {},
                "last_recovery": {
                    "status": "recovered",
                    "failed_backend": "openvino",
                    "failed_provider": "intel_gpu",
                    "recovered_backend": "openvino",
                    "recovered_provider": "intel_cpu",
                },
            },
        },
        app_version="2.10.0-dev+abc1234",
        platform_system="Linux",
        platform_release="6.8.0",
        platform_machine="x86_64",
        deployment_env={},
    )

    assert payload["hardware"]["openvino_gpu_fallback_active"] is True


def test_runtime_telemetry_payload_exposes_inference_health_distribution_fields():
    payload = build_runtime_telemetry_payload(
        model_type="birdnet_v2",
        model_runtime="onnx",
        classifier_status={
            "selected_provider": "intel_gpu",
            "active_provider": "intel_cpu",
            "inference_backend": "openvino",
            "cuda_available": False,
            "openvino_available": True,
            "intel_gpu_available": True,
            "openvino_model_compile_ok": True,
            "openvino_model_compile_device": "GPU",
            "inference_health": {
                "status": "unhealthy",
                "runtimes": {
                    "openvino/intel_gpu/eu_medium_focalnet_b": {"verdict": "unhealthy"},
                    "openvino/intel_cpu/eu_medium_focalnet_b": {"verdict": "degraded"},
                    "tflite/cpu/model.tflite": {"verdict": "healthy"},
                },
                "last_recovery": {
                    "status": "recovered",
                    "reason": "live_gpu_lease_expiry_fallback",
                    "failed_provider": "intel_gpu",
                    "recovered_provider": "intel_cpu",
                },
            },
        },
        app_version="2.10.0-dev+abc1234",
        platform_system="Linux",
        platform_release="6.8.0",
        platform_machine="x86_64",
        deployment_env={},
    )

    runtime = payload["runtime"]
    assert runtime["inference_health_status"] == "unhealthy"
    assert runtime["inference_health_unhealthy_runtimes"] == 1
    assert runtime["inference_health_degraded_runtimes"] == 1
    assert runtime["inference_health_total_runtimes"] == 3
    assert runtime["last_recovery_reason"] == "live_gpu_lease_expiry_fallback"
    assert runtime["last_recovery_status"] == "recovered"


def test_runtime_telemetry_payload_sanitizes_inference_health_unknown_values():
    payload = build_runtime_telemetry_payload(
        model_type="birdnet_v2",
        model_runtime="onnx",
        classifier_status={
            "selected_provider": "auto",
            "active_provider": "intel_gpu",
            "inference_backend": "openvino",
            "cuda_available": False,
            "openvino_available": True,
            "intel_gpu_available": True,
            "openvino_model_compile_ok": True,
            "openvino_model_compile_device": "GPU",
            "inference_health": {
                "status": "weird",
                "runtimes": {
                    "openvino/intel_gpu/x": {"verdict": "weird"},
                },
                "last_recovery": {
                    "status": "in_progress",
                    "reason": "bad reason with spaces;DROP",
                },
            },
        },
        app_version="2.10.0-dev+abc1234",
        platform_system="Linux",
        platform_release="6.8.0",
        platform_machine="x86_64",
        deployment_env={},
    )

    runtime = payload["runtime"]
    assert runtime["inference_health_status"] is None
    assert runtime["inference_health_unhealthy_runtimes"] == 0
    assert runtime["inference_health_degraded_runtimes"] == 0
    assert runtime["inference_health_total_runtimes"] == 1
    assert runtime["last_recovery_reason"] is None
    assert runtime["last_recovery_status"] is None


def test_runtime_telemetry_payload_inference_health_no_fallback_when_not_recovered():
    payload = build_runtime_telemetry_payload(
        model_type="birdnet_v2",
        model_runtime="onnx",
        classifier_status={
            "selected_provider": "intel_gpu",
            "active_provider": "intel_gpu",
            "inference_backend": "openvino",
            "cuda_available": False,
            "openvino_available": True,
            "intel_gpu_available": True,
            "openvino_model_compile_ok": True,
            "openvino_model_compile_device": "GPU",
            "inference_health": {
                "status": "degraded",
                "runtimes": {},
                "last_recovery": {
                    "status": "failed",
                    "failed_backend": "openvino",
                    "failed_provider": "intel_gpu",
                },
            },
        },
        app_version="2.10.0-dev+abc1234",
        platform_system="Linux",
        platform_release="6.8.0",
        platform_machine="x86_64",
        deployment_env={},
    )

    assert payload["hardware"]["openvino_gpu_fallback_active"] is False
