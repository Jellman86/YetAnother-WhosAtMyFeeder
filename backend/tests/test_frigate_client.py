import httpx
import pytest

from app.services.frigate_client import FrigateClient


def test_get_camera_recording_clip_url_uses_start_end_path_segments():
    client = FrigateClient()
    assert (
        client.get_camera_recording_clip_url("BirdCam", 1774511034, 1774511094)
        == f"{client.base_url}/api/BirdCam/start/1774511034/end/1774511094/clip.mp4"
    )


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
