"""Read a clip's video sample format out of the MP4 container.

Safari's `<video>` element rejects HEVC tagged `hev1` while QuickTime plays it,
so "the download opens fine" does not clear the packaging. The four-character
sample format in `stsd` is what decides it, and it sits in the `moov` index, so
a short prefix of the file is enough to read it.

Deliberately a pure function over bytes: no subprocess, no ffprobe dependency in
the runtime image, and every branch reachable from a unit test. All parsing is
bounded, because the input is a byte range fetched from an external service.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import Iterator, Optional

import aiofiles
import httpx
import structlog

from app.config import settings
from app.services.frigate_client import frigate_client
from app.services.media_cache import media_cache

log = structlog.get_logger()

# The id comes back from Frigate and is then interpolated into a URL, so it is
# validated on the same terms the media proxy uses rather than trusted.
_EVENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


def _is_safe_event_id(event_id: str) -> bool:
    return bool(_EVENT_ID_PATTERN.match(event_id)) and len(event_id) <= 64


_HEADER_SIZE = 8
# Containers nest shallowly (moov > trak > mdia > minf > stbl > stsd). A cap
# stops a malformed file from driving unbounded recursion.
_MAX_DEPTH = 8
# A prefix large enough to hold a clip index; anything past this is payload.
_MAX_BOXES_PER_LEVEL = 256

_CONTAINER_BOXES = frozenset({b"moov", b"trak", b"mdia", b"minf", b"stbl"})

# Safari plays HEVC only when the sample entry is tagged `hvc1`. `hev1` carries
# parameter sets in-band, which its media stack refuses.
_SAMPLE_FORMATS: dict[str, tuple[str, bool]] = {
    "hvc1": ("hevc", True),
    "hev1": ("hevc", False),
    "avc1": ("h264", True),
    "avc3": ("h264", True),
    "mp4v": ("mpeg4", True),
}


@dataclass(frozen=True)
class VideoSampleFormat:
    """What the container says about its video track."""

    codec_tag: Optional[str] = None
    codec: Optional[str] = None
    # None means "not established", never "fine". An unrecognised tag is not a
    # licence to claim compatibility.
    safari_compatible: Optional[bool] = None
    note: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "codec_tag": self.codec_tag,
            "codec": self.codec,
            "safari_compatible": self.safari_compatible,
            "note": self.note,
        }


def _iter_boxes(data: bytes, start: int, end: int) -> Iterator[tuple[bytes, int, int]]:
    """Yield (kind, payload_start, payload_end) for each box in a range."""
    offset = start
    seen = 0
    while offset + _HEADER_SIZE <= end and seen < _MAX_BOXES_PER_LEVEL:
        seen += 1
        (declared,) = struct.unpack_from(">I", data, offset)
        kind = data[offset + 4 : offset + 8]
        header = _HEADER_SIZE

        if declared == 1:
            # 64-bit size follows the header.
            if offset + 16 > end:
                return
            (declared,) = struct.unpack_from(">Q", data, offset + 8)
            header = 16
        elif declared == 0:
            # Runs to the end of the file.
            declared = end - offset

        if declared < header:
            # Nonsense size. Advancing by the header keeps the scan moving
            # rather than looping forever on the same offset.
            offset += _HEADER_SIZE
            continue

        payload_start = offset + header
        payload_end = min(offset + declared, end)
        if payload_start > end:
            return
        yield kind, payload_start, payload_end
        offset += declared


def _find_video_sample_format(data: bytes, start: int, end: int, depth: int = 0) -> Optional[str]:
    """Walk containers to the video track's first sample entry."""
    if depth > _MAX_DEPTH:
        return None

    for kind, payload_start, payload_end in _iter_boxes(data, start, end):
        if kind == b"trak":
            if not _track_is_video(data, payload_start, payload_end):
                continue
            found = _find_video_sample_format(data, payload_start, payload_end, depth + 1)
            if found:
                return found
        elif kind == b"stsd":
            return _first_sample_format(data, payload_start, payload_end)
        elif kind in _CONTAINER_BOXES:
            found = _find_video_sample_format(data, payload_start, payload_end, depth + 1)
            if found:
                return found
    return None


def _track_is_video(data: bytes, start: int, end: int, depth: int = 0) -> bool:
    """A track is video when its media handler says `vide`."""
    if depth > _MAX_DEPTH:
        return False
    for kind, payload_start, payload_end in _iter_boxes(data, start, end):
        if kind == b"hdlr":
            # version/flags (4) + pre_defined (4) + handler_type (4)
            handler_at = payload_start + 8
            if handler_at + 4 > payload_end:
                return False
            return data[handler_at : handler_at + 4] == b"vide"
        if kind in _CONTAINER_BOXES:
            if _track_is_video(data, payload_start, payload_end, depth + 1):
                return True
    return False


def _first_sample_format(data: bytes, start: int, end: int) -> Optional[str]:
    # version/flags (4) + entry_count (4), then entry size (4) + format (4).
    entry_at = start + 8
    if entry_at + 8 > end:
        return None
    tag = data[entry_at + 4 : entry_at + 8]
    if len(tag) != 4:
        return None
    try:
        decoded = tag.decode("ascii")
    except UnicodeDecodeError:
        return None
    return decoded if decoded.isprintable() else None


