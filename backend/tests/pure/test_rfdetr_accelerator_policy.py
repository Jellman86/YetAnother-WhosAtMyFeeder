from unittest.mock import Mock

import pytest

from app.config import settings
from app.services.bird_crop_service import BirdCropService
from app.services.bird_finder_health import finder_cpu_problem
from app.services import model_validation as validation

FINDER = "bird_crop_detector_accurate_rfdetr_nano"


@pytest.mark.parametrize(
    "eligible, expected",
    [
        (["cpu", "intel_gpu", "intel_npu"], "intel_npu"),
        (["cpu", "intel_gpu"], "intel_gpu"),
        (["cpu", "intel_cpu"], "cpu"),
    ],
)
@pytest.mark.parametrize("preference", ["auto", "intel_npu"])
def test_rfdetr_uses_npu_then_verified_gpu_before_cpu(monkeypatch, eligible, expected, preference):
    monkeypatch.setattr(settings.classification, "bird_crop_inference_provider", preference)
    monkeypatch.setattr(validation, "host_eligible_providers", lambda *args, **kwargs: eligible)
    monkeypatch.setattr(validation, "activation_provider_recommendation", lambda *args, **kwargs: "cpu")
    service = BirdCropService(accurate_model_id=FINDER)
    assert service._provider_for_tier("accurate") == expected


@pytest.mark.parametrize("gpu_works", [True, False])
def test_rfdetr_load_failure_tries_verified_gpu_before_cpu(tmp_path, monkeypatch, gpu_works):
    service = BirdCropService(accurate_model_id=FINDER, provider_override="intel_npu")
    monkeypatch.setattr(service, "_resolve_model_path", lambda _: tmp_path / "model.onnx")
    monkeypatch.setattr(service, "_load_model_config", lambda _: {})
    monkeypatch.setattr(validation, "host_eligible_providers", lambda *args, **kwargs: ["cpu", "intel_gpu"])
    calls = []

    def load(**kwargs):
        provider = kwargs["provider"]
        calls.append(provider)
        if provider == "intel_npu" or (provider == "intel_gpu" and not gpu_works):
            raise RuntimeError("device unavailable")
        return {"provider": provider}

    monkeypatch.setattr(service, "_load_model_on_provider", load)
    result = service._load_model_impl("accurate")
    assert calls == (["intel_npu", "intel_gpu"] if gpu_works else ["intel_npu", "intel_gpu", "cpu"])
    assert result["provider"] == ("intel_gpu" if gpu_works else "cpu")


def test_rfdetr_inference_failure_tries_verified_gpu_before_cpu(tmp_path, monkeypatch):
    service = BirdCropService(accurate_model_id=FINDER)
    monkeypatch.setattr(service, "_resolve_model_path", lambda _: tmp_path / "model.onnx")
    monkeypatch.setattr(service, "_load_model_config", lambda _: {})
    monkeypatch.setattr(validation, "host_eligible_providers", lambda *args, **kwargs: ["cpu", "intel_gpu"])
    load = Mock(side_effect=lambda **kwargs: {"provider": kwargs["provider"]})
    monkeypatch.setattr(service, "_load_model_on_provider", load)
    assert service._recover_tier_provider("accurate", failed_provider="intel_npu")["provider"] == "intel_gpu"
    assert load.call_args.kwargs["provider"] == "intel_gpu"


def test_cpu_problem_reports_finder_reason_and_action_and_clears_on_accelerator():
    status = {
        "model_id": FINDER,
        "healthy": True,
        "last_execution": {
            "provider": "cpu",
            "requested_provider": "intel_npu",
            "fallback_reason": "runtime_failed",
        },
    }
    problem = finder_cpu_problem(status, planned_provider="intel_npu")
    assert problem["active"] is True
    assert problem["model_id"] == FINDER
    assert "runtime_failed" in problem["reason"]
    assert "Check devices" in problem["action"]
    status["last_execution"]["provider"] = "intel_gpu"
    assert finder_cpu_problem(status, planned_provider="intel_npu")["active"] is False


