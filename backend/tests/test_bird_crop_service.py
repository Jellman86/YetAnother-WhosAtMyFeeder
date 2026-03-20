import types

import numpy as np
import pytest
from PIL import Image

from app.services.bird_crop_service import BirdCropService


def _make_image(width: int = 100, height: int = 100) -> Image.Image:
    return Image.new("RGB", (width, height), color="white")


def test_generate_crop_selects_and_expands_box(monkeypatch):
    service = BirdCropService(confidence_threshold=0.4, expand_ratio=0.25, min_crop_size=10)
    image = _make_image()

    monkeypatch.setattr(service, "_load_model", lambda: object())
    monkeypatch.setattr(
        service,
        "_infer_candidates",
        lambda _model, _image: [{"box": (20, 30, 40, 50), "confidence": 0.92}],
    )

    result = service.generate_crop(image)

    assert result["reason"] == "selected"
    assert result["confidence"] == pytest.approx(0.92)
    assert result["box"] == (15, 25, 45, 55)
    assert result["crop_image"].size == (30, 30)


def test_generate_crop_skips_invalid_high_confidence_candidate(monkeypatch):
    service = BirdCropService(confidence_threshold=0.4, expand_ratio=0.0, min_crop_size=10)
    image = _make_image()

    monkeypatch.setattr(service, "_load_model", lambda: object())
    monkeypatch.setattr(
        service,
        "_infer_candidates",
        lambda _model, _image: [
            {"box": (10, 10, 12, 12), "confidence": 0.99},
            {"box": (20, 20, 40, 50), "confidence": 0.80},
        ],
    )

    result = service.generate_crop(image)

    assert result["reason"] == "selected"
    assert result["confidence"] == pytest.approx(0.80)
    assert result["box"] == (20, 20, 40, 50)
    assert result["crop_image"].size == (20, 30)


def test_generate_crop_clamps_expanded_box_to_image_bounds(monkeypatch):
    service = BirdCropService(confidence_threshold=0.4, expand_ratio=0.5, min_crop_size=10)
    image = _make_image(width=60, height=40)

    monkeypatch.setattr(service, "_load_model", lambda: object())
    monkeypatch.setattr(
        service,
        "_infer_candidates",
        lambda _model, _image: [{"box": (50, 20, 60, 40), "confidence": 0.88}],
    )

    result = service.generate_crop(image)

    assert result["reason"] == "selected"
    assert result["confidence"] == pytest.approx(0.88)
    assert result["box"] == (45, 10, 60, 40)
    assert result["crop_image"].size == (15, 30)


@pytest.mark.parametrize(
    "box, expected_reason",
    [
        ((10, 10, 13, 13), "too_small"),
        ((10, 10, 10, 20), "invalid_box"),
    ],
)
def test_generate_crop_rejects_tiny_or_degenerate_boxes(monkeypatch, box, expected_reason):
    service = BirdCropService(confidence_threshold=0.4, expand_ratio=0.25, min_crop_size=10)
    image = _make_image()

    monkeypatch.setattr(service, "_load_model", lambda: object())
    monkeypatch.setattr(
        service,
        "_infer_candidates",
        lambda _model, _image: [{"box": box, "confidence": 0.91}],
    )

    result = service.generate_crop(image)

    assert result["crop_image"] is None
    assert result["box"] is None
    assert result["confidence"] == pytest.approx(0.91)
    assert result["reason"] == expected_reason


@pytest.mark.parametrize(
    "loader_side_effect, inference_side_effect, expected_reason",
    [
        (RuntimeError("load boom"), None, "load_failed"),
        (None, RuntimeError("infer boom"), "inference_failed"),
    ],
)
def test_generate_crop_soft_fails_when_model_load_or_inference_fails(
    monkeypatch,
    loader_side_effect,
    inference_side_effect,
    expected_reason,
):
    service = BirdCropService(confidence_threshold=0.4, expand_ratio=0.25, min_crop_size=10)
    image = _make_image()

    def _load_model():
        if loader_side_effect is not None:
            raise loader_side_effect
        return object()

    def _infer_candidates(_model, _image):
        if inference_side_effect is not None:
            raise inference_side_effect
        return []

    monkeypatch.setattr(service, "_load_model", _load_model)
    monkeypatch.setattr(service, "_infer_candidates", _infer_candidates)

    result = service.generate_crop(image)

    assert result["crop_image"] is None
    assert result["box"] is None
    assert result["confidence"] is None
    assert result["reason"] == expected_reason


