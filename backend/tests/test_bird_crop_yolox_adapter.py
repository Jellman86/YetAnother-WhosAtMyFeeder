import numpy as np
import pytest
from PIL import Image

from app.services.bird_crop_service import BirdCropService


def _make_image(width: int = 320, height: int = 160) -> Image.Image:
    return Image.new("RGB", (width, height), color="white")


def test_infer_candidates_parses_yolox_xyxy_rows_and_filters_to_bird_class():
    class _FakeSession:
        def run(self, _output_names, feeds):
            assert "images" in feeds
            return [
                np.array(
                    [[[16.0, 24.0, 80.0, 96.0, 0.92, 16.0], [8.0, 8.0, 40.0, 40.0, 0.99, 1.0]]],
                    dtype=np.float32,
                )
            ]

    service = BirdCropService(detector_tier="accurate")
    image = _make_image()
    model = {
        "session": _FakeSession(),
        "input_name": "images",
        "input_height": 160,
        "input_width": 320,
        "detector_tier": "accurate",
    }

    candidates = service._infer_candidates(model, image)

    assert len(candidates) == 1
    assert candidates[0]["box"] == pytest.approx((16.0, 24.0, 80.0, 96.0))
    assert candidates[0]["confidence"] == pytest.approx(0.92)


def test_infer_candidates_parses_yolox_object_and_class_confidence_rows():
    class _FakeSession:
        def run(self, _output_names, feeds):
            return [
                np.array(
                    [[[12.0, 20.0, 88.0, 120.0, 0.8, 0.75, 16.0]]],
                    dtype=np.float32,
                )
            ]

    service = BirdCropService(detector_tier="accurate")
    image = _make_image()
    model = {
        "session": _FakeSession(),
        "input_name": "images",
        "input_height": 160,
        "input_width": 320,
        "detector_tier": "accurate",
    }

    candidates = service._infer_candidates(model, image)

    assert len(candidates) == 1
    assert candidates[0]["box"] == pytest.approx((12.0, 20.0, 88.0, 120.0))
    assert candidates[0]["confidence"] == pytest.approx(0.6)


def test_infer_candidates_returns_empty_for_unknown_accurate_output_shape():
    class _FakeSession:
        def run(self, _output_names, feeds):
            return [
                np.array(
                    [[[16.0, 24.0, 80.0, 96.0, 0.92, 0.1, 0.8, 16.0]]],
                    dtype=np.float32,
                )
            ]

    service = BirdCropService(detector_tier="accurate")
    image = _make_image()
    model = {
        "session": _FakeSession(),
        "input_name": "images",
        "input_height": 160,
        "input_width": 320,
        "detector_tier": "accurate",
    }

    candidates = service._infer_candidates(model, image)

    assert candidates == []


def test_infer_candidates_decodes_official_yolox_raw_output_grid():
    service = BirdCropService(detector_tier="accurate")
    image = _make_image(416, 416)
    raw = np.zeros((1, 3549, 85), dtype=np.float32)

    # First prediction belongs to stride-8 grid cell (0,0).
    raw[0, 0, 0] = 10.0   # center x offset
    raw[0, 0, 1] = 12.0   # center y offset
    raw[0, 0, 2] = np.log(4.0)  # width factor
    raw[0, 0, 3] = np.log(6.0)  # height factor
    raw[0, 0, 4] = 0.9    # objectness
    raw[0, 0, 5 + 14] = 0.8  # COCO bird class index

    class _FakeSession:
        def run(self, _output_names, feeds):
            return [raw.copy()]

    model = {
        "session": _FakeSession(),
        "input_name": "images",
        "input_height": 416,
        "input_width": 416,
        "detector_tier": "accurate",
        "detector_config": {
            "parser": "yolox",
            "box_format": "xyxy",
            "target_class_id": 14,
            "confidence_mode": "object_times_class",
        },
    }

    candidates = service._infer_candidates(model, image)

    assert len(candidates) == 1
    # decoded center=(80,96), size=(32,48) => xyxy=(64,72,96,120)
    assert candidates[0]["box"] == pytest.approx((64.0, 72.0, 96.0, 120.0))
    assert candidates[0]["confidence"] == pytest.approx(0.72)


def test_infer_candidates_decodes_top_left_letterbox_yolox_using_actual_input_size():
    service = BirdCropService(detector_tier="accurate")
    image = _make_image(640, 480)
    raw = np.zeros((1, 3549, 85), dtype=np.float32)

    # Grid cell (26,22) at stride 8 should decode near the lower middle of a 416x416 tensor.
    prediction_index = (22 * 52) + 26
    raw[0, prediction_index, 0] = 0.5
    raw[0, prediction_index, 1] = 0.5
    raw[0, prediction_index, 2] = np.log(10.0)
    raw[0, prediction_index, 3] = np.log(8.0)
    raw[0, prediction_index, 4] = 0.9
    raw[0, prediction_index, 5 + 14] = 0.8

    class _FakeSession:
        def run(self, _output_names, feeds):
            return [raw.copy()]

    model = {
        "session": _FakeSession(),
        "input_name": "images",
        "input_height": 416,
        "input_width": 416,
        "detector_tier": "accurate",
        "preprocessing": {
            "resize_mode": "letterbox",
            "pad_alignment": "top_left",
            "color_space": "BGR",
            "normalization": "none",
        },
        "detector_config": {
            "parser": "yolox",
            "box_format": "cxcywh",
            "target_class_id": 14,
            "confidence_mode": "object_times_class",
        },
    }

    candidates = service._infer_candidates(model, image)

    assert len(candidates) == 1
    assert candidates[0]["confidence"] == pytest.approx(0.72)
    left, top, right, bottom = candidates[0]["box"]
    assert left < right
    assert top < bottom
    assert 250 <= left <= 280
    assert 200 <= top <= 260
