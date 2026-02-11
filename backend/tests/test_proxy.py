from pathlib import Path
from tempfile import NamedTemporaryFile
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
