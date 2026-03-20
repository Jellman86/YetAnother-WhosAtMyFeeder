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
