import json
import types

import numpy as np
import pytest
from PIL import Image

from app.services.bird_crop_service import BirdCropService
from app.services.model_manager import ModelManager


def _make_image(width: int = 320, height: int = 160) -> Image.Image:
    return Image.new("RGB", (width, height), color="white")


def test_crop_detector_model_config_payload_includes_detector_contract():
    manager = ModelManager()

    payload = manager._build_model_config_payload(
        {
            "id": "bird_crop_detector_accurate_yolox_tiny",
            "artifact_kind": "crop_detector",
            "runtime": "onnx",
            "input_size": 416,
            "preprocessing": {"resize_mode": "letterbox"},
            "supported_inference_providers": ["cpu", "intel_cpu", "cuda"],
            "sha256": "model-sha",
            "labels_sha256": "labels-sha",
            "detector": {
                "parser": "yolox",
                "box_format": "xyxy",
                "target_class_id": 16,
                "confidence_mode": "object_times_class",
            },
        }
    )

    assert payload["model_id"] == "bird_crop_detector_accurate_yolox_tiny"
    assert payload["runtime"] == "onnx"
    assert payload["detector"] == {
        "parser": "yolox",
        "box_format": "xyxy",
        "target_class_id": 16,
        "confidence_mode": "object_times_class",
    }
    assert payload["sha256"] == "model-sha"
    assert payload["labels_sha256"] == "labels-sha"


def test_load_model_reads_detector_contract_from_model_config(monkeypatch, tmp_path):
    model_dir = tmp_path / "bird_crop_detector_accurate_yolox_tiny"
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "model.onnx"
    model_path.write_bytes(b"fake")
    (model_dir / "model_config.json").write_text(
        json.dumps(
            {
                "runtime": "onnx",
                "input_size": 416,
                "detector": {
                    "parser": "yolox",
                    "box_format": "xyxy",
                    "target_class_id": 5,
                    "confidence_mode": "score",
                },
            }
        ),
        encoding="utf-8",
    )

    class _FakeSession:
        def get_inputs(self):
            return [types.SimpleNamespace(name="images", shape=[1, 3, 160, 320], type="tensor(float)")]

        def get_outputs(self):
            return []

        def run(self, _output_names, feeds):
            return [
                np.array(
                    [[[16.0, 24.0, 80.0, 96.0, 0.88, 5.0], [8.0, 8.0, 40.0, 40.0, 0.99, 16.0]]],
                    dtype=np.float32,
                )
            ]

    class _FakeOrt:
        class SessionOptions:
            pass

        def InferenceSession(self, path, sess_options=None, providers=None):
            assert path == str(model_path)
            return _FakeSession()

    service = BirdCropService(detector_tier="accurate")
    monkeypatch.setenv("BIRD_CROP_MODEL_PATH_ACCURATE", str(model_path))
    monkeypatch.setattr(service, "_import_onnxruntime", lambda: _FakeOrt())

    loaded = service._load_model_for_tier("accurate")
    candidates = service._infer_candidates(loaded, _make_image())

    assert loaded["detector_config"] == {
        "parser": "yolox",
        "box_format": "xyxy",
        "target_class_id": 5,
        "confidence_mode": "score",
    }
    assert len(candidates) == 1
    assert candidates[0]["box"] == pytest.approx((16.0, 24.0, 80.0, 96.0))
    assert candidates[0]["confidence"] == pytest.approx(0.88)
