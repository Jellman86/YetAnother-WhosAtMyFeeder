"""A Frigate connection failure must never put the configured address's credentials in a response.

Reverse proxies in front of Frigate are often reached with basic-auth userinfo, a token query
parameter or a token path segment in the configured URL. Guests get no address at all; owners get
only ``scheme://host[:port]``, which is enough to recognise and fix the setting.
"""

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import httpx
import pytest

from app.auth import AuthContext, AuthLevel
from app.config import settings
from app.main import app
from app.routers import proxy
from app.services.archive_service import archive_service
from app.services.garden_media_cache import garden_media_cache
from app.services.media_cache import media_cache

REDUCED_HOST = "https://frigate.example.test:8443"
SECRET_URLS = {
    "userinfo": ("https://feeder-user:hunter2-pass@frigate.example.test:8443", ("feeder-user", "hunter2-pass")),
    "token_query": ("https://frigate.example.test:8443/?token=query-secret-123", ("query-secret-123", "token=")),
    "token_path": ("https://frigate.example.test:8443/proxy/path-secret-456", ("path-secret-456", "/proxy")),
}

# (method, path, failure): "connect" refuses the connection, "read" drops it mid-stream.
GUEST_REACHABLE_ROUTES = [
    ("GET", "snapshot.jpg", "connect"),
    ("GET", "thumbnail.jpg", "connect"),
    ("HEAD", "clip.mp4", "connect"),
    ("HEAD", "recording-clip.mp4", "connect"),
    ("POST", "recording-clip/fetch", "read"),
    ("GET", "hls/master.m3u8", "connect"),
    ("GET", "hls/init-v1.mp4", "connect"),
    ("GET", "recording-hls/master.m3u8", "connect"),
    ("GET", "recording-hls/seg-1-v1.m4s", "connect"),
    ("GET", "clip-thumbnails.vtt", "connect"),
    ("GET", "clip-thumbnails.jpg", "connect"),
]


class _DroppedStream(httpx.AsyncByteStream):
    def __init__(self, request: httpx.Request) -> None:
        self._request = request

    async def __aiter__(self) -> AsyncIterator[bytes]:
        raise httpx.ReadError(f"connection to {self._request.url} dropped", request=self._request)
        yield b""


