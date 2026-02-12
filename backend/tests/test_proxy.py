from pathlib import Path
from tempfile import NamedTemporaryFile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from app.main import app
from app.config import settings
import pytest
import pytest_asyncio
import httpx

@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_proxy_clip_disabled(client: httpx.AsyncClient):
    """Test that clips return 403 when clips_enabled is False."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = False

    try:
        response = await client.get("/api/frigate/test_event_id/clip.mp4")
        assert response.status_code == 403
        assert response.json()["detail"] == "Clip fetching is disabled"
    finally:
        settings.frigate.clips_enabled = original_setting


@pytest.mark.asyncio
async def test_proxy_clip_head_disabled(client: httpx.AsyncClient):
    """Test that HEAD requests for clips return 403 when clips_enabled is False."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = False

    try:
        response = await client.head("/api/frigate/test_event_id/clip.mp4")
        assert response.status_code == 403
    finally:
        settings.frigate.clips_enabled = original_setting


@pytest.mark.asyncio
async def test_proxy_clip_invalid_event_id(client: httpx.AsyncClient):
    """Test that invalid event IDs are rejected."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = True

    try:
        # Use a path that won't be normalized away by the test client/server
        # but still fails our validation
        response = await client.get("/api/frigate/invalid@event!id/clip.mp4")
        assert response.status_code == 400
        assert "Invalid event ID format" in response.json()["detail"]
    finally:
        settings.frigate.clips_enabled = original_setting


@pytest.fixture
def mock_frigate_response():
    """Create a properly mocked async response for streaming."""
    async def async_iter_bytes():
        yield b"fake video data chunk 1"
        yield b"fake video data chunk 2"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {
        "content-type": "video/mp4",
        "content-length": "12345"
    }
    mock_response.aiter_bytes = async_iter_bytes
    mock_response.aclose = AsyncMock()
    return mock_response


@pytest.fixture
def mock_frigate_partial_response():
    """Create a mocked 206 Partial Content response for Range requests."""
    async def async_iter_bytes():
        yield b"partial video data"

    mock_response = MagicMock()
    mock_response.status_code = 206
    mock_response.headers = {
        "content-type": "video/mp4",
        "content-length": "1000",
        "content-range": "bytes 0-999/12345"
    }
    mock_response.aiter_bytes = async_iter_bytes
    mock_response.aclose = AsyncMock()
    return mock_response


@pytest.mark.asyncio
async def test_proxy_clip_enabled(client: httpx.AsyncClient, mock_frigate_response):
    """Test that clips are proxied when clips_enabled is True."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = True
    settings.media_cache.enabled = False # Disable cache for this test

    with patch("app.routers.proxy.httpx.AsyncClient") as MockClient, \
         patch("app.routers.proxy.frigate_client") as mock_frigate:
        
        mock_frigate.get_event = AsyncMock(return_value={"has_clip": True})
        mock_frigate._get_headers = MagicMock(return_value={})

        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_frigate_response)
        mock_client.aclose = AsyncMock()
        MockClient.return_value = mock_client

        try:
            response = await client.get("/api/frigate/test_event_id/clip.mp4")
            assert response.status_code == 200
            assert response.headers.get("content-type") == "video/mp4"
            assert response.headers.get("accept-ranges") == "bytes"
        finally:
            settings.frigate.clips_enabled = original_setting


@pytest.mark.asyncio
async def test_proxy_clip_range_header_forwarded(client: httpx.AsyncClient, mock_frigate_partial_response):
    """Test that Range headers are forwarded to Frigate and 206 responses are returned."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = True
    settings.media_cache.enabled = False # Disable cache for this test

    with patch("app.routers.proxy.httpx.AsyncClient") as MockClient, \
         patch("app.routers.proxy.frigate_client") as mock_frigate:
        
        mock_frigate.get_event = AsyncMock(return_value={"has_clip": True})
        mock_frigate._get_headers = MagicMock(return_value={})

        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_frigate_partial_response)
        mock_client.aclose = AsyncMock()
        MockClient.return_value = mock_client

        try:
            response = await client.get(
                "/api/frigate/test_event_id/clip.mp4",
                headers={"Range": "bytes=0-999"}
            )
            assert response.status_code == 206
            assert response.headers.get("content-range") == "bytes 0-999/12345"
        finally:
            settings.frigate.clips_enabled = original_setting


@pytest.mark.asyncio
async def test_proxy_clip_404_from_frigate(client: httpx.AsyncClient):
    """Test that 404 from Frigate is properly returned."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = True

    with patch("app.routers.proxy.frigate_client") as mock_frigate:
        mock_frigate.get_event = AsyncMock(return_value=None)

        try:
            response = await client.get("/api/frigate/test_event_id/clip.mp4")
            assert response.status_code == 404
            assert "Event not found in Frigate" in response.json()["detail"]
        finally:
            settings.frigate.clips_enabled = original_setting


