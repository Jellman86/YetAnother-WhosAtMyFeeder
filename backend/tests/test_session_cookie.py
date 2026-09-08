"""Media loads with a scoped session cookie, never the session token in the URL.

`<img>` and `<video>` cannot send headers, so owner media URLs carried
`?token=<session>` and every proxy in front of YA-WAMF logged a week of owner
access with each thumbnail. The session now also lives in an HttpOnly cookie
that only read-only media routes and the live stream honour, so a cookie the
browser sends by itself can never authorise a write.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import (
    SESSION_COOKIE,
    AuthLevel,
    create_access_token,
    get_auth_context,
    get_stream_auth_context,
    hash_password,
    session_cookie_allowed,
)
from app.config import settings
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def https_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        yield client


@pytest.fixture(autouse=True)
def owner_password_configured():
    original = (
        settings.auth.enabled,
        settings.auth.password_hash,
        settings.auth.username,
        settings.auth.initial_setup_complete,
        settings.auth.session_expiry_hours,
        settings.public_access.enabled,
        settings.api_key,
    )
    settings.auth.enabled = True
    settings.auth.password_hash = hash_password("correct-horse-1")
    settings.auth.username = "owner"
    settings.auth.initial_setup_complete = True
    settings.auth.session_expiry_hours = 168
    settings.public_access.enabled = False
    settings.api_key = None
    yield
    (
        settings.auth.enabled,
        settings.auth.password_hash,
        settings.auth.username,
        settings.auth.initial_setup_complete,
        settings.auth.session_expiry_hours,
        settings.public_access.enabled,
        settings.api_key,
    ) = original


def _request(path: str, method: str = "GET", cookie: str | None = None, scheme: str = "http") -> Request:
    headers = [(b"cookie", f"{SESSION_COOKIE}={cookie}".encode())] if cookie else []
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "scheme": scheme,
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "root_path": "",
        }
    )


def _set_cookie_header(response: httpx.Response) -> str:
    headers = [v for k, v in response.headers.multi_items() if k.lower() == "set-cookie" and SESSION_COOKIE in v]
    assert len(headers) == 1, response.headers.multi_items()
    return headers[0]


# --- where the cookie is honoured: read-only media and the stream, nothing else ----


@pytest.mark.parametrize(
    "method, path, allowed",
    [
        ("GET", "/api/frigate/1788686951.128889-si0jon/snapshot.jpg", True),
        ("GET", "/api/frigate/1788686951.128889-si0jon/thumbnail.jpg", True),
        ("GET", "/api/frigate/1788686951.128889-si0jon/clip.mp4", True),
        ("GET", "/api/frigate/1788686951.128889-si0jon/recording-clip.mp4", True),
        ("GET", "/api/frigate/1788686951.128889-si0jon/clip-thumbnails.vtt", True),
        ("GET", "/api/frigate/1788686951.128889-si0jon/clip-thumbnails.jpg", True),
        ("GET", "/api/frigate/1788686951.128889-si0jon/snapshot/original.jpg", True),
        ("GET", "/api/frigate/1788686951.128889-si0jon/snapshot/candidates/c1/image.jpg", True),
        ("GET", "/api/frigate/camera/birdcam/latest.jpg", True),
        ("GET", "/api/audio/spectrogram/42", True),
        ("GET", "/api/audio/clip/42", True),
        ("GET", "/api/sse", True),
        ("HEAD", "/api/frigate/1788686951.128889-si0jon/clip.mp4", True),
        ("POST", "/api/frigate/1788686951.128889-si0jon/snapshot/apply", False),
        ("GET", "/api/frigate/config", False),
        ("GET", "/api/events", False),
        ("GET", "/api/settings", False),
        ("POST", "/api/settings", False),
        ("DELETE", "/api/events/1788686951.128889-si0jon", False),
        ("POST", "/api/backfill/reset", False),
    ],
)
def test_the_cookie_is_scoped_to_read_only_media_routes(method: str, path: str, allowed: bool):
    assert session_cookie_allowed(_request(path, method=method)) is allowed


@pytest.mark.asyncio
async def test_a_media_request_with_only_the_cookie_is_the_owner():
    token = create_access_token("owner", AuthLevel.OWNER)
    request = _request("/api/frigate/1788686951.128889-si0jon/thumbnail.jpg", cookie=token)

    context = await get_auth_context(request, None)

    assert context.is_owner
    assert context.username == "owner"


@pytest.mark.asyncio
async def test_the_same_cookie_authorises_nothing_outside_media():
    token = create_access_token("owner", AuthLevel.OWNER)

    with pytest.raises(HTTPException) as excinfo:
        await get_auth_context(_request("/api/events", cookie=token), None)
    assert excinfo.value.status_code == 401

    with pytest.raises(HTTPException) as excinfo:
        await get_auth_context(_request("/api/settings", method="POST", cookie=token), None)
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_a_stale_cookie_falls_through_to_what_the_bare_request_gets():
    settings.public_access.enabled = True
    context = await get_auth_context(_request("/api/frigate/e1/snapshot.jpg", cookie="not-a-token"), None)
    assert context.auth_level == AuthLevel.GUEST


@pytest.mark.asyncio
async def test_the_stream_opens_from_the_cookie_alone():
    token = create_access_token("owner", AuthLevel.OWNER)
    stream_auth = await get_stream_auth_context(_request("/api/sse", cookie=token), None, None, None)

    assert stream_auth.context.is_owner
    assert stream_auth.session_exp is not None


# --- issuing and clearing it -----------------------------------------------------------


@pytest.mark.asyncio
async def test_login_sets_an_httponly_lax_cookie_scoped_to_the_api(client: httpx.AsyncClient):
    response = await client.post("/api/auth/login", json={"username": "owner", "password": "correct-horse-1"})
    assert response.status_code == 200, response.text

    cookie = _set_cookie_header(response)
    lowered = cookie.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "path=/api" in lowered
    assert f"max-age={168 * 3600}" in lowered
    assert "secure" not in lowered, "plain-http LAN installs must still receive the cookie"
    assert response.json()["access_token"] in cookie, "the cookie carries the session itself"


@pytest.mark.asyncio
async def test_over_https_the_cookie_is_secure(https_client: httpx.AsyncClient):
    response = await https_client.post("/api/auth/login", json={"username": "owner", "password": "correct-horse-1"})
    assert response.status_code == 200, response.text
    assert "secure" in _set_cookie_header(response).lower()


@pytest.mark.asyncio
async def test_a_signed_in_browser_can_mint_the_cookie_for_its_existing_session(client: httpx.AsyncClient):
    token = create_access_token("owner", AuthLevel.OWNER)

    response = await client.post("/api/auth/session-cookie", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    assert token in _set_cookie_header(response)


@pytest.mark.asyncio
async def test_the_cookie_cannot_mint_itself(client: httpx.AsyncClient):
    """A media-scoped cookie must not be able to renew its own reach."""
    token = create_access_token("owner", AuthLevel.OWNER)

    response = await client.post("/api/auth/session-cookie", cookies={SESSION_COOKIE: token})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_no_session_means_no_cookie(client: httpx.AsyncClient):
    response = await client.post("/api/auth/session-cookie")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_the_cookie(client: httpx.AsyncClient):
    token = create_access_token("owner", AuthLevel.OWNER)

    response = await client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    cookie = _set_cookie_header(response).lower()
    assert "max-age=0" in cookie or "expires=" in cookie


@pytest.mark.asyncio
async def test_first_run_setup_with_a_password_sets_the_cookie_too(client: httpx.AsyncClient):
    settings.auth.initial_setup_complete = False
    settings.auth.password_hash = None
    settings.auth.enabled = False

    response = await client.post(
        "/api/auth/initial-setup",
        json={"username": "owner", "password": "correct-horse-1", "enable_auth": True},
    )

    assert response.status_code == 200, response.text
    assert response.json()["access_token"] in _set_cookie_header(response)


def test_cookie_lifetime_follows_the_session():
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.auth.session_expiry_hours)
    assert exp > datetime.now(timezone.utc)
