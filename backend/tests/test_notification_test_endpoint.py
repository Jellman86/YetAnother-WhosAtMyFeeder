import httpx
import pytest
from unittest.mock import AsyncMock

from app.auth import AuthContext, AuthLevel, require_owner
from app.main import app
from app.services.notification_service import notification_service


@pytest.mark.asyncio
async def test_notification_test_endpoint_telegram_argument_order(monkeypatch):
    # Ensure owner auth for this test-only endpoint.
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="test")

    send = AsyncMock()
    monkeypatch.setattr(notification_service, "_send_telegram", send)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/settings/notifications/test", json={"platform": "telegram"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"

    # The bug was caused by passing (species, common_name, confidence, ...) which shifted args.
    # Expect a display-name string in species slot, and a float for confidence.
    send.assert_awaited_once()
    args, _kwargs = send.call_args
    assert args[0] == "Eurasian Blue Tit (Test)"
    assert isinstance(args[1], float)
    assert args[2] == "test_camera"
    assert hasattr(args[3], "timestamp")  # datetime-like
    assert args[4].startswith("https://")
    assert args[5] is None
    assert isinstance(args[6], str) and args[6]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_notification_test_endpoint_pushover_argument_order(monkeypatch):
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="test")

    send = AsyncMock()
    monkeypatch.setattr(notification_service, "_send_pushover", send)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/settings/notifications/test", json={"platform": "pushover"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"

    send.assert_awaited_once()
    args, _kwargs = send.call_args
    assert args[0] == "Eurasian Blue Tit (Test)"
    assert isinstance(args[1], float)
    assert args[2] == "test_camera"
    assert args[4].startswith("https://")
    assert args[5] is None
    assert isinstance(args[6], str) and args[6]

    app.dependency_overrides.clear()
