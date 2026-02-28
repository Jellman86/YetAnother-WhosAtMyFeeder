import httpx
import pytest

from app.auth import AuthContext, AuthLevel, require_owner
from app.config import settings
from app.main import app


class _DummyClassifier:
    def __init__(self) -> None:
        self.reload_calls = 0

    def reload_bird_model(self) -> None:
        self.reload_calls += 1


def _base_payload() -> dict:
    return {
        "frigate_url": settings.frigate.frigate_url,
        "mqtt_server": settings.frigate.mqtt_server,
        "mqtt_port": settings.frigate.mqtt_port,
        "mqtt_auth": settings.frigate.mqtt_auth,
        "classification_threshold": settings.classification.threshold,
    }


@pytest.mark.asyncio
async def test_update_settings_does_not_reload_model_when_provider_unchanged(monkeypatch):
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="test")
    original_provider = settings.classification.inference_provider
    settings.classification.inference_provider = "auto"

    dummy = _DummyClassifier()
    monkeypatch.setattr("app.services.classifier_service.get_classifier", lambda: dummy)

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = _base_payload()
            payload["inference_provider"] = "auto"
            resp = await client.post("/api/settings", json=payload)

        assert resp.status_code == 200
        assert dummy.reload_calls == 0
    finally:
        settings.classification.inference_provider = original_provider
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_update_settings_reloads_model_when_provider_changes(monkeypatch):
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="test")
    original_provider = settings.classification.inference_provider
    settings.classification.inference_provider = "auto"

    dummy = _DummyClassifier()
    monkeypatch.setattr("app.services.classifier_service.get_classifier", lambda: dummy)

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = _base_payload()
            payload["inference_provider"] = "cpu"
            resp = await client.post("/api/settings", json=payload)

        assert resp.status_code == 200
        assert dummy.reload_calls == 1
    finally:
        settings.classification.inference_provider = original_provider
        app.dependency_overrides.clear()