def test_selected_cpu_is_a_problem_even_before_first_rfdetr_frame():
    assert finder_cpu_problem({"model_id": FINDER, "healthy": True}, planned_provider="cpu")["active"] is True
    assert finder_cpu_problem({"model_id": "yolox", "healthy": True}, planned_provider="cpu")["active"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("npu_passes", [True, False])
async def test_automatic_rfdetr_sweep_tries_gpu_only_after_npu_fails(monkeypatch, npu_passes):
    from app.services import classifier_service
    from app.services.model_manager import model_manager

    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    monkeypatch.setattr(
        classifier_service,
        "_detect_acceleration_capabilities",
        lambda: {
            "ort_available": True,
            "openvino_available": True,
            "intel_npu_available": True,
            "intel_gpu_available": True,
        },
    )
    monkeypatch.setattr(
        model_manager,
        "get_crop_detector_spec_by_model_id",
        lambda _: {
            "healthy": True,
            "metadata": {"runtime": "onnx", "supported_inference_providers": ["cpu", "intel_npu", "intel_gpu"]},
        },
    )
    probes = []

    async def probe(provider, **kwargs):
        probes.append(provider)
        return {
            "compile": {"ok": provider != "intel_npu" or npu_passes},
            "output_summary": {"finite_count": 1, "element_count": 1},
            "per_image_detections": [
                {
                    "image": "bird",
                    "kind": "real",
                    "detections": [
                        {"normalized_box": [0.1, 0.1, 0.5, 0.5], "confidence": 0.8},
                    ],
                }
            ],
        }

    monkeypatch.setattr(validation, "_probe_one_crop_provider", probe)
    result = await validation.sweep_crop_model_devices(FINDER, prefer_accelerators=True)
    assert probes == (["cpu", "intel_npu"] if npu_passes else ["cpu", "intel_npu", "intel_gpu"])
    assert result["eligible_providers"] == (["cpu", "intel_npu"] if npu_passes else ["cpu", "intel_gpu"])


def test_rfdetr_saved_gpu_uses_verified_npu_before_cpu(monkeypatch):
    monkeypatch.setattr(settings.classification, "bird_crop_inference_provider", "intel_gpu")
    monkeypatch.setattr(validation, "host_eligible_providers", lambda *args, **kwargs: ["cpu", "intel_npu"])
    service = BirdCropService(accurate_model_id=FINDER)
    assert service._provider_for_tier("accurate") == "intel_npu"


def test_rfdetr_gpu_runtime_failure_uses_verified_npu_before_cpu(tmp_path, monkeypatch):
    service = BirdCropService(accurate_model_id=FINDER)
    monkeypatch.setattr(service, "_resolve_model_path", lambda _: tmp_path / "model.onnx")
    monkeypatch.setattr(service, "_load_model_config", lambda _: {})
    monkeypatch.setattr(validation, "host_eligible_providers", lambda *args, **kwargs: ["cpu", "intel_npu"])
    monkeypatch.setattr(service, "_load_model_on_provider", lambda **kwargs: {"provider": kwargs["provider"]})
    assert service._recover_tier_provider("accurate", failed_provider="intel_gpu")["provider"] == "intel_npu"


def test_rfdetr_recommendation_keeps_accelerators_ahead_of_faster_cpu(tmp_path, monkeypatch):
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    validation.write_eligibility_entry(
        FINDER,
        ["cpu", "intel_gpu", "intel_npu"],
        image_flavor="intel",
        provider_results=[
            {"provider": "cpu", "ok": True, "latency_ms": 1},
            {"provider": "intel_gpu", "ok": True, "latency_ms": 3},
            {"provider": "intel_npu", "ok": True, "latency_ms": 10},
        ],
    )
    assert validation.host_provider_preference_order(FINDER) == ["intel_npu", "intel_gpu", "cpu"]


def test_cpu_health_explains_an_unusable_positive_baseline_without_changing_legacy_check_text():
    problem = finder_cpu_problem(
        {
            "model_id": FINDER,
            "healthy": True,
            "device_check": {
                "reason_code": "no_positive_baseline",
                "reason": "The accelerators did not match the CPU on saved bird photos, so the finder stays on the CPU.",
            },
        },
        planned_provider="cpu",
    )
    assert problem["active"] is True
    assert "no admitted birds" in problem["reason"]
