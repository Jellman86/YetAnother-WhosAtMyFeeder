"""Acquire the clip a video classification job works on.

The stage reserves a temporary file and lets the loader fill it in place, so a clip
never passes through this process's heap (#341). It returns either a typed work input,
which the coordinator then owns and must remove, or the loader's reason the clip is
unavailable. A refused, failed or cancelled load never leaves the reserved file behind.
"""

import asyncio
import contextlib
import os
import tempfile
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal, Optional

ClipVariant = Literal["event", "recording"]
# Fills the destination path; returns (loaded, error, variant, clip start timestamp).
ClipLoader = Callable[[str], Awaitable[tuple[bool, Optional[str], ClipVariant, float | None]]]


@dataclass(frozen=True)
class VideoWorkInput:
    """A playable clip on disk, owned by whoever received it."""

    clip_path: str
    clip_variant: ClipVariant
    clip_start_timestamp: float | None


@dataclass(frozen=True)
class ClipUnavailable:
    """No clip could be loaded; ``error`` is the loader's reason, if it gave one."""

    error: Optional[str]


async def _discard(path: str) -> None:
    with contextlib.suppress(OSError):
        await asyncio.to_thread(os.remove, path)


async def acquire_video_clip(load_clip: ClipLoader) -> VideoWorkInput | ClipUnavailable:
    # Reserved without an await, so no cancellation can land between creating the
    # file and the cleanup below taking responsibility for it.
    fd, clip_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    try:
        loaded, error, variant, start_timestamp = await load_clip(clip_path)
    except BaseException:
        await _discard(clip_path)
        raise
    if not loaded:
        await _discard(clip_path)
        return ClipUnavailable(error=error)
    return VideoWorkInput(clip_path=clip_path, clip_variant=variant, clip_start_timestamp=start_timestamp)
