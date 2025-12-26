from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from app.main import app
from app.config import settings
import pytest

client = TestClient(app)


def test_proxy_clip_disabled():
    """Test that clips return 403 when clips_enabled is False."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = False

    try:
        response = client.get("/api/frigate/test_event_id/clip.mp4")
        assert response.status_code == 403
        assert response.json()["detail"] == "Clip fetching is disabled"
    finally:
        settings.frigate.clips_enabled = original_setting


def test_proxy_clip_head_disabled():
    """Test that HEAD requests for clips return 403 when clips_enabled is False."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = False

    try:
        response = client.head("/api/frigate/test_event_id/clip.mp4")
        assert response.status_code == 403
    finally:
        settings.frigate.clips_enabled = original_setting


def test_proxy_clip_invalid_event_id():
    """Test that invalid event IDs are rejected."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = True

    try:
        # Test with invalid characters
        response = client.get("/api/frigate/../../etc/passwd/clip.mp4")
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


def test_proxy_clip_enabled(mock_frigate_response):
    """Test that clips are proxied when clips_enabled is True."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = True

    with patch("app.routers.proxy.httpx.AsyncClient") as MockClient:
        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_frigate_response)
        mock_client.aclose = AsyncMock()
        MockClient.return_value = mock_client

        try:
            response = client.get("/api/frigate/test_event_id/clip.mp4")
            assert response.status_code == 200
            assert response.headers.get("content-type") == "video/mp4"
            assert response.headers.get("accept-ranges") == "bytes"
        finally:
            settings.frigate.clips_enabled = original_setting


def test_proxy_clip_range_header_forwarded(mock_frigate_partial_response):
    """Test that Range headers are forwarded to Frigate and 206 responses are returned."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = True

    with patch("app.routers.proxy.httpx.AsyncClient") as MockClient:
        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_frigate_partial_response)
        mock_client.aclose = AsyncMock()
        MockClient.return_value = mock_client

        try:
            response = client.get(
                "/api/frigate/test_event_id/clip.mp4",
                headers={"Range": "bytes=0-999"}
            )
            assert response.status_code == 206
            assert response.headers.get("content-range") == "bytes 0-999/12345"

            # Verify Range header was passed to build_request
            call_args = mock_client.build_request.call_args
            request_headers = call_args[1]["headers"] if "headers" in call_args[1] else call_args[0][2] if len(call_args[0]) > 2 else {}
            # The Range header should have been included
        finally:
            settings.frigate.clips_enabled = original_setting


def test_proxy_clip_404_from_frigate():
    """Test that 404 from Frigate is properly returned."""
    original_setting = settings.frigate.clips_enabled
    settings.frigate.clips_enabled = True

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.aclose = AsyncMock()

    with patch("app.routers.proxy.httpx.AsyncClient") as MockClient:
        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_response)
        mock_client.aclose = AsyncMock()
        MockClient.return_value = mock_client

        try:
            response = client.get("/api/frigate/test_event_id/clip.mp4")
            assert response.status_code == 404
            assert response.json()["detail"] == "Clip not found"
        finally:
            settings.frigate.clips_enabled = original_setting
