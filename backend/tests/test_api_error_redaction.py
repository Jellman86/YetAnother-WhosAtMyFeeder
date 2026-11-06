"""Integration failures remain useful without echoing configured credentials."""

from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import settings
from app.main import app
from app.routers import email


@pytest.mark.asyncio
async def test_email_authorization_failure_redacts_credentials_in_response_and_logs(monkeypatch, capsys):
    secret = "fixture-gmail-secret-not-for-the-response"
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.notifications.email, "gmail_client_id", "fixture-client")
    monkeypatch.setattr(settings.notifications.email, "gmail_client_secret", secret)

    def fail(*args, **kwargs):
        raise RuntimeError("Provider rejected client credential " + secret)

    monkeypatch.setattr(email.Flow, "from_client_config", fail)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/email/oauth/gmail/authorize")
    output = capsys.readouterr()
    assert response.status_code == 500
    assert secret not in response.text + output.out + output.err
    assert "Provider rejected client credential" in response.text


@pytest.mark.asyncio
async def test_geocoding_failure_redacts_configured_credentials_and_keeps_status(monkeypatch):
    secret = "fixture-configured-secret-in-upstream-failure"
    monkeypatch.setattr(settings.auth, "enabled", False)
    monkeypatch.setattr(settings.ebird, "api_key", secret)
    monkeypatch.setattr(
        "app.routers.geocoding.geocoding_service.reverse",
        AsyncMock(side_effect=RuntimeError("Upstream failed: " + secret)),
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/location/reverse-geocode", params={"lat": 51, "lon": 0})
    assert response.status_code == 502
    assert secret not in response.text
    assert "Upstream failed" in response.text
