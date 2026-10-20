"""RF-DETR CUDA remains a candidate until this host's crop sweep passes."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image
import pytest

from app.services import classifier_service, model_validation as validation
from app.services.bird_crop_service import BirdCropService, bird_crop_service
from app.services.model_eval_service import IMAGES_SUBDIR, ModelEvalRunner
from app.services.model_manager import model_manager


MODEL_ID = "bird_crop_detector_accurate_rfdetr_nano"


@pytest.fixture
def installed_rfdetr(tmp_path, monkeypatch):
    models = tmp_path / "models"
    model = models / MODEL_ID
    model.mkdir(parents=True)
    (model / "model.onnx").write_bytes(b"inference is replaced at the native probe boundary")
    # An existing download keeps its older sidecar after an application update.
    (model / "model_config.json").write_text(
        json.dumps({"supported_inference_providers": ["cpu", "intel_cpu", "intel_gpu", "intel_npu"]})
    )
    monkeypatch.setattr("app.services.model_manager.MODELS_DIR", str(models))
    monkeypatch.setenv("YAWAMF_EVAL_RUNS_DIR", str(tmp_path / "evidence"))
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "cuda")
    monkeypatch.setattr(
        classifier_service,
        "_detect_acceleration_capabilities",
        lambda: {
            "ort_available": True,
            "cuda_available": True,
            "openvino_available": True,
            "intel_cpu_available": True,
            "intel_gpu_available": True,
            "intel_npu_available": True,
        },
    )
    signatures = {provider: f"{provider}-runtime-and-driver-v1" for provider in ("cpu", "cuda")}
    monkeypatch.setattr(validation, "current_provider_runtime_signature", lambda provider: signatures[provider])
    return signatures


def _probe_report(provider: str) -> dict:
    return {
        "compile": {"ok": True},
        "output_summary": {"finite_count": 100, "element_count": 100},
        "per_image_detections": [
            {
                "image": "real:bird.jpg",
                "kind": "real",
                "top_detection": {"normalized_box": [0.1, 0.2, 0.5, 0.7], "confidence": 0.7},
            },
            {"image": "negative_foliage", "kind": "negative", "top_detection": None},
        ],
        "inference_latency_ms": 8.0 if provider == "cuda" else 100.0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flavor", "providers"),
    [
        ("cuda", ["cpu", "cuda"]),
        ("full", ["cpu", "intel_cpu", "cuda", "intel_gpu", "intel_npu"]),
        ("intel", ["cpu", "intel_cpu", "intel_gpu", "intel_npu"]),
        ("cpu", ["cpu"]),
        ("rpi", ["cpu"]),
    ],
)
async def test_normal_rfdetr_sweep_preserves_image_provider_boundaries(
    installed_rfdetr, monkeypatch, flavor, providers
):
    monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", flavor)
    probed = []

    async def probe(provider, **kwargs):
        assert kwargs["model_id"] == MODEL_ID
        probed.append(provider)
        return _probe_report(provider)

    monkeypatch.setattr(validation, "_probe_one_crop_provider", probe)

    result = await validation.sweep_crop_model_devices(MODEL_ID, image_paths=["bird.jpg"])

    assert probed == providers
    assert result["eligible_providers"] == providers
    assert result["discovered_providers"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "condition",
    [
        "passed",
        "compile_failed",
        "nonfinite",
        "disagrees",
        "false_positive",
        "artifact_changed",
        "driver_changed",
        "image_changed",
    ],
)
async def test_rfdetr_cuda_selection_requires_current_cpu_agreeing_evidence(
    installed_rfdetr, tmp_path, monkeypatch, condition
):
    service = BirdCropService(detector_tier="accurate", accurate_model_id=MODEL_ID)
    assert service._provider_for_tier("accurate") == "cpu"
    probed = []

    async def probe(provider, **_kwargs):
        probed.append(provider)
        report = _probe_report(provider)
        if provider == "cuda":
            if condition == "compile_failed":
                report["compile"] = {"ok": False, "error": "CUDA compile failed"}
            elif condition == "nonfinite":
                report["output_summary"]["finite_count"] = 99
            elif condition == "disagrees":
                report["per_image_detections"][0]["top_detection"]["normalized_box"] = [0.6, 0.6, 0.9, 0.9]
            elif condition == "false_positive":
                report["per_image_detections"][1]["top_detection"] = {
                    "normalized_box": [0.1, 0.2, 0.5, 0.7],
                    "confidence": 0.7,
                }
        return report

    monkeypatch.setattr(validation, "_probe_one_crop_provider", probe)
    monkeypatch.setattr(bird_crop_service, "reset_models", lambda: None)
    run = tmp_path / "compatibility"
    images = run / IMAGES_SUBDIR
    images.mkdir(parents=True)
    Image.new("RGB", (16, 16), "green").save(images / "bird.jpg")
    runner = ModelEvalRunner()
    monkeypatch.setattr(runner, "_emit", AsyncMock())
    metadata = model_manager._get_registry_model_meta(MODEL_ID)

    matrix = await runner._device_sweep(
        "rfdetr-cuda", run, [], [SimpleNamespace(id=MODEL_ID, metadata=SimpleNamespace(sha256=metadata["sha256"]))]
    )

    assert probed == ["cpu", "cuda"]
    cuda = matrix["crop_detectors"][MODEL_ID]["providers"]["cuda"]
    rejected = condition in {"compile_failed", "nonfinite", "disagrees", "false_positive"}
    assert cuda["ok"] is not rejected
    assert service._provider_for_tier("accurate") == ("cpu" if rejected else "cuda")
    if condition == "artifact_changed":
        monkeypatch.setattr(
            model_manager, "_get_registry_model_meta", lambda _model_id: metadata | {"sha256": "replaced"}
        )
    elif condition == "driver_changed":
        installed_rfdetr["cuda"] = "cuda-runtime-and-driver-v2"
    elif condition == "image_changed":
        monkeypatch.setenv("YAWAMF_IMAGE_FLAVOR", "intel")
    if condition.endswith("_changed"):
        assert service._provider_for_tier("accurate") == "cpu"


def test_generated_rfdetr_sidecar_keeps_cuda_candidate_only():
    from scripts.generate_model_release_configs import build_release_model_configs

    config = build_release_model_configs()[f"{MODEL_ID}_model_config.json"]

    assert "cuda" in config["candidate_inference_providers"]
    assert "cuda" not in config["supported_inference_providers"]
    assert set(config["supported_inference_providers"]) <= set(config["candidate_inference_providers"])
