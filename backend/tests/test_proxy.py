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
async def test_proxy_recording_clip_enabled(client: httpx.AsyncClient, mock_frigate_response):
    original_clips = settings.frigate.clips_enabled
    original_recording = settings.frigate.recording_clip_enabled
    settings.frigate.clips_enabled = True
    settings.frigate.recording_clip_enabled = True
    settings.media_cache.enabled = False

    with patch("app.routers.proxy._get_recording_clip_context", new_callable=AsyncMock) as mock_context, \
         patch("app.routers.proxy.httpx.AsyncClient") as MockClient, \
         patch("app.routers.proxy.frigate_client") as mock_frigate:
        mock_context.return_value = ("front_feeder", 1700000000, 1700000120)
        mock_frigate.get_camera_recording_clip_url = MagicMock(
            return_value="http://frigate/api/front_feeder/start/1700000000/end/1700000120/clip.mp4"
        )
        mock_frigate._get_headers = MagicMock(return_value={})

        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_frigate_response)
        mock_client.aclose = AsyncMock()
        MockClient.return_value = mock_client

        try:
            response = await client.get("/api/frigate/test_event_id/recording-clip.mp4")
            assert response.status_code == 200
            assert response.headers.get("content-type") == "video/mp4"
            assert response.headers.get("accept-ranges") == "bytes"
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.frigate.recording_clip_enabled = original_recording


@pytest.mark.asyncio
async def test_proxy_recording_clip_returns_404_when_no_recordings_found(client: httpx.AsyncClient):
    original_clips = settings.frigate.clips_enabled
    original_recording = settings.frigate.recording_clip_enabled
    settings.frigate.clips_enabled = True
    settings.frigate.recording_clip_enabled = True
    settings.media_cache.enabled = False

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json = MagicMock(return_value={"message": "No recordings found for the specified time range"})
    mock_response.text = '{"message":"No recordings found for the specified time range"}'
    mock_response.aclose = AsyncMock()

    with patch("app.routers.proxy._get_recording_clip_context", new_callable=AsyncMock) as mock_context, \
         patch("app.routers.proxy.httpx.AsyncClient") as MockClient, \
         patch("app.routers.proxy.frigate_client") as mock_frigate:
        mock_context.return_value = ("front_feeder", 1700000000, 1700000120)
        mock_frigate.get_camera_recording_clip_url = MagicMock(
            return_value="http://frigate/api/front_feeder/start/1700000000/end/1700000120/clip.mp4"
        )
        mock_frigate._get_headers = MagicMock(return_value={})

        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()
        MockClient.return_value = mock_client

        try:
            response = await client.get("/api/frigate/test_event_id/recording-clip.mp4")
            assert response.status_code == 404
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.frigate.recording_clip_enabled = original_recording


@pytest.mark.asyncio
async def test_proxy_recording_clip_allows_valid_share_token_without_auth(client: httpx.AsyncClient, mock_frigate_response):
    original_clips = settings.frigate.clips_enabled
    original_recording = settings.frigate.recording_clip_enabled
    original_cache = settings.media_cache.enabled
    original_auth = settings.auth.enabled
    original_public = settings.public_access.enabled

    settings.frigate.clips_enabled = True
    settings.frigate.recording_clip_enabled = True
    settings.media_cache.enabled = False
    settings.auth.enabled = True
    settings.public_access.enabled = False

    with patch("app.routers.proxy._resolve_video_share_token", new_callable=AsyncMock) as mock_share, \
         patch("app.routers.proxy._get_recording_clip_context", new_callable=AsyncMock) as mock_context, \
         patch("app.routers.proxy.httpx.AsyncClient") as MockClient, \
         patch("app.routers.proxy.frigate_client") as mock_frigate:
        mock_share.return_value = {
            "frigate_event": "test_event_id",
            "watermark_label": "Shared",
            "expires_at": datetime.utcnow() + timedelta(hours=1),
        }
        mock_context.return_value = ("front_feeder", 1700000000, 1700000120)
        mock_frigate.get_camera_recording_clip_url = MagicMock(
            return_value="http://frigate/api/front_feeder/start/1700000000/end/1700000120/clip.mp4"
        )
        mock_frigate._get_headers = MagicMock(return_value={})

        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_frigate_response)
        mock_client.aclose = AsyncMock()
        MockClient.return_value = mock_client

        try:
            response = await client.get("/api/frigate/test_event_id/recording-clip.mp4?share=valid_share_token_123456")
            assert response.status_code == 200
            assert response.headers.get("content-type") == "video/mp4"
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.frigate.recording_clip_enabled = original_recording
            settings.media_cache.enabled = original_cache
            settings.auth.enabled = original_auth
            settings.public_access.enabled = original_public