def test_generate_crop_retries_loading_after_initial_empty_load(monkeypatch):
    service = BirdCropService(confidence_threshold=0.4, expand_ratio=0.0, min_crop_size=10)
    image = _make_image()
    load_calls = []

    def _load_model():
        load_calls.append(len(load_calls))
        return None if len(load_calls) == 1 else object()

    monkeypatch.setattr(service, "_load_model", _load_model)
    monkeypatch.setattr(
        service,
        "_infer_candidates",
        lambda _model, _image: [{"box": (20, 20, 40, 50), "confidence": 0.91}],
    )

    first = service.generate_crop(image)
    second = service.generate_crop(image)

    assert first["reason"] == "load_failed"
    assert first["crop_image"] is None
    assert second["reason"] == "selected"
    assert second["box"] == (20, 20, 40, 50)
    assert second["confidence"] == pytest.approx(0.91)
    assert second["crop_image"].size == (20, 30)
    assert len(load_calls) == 2


def test_load_model_uses_local_onnx_detector_path(monkeypatch, tmp_path):
    model_path = tmp_path / "bird_crop.onnx"
    model_path.write_bytes(b"fake")

    class _FakeSession:
        def get_inputs(self):
            return [types.SimpleNamespace(name="images", shape=[1, 3, 640, 640])]

    class _FakeOrt:
        class SessionOptions:
            pass

        def InferenceSession(self, path, sess_options=None, providers=None):
            assert path == str(model_path)
            assert providers == ["CPUExecutionProvider"]
            return _FakeSession()

    service = BirdCropService()
    monkeypatch.setenv("BIRD_CROP_MODEL_PATH", str(model_path))
    monkeypatch.setattr(service, "_import_onnxruntime", lambda: _FakeOrt())

    loaded = service._load_model()

    assert loaded["input_name"] == "images"
    assert loaded["input_height"] == 640
    assert loaded["input_width"] == 640
    assert loaded["session"].__class__.__name__ == "_FakeSession"


def test_load_model_autodiscovers_standard_detector_path_without_env(monkeypatch, tmp_path):
    model_dir = tmp_path / "bird_crop"
    model_dir.mkdir(parents=True)
    model_path = model_dir / "model.onnx"
    model_path.write_bytes(b"fake")

    class _FakeSession:
        def get_inputs(self):
            return [types.SimpleNamespace(name="images", shape=[1, 3, 640, 640])]

    class _FakeOrt:
        class SessionOptions:
            pass

        def InferenceSession(self, path, sess_options=None, providers=None):
            assert path == str(model_path)
            assert providers == ["CPUExecutionProvider"]
            return _FakeSession()

    service = BirdCropService()
    monkeypatch.delenv("BIRD_CROP_MODEL_PATH", raising=False)
    monkeypatch.setattr(service, "_import_onnxruntime", lambda: _FakeOrt())
    monkeypatch.setattr(service, "_candidate_model_paths", lambda: [str(model_path)])

    loaded = service._load_model()

    assert loaded is not None
    assert loaded["model_path"] == str(model_path)


def test_load_model_handles_nhwc_input_shape(monkeypatch, tmp_path):
    model_path = tmp_path / "bird_crop.onnx"
    model_path.write_bytes(b"fake")

    class _FakeSession:
        def get_inputs(self):
            return [types.SimpleNamespace(name="images", shape=[1, 640, 640, 3])]

    class _FakeOrt:
        class SessionOptions:
            pass

        def InferenceSession(self, path, sess_options=None, providers=None):
            return _FakeSession()

    service = BirdCropService()
    monkeypatch.setenv("BIRD_CROP_MODEL_PATH", str(model_path))
    monkeypatch.setattr(service, "_import_onnxruntime", lambda: _FakeOrt())

    loaded = service._load_model()

    assert loaded["input_height"] == 640
    assert loaded["input_width"] == 640


def test_infer_candidates_parses_single_output_detection_tensor():
    class _FakeSession:
        def run(self, _output_names, feeds):
            assert "images" in feeds
            return [
                np.array(
                    [[[16.0, 32.0, 80.0, 96.0, 0.91, 0.0]]],
                    dtype=np.float32,
                )
            ]

    service = BirdCropService()
    image = _make_image(width=320, height=160)
    model = {
        "session": _FakeSession(),
        "input_name": "images",
        "input_height": 160,
        "input_width": 320,
    }

    candidates = service._infer_candidates(model, image)

    assert len(candidates) == 1
    assert candidates[0]["box"] == pytest.approx((16.0, 32.0, 80.0, 96.0))
    assert candidates[0]["confidence"] == pytest.approx(0.91)


