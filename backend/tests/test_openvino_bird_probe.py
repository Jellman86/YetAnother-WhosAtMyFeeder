from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from backend.scripts.probe_openvino_bird_model import (
    compare_probe_outputs,
    probe_openvino_bird_model,
    summarize_array,
)


def test_summarize_array_reports_bounded_numeric_metadata():
    summary = summarize_array(
        np.array([[1.0, np.nan, np.inf, -np.inf]], dtype=np.float32),
        name="logits",
    )

    assert summary["name"] == "logits"
    assert summary["shape"] == [1, 4]
    assert summary["dtype"] == "float32"
    assert summary["finite_count"] == 1
    assert summary["nan_count"] == 1
    assert summary["pos_inf_count"] == 1
    assert summary["neg_inf_count"] == 1
    assert summary["finite_min"] == 1.0
    assert summary["finite_max"] == 1.0


def test_compare_probe_outputs_reports_delta_for_shared_shape():
    cpu = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
    gpu = np.array([[0.1, 0.25, 0.35]], dtype=np.float32)

    comparison = compare_probe_outputs(cpu, gpu)

    assert comparison["shape_matches"] is True
    assert comparison["cpu_shape"] == [1, 3]
    assert comparison["gpu_shape"] == [1, 3]
    assert comparison["max_abs_diff"] == 0.05


def test_probe_openvino_bird_model_returns_json_safe_report(monkeypatch):
    fake_meta = {
        "id": "convnext_large_inat21",
        "input_size": 384,
        "preprocessing": {
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
            "normalization": "float32",
        },
    }
    monkeypatch.setattr(
        "backend.scripts.probe_openvino_bird_model.resolve_active_bird_model_spec",
        lambda: {
            "model_id": fake_meta["id"],
            "model_path": "/tmp/model.onnx",
            "labels_path": "/tmp/labels.txt",
            "input_size": fake_meta["input_size"],
            "preprocessing": dict(fake_meta["preprocessing"]),
        },
    )

    fake_compiled_model = MagicMock()
    fake_compiled_model.get_property.side_effect = lambda name: {
        "INFERENCE_PRECISION_HINT": "f32",
        "NUM_STREAMS": "1",
        "PERFORMANCE_HINT": "LATENCY",
        "EXECUTION_DEVICES": ["GPU.0"],
    }[name]

    fake_model = SimpleNamespace(
        loaded=True,
        error=None,
        preprocessing=fake_meta["preprocessing"],
        input_size=384,
        device_name="GPU",
        model_path="/tmp/model.onnx",
        labels_path="/tmp/labels.txt",
        compiled_model=fake_compiled_model,
    )
    fake_input = np.ones((1, 3, 384, 384), dtype=np.float32)
    fake_logits = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)
    fake_model._preprocess = lambda image: fake_input
    fake_model._infer_logits = lambda image: fake_logits[0]
    fake_model.load = lambda: True

    monkeypatch.setattr(
        "backend.scripts.probe_openvino_bird_model.build_probe_model",
        lambda spec, device: fake_model,
    )

    report = probe_openvino_bird_model(device="GPU")

    assert report["device"] == "GPU"
    assert report["model"]["model_id"] == "convnext_large_inat21"
    assert report["compile"]["ok"] is True
    assert report["compile"]["properties"]["INFERENCE_PRECISION_HINT"] == "f32"
    assert report["input_summary"]["shape"] == [1, 3, 384, 384]
    assert report["output_summary"]["finite_count"] == 3
    assert report["output_summary"]["nan_count"] == 0