def probe_video_sample_format(data: bytes) -> VideoSampleFormat:
    """Read the video sample format from an MP4 prefix.

    Returns an empty result with a reason rather than raising: this runs while
    assembling a diagnostics bundle, where a readable "could not tell" is worth
    more than a failed export.
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < _HEADER_SIZE:
        return VideoSampleFormat(note="No media bytes to read.")

    payload = bytes(data)
    try:
        tag = _find_video_sample_format(payload, 0, len(payload))
    except (struct.error, IndexError, ValueError):
        return VideoSampleFormat(note="Media header could not be parsed.")

    if not tag:
        return VideoSampleFormat(
            note=(
                "No moov index in the fetched prefix, so the sample format is unknown. "
                "A clip written without faststart keeps its index at the end of the file."
            )
        )

    codec, safari_compatible = _SAMPLE_FORMATS.get(tag, (None, None))
    if codec is None:
        return VideoSampleFormat(codec_tag=tag, note=f"Unrecognised video sample format {tag!r}.")

    if codec == "hevc" and safari_compatible is False:
        note = (
            "HEVC tagged hev1. Safari refuses this in a video element even though QuickTime "
            "plays it. Frigate's apple_compatibility setting produces hvc1 instead, and only "
            "for recordings made after it is applied."
        )
    else:
        note = f"{codec} tagged {tag}."

    return VideoSampleFormat(codec_tag=tag, codec=codec, safari_compatible=safari_compatible, note=note)


# ── Collecting the sample ────────────────────────────────────────────────────
# The parser above is pure. Everything below is the bounded I/O that feeds it.

#: Enough of a clip to carry its index. A real 4K HEVC clip resolves in 32KB.
CLIP_PREFIX_BYTES = 64 * 1024
CLIP_PROBE_TIMEOUT_SECONDS = 8.0


def _unavailable(note: str) -> dict[str, object]:
    return {
        "available": False,
        "event_id": None,
        "source": None,
        "bytes_read": 0,
        **VideoSampleFormat(note=note).as_dict(),
    }


async def _read_cached_prefix(event_id: str, max_bytes: int) -> Optional[bytes]:
    try:
        path = media_cache.get_clip_path(event_id)
    except Exception:
        return None
    if not path:
        return None
    try:
        async with aiofiles.open(path, "rb") as handle:
            return await handle.read(max_bytes)
    except Exception:
        return None


async def _read_frigate_prefix(event_id: str, max_bytes: int, timeout: float) -> Optional[bytes]:
    base = (settings.frigate.frigate_url or "").rstrip("/")
    if not base:
        return None

    headers = dict(frigate_client._get_headers())
    headers["Range"] = f"bytes=0-{max_bytes - 1}"
    url = f"{base}/api/events/{event_id}/clip.mp4"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            if response.status_code not in (200, 206):
                return None
            return response.content[:max_bytes]
    except Exception:
        return None


async def _recent_event_with_clip(timeout: float) -> Optional[str]:
    try:
        response = await frigate_client.get("api/events", params={"limit": 1, "has_clip": 1}, timeout=timeout)
        response.raise_for_status()
        events = response.json()
    except Exception:
        return None
    if not isinstance(events, list) or not events:
        return None
    event_id = events[0].get("id") if isinstance(events[0], dict) else None
    if not isinstance(event_id, str) or not _is_safe_event_id(event_id):
        return None
    return event_id


async def collect_video_sample_diagnostic(
    *,
    max_bytes: int = CLIP_PREFIX_BYTES,
    timeout: float = CLIP_PROBE_TIMEOUT_SECONDS,
) -> dict[str, object]:
    """Describe how this instance's clips are packaged.

    Answers "why does Safari refuse my video" from the bundle rather than from a
    round trip asking the reporter to install ffprobe. Never raises and never
    blocks for long: a diagnostics export that fails because a probe failed is
    worse than an export that says it could not tell.
    """
    try:
        return await _collect_video_sample(max_bytes=max_bytes, timeout=timeout)
    except Exception as error:  # pragma: no cover - guarded by test_probe_never_escapes
        # Each helper already swallows its own failures. This is the backstop:
        # a bundle must never fail to assemble because a probe went wrong.
        log.warning("media_sample_probe_failed", error=str(error))
        return _unavailable("The media sample could not be read.")


async def _collect_video_sample(*, max_bytes: int, timeout: float) -> dict[str, object]:
    event_id = await _recent_event_with_clip(timeout)
    if not event_id:
        return _unavailable("No recent Frigate event with a clip was available to sample.")

    prefix = await _read_cached_prefix(event_id, max_bytes)
    source = "media_cache"
    if not prefix:
        prefix = await _read_frigate_prefix(event_id, max_bytes, timeout)
        source = "frigate"

    if not prefix:
        return {**_unavailable("The clip could not be read from the cache or from Frigate."), "event_id": event_id}

    result = probe_video_sample_format(prefix)
    log.debug(
        "media_sample_probed",
        event_id=event_id,
        source=source,
        codec_tag=result.codec_tag,
        safari_compatible=result.safari_compatible,
    )
    return {
        "available": result.codec_tag is not None,
        "event_id": event_id,
        "source": source,
        "bytes_read": len(prefix),
        **result.as_dict(),
    }