@pytest.mark.asyncio
async def test_check_recording_clip_exists_uses_streaming_probe(client: httpx.AsyncClient):
    original_clips = settings.frigate.clips_enabled
    original_recording = settings.frigate.recording_clip_enabled
    settings.frigate.clips_enabled = True
    settings.frigate.recording_clip_enabled = True

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "video/mp4"}
    mock_response.aclose = AsyncMock()

    mock_client = MagicMock()
    mock_client.build_request = MagicMock(return_value=object())
    mock_client.send = AsyncMock(return_value=mock_response)

    with patch("app.routers.proxy._get_recording_clip_context", new_callable=AsyncMock) as mock_context, \
         patch("app.routers.proxy.get_http_client", return_value=mock_client), \
         patch("app.routers.proxy.frigate_client") as mock_frigate:
        mock_context.return_value = ("front_feeder", 1700000000, 1700000120)
        mock_frigate.get_camera_recording_clip_url = MagicMock(
            return_value="http://frigate/api/front_feeder/start/1700000000/end/1700000120/clip.mp4"
        )
        mock_frigate._get_headers = MagicMock(return_value={})

        try:
            response = await client.head("/api/frigate/test_event_id/recording-clip.mp4")
            assert response.status_code == 200
            mock_client.send.assert_awaited_once()
            _args, kwargs = mock_client.send.await_args
            assert kwargs["stream"] is True
            mock_response.aclose.assert_awaited_once()
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.frigate.recording_clip_enabled = original_recording


@pytest.mark.asyncio
async def test_check_recording_clip_exists_returns_404_for_streamed_no_recordings_response(client: httpx.AsyncClient):
    original_clips = settings.frigate.clips_enabled
    original_recording = settings.frigate.recording_clip_enabled
    settings.frigate.clips_enabled = True
    settings.frigate.recording_clip_enabled = True

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.headers = {"content-type": "application/json"}
    mock_response.json = MagicMock(side_effect=[
        ValueError("response not read yet"),
        {"message": "No recordings found for the specified time range"},
    ])
    mock_response.aread = AsyncMock(return_value=b'{"message":"No recordings found for the specified time range"}')
    mock_response.text = '{"message":"No recordings found for the specified time range"}'
    mock_response.aclose = AsyncMock()

    mock_client = MagicMock()
    mock_client.build_request = MagicMock(return_value=object())
    mock_client.send = AsyncMock(return_value=mock_response)

    with patch("app.routers.proxy._get_recording_clip_context", new_callable=AsyncMock) as mock_context, \
         patch("app.routers.proxy.get_http_client", return_value=mock_client), \
         patch("app.routers.proxy.frigate_client") as mock_frigate:
        mock_context.return_value = ("front_feeder", 1700000000, 1700000120)
        mock_frigate.get_camera_recording_clip_url = MagicMock(
            return_value="http://frigate/api/front_feeder/start/1700000000/end/1700000120/clip.mp4"
        )
        mock_frigate._get_headers = MagicMock(return_value={})

        try:
            response = await client.head("/api/frigate/test_event_id/recording-clip.mp4")
            assert response.status_code == 404
            mock_response.aread.assert_awaited_once()
            mock_response.aclose.assert_awaited_once()
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.frigate.recording_clip_enabled = original_recording


@pytest.mark.asyncio
async def test_recording_clip_fetch_warms_cache_when_available(client: httpx.AsyncClient, mock_frigate_response):
    original_clips = settings.frigate.clips_enabled
    original_recording = settings.frigate.recording_clip_enabled
    original_cache_enabled = settings.media_cache.enabled
    original_cache_clips = settings.media_cache.cache_clips
    settings.frigate.clips_enabled = True
    settings.frigate.recording_clip_enabled = True
    settings.media_cache.enabled = True
    settings.media_cache.cache_clips = True

    with patch("app.routers.proxy._get_recording_clip_context", new_callable=AsyncMock) as mock_context, \
         patch("app.routers.proxy.httpx.AsyncClient") as MockClient, \
         patch("app.routers.proxy.frigate_client") as mock_frigate, \
         patch("app.services.media_cache.media_cache.get_recording_clip_path", return_value=None), \
         patch("app.services.media_cache.media_cache.cache_recording_clip_streaming", new_callable=AsyncMock) as mock_cache:
        mock_context.return_value = ("front_feeder", 1700000000, 1700000120)
        mock_frigate.get_camera_recording_clip_url = MagicMock(
            return_value="http://frigate/api/front_feeder/start/1700000000/end/1700000120/clip.mp4"
        )
        mock_frigate._get_headers = MagicMock(return_value={})
        mock_cache.return_value = Path("/config/media_cache/clips/test_event_id_recording.mp4")

        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_frigate_response)
        mock_client.aclose = AsyncMock()
        MockClient.return_value = mock_client

        try:
            response = await client.post("/api/frigate/test_event_id/recording-clip/fetch")
            assert response.status_code == 200
            assert response.json()["status"] == "ready"
            assert response.json()["clip_variant"] == "recording"
            assert response.json()["cached"] is True
            mock_cache.assert_awaited_once()
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.frigate.recording_clip_enabled = original_recording
            settings.media_cache.enabled = original_cache_enabled
            settings.media_cache.cache_clips = original_cache_clips