def test_infer_candidates_supports_cxcywh_box_format(monkeypatch):
    class _FakeSession:
        def run(self, _output_names, feeds):
            return [
                np.array(
                    [[[48.0, 64.0, 64.0, 64.0, 0.91, 0.0]]],
                    dtype=np.float32,
                )
            ]

    service = BirdCropService()
    monkeypatch.setenv("BIRD_CROP_BOX_FORMAT", "cxcywh")
    image = _make_image(width=320, height=160)
    model = {
        "session": _FakeSession(),
        "input_name": "images",
        "input_height": 160,
        "input_width": 320,
    }

    candidates = service._infer_candidates(model, image)

    assert len(candidates) == 1
    assert candidates[0]["box"] == pytest.approx((16.0, 32.0, 80.0, 96.0))


def test_infer_candidates_rejects_unsupported_multiclass_row_layout():
    class _FakeSession:
        def run(self, _output_names, feeds):
            return [
                np.array(
                    [[[16.0, 32.0, 80.0, 96.0, 0.91, 0.10, 0.90]]],
                    dtype=np.float32,
                )
            ]

    service = BirdCropService()
    image = _make_image(width=320, height=160)
    model = {
        "session": _FakeSession(),
        "input_name": "images",
        "input_height": 160,
        "input_width": 320,
    }

    candidates = service._infer_candidates(model, image)

    assert candidates == []


def test_load_model_captures_nhwc_uint8_detector_metadata(monkeypatch, tmp_path):
    model_path = tmp_path / "bird_crop.onnx"
    model_path.write_bytes(b"fake")

    class _FakeSession:
        def get_inputs(self):
            return [types.SimpleNamespace(name="inputs", shape=["N", "H", "W", 3], type="tensor(uint8)")]

        def get_outputs(self):
            return [
                types.SimpleNamespace(name="detection_boxes"),
                types.SimpleNamespace(name="detection_classes"),
                types.SimpleNamespace(name="detection_scores"),
                types.SimpleNamespace(name="num_detections"),
            ]

    class _FakeOrt:
        class SessionOptions:
            pass

        def InferenceSession(self, path, sess_options=None, providers=None):
            return _FakeSession()

    service = BirdCropService()
    monkeypatch.setenv("BIRD_CROP_MODEL_PATH", str(model_path))
    monkeypatch.setattr(service, "_import_onnxruntime", lambda: _FakeOrt())

    loaded = service._load_model()

    assert loaded["input_name"] == "inputs"
    assert loaded["input_layout"] == "nhwc"
    assert loaded["input_type"] == "tensor(uint8)"
    assert loaded["dynamic_input_hw"] is True
    assert loaded["output_names"] == [
        "detection_boxes",
        "detection_classes",
        "detection_scores",
        "num_detections",
    ]


def test_infer_candidates_parses_ssd_detection_outputs_and_filters_to_bird_class():
    class _FakeSession:
        def run(self, _output_names, feeds):
            payload = feeds["inputs"]
            assert payload.dtype == np.uint8
            assert payload.shape == (1, 160, 320, 3)
            return [
                np.array([[[0.10, 0.20, 0.90, 0.70], [0.0, 0.0, 0.5, 0.5]]], dtype=np.float32),
                np.array([[16.0, 1.0]], dtype=np.float32),
                np.array([[0.95, 0.99]], dtype=np.float32),
                np.array([2.0], dtype=np.float32),
            ]

    service = BirdCropService()
    image = _make_image(width=320, height=160)
    model = {
        "session": _FakeSession(),
        "input_name": "inputs",
        "input_layout": "nhwc",
        "input_type": "tensor(uint8)",
        "dynamic_input_hw": True,
        "output_names": [
            "detection_boxes",
            "detection_classes",
            "detection_scores",
            "num_detections",
        ],
    }

    candidates = service._infer_candidates(model, image)

    assert len(candidates) == 1
    assert candidates[0]["confidence"] == pytest.approx(0.95)
    assert candidates[0]["box"] == pytest.approx((64.0, 16.0, 224.0, 144.0))


