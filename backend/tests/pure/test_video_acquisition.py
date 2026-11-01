"""The clip acquisition stage hands over a clip it no longer owns, or nothing at all.

Whatever happens to the load (refusal, error or cancellation), the stage never leaves
its reserved temporary file behind. Once it returns a work input, the coordinator
owns that file.
"""

import asyncio
import os

import pytest

from app.services.video_acquisition import ClipUnavailable, VideoWorkInput, acquire_video_clip


@pytest.mark.asyncio
async def test_a_loaded_clip_is_handed_over_with_its_variant_and_origin():
    async def load(dest_path: str):
        with open(dest_path, "wb") as handle:
            handle.write(b"clip")
        return True, None, "recording", 1700.5

    acquired = await acquire_video_clip(load)

    try:
        assert isinstance(acquired, VideoWorkInput)
        assert acquired.clip_variant == "recording"
        assert acquired.clip_start_timestamp == 1700.5
        assert acquired.clip_path.endswith(".mp4")
        with open(acquired.clip_path, "rb") as handle:
            assert handle.read() == b"clip"
    finally:
        os.remove(acquired.clip_path)


@pytest.mark.asyncio
async def test_an_unavailable_clip_reports_the_loader_reason_and_removes_the_reservation():
    reserved: list[str] = []

    async def load(dest_path: str):
        reserved.append(dest_path)
        return False, "clip_not_ready", "event", None

    acquired = await acquire_video_clip(load)

    assert acquired == ClipUnavailable(error="clip_not_ready")
    assert not os.path.exists(reserved[0])


@pytest.mark.asyncio
async def test_a_failing_loader_propagates_and_removes_the_reservation():
    reserved: list[str] = []

    async def load(dest_path: str):
        reserved.append(dest_path)
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        await acquire_video_clip(load)

    assert not os.path.exists(reserved[0])


@pytest.mark.asyncio
async def test_cancelling_the_load_propagates_and_removes_the_reservation():
    reserved: list[str] = []
    loading = asyncio.Event()

    async def load(dest_path: str):
        reserved.append(dest_path)
        loading.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(acquire_video_clip(load))
    await loading.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert not os.path.exists(reserved[0])
