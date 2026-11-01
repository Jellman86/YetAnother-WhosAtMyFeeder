from pathlib import Path

import numpy as np
from PIL import Image

from scripts import probe_bird_model_provider as probe


class _FakeModel:
    def __init__(self):
        self.error = None
        self.cleaned = False
        self.calls = 0

    def load(self):
        return True

    def classify_raw(self, _image):
        self.calls += 1
        return np.asarray([0.1, 0.8, 0.1], dtype=np.float32)

    def cleanup(self):
        self.cleaned = True


def _spec(model_id: str = "rope"):
    return {
        "model_id": model_id,
        "model_path": "/models/rope/model.onnx",
        "labels_path": "/models/rope/labels.txt",
        "runtime": "onnx",
        "input_size": 8,
        "preprocessing": {},
        "label_grouping": {},
    }


def test_probe_uses_real_images_and_reports_provider_latency(tmp_path: Path, monkeypatch):
    image_path = tmp_path / "bird.jpg"
    Image.new("RGB", (12, 8), "blue").save(image_path)
    model = _FakeModel()
    monkeypatch.setattr(probe.model_manager, "get_active_model_spec", lambda: _spec())
    monkeypatch.setattr(probe, "_build_model", lambda _spec, _provider: model)

    report = probe.probe_provider("cpu", [str(image_path)], expected_model_id="rope")

    assert report["compile"]["ok"] is True
    assert report["provider"] == "cpu"
    assert report["per_image_top_indices"] == [[1, 2, 0]]
    assert report["output_summary"]["finite_count"] == 3
    assert report["inference_latency_ms"] >= 0
    assert model.calls == 2  # one warm-up + one measured real image
    assert model.cleaned is True


def test_probe_fails_closed_when_active_model_changes(monkeypatch):
    monkeypatch.setattr(probe.model_manager, "get_active_model_spec", lambda: _spec("other"))

    report = probe.probe_provider("cuda", expected_model_id="rope")

    assert report["compile"]["ok"] is False
    assert "Active model changed" in report["compile"]["error"]


def test_provider_builder_maps_cuda_to_the_cuda_execution_provider(monkeypatch):
    captured = {}

    class _FakeOnnx:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(probe, "ONNXModelInstance", _FakeOnnx)

    probe._build_model(_spec(), "cuda")

    assert captured["ort_providers"] == ["CUDAExecutionProvider"]