@pytest.mark.asyncio
async def test_recording_clip_fetch_returns_404_when_timespan_missing(client: httpx.AsyncClient):
    original_clips = settings.frigate.clips_enabled
    original_recording = settings.frigate.recording_clip_enabled
    original_cache_enabled = settings.media_cache.enabled
    original_cache_clips = settings.media_cache.cache_clips
    settings.frigate.clips_enabled = True
    settings.frigate.recording_clip_enabled = True
    settings.media_cache.enabled = True
    settings.media_cache.cache_clips = True

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json = MagicMock(return_value={"message": "No recordings found for the specified time range"})
    mock_response.text = '{"message":"No recordings found for the specified time range"}'
    mock_response.aclose = AsyncMock()

    with patch("app.routers.proxy._get_recording_clip_context", new_callable=AsyncMock) as mock_context, \
         patch("app.routers.proxy.httpx.AsyncClient") as MockClient, \
         patch("app.routers.proxy.frigate_client") as mock_frigate, \
         patch("app.services.media_cache.media_cache.get_recording_clip_path", return_value=None), \
         patch("app.services.media_cache.media_cache.cache_recording_clip_streaming", new_callable=AsyncMock) as mock_cache:
        mock_context.return_value = ("front_feeder", 1700000000, 1700000120)
        mock_frigate.get_camera_recording_clip_url = MagicMock(
            return_value="http://frigate/api/front_feeder/start/1700000000/end/1700000120/clip.mp4"
        )
        mock_frigate._get_headers = MagicMock(return_value={})

        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()
        MockClient.return_value = mock_client

        try:
            response = await client.post("/api/frigate/test_event_id/recording-clip/fetch")
            assert response.status_code == 404
            mock_cache.assert_not_awaited()
        finally:
            settings.frigate.clips_enabled = original_clips
            settings.frigate.recording_clip_enabled = original_recording
            settings.media_cache.enabled = original_cache_enabled
            settings.media_cache.cache_clips = original_cache_clips


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
async def test_proxy_snapshot_cache_hit_sets_no_store_headers(client: httpx.AsyncClient):
    original_cache_enabled = settings.media_cache.enabled
    original_cache_snapshots = settings.media_cache.cache_snapshots
    settings.media_cache.enabled = True
    settings.media_cache.cache_snapshots = True

    with patch("app.services.media_cache.media_cache.get_snapshot", new_callable=AsyncMock) as mock_snapshot:
        mock_snapshot.return_value = b"fake-jpeg"

        try:
            response = await client.get("/api/frigate/test_event_id/snapshot.jpg")
            assert response.status_code == 200
            assert response.content == b"fake-jpeg"
            assert response.headers["cache-control"] == "no-store, max-age=0"
            assert response.headers["pragma"] == "no-cache"
        finally:
            settings.media_cache.enabled = original_cache_enabled
            settings.media_cache.cache_snapshots = original_cache_snapshots


@pytest.mark.asyncio
async def test_proxy_thumbnail_cache_hit_sets_no_store_headers(client: httpx.AsyncClient):
    original_cache_enabled = settings.media_cache.enabled
    original_cache_snapshots = settings.media_cache.cache_snapshots
    settings.media_cache.enabled = True
    settings.media_cache.cache_snapshots = True

    with patch("app.services.media_cache.media_cache.get_snapshot", new_callable=AsyncMock) as mock_snapshot:
        mock_snapshot.return_value = b"fake-jpeg"

        try:
            response = await client.get("/api/frigate/test_event_id/thumbnail.jpg")
            assert response.status_code == 200
            assert response.content == b"fake-jpeg"
            assert response.headers["cache-control"] == "no-store, max-age=0"
            assert response.headers["pragma"] == "no-cache"
        finally:
            settings.media_cache.enabled = original_cache_enabled
            settings.media_cache.cache_snapshots = original_cache_snapshots


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