@pytest.mark.asyncio
async def test_proxy_clip_thumbnails_vtt_success(client: httpx.AsyncClient):
    """VTT endpoint should return WebVTT with sprite cue URLs."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = True

    manifest_json = (
        '{"version":1,"event_id":"test_event_id","tile_width":160,"tile_height":90,'
        '"cues":[{"start":0.0,"end":2.0,"x":0,"y":0,"w":160,"h":90}]}'
    )

    with patch("app.routers.proxy.frigate_client") as mock_frigate, \
         patch("app.routers.proxy._ensure_preview_assets", new_callable=AsyncMock) as mock_ensure, \
         patch("app.services.media_cache.media_cache.get_preview_manifest", new_callable=AsyncMock) as mock_manifest:
        mock_frigate.get_event = AsyncMock(return_value={"has_clip": True})
        mock_manifest.return_value = manifest_json
        mock_ensure.return_value = None

        try:
            response = await client.get("/api/frigate/test_event_id/clip-thumbnails.vtt?token=abc123")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/vtt")
            assert "WEBVTT" in response.text
            assert "clip-thumbnails.jpg?token=abc123#xywh=0,0,160,90" in response.text
            assert "http://" not in response.text
            assert "https://" not in response.text
        finally:
            settings.frigate.clips_enabled = original_setting


@pytest.mark.asyncio
async def test_proxy_clip_thumbnails_sprite_success(client: httpx.AsyncClient):
    """Sprite endpoint should serve generated sprite file."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = True

    with NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(b"fake-jpeg")
        sprite_path = Path(tmp.name)

    with patch("app.routers.proxy._ensure_preview_assets", new_callable=AsyncMock) as mock_ensure, \
         patch("app.services.media_cache.media_cache.get_preview_sprite_path") as mock_sprite:
        mock_ensure.return_value = None
        mock_sprite.return_value = sprite_path

        try:
            response = await client.get("/api/frigate/test_event_id/clip-thumbnails.jpg")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("image/jpeg")
        finally:
            settings.frigate.clips_enabled = original_setting
            sprite_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_proxy_clip_thumbnails_vtt_disabled_when_media_cache_off(client: httpx.AsyncClient):
    """Preview generation should be disabled when media cache is disabled."""
    original_clips = settings.frigate.clips_enabled
    original_cache = settings.media_cache.enabled
    settings.frigate.clips_enabled = True
    settings.media_cache.enabled = False

    with patch("app.routers.proxy.frigate_client") as mock_frigate:
        mock_frigate.get_event = AsyncMock(return_value={"has_clip": True})
        try:
            response = await client.get("/api/frigate/test_event_id/clip-thumbnails.vtt")
            assert response.status_code == 503
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.media_cache.enabled = original_cache


@pytest.mark.asyncio
async def test_proxy_clip_download_forbidden_for_guest_when_disabled(client: httpx.AsyncClient):
    """Guest downloads should be blocked when public clip downloads are disabled."""
    original_clips = settings.frigate.clips_enabled
    original_auth = settings.auth.enabled
    original_public = settings.public_access.enabled
    original_allow_downloads = settings.public_access.allow_clip_downloads

    settings.frigate.clips_enabled = True
    settings.auth.enabled = True
    settings.public_access.enabled = True
    settings.public_access.allow_clip_downloads = False

    with patch("app.routers.proxy.require_event_access", new_callable=AsyncMock) as mock_access:
        mock_access.return_value = None
        try:
            response = await client.get("/api/frigate/test_event_id/clip.mp4?download=1")
            assert response.status_code == 403
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.auth.enabled = original_auth
            settings.public_access.enabled = original_public
            settings.public_access.allow_clip_downloads = original_allow_downloads


