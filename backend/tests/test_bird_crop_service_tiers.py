from PIL import Image

from app.config import settings
from app.services.bird_crop_service import BirdCropService


def _img() -> Image.Image:
    return Image.new("RGB", (128, 128), "white")


def test_generate_crop_defaults_to_fast_tier_when_available(monkeypatch):
    service = BirdCropService()

    monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: {"tier": tier})
    monkeypatch.setattr(
        service,
        "_infer_candidates",
        lambda model, image: [{"box": (8, 8, 120, 120), "confidence": 0.9, "tier": model["tier"]}],
    )

    result = service.generate_crop(_img())

    assert result["reason"] == "selected"
    assert result["detector_tier"] == "fast"
    assert result["fallback_reason"] is None


def test_generate_crop_uses_runtime_setting_when_no_explicit_tier_is_bound(monkeypatch):
    service = BirdCropService()
    original_tier = settings.classification.bird_crop_detector_tier
    settings.classification.bird_crop_detector_tier = "accurate"

    try:
        monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: {"tier": tier})
        monkeypatch.setattr(
            service,
            "_infer_candidates",
            lambda model, image: [{"box": (8, 8, 120, 120), "confidence": 0.9, "tier": model["tier"]}],
        )

        result = service.generate_crop(_img())
    finally:
        settings.classification.bird_crop_detector_tier = original_tier

    assert result["reason"] == "selected"
    assert result["detector_tier"] == "accurate"


def test_generate_crop_falls_back_to_fast_when_accurate_unavailable(monkeypatch):
    service = BirdCropService(detector_tier="accurate")

    def _load(tier: str):
        if tier == "accurate":
            return None
        return {"tier": tier}

    monkeypatch.setattr(service, "_load_model_for_tier", _load)
    monkeypatch.setattr(
        service,
        "_infer_candidates",
        lambda model, image: [{"box": (8, 8, 120, 120), "confidence": 0.9, "tier": model["tier"]}],
    )

    result = service.generate_crop(_img())

    assert result["reason"] == "selected"
    assert result["detector_tier"] == "fast"
    assert result["fallback_reason"] == "accurate_unavailable"


def test_generate_crop_returns_fail_soft_when_no_detector_tier_is_available(monkeypatch):
    service = BirdCropService(detector_tier="accurate")

    monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: None)

    result = service.generate_crop(_img())

    assert result["crop_image"] is None
    assert result["box"] is None
    assert result["reason"] == "load_failed"
    assert result["detector_tier"] is None
    assert result["fallback_reason"] == "no_detector_available"
