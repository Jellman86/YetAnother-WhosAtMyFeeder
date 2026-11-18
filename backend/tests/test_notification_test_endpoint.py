import httpx
import pytest
from unittest.mock import AsyncMock

from app.config import settings
from app.services.notifications.message import DeliveryResult

from app.auth import AuthContext, AuthLevel, require_owner
from app.main import app
from app.services.notification_service import notification_service


@pytest.mark.asyncio
async def test_notification_test_endpoint_telegram_argument_order(monkeypatch):
    # Ensure owner auth for this test-only endpoint.
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="test")

    send = AsyncMock(return_value=DeliveryResult(sent=True))
    monkeypatch.setattr(notification_service, "deliver_telegram", send)

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

    send = AsyncMock(return_value=DeliveryResult(sent=True))
    monkeypatch.setattr(notification_service, "deliver_pushover", send)

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


@pytest.mark.asyncio
async def test_notification_test_endpoint_links_to_the_detections_page(monkeypatch):
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="test")
    monkeypatch.setattr(settings.notifications, "instance_url", "https://feeder.example.com/")
    send = AsyncMock(return_value=DeliveryResult(sent=True))
    monkeypatch.setattr(notification_service, "deliver_discord", send)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/settings/notifications/test", json={"platform": "discord"})
    app.dependency_overrides.pop(require_owner, None)
    assert resp.status_code == 200
    send.assert_awaited_once()
    assert send.call_args.kwargs["detection_url"] == "https://feeder.example.com/events"


# What the owner typed for each channel. Every value is a credential and must never be answered back.
CHANNEL_CREDENTIALS = {
    "discord": {"webhook_url": "https://discord.com/api/webhooks/123456/webhook-secret-value"},
    "pushover": {"user_key": "pushover-user-secret", "api_token": "pushover-token-secret"},
    "telegram": {"bot_token": "telegram-bot-secret", "chat_id": "telegram-chat-secret"},
}
CHANNEL_NAMES = {"discord": "Discord", "pushover": "Pushover", "telegram": "Telegram"}


def _raising(error_type):
    def handler(request: httpx.Request) -> httpx.Response:
        raise error_type(f"failed talking to {request.url}", request=request)

    return handler


def _answering(status_code, body=None):
    return lambda request: httpx.Response(status_code, json=body if body is not None else {"message": str(request.url)})


async def _run_channel_test(monkeypatch, platform, handler):
    """Press the channel's test with the provider's HTTP answer replaced at the boundary."""
    monkeypatch.setattr(notification_service, "client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="test")
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/api/settings/notifications/test", json={"platform": platform, **CHANNEL_CREDENTIALS[platform]}
            )
    finally:
        app.dependency_overrides.pop(require_owner, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", sorted(CHANNEL_CREDENTIALS))
@pytest.mark.parametrize(
    "handler, cause, wording",
    [
        (_raising(httpx.ConnectError), "no_answer", "did not answer"),
        (_raising(httpx.ReadTimeout), "timeout", "took too long to answer"),
        (_answering(401), "refused", "refused the message"),
        (_answering(404), "refused", "refused the message"),
        (_answering(429), "rate_limited", "is limiting messages"),
        (_answering(500), "provider_error", "reported a problem on its side"),
        (_answering(503), "provider_error", "reported a problem on its side"),
    ],
    ids=["connect-error", "timeout", "401", "404", "429", "500", "503"],
)
async def test_channel_test_reports_a_failed_delivery_with_its_cause(monkeypatch, platform, handler, cause, wording):
    response = await _run_channel_test(monkeypatch, platform, handler)

    assert response.status_code == 502
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["cause"] == cause
    assert payload["channel"] == platform
    assert payload["message"].startswith(f"{CHANNEL_NAMES[platform]} {wording}")
    assert payload["message"].endswith("then test again.")
    for secret in CHANNEL_CREDENTIALS[platform].values():
        assert secret not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "platform, body",
    [("telegram", {"ok": False, "description": "chat not found"}), ("pushover", {"status": 0, "errors": ["bad"]})],
)
async def test_channel_test_fails_when_the_provider_answers_200_but_does_not_accept(monkeypatch, platform, body):
    response = await _run_channel_test(monkeypatch, platform, _answering(200, body))

    assert response.status_code == 502
    assert response.json()["cause"] == "refused"
    assert "chat not found" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("platform, body", [("discord", {}), ("telegram", {"ok": True}), ("pushover", {"status": 1})])
async def test_channel_test_passes_only_when_the_provider_accepted_the_message(monkeypatch, platform, body):
    response = await _run_channel_test(monkeypatch, platform, _answering(200, body))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", sorted(CHANNEL_CREDENTIALS))
async def test_channel_test_without_credentials_says_the_channel_is_not_set_up(monkeypatch, platform):
    channel = getattr(settings.notifications, platform)
    for field in CHANNEL_CREDENTIALS[platform]:
        monkeypatch.setattr(channel, field, None)
    monkeypatch.setattr(
        notification_service, "client", httpx.AsyncClient(transport=httpx.MockTransport(_answering(200)))
    )
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="test")
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/settings/notifications/test", json={"platform": platform})
    finally:
        app.dependency_overrides.pop(require_owner, None)

    assert response.status_code == 400
    assert response.json()["cause"] == "not_configured"
