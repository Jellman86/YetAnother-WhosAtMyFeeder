"""Credential changes revoke login sessions without rotating integration keys."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import HTTPException
import httpx
import jwt
import pytest
from starlette.requests import Request

from app.auth import create_access_token, get_stream_auth_context, hash_password, verify_token
from app.config import Settings, settings
from app.config_loader import load_settings_instance
from app.main import app, sse_endpoint
from app.routers.settings import SettingsUpdate
from app.services.broadcaster import broadcaster
from app.services.oauth_token_crypto import decrypt_oauth_token, encrypt_oauth_token
from app.services.settings_update import apply_update, prepare_update


_REAL_SAVE = Settings.save


@pytest.fixture(autouse=True)
def private_auth(monkeypatch):
    monkeypatch.setattr(settings, "auth", settings.auth.model_copy(deep=True))
    settings.auth.enabled = True
    settings.auth.session_version = 0
    settings.auth.username = "fixture-owner"
    settings.auth.password_hash = hash_password("fixture-original-password123")
    settings.auth.session_secret = "fixture-stable-signing-key-at-least-32-bytes"
    settings.auth.oauth_token_secret = "fixture-stable-integration-key"
    monkeypatch.setattr(Settings, "save", AsyncMock())


async def change_password() -> None:
    prepared = prepare_update(settings, SettingsUpdate(auth_password="fixture-new-password123"), "fixture-owner")
    await apply_update(settings, prepared.candidate)


@pytest.mark.asyncio
async def test_password_change_revokes_old_logins_and_preserves_oauth_tokens():
    token = create_access_token(settings.auth.username)
    encrypted = encrypt_oauth_token("fixture-oauth-refresh-token")
    assert verify_token(token).username == settings.auth.username

    await change_password()

    with pytest.raises(HTTPException) as error:
        verify_token(token)
    assert error.value.status_code == 401
    assert verify_token(create_access_token(settings.auth.username)).username == settings.auth.username
    assert settings.auth.session_secret == "fixture-stable-signing-key-at-least-32-bytes"
    assert decrypt_oauth_token(encrypted) == "fixture-oauth-refresh-token"


@pytest.mark.asyncio
async def test_legacy_login_survives_upgrade_until_the_password_changes():
    token = jwt.encode(
        {
            "username": settings.auth.username,
            "auth_level": "owner",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        settings.auth.session_secret,
        algorithm="HS256",
    )
    assert verify_token(token).username == settings.auth.username
    await change_password()
    with pytest.raises(HTTPException):
        verify_token(token)


@pytest.mark.asyncio
async def test_failed_save_keeps_existing_logins_and_the_original_password(monkeypatch):
    token = create_access_token(settings.auth.username)
    original_hash = settings.auth.password_hash
    monkeypatch.setattr(Settings, "save", AsyncMock(side_effect=OSError("fixture save failure")))
    with pytest.raises(OSError):
        await change_password()
    assert settings.auth.password_hash == original_hash
    assert verify_token(token).username == settings.auth.username


@pytest.mark.asyncio
async def test_import_cannot_restore_revoked_logins_or_revoke_current_ones():
    old = create_access_token(settings.auth.username)
    await change_password()
    current = create_access_token(settings.auth.username)
    candidate = settings.model_copy(deep=True)
    # A backup's old revocation state belongs to its original save, not this installation.
    candidate.auth.session_version = 0
    await apply_update(settings, candidate)
    with pytest.raises(HTTPException):
        verify_token(old)
    assert verify_token(current).username == settings.auth.username


@pytest.mark.asyncio
async def test_stream_ticket_from_before_password_change_cannot_open_an_owner_stream():
    token = create_access_token(settings.auth.username)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        ticket_response = await client.post("/api/auth/stream-ticket", headers={"Authorization": "Bearer " + token})
    assert ticket_response.status_code == 200
    ticket = ticket_response.json()["ticket"]
    await change_password()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/sse",
            "headers": [],
            "query_string": ("ticket=" + ticket).encode(),
        }
    )
    context = None
    try:
        context = await get_stream_auth_context(request, credentials=None, header_key=None, query_key=None)
    except HTTPException as error:
        assert error.status_code == 401
    assert context is None or not context.context.is_owner


@pytest.mark.asyncio
async def test_open_stream_stops_before_delivering_owner_data_after_password_change():
    token = create_access_token(settings.auth.username)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/sse",
            "headers": [(b"authorization", ("Bearer " + token).encode())],
            "query_string": b"",
        }
    )
    context = await get_stream_auth_context(request, credentials=None, header_key=None, query_key=None)
    response = await sse_endpoint(request, stream_auth=context)
    stream = response.body_iterator
    try:
        assert "connected" in await anext(stream)
        await change_password()
        await broadcaster.broadcast({"type": "detection", "data": {"private": "fixture-owner-data"}})
        event = await anext(stream)
        assert "session_expired" in event
        assert "fixture-owner-data" not in event
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_password_change_preserves_legacy_oauth_encryption_fallback():
    settings.auth.oauth_token_secret = None
    encrypted = encrypt_oauth_token("fixture-legacy-refresh-token")
    await change_password()
    assert decrypt_oauth_token(encrypted) == "fixture-legacy-refresh-token"


@pytest.mark.asyncio
async def test_revocation_survives_reload_with_an_environment_provided_signing_key(tmp_path: Path, monkeypatch):
    from app import config

    destination = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", destination)
    monkeypatch.setattr(Settings, "save", _REAL_SAVE)
    monkeypatch.setenv("AUTH__SESSION_SECRET", settings.auth.session_secret)
    token = create_access_token(settings.auth.username)
    await change_password()
    loaded = load_settings_instance(Settings, destination)
    assert loaded.auth.session_version == settings.auth.session_version
    assert loaded.auth.session_version > 0
    assert json.loads(destination.read_text())["auth"]["session_version"] == loaded.auth.session_version
    monkeypatch.setattr(settings, "auth", loaded.auth)
    with pytest.raises(HTTPException):
        verify_token(token)


@pytest.mark.asyncio
async def test_ticket_exchange_rechecks_a_login_authorized_before_password_change():
    from app.auth import AuthContext, AuthLevel
    from app.routers.auth import create_stream_ticket

    token = create_access_token(settings.auth.username)
    authorized = AuthContext(auth_level=AuthLevel.OWNER, username=settings.auth.username)
    await change_password()
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/stream-ticket",
            "headers": [(b"authorization", ("Bearer " + token).encode())],
            "query_string": b"",
        }
    )
    with pytest.raises(HTTPException) as error:
        await create_stream_ticket(request, auth=authorized)
    assert error.value.status_code == 401