def test_prepare_detector_input_resizes_fixed_nhwc_uint8_models():
    service = BirdCropService()
    image = _make_image(width=320, height=160)

    tensor, transform = service._prepare_detector_input(
        image,
        input_width=224,
        input_height=224,
        input_layout="nhwc",
        input_type="tensor(uint8)",
        dynamic_input_hw=False,
    )

    assert tensor.dtype == np.uint8
    assert tensor.shape == (1, 224, 224, 3)
    assert transform["resize_mode"] == "direct_resize"
    assert transform["scale"] == pytest.approx(1.0)
    assert transform["scale_x"] == pytest.approx(224.0 / 320.0)
    assert transform["scale_y"] == pytest.approx(224.0 / 160.0)


def test_infer_candidates_returns_empty_when_named_ssd_outputs_have_no_bird_class():
    class _FakeSession:
        def run(self, _output_names, feeds):
            return [
                np.array([[[0.10, 0.20, 0.90, 0.70]]], dtype=np.float32),
                np.array([[1.0]], dtype=np.float32),
                np.array([[0.95]], dtype=np.float32),
                np.array([1.0], dtype=np.float32),
            ]

    service = BirdCropService()
    image = _make_image(width=320, height=160)
    model = {
        "session": _FakeSession(),
        "input_name": "inputs",
        "input_layout": "nhwc",
        "input_type": "tensor(uint8)",
        "dynamic_input_hw": True,
        "output_names": [
            "detection_boxes",
            "detection_classes",
            "detection_scores",
            "num_detections",
        ],
    }

    candidates = service._infer_candidates(model, image)

    assert candidates == []


def test_infer_candidates_allows_overriding_target_bird_class(monkeypatch):
    class _FakeSession:
        def run(self, _output_names, feeds):
            return [
                np.array([[[0.10, 0.20, 0.90, 0.70]]], dtype=np.float32),
                np.array([[15.0]], dtype=np.float32),
                np.array([[0.95]], dtype=np.float32),
                np.array([1.0], dtype=np.float32),
            ]

    service = BirdCropService()
    monkeypatch.setenv("BIRD_CROP_CLASS_ID", "15")
    image = _make_image(width=320, height=160)
    model = {
        "session": _FakeSession(),
        "input_name": "inputs",
        "input_layout": "nhwc",
        "input_type": "tensor(uint8)",
        "dynamic_input_hw": True,
        "output_names": [
            "detection_boxes",
            "detection_classes",
            "detection_scores",
            "num_detections",
        ],
    }

    candidates = service._infer_candidates(model, image)

    assert len(candidates) == 1


def test_infer_candidates_does_not_fall_through_when_named_ssd_outputs_are_malformed():
    class _FakeSession:
        def run(self, _output_names, feeds):
            return [
                np.array(
                    [[[16.0, 32.0, 80.0, 96.0, 0.91, 0.0]]],
                    dtype=np.float32,
                ),
                np.array([[16.0]], dtype=np.float32),
                np.array([[0.95]], dtype=np.float32),
            ]

    service = BirdCropService()
    image = _make_image(width=320, height=160)
    model = {
        "session": _FakeSession(),
        "input_name": "inputs",
        "input_layout": "nhwc",
        "input_type": "tensor(uint8)",
        "dynamic_input_hw": True,
        "output_names": [
            "detection_boxes",
            "detection_classes",
            "detection_scores",
        ],
    }

    candidates = service._infer_candidates(model, image)

    assert candidates == []


def test_infer_candidates_parses_fixed_size_ssd_outputs_and_restores_image_box():
    class _FakeSession:
        def run(self, _output_names, feeds):
            payload = feeds["inputs"]
            assert payload.dtype == np.uint8
            assert payload.shape == (1, 224, 224, 3)
            return [
                np.array([[[0.25, 0.25, 0.75, 0.75]]], dtype=np.float32),
                np.array([[16.0]], dtype=np.float32),
                np.array([[0.93]], dtype=np.float32),
                np.array([1.0], dtype=np.float32),
            ]

    service = BirdCropService()
    image = _make_image(width=320, height=160)
    model = {
        "session": _FakeSession(),
        "input_name": "inputs",
        "input_layout": "nhwc",
        "input_type": "tensor(uint8)",
        "input_width": 224,
        "input_height": 224,
        "dynamic_input_hw": False,
        "output_names": [
            "detection_boxes",
            "detection_classes",
            "detection_scores",
            "num_detections",
        ],
    }

    candidates = service._infer_candidates(model, image)

    assert len(candidates) == 1
    assert candidates[0]["confidence"] == pytest.approx(0.93)
    assert candidates[0]["box"] == pytest.approx((80.0, 40.0, 240.0, 120.0))
