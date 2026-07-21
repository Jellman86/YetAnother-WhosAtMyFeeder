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


def test_generate_classification_crop_uses_validated_tier_independently_of_thumbnail_setting(monkeypatch):
    service = BirdCropService()
    original_tier = settings.classification.bird_crop_detector_tier
    settings.classification.bird_crop_detector_tier = "fast"

    try:
        monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: {"tier": tier})
        monkeypatch.setattr(
            service,
            "_infer_candidates",
            lambda model, image: [{"box": (8, 8, 120, 120), "confidence": 0.9, "tier": model["tier"]}],
        )

        result = service.generate_classification_crop(_img())
    finally:
        settings.classification.bird_crop_detector_tier = original_tier

    assert result["reason"] == "selected"
    assert result["detector_tier"] == "accurate"


def test_classification_candidate_crop_admits_distant_box_without_weakening_normal_policy(monkeypatch):
    service = BirdCropService(detector_tier="accurate", expand_ratio=0.0)
    monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: {"tier": tier})

    def _infer(model, _image):
        if model["tier"] == "accurate":
            return [{"box": (16, 16, 96, 112), "confidence": 0.03}]
        return []

    monkeypatch.setattr(service, "_infer_candidates", _infer)

    normal = service.generate_classification_crop(_img())
    candidate = service.generate_classification_candidate_crop(_img())

    assert normal["crop_image"] is None
    assert normal["fallback_reason"] == "accurate_below_threshold"
    assert candidate["reason"] == "selected"
    assert candidate["detector_tier"] == "accurate"
    assert candidate["confidence"] == 0.03
    assert service.get_effective_crop_policy("accurate")["confidence_threshold"] == 0.05
    assert service.get_classification_candidate_crop_policy() == {
        "detector_tier": "accurate",
        "confidence_threshold": 0.02,
        "min_crop_size": 64,
        "expand_ratio": 0.0,
        "selection_mode": "evidence_candidate",
    }


def test_classification_candidate_crop_still_rejects_noise_below_distance_floor(monkeypatch):
    service = BirdCropService(detector_tier="accurate", expand_ratio=0.0)
    monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: {"tier": tier})
    monkeypatch.setattr(
        service,
        "_infer_candidates",
        lambda model, _image: [{"box": (16, 16, 96, 112), "confidence": 0.019}] if model["tier"] == "accurate" else [],
    )

    result = service.generate_classification_candidate_crop(_img())

    assert result["crop_image"] is None
    assert result["fallback_reason"] == "accurate_below_threshold"


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


def test_generate_crop_falls_back_to_fast_when_accurate_finds_no_candidate(monkeypatch):
    service = BirdCropService(detector_tier="accurate")
    monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: {"tier": tier})

    def _infer(model, image):
        if model["tier"] == "accurate":
            return []
        return [{"box": (8, 8, 120, 120), "confidence": 0.9, "tier": model["tier"]}]

    monkeypatch.setattr(service, "_infer_candidates", _infer)

    result = service.generate_crop(_img())

    assert result["reason"] == "selected"
    assert result["detector_tier"] == "fast"
    assert result["fallback_reason"] == "accurate_no_candidate"


def test_generate_crop_falls_back_to_fast_when_accurate_inference_fails(monkeypatch):
    service = BirdCropService(detector_tier="accurate")
    monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: {"tier": tier})

    def _infer(model, image):
        if model["tier"] == "accurate":
            raise RuntimeError("bad accurate output")
        return [{"box": (8, 8, 120, 120), "confidence": 0.9, "tier": model["tier"]}]

    monkeypatch.setattr(service, "_infer_candidates", _infer)

    result = service.generate_crop(_img())

    assert result["reason"] == "selected"
    assert result["detector_tier"] == "fast"
    assert result["fallback_reason"] == "accurate_inference_failed"


def test_generate_crop_falls_back_to_fast_when_accurate_candidate_is_too_small(monkeypatch):
    service = BirdCropService(detector_tier="accurate", expand_ratio=0.0)
    monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: {"tier": tier})

    def _infer(model, image):
        if model["tier"] == "accurate":
            return [{"box": (16, 16, 32, 32), "confidence": 0.9}]
        return [{"box": (8, 8, 120, 120), "confidence": 0.9}]

    monkeypatch.setattr(service, "_infer_candidates", _infer)

    result = service.generate_crop(_img())

    assert result["reason"] == "selected"
    assert result["detector_tier"] == "fast"
    assert result["fallback_reason"] == "accurate_too_small"


def test_generate_crop_returns_fail_soft_when_no_detector_tier_is_available(monkeypatch):
    service = BirdCropService(detector_tier="accurate")

    monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: None)

    result = service.generate_crop(_img())

    assert result["crop_image"] is None
    assert result["box"] is None
    assert result["reason"] == "load_failed"
    assert result["detector_tier"] is None
    assert result["fallback_reason"] == "no_detector_available"


def test_generate_crop_accurate_tier_accepts_medium_confidence_candidate(monkeypatch):
    service = BirdCropService(detector_tier="accurate")

    monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: {"tier": tier})
    monkeypatch.setattr(
        service,
        "_infer_candidates",
        lambda model, image: [{"box": (16, 16, 88, 88), "confidence": 0.22, "tier": model["tier"]}],
    )

    result = service.generate_crop(_img())

    assert result["reason"] == "selected"
    assert result["detector_tier"] == "accurate"
    assert result["confidence"] == 0.22


def test_generate_crop_accurate_tier_accepts_smaller_valid_box(monkeypatch):
    service = BirdCropService(detector_tier="accurate", expand_ratio=0.0)

    monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: {"tier": tier})
    monkeypatch.setattr(
        service,
        "_infer_candidates",
        lambda model, image: [{"box": (20, 20, 84, 84), "confidence": 0.48, "tier": model["tier"]}],
    )

    result = service.generate_crop(_img())

    assert result["reason"] == "selected"
    assert result["detector_tier"] == "accurate"
    assert result["box"] == (20, 20, 84, 84)


def test_generate_crop_fast_tier_keeps_legacy_threshold_and_size(monkeypatch):
    service = BirdCropService(detector_tier="fast", expand_ratio=0.0)

    monkeypatch.setattr(service, "_load_model_for_tier", lambda tier: {"tier": tier})
    monkeypatch.setattr(
        service,
        "_infer_candidates",
        lambda model, image: [
            {"box": (20, 20, 84, 84), "confidence": 0.48, "tier": model["tier"]},
            {"box": (16, 16, 88, 88), "confidence": 0.22, "tier": model["tier"]},
        ],
    )

    result = service.generate_crop(_img())

    assert result["crop_image"] is None
    assert result["detector_tier"] == "fast"
    assert result["reason"] == "too_small"
    assert result["confidence"] == 0.48
