"""The email test passes only when the mail was accepted, and a failure states its cause and next step."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.auth import AuthContext, AuthLevel, require_owner
from app.config import settings
from app.main import app
from app.services.smtp_service import smtp_service

SMTP_PASSWORD = "smtp-password-secret"


@pytest.fixture
def smtp_channel(monkeypatch):
    email = settings.notifications.email
    for field, value in {
        "enabled": True,
        "use_oauth": False,
        "oauth_provider": None,
        "smtp_host": "mail.example.test",
        "smtp_port": 587,
        "smtp_username": "feeder",
        "smtp_password": SMTP_PASSWORD,
        "from_email": "feeder@example.test",
        "to_email": "owner@example.test",
    }.items():
        monkeypatch.setattr(email, field, value)
    return email


async def _press_email_test() -> httpx.Response:
    app.dependency_overrides[require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER, username="test")
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/api/email/test", json={})
    finally:
        app.dependency_overrides.pop(require_owner, None)


@pytest.mark.asyncio
async def test_email_test_passes_when_the_mail_server_accepted_the_message(monkeypatch, smtp_channel):
    monkeypatch.setattr(smtp_service, "send_email_password", AsyncMock(return_value=True))

    response = await _press_email_test()

    assert response.status_code == 200
    assert response.json()["to"] == "owner@example.test"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "send",
    [
        AsyncMock(return_value=False),
        AsyncMock(side_effect=ConnectionRefusedError(f"cannot log in with {SMTP_PASSWORD}")),
    ],
    ids=["not-accepted", "connection-error"],
)
async def test_email_test_reports_a_failed_smtp_send_with_what_to_check(monkeypatch, smtp_channel, send):
    monkeypatch.setattr(smtp_service, "send_email_password", send)

    response = await _press_email_test()

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "The mail server did not accept the test email. "
        "Check the SMTP host, port, user name and password, then test again."
    )
    assert SMTP_PASSWORD not in response.text


@pytest.mark.asyncio
async def test_email_test_reports_a_mail_server_that_takes_too_long(monkeypatch, smtp_channel):
    monkeypatch.setattr(smtp_service, "send_email_password", AsyncMock(side_effect=asyncio.TimeoutError()))

    response = await _press_email_test()

    assert response.status_code == 504
    assert response.json()["detail"] == (
        "The mail server took too long to answer. Check the SMTP host and port, then test again."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider, name", [("gmail", "Gmail"), ("outlook", "Outlook")])
async def test_email_test_reports_a_failed_oauth_send_with_what_to_do(monkeypatch, smtp_channel, provider, name):
    monkeypatch.setattr(smtp_channel, "use_oauth", True)
    monkeypatch.setattr(smtp_channel, "oauth_provider", provider)
    monkeypatch.setattr(smtp_service, "send_email_oauth", AsyncMock(return_value=False))

    response = await _press_email_test()

    assert response.status_code == 502
    assert response.json()["detail"] == (
        f"{name} did not accept the test email. Reconnect the account, then test again."
    )


@pytest.mark.asyncio
async def test_email_test_reports_an_oauth_provider_that_takes_too_long_without_naming_smtp(monkeypatch, smtp_channel):
    monkeypatch.setattr(smtp_channel, "use_oauth", True)
    monkeypatch.setattr(smtp_channel, "oauth_provider", "gmail")
    monkeypatch.setattr(smtp_service, "send_email_oauth", AsyncMock(side_effect=asyncio.TimeoutError()))

    response = await _press_email_test()

    assert response.status_code == 504
    assert response.json()["detail"] == "Gmail took too long to answer. Wait a moment, then test again."


@pytest.mark.asyncio
async def test_email_test_that_cannot_be_prepared_does_not_blame_the_mail_server(monkeypatch, smtp_channel):
    from app.routers import email as email_router

    send = AsyncMock(return_value=True)
    monkeypatch.setattr(smtp_service, "send_email_password", send)

    def broken_font(*_args, **_kwargs):
        raise RuntimeError(f"template data broke near {SMTP_PASSWORD}")

    monkeypatch.setattr(email_router, "get_email_font_family", broken_font)

    response = await _press_email_test()

    assert response.status_code == 500
    assert response.json()["detail"] == "YA-WAMF could not prepare the test email. Open Health, then test again."
    assert SMTP_PASSWORD not in response.text
    send.assert_not_awaited()
