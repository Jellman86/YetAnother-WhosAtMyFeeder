from app.services.telemetry_service import build_health_issue_report, build_runtime_telemetry_payload


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
    assert report["schema_version"] == "2026-05-03.health-issues.v1"
    assert len(report["issues"]) == 1

    issue = report["issues"][0]
    assert issue["component"] == "video_classifier"
    assert issue["reason_code"] == "video_timeout"
    assert issue["severity"] == "error"
    assert issue["count"] == 2
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