def _unreachable_frigate(monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    """Fail every real outgoing request; the in-process test client uses its own ASGI transport."""

    async def fail(_transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        if failure == "read":
            return httpx.Response(200, stream=_DroppedStream(request), request=request)
        # httpx can name the full request URL in its error text.
        raise httpx.ConnectError(f"cannot connect to {request.url}", request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fail)
    # Shared clients created before the patch keep their own pools; start fresh ones.
    monkeypatch.setattr(proxy, "_http_client", None)
    monkeypatch.setattr(proxy.frigate_client, "_client", None)


def _bypass_local_media(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every handler fall through to Frigate, as on a first visit with nothing cached."""
    monkeypatch.setattr(proxy, "require_event_access", AsyncMock(return_value=None))
    monkeypatch.setattr(
        proxy, "_get_cached_recording_clip_details", AsyncMock(return_value=(None, None, None, "birdcam", 100, 200))
    )
    monkeypatch.setattr(proxy, "_get_recording_clip_context", AsyncMock(return_value=("birdcam", 100, 200)))
    monkeypatch.setattr(proxy, "_head_response_cache", {})
    monkeypatch.setattr(proxy.frigate_client, "get_event", AsyncMock(return_value={"has_clip": True}))
    monkeypatch.setattr(proxy.frigate_client, "get_snapshot_with_error", AsyncMock(return_value=(None, "unreachable")))
    for name in ("get_snapshot", "get_snapshot_metadata", "get_thumbnail", "get_thumbnail_metadata"):
        monkeypatch.setattr(media_cache, name, AsyncMock(return_value=None))
    monkeypatch.setattr(media_cache, "get_preview_manifest", AsyncMock(return_value=None))
    monkeypatch.setattr(media_cache, "get_preview_sprite_path", lambda _event_id: None)
    monkeypatch.setattr(media_cache, "get_clip_path", lambda _event_id: None)
    monkeypatch.setattr(media_cache, "_available", True)
    for name in ("snapshot_path", "video_path", "recording_path"):
        monkeypatch.setattr(archive_service, name, AsyncMock(return_value=None))
    monkeypatch.setattr(garden_media_cache, "event_clip", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(settings.frigate, "clips_enabled", True)
    monkeypatch.setattr(settings.frigate, "recording_clip_enabled", True)
    monkeypatch.setattr(settings.media_cache, "cache_clips", False)


@pytest.fixture
def as_role(request: pytest.FixtureRequest):
    level = request.param
    app.dependency_overrides[proxy.get_proxy_auth_context] = lambda: AuthContext(auth_level=level)
    yield level
    app.dependency_overrides.pop(proxy.get_proxy_auth_context, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("as_role", [AuthLevel.GUEST, AuthLevel.OWNER], indirect=True)
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
@pytest.mark.parametrize("method, asset, failure", GUEST_REACHABLE_ROUTES)
async def test_guest_reachable_media_connection_failure_hides_frigate_credentials(
    monkeypatch, as_role, url_shape, method, asset, failure
):
    frigate_url, secrets = SECRET_URLS[url_shape]
    monkeypatch.setattr(settings.frigate, "frigate_url", frigate_url)
    _bypass_local_media(monkeypatch)
    if failure == "read":
        monkeypatch.setattr(media_cache, "_available", False)
    _unreachable_frigate(monkeypatch, failure)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
        response = await client.request(method, f"/api/frigate/event_media/{asset}")

    assert response.status_code == 502
    body = response.text
    detail = response.headers.get("x-error-detail", "")
    for secret in secrets:
        assert secret not in body
        assert secret not in detail
    if method == "HEAD":
        return
    if as_role == AuthLevel.OWNER:
        assert REDUCED_HOST in body
    else:
        assert "frigate.example.test" not in body
        assert "Frigate" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
@pytest.mark.parametrize(
    "path",
    ["/api/frigate/config", "/api/frigate/camera/birdcam/latest.jpg", "/api/frigate/cameras/status"],
)
async def test_owner_frigate_routes_show_only_the_reduced_address_on_connection_failure(monkeypatch, url_shape, path):
    frigate_url, secrets = SECRET_URLS[url_shape]
    monkeypatch.setattr(settings.frigate, "frigate_url", frigate_url)
    _unreachable_frigate(monkeypatch, "connect")
    app.dependency_overrides[proxy.require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
            response = await client.get(path)
    finally:
        app.dependency_overrides.pop(proxy.require_owner, None)

    assert response.status_code == 502
    for secret in secrets:
        assert secret not in response.text
    assert REDUCED_HOST in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("url_shape", sorted(SECRET_URLS))
@pytest.mark.parametrize("outcome", ["reachable", "unreachable"])
async def test_frigate_connection_test_reports_only_the_reduced_address(monkeypatch, url_shape, outcome):
    frigate_url, secrets = SECRET_URLS[url_shape]
    monkeypatch.setattr(settings.frigate, "frigate_url", frigate_url)
    monkeypatch.setattr(proxy, "_http_client", None)
    if outcome == "reachable":

        async def answer(_transport: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text='"0.16.0"', request=request)

        monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", answer)
    else:
        _unreachable_frigate(monkeypatch, "connect")
    app.dependency_overrides[proxy.require_owner] = lambda: AuthContext(auth_level=AuthLevel.OWNER)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://fixture") as client:
            response = await client.get("/api/frigate/test")
    finally:
        app.dependency_overrides.pop(proxy.require_owner, None)

    for secret in secrets:
        assert secret not in response.text
    if url_shape != "token_path":
        # Userinfo and query strings are refused before any request, without echoing the address.
        assert response.status_code == 400
        assert "frigate.example.test" not in response.text
        return
    assert response.status_code == (200 if outcome == "reachable" else 502)
    assert REDUCED_HOST in response.text
    if outcome == "reachable":
        assert response.json()["frigate_url"] == REDUCED_HOST


def test_frigate_unreachable_message_exists_in_every_locale():
    from app.services.i18n_service import i18n_service

    english = i18n_service.translate("errors.proxy.frigate_unreachable", "en")
    assert "Frigate" in english
    for lang in sorted(i18n_service.translations):
        message = i18n_service.translate("errors.proxy.frigate_unreachable", lang)
        assert message != "errors.proxy.frigate_unreachable"
        assert "{" not in message
        assert "{url}" in i18n_service.translations[lang]["errors"]["proxy"]["connection_failed"]
