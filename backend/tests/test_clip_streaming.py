"""Clips reach the video pipeline as files, never as heap-resident bytes (#341).

The API process was observed at ~3.2GB anon with a wall of glibc arena-sized
regions: whole clips passed through its heap on the way to a temp file the
worker reads anyway. Downloads now stream to disk, cached clips are copied
disk-to-disk, and validation runs against the file.
"""

import inspect
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import httpx
import pytest

from app.services.frigate_client import FrigateClient


def _streaming_client(status_code: int, chunks: list[bytes] | None = None, body: bytes = b""):
    class _Resp:
        def __init__(self):
            self.status_code = status_code

        async def aiter_bytes(self, _size):
            for chunk in chunks or []:
                yield chunk

        async def aread(self):
            return body

    client = MagicMock()

    @asynccontextmanager
    async def _stream(method, url, headers=None, timeout=None):
        yield _Resp()

    client.stream = _stream
    return client


@pytest.mark.asyncio
async def test_download_streams_the_clip_to_the_file(tmp_path, monkeypatch):
    fc = FrigateClient()
    monkeypatch.setattr(fc, "_get_client", lambda: _streaming_client(200, chunks=[b"abc", b"def"]))
    dest = tmp_path / "clip.mp4"
    ok, error = await fc.download_clip_to_file("evt-1", str(dest))
    assert ok is True and error is None
    assert dest.read_bytes() == b"abcdef"


@pytest.mark.asyncio
async def test_download_maps_missing_and_not_retained_like_the_bytes_fetch(tmp_path, monkeypatch):
    fc = FrigateClient()
    monkeypatch.setattr(fc, "_get_client", lambda: _streaming_client(404))
    ok, error = await fc.download_clip_to_file("evt-404", str(tmp_path / "a.mp4"))
    assert (ok, error) == (False, "clip_not_found")

    monkeypatch.setattr(
        fc,
        "_get_client",
        lambda: _streaming_client(400, body=b'{"message": "No recordings found for the specified time range"}'),
    )
    ok, error = await fc.download_clip_to_file("evt-400", str(tmp_path / "b.mp4"))
    assert (ok, error) == (False, "clip_not_retained")


@pytest.mark.asyncio
async def test_download_reports_timeouts_without_raising(tmp_path, monkeypatch):
    fc = FrigateClient()

    class _TimeoutClient:
        def stream(self, *args, **kwargs):
            raise httpx.TimeoutException("slow")

    monkeypatch.setattr(fc, "_get_client", lambda: _TimeoutClient())
    ok, error = await fc.download_clip_to_file("evt-slow", str(tmp_path / "c.mp4"))
    assert (ok, error) == (False, "clip_timeout")


def test_no_whole_clip_bytes_transit_the_video_job():
    """The job path holds a temp-file path, never the clip's bytes."""
    from app.services import auto_video_classifier_service as avs

    loader_source = inspect.getsource(avs.AutoVideoClassifierService._load_preferred_clip)
    assert "read_bytes" not in loader_source
    assert "copyfile" in loader_source

    wait_source = inspect.getsource(avs.AutoVideoClassifierService._wait_for_clip)
    assert "download_clip_to_file" in wait_source
    assert "get_clip_with_error" not in wait_source

    process_source = inspect.getsource(avs.AutoVideoClassifierService._process_event)
    assert "replace_from_clip_path" in process_source
    assert "write_bytes, clip_bytes" not in process_source
