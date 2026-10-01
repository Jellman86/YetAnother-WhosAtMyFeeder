"""Owner-issued callbacks work without broadening cookie or guest access."""

import base64
import asyncio
from contextlib import asynccontextmanager, closing
import json
import os
import secrets
import sqlite3
from types import SimpleNamespace

import aiosqlite
import httpx
import pytest
import pytest_asyncio

from app.auth import create_access_token, AuthLevel
from app.config import settings
from app.main import app
from app.routers import email
from app.services import inaturalist_service, smtp_service


@pytest_asyncio.fixture
async def oauth_flow(tmp_path, monkeypatch):
    path = tmp_path / "oauth.db"
    with closing(sqlite3.connect(os.environ["DB_PATH"])) as source, closing(sqlite3.connect(path)) as target:
        source.backup(target)
        target.execute("DELETE FROM oauth_tokens")
        target.commit()

    @asynccontextmanager
    async def database():
        async with aiosqlite.connect(path) as db:
            yield db

    monkeypatch.setattr(inaturalist_service, "get_db", database)
    monkeypatch.setattr(smtp_service, "get_db", database)
    monkeypatch.setattr(settings.auth, "enabled", True)
    monkeypatch.setattr(settings.auth, "initial_setup_complete", True)
    monkeypatch.setattr(settings.public_access, "enabled", False)
    monkeypatch.setattr(settings.inaturalist, "enabled", True)
    for config, names in [
        (settings.inaturalist, ["client_id", "client_secret"]),
        (
            settings.notifications.email,
            ["gmail_client_id", "gmail_client_secret", "outlook_client_id", "outlook_client_secret"],
        ),
    ]:
        for name in names:
            monkeypatch.setattr(config, name, "fixture-only")

    calls = []

    class GmailFlow:
        redirect_uri = ""
        credentials = SimpleNamespace(
            token="fixture-access", refresh_token="fixture-refresh", expiry=None, scopes=["email"]
        )

        def authorization_url(self, **kwargs):
            return "https://fixture.invalid/authorize", secrets.token_urlsafe(32)

        def fetch_token(self, **kwargs):
            calls.append("gmail-token")

    monkeypatch.setattr(email, "Flow", SimpleNamespace(from_client_config=lambda *args, **kwargs: GmailFlow()))
    original_send = httpx.AsyncClient.send

    async def send(client, request, **kwargs):
        if request.url.host == "testserver":
            return await original_send(client, request, **kwargs)
        calls.append(str(request.url))
        claims = base64.urlsafe_b64encode(json.dumps({"email": "bird@example.test"}).encode()).decode().rstrip("=")
        data = {
            "access_token": "fixture-access",
            "refresh_token": "fixture-refresh",
            "id_token": f"e30.{claims}.fixture",
        }
        if "userinfo" in str(request.url):
            data = {"email": "bird@example.test"}
        if "/users/me" in str(request.url):
            data = {"results": [{"login": "fixture-bird"}]}
        return httpx.Response(200, json=data, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    token = create_access_token("review-owner", AuthLevel.OWNER)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        yield client, {"Authorization": f"Bearer {token}"}, calls, database


def paths(provider):
    prefix = "/api/inaturalist/oauth" if provider == "inaturalist" else f"/api/email/oauth/{provider}"
    return f"{prefix}/authorize", f"{prefix}/callback"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["inaturalist", "gmail", "outlook"])
async def test_private_owner_oauth_redirect_completes_once_without_bearer_or_cookie(oauth_flow, provider):
    client, headers, calls, database = oauth_flow
    authorize, callback = paths(provider)
    started = await client.get(authorize, headers=headers)
    assert started.status_code == 200
    state = started.json()["state"]
    response = await client.get(callback, params={"code": "fixture-code", "state": state})
    assert response.status_code == 200
    async with database() as db:
        rows = await (await db.execute("SELECT provider, access_token FROM oauth_tokens")).fetchall()
    assert len(rows) == 1 and rows[0][0] == provider
    assert rows[0][1] != "fixture-access"
    before = len(calls)
    replay = await client.get(callback, params={"code": "fixture-code", "state": state})
    assert replay.status_code == 400
    assert len(calls) == before


