from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_get_settings_route_declares_response_model_and_payload_validates(monkeypatch):
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
    assert validated.location_temperature_unit in {"celsius", "fahrenheit"}

    route = next(
        route
        for route in settings_router.router.routes
        if getattr(route, "path", None) == "/settings"
    )
    assert route.response_model is settings_router.SettingsResponse
    assert "auth_password" not in settings_router.SettingsResponse.model_fields
