import httpx
import pytest

from app.services.frigate_client import FrigateClient


@pytest.mark.asyncio
async def test_get_clip_with_error_maps_missing_recordings_400_to_clip_not_retained():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/api/events/evt-1/clip.mp4")
        return httpx.Response(
            400,
            json={"success": False, "message": "No recordings found for the specified time range"},
        )

    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://frigate")

    try:
        clip, error = await client.get_clip_with_error("evt-1")
    finally:
        await client._client.aclose()
        client._client = None

    assert clip is None
    assert error == "clip_not_retained"
