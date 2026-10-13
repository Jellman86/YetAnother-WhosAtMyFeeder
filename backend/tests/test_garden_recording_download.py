"""Recording media is streamed, authenticated and bounded before native decoding."""

import httpx
import pytest

from app.config import settings
from app.services.frigate_client import FrigateClient


@pytest.mark.asyncio
async def test_recording_download_streams_with_auth_and_exact_fractional_window(tmp_path, monkeypatch):
    monkeypatch.setattr(settings.frigate, "frigate_auth_token", "private-test-token")
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, content=b"recording")

    service = FrigateClient()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        service._client = client
        path = tmp_path / "clip.mp4"
        await service.download_motion_recording("patio", 100.125, 110.125, path)
    assert path.read_bytes() == b"recording"
    assert seen[0].url.path.endswith("/api/patio/start/100.125000/end/110.125000/clip.mp4")
    assert seen[0].headers["Authorization"] == "Bearer private-test-token"


@pytest.mark.asyncio
async def test_recording_download_rejects_oversize_before_writing(tmp_path):
    service = FrigateClient()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"12345"))
    ) as client:
        service._client = client
        with pytest.raises(ValueError):
            await service.download_motion_recording("patio", 100.0, 110.0, tmp_path / "clip", byte_limit=4)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "camera,start,end", [("../patio", 100.0, 110.0), ("patio", 100.0, 111.0), ("patio", float("nan"), 110.0)]
)
async def test_invalid_window_never_fetches(camera, start, end, tmp_path):
    service = FrigateClient()
    with pytest.raises(ValueError):
        await service.download_motion_recording(camera, start, end, tmp_path / "clip")