@pytest.mark.asyncio
async def test_outlook_state_cannot_authorize_gmail_even_with_public_access(oauth_flow, monkeypatch):
    client, headers, calls, database = oauth_flow
    monkeypatch.setattr(settings.public_access, "enabled", True)
    started = await client.get(paths("outlook")[0], headers=headers)
    wrong = await client.get(paths("gmail")[1], params={"code": "fixture-code", "state": started.json()["state"]})
    assert wrong.status_code == 400
    assert calls == []
    correct = await client.get(paths("outlook")[1], params={"code": "fixture-code", "state": started.json()["state"]})
    assert correct.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["inaturalist", "gmail", "outlook"])
async def test_forged_callbacks_and_guest_initiation_do_not_call_providers(oauth_flow, provider, monkeypatch):
    client, headers, calls, database = oauth_flow
    authorize, callback = paths(provider)
    response = await client.get(callback, params={"code": "fixture", "state": "forged"})
    assert response.status_code == 400
    monkeypatch.setattr(settings.public_access, "enabled", True)
    assert (await client.get(authorize)).status_code == 403
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["inaturalist", "gmail", "outlook"])
async def test_expired_callback_does_not_exchange_or_store_tokens(oauth_flow, provider, monkeypatch):
    from app.services.oauth_state import oauth_states

    client, headers, calls, database = oauth_flow
    authorize, callback = paths(provider)
    started = await client.get(authorize, headers=headers)
    monkeypatch.setattr(oauth_states, "ttl_seconds", -1)
    oauth_states.remember(provider, started.json()["state"])
    response = await client.get(callback, params={"code": "fixture", "state": started.json()["state"]})
    assert response.status_code == 400
    assert calls == []


@pytest.mark.asyncio
async def test_oauth_callback_exception_does_not_authorize_other_private_routes(oauth_flow):
    client, headers, calls, database = oauth_flow
    for method, path in [
        ("GET", "/api/email/oauth/gmail/authorize"),
        ("GET", "/api/inaturalist/status"),
        ("DELETE", "/api/email/oauth/gmail/disconnect"),
        ("POST", "/api/email/test"),
    ]:
        assert (await client.request(method, path, json={})).status_code == 401
    assert (await client.post(paths("gmail")[1], json={})).status_code in {401, 405}
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["inaturalist", "gmail", "outlook"])
async def test_concurrent_callbacks_exchange_a_single_owner_state_only_once(oauth_flow, provider):
    client, headers, calls, database = oauth_flow
    authorize, callback = paths(provider)
    started = await client.get(authorize, headers=headers)
    responses = await asyncio.gather(
        client.get(callback, params={"code": "fixture", "state": started.json()["state"]}),
        client.get(callback, params={"code": "fixture", "state": started.json()["state"]}),
    )
    assert sorted(response.status_code for response in responses) == [200, 400]
    token_calls = [call for call in calls if call == "gmail-token" or call.endswith("/token")]
    assert len(token_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gmail", "outlook"])
async def test_failed_email_token_storage_does_not_report_connected(oauth_flow, provider, monkeypatch):
    from unittest.mock import AsyncMock

    client, headers, calls, database = oauth_flow
    monkeypatch.setattr(email.smtp_service, "store_oauth_token", AsyncMock(return_value=False))
    authorize, callback = paths(provider)
    started = await client.get(authorize, headers=headers)
    response = await client.get(callback, params={"code": "fixture", "state": started.json()["state"]})
    assert response.status_code == 500
    assert "Connection Failed" in response.text
    async with database() as db:
        assert await (await db.execute("SELECT COUNT(*) FROM oauth_tokens")).fetchone() == (0,)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["gmail", "outlook"])
async def test_provider_email_is_text_in_callback_page(oauth_flow, provider, monkeypatch):
    client, headers, calls, database = oauth_flow
    original_send = httpx.AsyncClient.send
    unsafe_email = '<img src=x onerror="alert(1)">@example.test'

    async def send(session, request, **kwargs):
        response = await original_send(session, request, **kwargs)
        if "userinfo" in str(request.url):
            return httpx.Response(200, json={"email": unsafe_email}, request=request)
        if request.url.host == "login.microsoftonline.com":
            data = response.json()
            claims = base64.urlsafe_b64encode(json.dumps({"email": unsafe_email}).encode()).decode().rstrip("=")
            data["id_token"] = f"e30.{claims}.fixture"
            return httpx.Response(200, json=data, request=request)
        return response

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    authorize, callback = paths(provider)
    started = await client.get(authorize, headers=headers)
    response = await client.get(callback, params={"code": "fixture", "state": started.json()["state"]})
    assert response.status_code == 200
    assert "<img" not in response.text
    assert "&lt;img" in response.text