@pytest.mark.asyncio
async def test_recording_clip_capability_reports_supported_config(client: httpx.AsyncClient):
    original_auth = settings.auth.enabled
    original_public = settings.public_access.enabled
    original_cameras = list(settings.frigate.camera)

    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera = ["front_feeder"]

    frigate_config = {
        "record": {
            "enabled": True,
            "retain": {
                "days": 7,
            },
        },
        "cameras": {
            "front_feeder": {
                "record": {
                    "enabled": True,
                }
            }
        },
    }

    with patch("app.routers.proxy.frigate_client") as mock_frigate:
        mock_frigate.get_config = AsyncMock(return_value=frigate_config)

        try:
            response = await client.get("/api/frigate/recording-clip-capability")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["supported"] is True
            assert body["recordings_enabled"] is True
            assert body["retention_days"] == 7
            assert body["eligible_cameras"] == ["front_feeder"]
            assert body["reason"] is None
        finally:
            settings.auth.enabled = original_auth
            settings.public_access.enabled = original_public
            settings.frigate.camera = original_cameras


@pytest.mark.asyncio
async def test_recording_clip_capability_reports_unsupported_config(client: httpx.AsyncClient):
    original_auth = settings.auth.enabled
    original_public = settings.public_access.enabled
    original_cameras = list(settings.frigate.camera)

    settings.auth.enabled = False
    settings.public_access.enabled = False
    settings.frigate.camera = ["front_feeder"]

    frigate_config = {
        "record": {
            "enabled": False,
        },
        "cameras": {
            "front_feeder": {
                "record": {
                    "enabled": False,
                }
            }
        },
    }

    with patch("app.routers.proxy.frigate_client") as mock_frigate:
        mock_frigate.get_config = AsyncMock(return_value=frigate_config)

        try:
            response = await client.get("/api/frigate/recording-clip-capability")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["supported"] is False
            assert body["recordings_enabled"] is False
            assert body["eligible_cameras"] == []
            assert body["reason"] == "recordings_disabled"
        finally:
            settings.auth.enabled = original_auth
            settings.public_access.enabled = original_public
            settings.frigate.camera = original_cameras


