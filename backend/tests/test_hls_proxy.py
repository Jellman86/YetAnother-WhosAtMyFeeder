from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

import app.routers.proxy as proxy_module
from app.config import settings
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def hls_enabled():
    original = (
        settings.frigate.clips_enabled,
        settings.frigate.recording_clip_enabled,
        settings.frigate.frigate_url,
    )
    settings.frigate.clips_enabled = True
    settings.frigate.recording_clip_enabled = True
    settings.frigate.frigate_url = "http://frigate"
    yield
    (
        settings.frigate.clips_enabled,
        settings.frigate.recording_clip_enabled,
        settings.frigate.frigate_url,
    ) = original


def playlist_response(body: str, status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.text = body
    response.headers = {"content-type": "application/vnd.apple.mpegurl"}
    response.raise_for_status.side_effect = (
        httpx.HTTPStatusError("upstream", request=MagicMock(), response=MagicMock(status_code=status_code))
        if status_code >= 400
        else None
    )
    response.aclose = AsyncMock()
    return response


def segment_response(*, accept_ranges: str | None = "bytes") -> MagicMock:
    async def chunks():
        yield b"fragment"

    response = MagicMock()
    response.status_code = 206
    response.headers = {
        "content-type": "video/mp4",
        "content-length": "8",
        "content-range": "bytes 0-7/20",
    }
    if accept_ranges:
        response.headers["accept-ranges"] = accept_ranges
    response.aiter_bytes = chunks
    response.aclose = AsyncMock()
    return response


@pytest.mark.asyncio
async def test_event_hls_playlist_rewrites_only_relative_allowlisted_assets(client: httpx.AsyncClient):
    upstream = playlist_response(
        '#EXTM3U\n#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",URI="index-v1-a1.m3u8"\nindex-v1.m3u8\n'
    )
    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=upstream)

    with patch.object(proxy_module, "get_http_client", return_value=mock_http):
        response = await client.get("/api/frigate/event-1/hls/master.m3u8?share=share_token_123456&ignored=secret")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert 'URI="index-v1-a1.m3u8?share=share_token_123456"' in response.text
    assert "index-v1.m3u8?share=share_token_123456" in response.text
    assert "ignored" not in response.text
    mock_http.get.assert_awaited_once_with(
        "http://frigate/api/vod/event/event-1/master.m3u8",
        headers=proxy_module.frigate_client._get_headers(),
        timeout=10.0,
    )


@pytest.mark.asyncio
async def test_hls_media_playlist_rewrites_init_and_segment_with_api_key(client: httpx.AsyncClient):
    upstream = playlist_response('#EXTM3U\n#EXT-X-MAP:URI="init-v1-a1.mp4"\n#EXTINF:4.0,\nseg-1-v1-a1.m4s\n')
    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=upstream)

    with patch.object(proxy_module, "get_http_client", return_value=mock_http):
        response = await client.get("/api/frigate/event-1/hls/index-v1-a1.m3u8?api_key=key%20value")

    assert response.status_code == 200
    assert 'URI="init-v1-a1.mp4?api_key=key+value"' in response.text
    assert "seg-1-v1-a1.m4s?api_key=key+value" in response.text


@pytest.mark.asyncio
async def test_hls_rejects_an_unexpected_requested_asset_before_contacting_frigate(client: httpx.AsyncClient):
    mock_http = MagicMock()
    with patch.object(proxy_module, "get_http_client", return_value=mock_http):
        response = await client.get("/api/frigate/event-1/hls/not-a-frigate-asset.txt")

    assert response.status_code == 400
    mock_http.get.assert_not_called()


@pytest.mark.asyncio
async def test_hls_rejects_an_unsafe_uri_in_an_upstream_playlist(client: httpx.AsyncClient):
    upstream = playlist_response("#EXTM3U\nhttps://attacker.invalid/segment.m4s\n")
    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=upstream)

    with patch.object(proxy_module, "get_http_client", return_value=mock_http):
        response = await client.get("/api/frigate/event-1/hls/master.m3u8")

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_hls_segment_forwards_range_and_only_copies_upstream_range_support(client: httpx.AsyncClient):
    upstream = segment_response()
    mock_http = MagicMock()
    mock_http.build_request.return_value = MagicMock()
    mock_http.send = AsyncMock(return_value=upstream)

    with patch.object(proxy_module, "get_http_client", return_value=mock_http):
        response = await client.get(
            "/api/frigate/event-1/hls/seg-1-v1-a1.m4s",
            headers={"Range": "bytes=0-7"},
        )

    assert response.status_code == 206
    assert response.content == b"fragment"
    assert response.headers["content-range"] == "bytes 0-7/20"
    assert response.headers["accept-ranges"] == "bytes"
    sent_headers = mock_http.build_request.call_args.kwargs["headers"]
    assert sent_headers["Range"] == "bytes=0-7"
    upstream.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_hls_segment_does_not_invent_accept_ranges(client: httpx.AsyncClient):
    upstream = segment_response(accept_ranges=None)
    mock_http = MagicMock()
    mock_http.build_request.return_value = MagicMock()
    mock_http.send = AsyncMock(return_value=upstream)

    with patch.object(proxy_module, "get_http_client", return_value=mock_http):
        response = await client.get("/api/frigate/event-1/hls/init-v1-a1.mp4")

    assert response.status_code == 206
    assert "accept-ranges" not in response.headers


@pytest.mark.asyncio
async def test_recording_hls_uses_the_existing_full_visit_window(client: httpx.AsyncClient):
    upstream = playlist_response("#EXTM3U\nindex-v1-a1.m3u8\n")
    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=upstream)

    with (
        patch.object(proxy_module, "get_http_client", return_value=mock_http),
        patch.object(
            proxy_module,
            "_get_recording_clip_context",
            new=AsyncMock(return_value=("front_feeder", 1700000000, 1700000120)),
        ),
    ):
        response = await client.get("/api/frigate/event-1/recording-hls/master.m3u8")

    assert response.status_code == 200
    mock_http.get.assert_awaited_once_with(
        "http://frigate/api/vod/front_feeder/start/1700000000/end/1700000120/master.m3u8",
        headers=proxy_module.frigate_client._get_headers(),
        timeout=10.0,
    )


@pytest.mark.asyncio
async def test_recording_hls_rejects_an_invalid_camera_from_storage(client: httpx.AsyncClient):
    mock_http = MagicMock()
    with (
        patch.object(proxy_module, "get_http_client", return_value=mock_http),
        patch.object(
            proxy_module,
            "_get_recording_clip_context",
            new=AsyncMock(return_value=("../other-service", 1700000000, 1700000120)),
        ),
    ):
        response = await client.get("/api/frigate/event-1/recording-hls/master.m3u8")

    assert response.status_code == 400
    mock_http.get.assert_not_called()


@pytest.mark.asyncio
async def test_hls_upstream_404_is_a_404_for_frontend_mp4_fallback(client: httpx.AsyncClient):
    upstream = playlist_response("missing", status_code=404)
    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=upstream)

    with patch.object(proxy_module, "get_http_client", return_value=mock_http):
        response = await client.get("/api/frigate/event-1/hls/master.m3u8")

    assert response.status_code == 404
