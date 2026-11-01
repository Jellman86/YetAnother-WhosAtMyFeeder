import cv2
import numpy as np
import pytest
from PIL import Image

from app.config import settings
from app.services.bird_crop_service import BirdCropService

RFDETR_PREPROCESSING = {
    "color_space": "RGB",
    "resize_mode": "stretch",
    "interpolation": "bilinear",
    "normalization": "imagenet",
}
RFDETR_DETECTOR = {
    "parser": "detr",
    "box_format": "cxcywh_normalized",
    "target_class_id": 16,
    "min_confidence": 0.3,
    "frame_scan": {"tile_grid": 2, "tile_overlap": 0.2},
}


def _logit(probability: float) -> float:
    return float(np.log(probability / (1.0 - probability)))


def _detr_outputs(queries: list[tuple[tuple[float, float, float, float], int, float]], classes: int = 91):
    boxes = np.zeros((1, len(queries), 4), dtype=np.float32)
    logits = np.full((1, len(queries), classes), -12.0, dtype=np.float32)
    for index, (box, class_id, probability) in enumerate(queries):
        boxes[0, index] = box
        logits[0, index, class_id] = _logit(probability)
    return [boxes, logits]


def _rfdetr_model(session) -> dict:
    return {
        "session": session,
        "input_name": "input",
        "input_height": 384,
        "input_width": 384,
        "input_layout": "nchw",
        "input_type": "tensor(float)",
        "preprocessing": dict(RFDETR_PREPROCESSING),
        "output_names": ["dets", "labels"],
        "detector_tier": "accurate",
        "detector_config": dict(RFDETR_DETECTOR),
        "provider": "cpu",
    }


