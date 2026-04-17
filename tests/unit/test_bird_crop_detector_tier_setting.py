from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError


def test_classification_settings_accepts_supported_bird_crop_detector_tiers():
    from app.config_models import ClassificationSettings

    fast = ClassificationSettings(bird_crop_detector_tier="fast")
    accurate = ClassificationSettings(bird_crop_detector_tier="accurate")

    assert fast.bird_crop_detector_tier == "fast"
    assert accurate.bird_crop_detector_tier == "accurate"


def test_classification_settings_rejects_unknown_bird_crop_detector_tier():
    from app.config_models import ClassificationSettings

    with pytest.raises(ValidationError):
        ClassificationSettings(bird_crop_detector_tier="unknown")


@pytest.mark.asyncio
async def test_settings_route_exposes_bird_crop_detector_tier(monkeypatch):
    from app.auth import AuthContext, AuthLevel
    from app.routers import settings as settings_router

    monkeypatch.setattr(settings_router.smtp_service, "get_oauth_status", AsyncMock(return_value=None))
    monkeypatch.setattr(settings_router.inaturalist_service, "refresh_connected_user", AsyncMock(return_value=None))
    monkeypatch.setattr(
        settings_router.auto_video_classifier,
        "get_circuit_status",
        lambda _kind: {"open": False, "open_until": None, "failure_count": 0},
    )

    payload = await settings_router.get_settings(
        auth=AuthContext(AuthLevel.OWNER, username="owner"),
    )

    validated = settings_router.SettingsResponse.model_validate(payload)
    assert validated.bird_crop_detector_tier in {"fast", "accurate"}