@pytest.mark.asyncio
async def test_proxy_clip_allows_valid_share_token_without_auth(client: httpx.AsyncClient, mock_frigate_response):
    """A valid share token should allow clip playback even when auth is otherwise required."""
    original_clips = settings.frigate.clips_enabled
    original_cache = settings.media_cache.enabled
    original_auth = settings.auth.enabled
    original_public = settings.public_access.enabled

    settings.frigate.clips_enabled = True
    settings.media_cache.enabled = False
    settings.auth.enabled = True
    settings.public_access.enabled = False

    with patch("app.routers.proxy._resolve_video_share_token", new_callable=AsyncMock) as mock_share,          patch("app.routers.proxy.httpx.AsyncClient") as MockClient,          patch("app.routers.proxy.frigate_client") as mock_frigate:
        mock_share.return_value = {
            "frigate_event": "test_event_id",
            "watermark_label": "Shared",
            "expires_at": datetime.utcnow() + timedelta(hours=1),
        }
        mock_frigate.get_event = AsyncMock(return_value={"has_clip": True})
        mock_frigate._get_headers = MagicMock(return_value={})

        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_frigate_response)
        mock_client.aclose = AsyncMock()
        MockClient.return_value = mock_client

        try:
            response = await client.get("/api/frigate/test_event_id/clip.mp4?share=valid_share_token_123456")
            assert response.status_code == 200
            assert response.headers.get("content-type") == "video/mp4"
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.media_cache.enabled = original_cache
            settings.auth.enabled = original_auth
            settings.public_access.enabled = original_public


@pytest.mark.asyncio
async def test_proxy_clip_rejects_invalid_share_token_when_auth_required(client: httpx.AsyncClient):
    """Invalid share tokens must not bypass auth requirements."""
    original_clips = settings.frigate.clips_enabled
    original_auth = settings.auth.enabled
    original_public = settings.public_access.enabled

    settings.frigate.clips_enabled = True
    settings.auth.enabled = True
    settings.public_access.enabled = False

    with patch("app.routers.proxy._resolve_video_share_token", new_callable=AsyncMock) as mock_share:
        mock_share.return_value = None
        try:
            response = await client.get("/api/frigate/test_event_id/clip.mp4?share=invalid_share_token_123456")
            assert response.status_code == 401
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.auth.enabled = original_auth
            settings.public_access.enabled = original_public


@pytest.mark.asyncio
async def test_proxy_clip_thumbnails_vtt_preserves_share_query(client: httpx.AsyncClient):
    """VTT cue sprite URLs should preserve share query tokens."""
    original_clips = settings.frigate.clips_enabled
    original_auth = settings.auth.enabled
    original_public = settings.public_access.enabled

    settings.frigate.clips_enabled = True
    settings.auth.enabled = True
    settings.public_access.enabled = False

    manifest_json = (
        '{"version":1,"event_id":"test_event_id","tile_width":160,"tile_height":90,'
        '"cues":[{"start":0.0,"end":2.0,"x":0,"y":0,"w":160,"h":90}]}'
    )

    with patch("app.routers.proxy._resolve_video_share_token", new_callable=AsyncMock) as mock_share,          patch("app.routers.proxy.frigate_client") as mock_frigate,          patch("app.routers.proxy._ensure_preview_assets", new_callable=AsyncMock) as mock_ensure,          patch("app.services.media_cache.media_cache.get_preview_manifest", new_callable=AsyncMock) as mock_manifest:
        mock_share.return_value = {
            "frigate_event": "test_event_id",
            "watermark_label": "Shared",
            "expires_at": datetime.utcnow() + timedelta(hours=1),
        }
        mock_frigate.get_event = AsyncMock(return_value={"has_clip": True})
        mock_manifest.return_value = manifest_json
        mock_ensure.return_value = None

        try:
            response = await client.get("/api/frigate/test_event_id/clip-thumbnails.vtt?share=valid_share_token_123456")
            assert response.status_code == 200
            assert "clip-thumbnails.jpg?share=valid_share_token_123456#xywh=0,0,160,90" in response.text
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.auth.enabled = original_auth
            settings.public_access.enabled = original_public