def test_stretch_imagenet_preprocessing_matches_the_official_rfdetr_input():
    rng = np.random.default_rng(7)
    pixels = rng.integers(0, 256, size=(90, 160, 3), dtype=np.uint8)
    image = Image.fromarray(pixels, "RGB")
    service = BirdCropService(detector_tier="accurate")

    tensor, transform = service._prepare_detector_input(
        image, input_width=384, input_height=384, preprocessing=RFDETR_PREPROCESSING
    )

    expected = cv2.resize(pixels.astype(np.float32) / 255.0, (384, 384), interpolation=cv2.INTER_LINEAR)
    expected = (expected - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    assert tensor.shape == (1, 3, 384, 384)
    assert tensor.dtype == np.float32
    np.testing.assert_allclose(tensor[0], expected.transpose(2, 0, 1), atol=1e-5)
    assert transform["scale_x"] == pytest.approx(384 / 160)
    assert transform["scale_y"] == pytest.approx(384 / 90)
    assert transform["pad_x"] == 0.0 and transform["pad_y"] == 0.0


def test_detr_parser_keeps_confident_bird_queries_in_source_coordinates():
    service = BirdCropService(detector_tier="accurate")
    outputs = _detr_outputs(
        [
            ((0.25, 0.5, 0.1, 0.2), 16, 0.81),
            ((0.75, 0.5, 0.1, 0.2), 16, 0.12),
            ((0.5, 0.5, 0.2, 0.2), 1, 0.97),
        ]
    )
    transform = {
        "scale_x": 384 / 1000,
        "scale_y": 384 / 500,
        "pad_x": 0.0,
        "pad_y": 0.0,
        "resize_mode": "direct_resize",
    }

    parsed = service._parse_detector_outputs(
        outputs,
        transform=transform,
        image_size=(1000, 500),
        output_names=["dets", "labels"],
        detector_tier="accurate",
        detector_config=RFDETR_DETECTOR,
    )

    assert len(parsed) == 1
    assert parsed[0]["box"] == pytest.approx((200.0, 200.0, 300.0, 300.0), abs=1e-3)
    assert parsed[0]["confidence"] == pytest.approx(0.81, abs=1e-4)


def test_detr_parser_rejects_malformed_outputs():
    service = BirdCropService(detector_tier="accurate")
    boxes, logits = _detr_outputs([((0.5, 0.5, 0.2, 0.2), 16, 0.9)])
    transform = {"scale_x": 1.0, "scale_y": 1.0, "resize_mode": "direct_resize"}

    assert (
        service._parse_detector_outputs(
            [boxes, logits[:, :, :10]],
            transform=transform,
            image_size=(384, 384),
            output_names=["dets", "labels"],
            detector_tier="accurate",
            detector_config=RFDETR_DETECTOR,
        )
        == []
    )
    boxes[0, 0, 0] = np.nan
    assert (
        service._parse_detector_outputs(
            [boxes, logits],
            transform=transform,
            image_size=(384, 384),
            output_names=["dets", "labels"],
            detector_tier="accurate",
            detector_config=RFDETR_DETECTOR,
        )
        == []
    )


def test_frame_scan_model_reads_full_frame_and_overlapping_tiles_and_merges_duplicates():
    seen_sizes: list[tuple[int, int]] = []

    class _Session:
        def run(self, _names, feeds):
            tensor = feeds["input"]
            assert tensor.shape == (1, 3, 384, 384)
            seen_sizes.append(len(seen_sizes))
            # Every view reports the same normalized box; restored to the frame they
            # land in different places, except the full frame and the top-left tile overlap.
            return _detr_outputs([((0.1, 0.1, 0.05, 0.05), 16, 0.9)])

    service = BirdCropService(detector_tier="accurate")
    image = Image.new("RGB", (2560, 1440), "white")

    candidates = service._infer_candidates(_rfdetr_model(_Session()), image)

    assert len(seen_sizes) == 5
    boxes = [tuple(round(v) for v in item["box"]) for item in candidates]
    assert len(boxes) == len(set(boxes))
    assert all(item["confidence"] == pytest.approx(0.9, abs=1e-4) for item in candidates)


def test_frame_scan_is_skipped_for_frames_too_small_to_tile():
    calls = []

    class _Session:
        def run(self, _names, feeds):
            calls.append(1)
            return _detr_outputs([((0.5, 0.5, 0.2, 0.2), 16, 0.9)])

    service = BirdCropService(detector_tier="accurate")

    candidates = service._infer_candidates(_rfdetr_model(_Session()), Image.new("RGB", (500, 400), "white"))

    assert len(calls) == 1
    assert len(candidates) == 1


def test_intensive_mode_does_not_tile_a_frame_scan_model_twice(monkeypatch):
    calls = []

    class _Session:
        def run(self, _names, feeds):
            calls.append(1)
            return _detr_outputs([((0.5, 0.5, 0.05, 0.05), 16, 0.9)])

    service = BirdCropService(detector_tier="accurate")
    monkeypatch.setattr(settings.media_cache, "bird_scan_mode", "intensive")

    service._infer_frame_candidates(_rfdetr_model(_Session()), Image.new("RGB", (3840, 2160), "white"))

    assert len(calls) == 5


def test_sliced_fallback_is_not_run_on_top_of_a_frame_scan_model(monkeypatch):
    calls = []

    class _Session:
        def run(self, _names, feeds):
            calls.append(1)
            return _detr_outputs([((0.5, 0.5, 0.05, 0.05), 16, 0.05)])

    service = BirdCropService(detector_tier="accurate")
    monkeypatch.setattr(
        service, "_load_model_for_tier", lambda tier: _rfdetr_model(_Session()) if tier == "accurate" else None
    )

    result = service.generate_classification_candidate_crop(Image.new("RGB", (2560, 1440), "white"))

    assert result["reason"] != "selected"
    assert len(calls) == 5


def test_accurate_model_follows_the_owner_choice_and_reloads_when_it_changes(monkeypatch):
    from app.services.model_manager import model_manager

    service = BirdCropService()
    loads: list[str] = []
    monkeypatch.setattr(
        service,
        "_load_model_for_tier",
        lambda tier: loads.append(service._registry_model_id_for_tier(tier)) or {"tier": tier},
    )
    monkeypatch.setattr(
        model_manager,
        "get_crop_detector_spec",
        lambda tier=None: {"model_id": model_manager._crop_detector_id_for_tier(tier), "model_path": ""},
    )
    original = settings.classification.bird_crop_accurate_detector
    try:
        settings.classification.bird_crop_accurate_detector = "yolox_tiny"
        service._ensure_model_for_tier("accurate")
        service._ensure_model_for_tier("accurate")
        settings.classification.bird_crop_accurate_detector = "rfdetr_nano"
        service._ensure_model_for_tier("accurate")
    finally:
        settings.classification.bird_crop_accurate_detector = original

    assert loads == ["bird_crop_detector_accurate_yolox_tiny", "bird_crop_detector_accurate_rfdetr_nano"]


def test_a_fixed_accurate_model_loads_its_own_artifact_not_the_runtime_choice(tmp_path, monkeypatch):
    """Hardware validation must exercise the exact artifact it records a result for."""
    for model_id in ("bird_crop_detector_accurate_yolox_tiny", "bird_crop_detector_accurate_rfdetr_nano"):
        model_dir = tmp_path / model_id
        model_dir.mkdir()
        (model_dir / "model.onnx").write_bytes(model_id.encode())
        (model_dir / "model_config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr("app.services.model_manager.MODELS_DIR", str(tmp_path))
    monkeypatch.delenv("BIRD_CROP_MODEL_PATH_ACCURATE", raising=False)
    original = settings.classification.bird_crop_accurate_detector
    settings.classification.bird_crop_accurate_detector = "yolox_tiny"
    try:
        service = BirdCropService(detector_tier="accurate", accurate_model_id="bird_crop_detector_accurate_rfdetr_nano")
        resolved = service._resolve_model_path("accurate")
    finally:
        settings.classification.bird_crop_accurate_detector = original

    assert resolved is not None
    assert resolved.parent.name == "bird_crop_detector_accurate_rfdetr_nano"


def test_the_provider_probe_pins_the_model_it_validates():
    import inspect

    from scripts import probe_crop_model_provider

    source = inspect.getsource(probe_crop_model_provider.probe_provider)
    assert "accurate_model_id=model_id" in source
