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
async def test_get_clean_snapshot_with_error_uses_frigate_clean_copy_endpoint():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/events/evt-clean/snapshot-clean.webp"
        return httpx.Response(200, content=b"clean-webp")

    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://frigate")
    try:
        snapshot, error = await client.get_clean_snapshot_with_error("evt-clean")
    finally:
        await client._client.aclose()
        client._client = None

    assert snapshot == b"clean-webp"
    assert error is None


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


@pytest.mark.asyncio
async def test_get_recording_clip_with_error_returns_bytes_for_time_window():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/BirdCam/start/1774511034/end/1774511044/clip.mp4"
        return httpx.Response(200, content=b"\x00\x00\x00\x18ftypisomrecording")

    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://frigate")
    try:
        clip, error = await client.get_recording_clip_with_error("BirdCam", 1774511034, 1774511044)
    finally:
        await client._client.aclose()
        client._client = None

    assert clip == b"\x00\x00\x00\x18ftypisomrecording"
    assert error is None


@pytest.mark.asyncio
async def test_get_recording_clip_with_error_maps_404_to_clip_not_found():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://frigate")
    try:
        clip, error = await client.get_recording_clip_with_error("BirdCam", 1, 2)
    finally:
        await client._client.aclose()
        client._client = None

    assert clip is None
    assert error == "clip_not_found"


@pytest.mark.asyncio
async def test_get_recording_clip_with_error_maps_missing_recordings_400_to_clip_not_retained():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "No recordings found for the specified time range"})

    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://frigate")
    try:
        clip, error = await client.get_recording_clip_with_error("BirdCam", 1, 2)
    finally:
        await client._client.aclose()
        client._client = None

    assert clip is None
    assert error == "clip_not_retained"


@pytest.mark.asyncio
async def test_set_sublabel_preserves_full_species_name_and_confidence():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://frigate")
    try:
        updated = await client.set_sublabel(
            "evt-long-species",
            "Black-crowned Night Heron",
            score=0.876,
        )
    finally:
        await client._client.aclose()
        client._client = None

    assert updated is True
    assert requests[0].url.path == "/api/events/evt-long-species/sub_label"
    assert requests[0].read().decode() == ('{"subLabel":"Black-crowned Night Heron","subLabelScore":0.876}')