@pytest.mark.asyncio
async def test_video_share_create_returns_link_id(client: httpx.AsyncClient):
    """Create endpoint should return link_id alongside share token metadata."""
    with patch("app.routers.proxy.frigate_client") as mock_frigate,          patch("app.routers.proxy._create_video_share_token", new_callable=AsyncMock) as mock_create:
        mock_frigate.get_event = AsyncMock(return_value={"has_clip": True})
        mock_create.return_value = (42, "share_token_abcdefghijklmnopqrstuvwxyz", datetime.utcnow() + timedelta(hours=1))

        response = await client.post(
            "/api/video-share",
            json={
                "event_id": "test_event_id",
                "expires_in_minutes": 60,
                "watermark_label": "Tester",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["link_id"] == 42
        assert body["event_id"] == "test_event_id"
        assert body["token"] == "share_token_abcdefghijklmnopqrstuvwxyz"


@pytest.mark.asyncio
async def test_video_share_create_allows_recording_variant_without_event_clip(client: httpx.AsyncClient):
    with patch("app.routers.proxy.frigate_client") as mock_frigate, \
         patch("app.routers.proxy._create_video_share_token", new_callable=AsyncMock) as mock_create, \
         patch("app.routers.proxy._recording_clip_exists_for_share", new_callable=AsyncMock) as mock_recording_exists:
        mock_frigate.get_event = AsyncMock(return_value={"has_clip": False})
        mock_recording_exists.return_value = True
        mock_create.return_value = (43, "share_token_recording_variant", datetime.utcnow() + timedelta(hours=1))

        response = await client.post(
            "/api/video-share",
            json={
                "event_id": "test_event_id",
                "expires_in_minutes": 60,
                "watermark_label": "Tester",
                "clip_variant": "recording",
            },
        )

        assert response.status_code == 200
        body = response.json()
        assert body["link_id"] == 43
        assert "clip=recording" in body["share_url"]


@pytest.mark.asyncio
async def test_video_share_create_uses_configured_external_base_url(client: httpx.AsyncClient):
    """Share links should honor PUBLIC_ACCESS external base URL when configured."""
    original_base_url = settings.public_access.external_base_url
    settings.public_access.external_base_url = "https://public.example.com/app/"
    try:
        with patch("app.routers.proxy.frigate_client") as mock_frigate, \
             patch("app.routers.proxy._create_video_share_token", new_callable=AsyncMock) as mock_create:
            mock_frigate.get_event = AsyncMock(return_value={"has_clip": True})
            mock_create.return_value = (
                77,
                "share_token_abcdefghijklmnopqrstuvwxyz",
                datetime.utcnow() + timedelta(hours=1),
            )

            response = await client.post(
                "/api/video-share",
                json={
                    "event_id": "test_event_id",
                    "expires_in_minutes": 60,
                    "watermark_label": "Tester",
                },
            )

            assert response.status_code == 200
            body = response.json()
            assert body["share_url"].startswith("https://public.example.com/app/events?")
    finally:
        settings.public_access.external_base_url = original_base_url


@pytest.mark.asyncio
async def test_video_share_create_falls_back_on_invalid_external_base_url(client: httpx.AsyncClient):
    """Invalid configured base URLs should fall back to request base URL."""
    original_base_url = settings.public_access.external_base_url
    settings.public_access.external_base_url = "not-a-valid-url"
    try:
        with patch("app.routers.proxy.frigate_client") as mock_frigate, \
             patch("app.routers.proxy._create_video_share_token", new_callable=AsyncMock) as mock_create:
            mock_frigate.get_event = AsyncMock(return_value={"has_clip": True})
            mock_create.return_value = (
                78,
                "share_token_abcdefghijklmnopqrstuvwxyz",
                datetime.utcnow() + timedelta(hours=1),
            )

            response = await client.post(
                "/api/video-share",
                json={
                    "event_id": "test_event_id",
                    "expires_in_minutes": 60,
                    "watermark_label": "Tester",
                },
            )

            assert response.status_code == 200
            body = response.json()
            assert body["share_url"].startswith("http://test/events?")
    finally:
        settings.public_access.external_base_url = original_base_url


@pytest.mark.asyncio
async def test_video_share_list_links_returns_payload(client: httpx.AsyncClient):
    """List endpoint should return active share links for an event."""
    from app.routers import proxy

    with patch("app.routers.proxy._list_active_video_share_links", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [
            proxy.VideoShareLinkItemResponse(
                id=1,
                event_id="test_event_id",
                created_by="owner",
                watermark_label="owner",
                created_at=datetime.utcnow().isoformat(),
                expires_at=(datetime.utcnow() + timedelta(hours=1)).isoformat(),
                is_active=True,
                remaining_seconds=3600,
            )
        ]

        response = await client.get("/api/video-share/test_event_id/links")
        assert response.status_code == 200
        body = response.json()
        assert body["event_id"] == "test_event_id"
        assert len(body["links"]) == 1
        assert body["links"][0]["id"] == 1


@pytest.mark.asyncio
async def test_video_share_update_link_requires_payload_fields(client: httpx.AsyncClient):
    """Update endpoint should reject empty payloads."""
    response = await client.patch("/api/video-share/test_event_id/links/5", json={})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_video_share_update_link_success(client: httpx.AsyncClient):
    """Update endpoint should return updated share-link metadata."""
    from app.routers import proxy

    with patch("app.routers.proxy._update_video_share_link", new_callable=AsyncMock) as mock_update:
        mock_update.return_value = proxy.VideoShareLinkItemResponse(
            id=5,
            event_id="test_event_id",
            created_by="owner",
            watermark_label="Updated Label",
            created_at=datetime.utcnow().isoformat(),
            expires_at=(datetime.utcnow() + timedelta(hours=2)).isoformat(),
            is_active=True,
            remaining_seconds=7200,
        )

        response = await client.patch(
            "/api/video-share/test_event_id/links/5",
            json={"expires_in_minutes": 120, "watermark_label": "Updated Label"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == 5
        assert body["watermark_label"] == "Updated Label"


@pytest.mark.asyncio
async def test_video_share_revoke_link_success(client: httpx.AsyncClient):
    """Revoke endpoint should mark active links as revoked."""
    with patch("app.routers.proxy._revoke_video_share_link", new_callable=AsyncMock) as mock_revoke:
        mock_revoke.return_value = True

        response = await client.post("/api/video-share/test_event_id/links/9/revoke")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "revoked"
        assert body["link_id"] == 9
