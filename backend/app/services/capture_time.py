"""When an uploaded photo or video was taken, read from its own metadata.

Every value here comes from a file someone uploaded, so it is untrusted: each reader is bounded,
accepts only the exact shape the format defines, and answers ``None`` rather than guessing. A
missing capture time is recoverable (the person can type one); a wrong one silently rewrites
when a sighting happened.

Timezone rule:

- EXIF ``DateTimeOriginal`` (or ``DateTime``) carries a wall-clock time. With an
  ``OffsetTimeOriginal``/``OffsetTime`` offset it is exact. Without one it is read as local time in
  the configured timezone, the container's ``TZ`` (UTC when unset or unknown).
- MP4/MOV ``mvhd`` creation time is defined by the format as UTC, so no zone is applied.

Times before 1990, or more than a few minutes in the future, are rejected as unset or wrong clocks.
"""

from __future__ import annotations

import os
import re
import struct
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone, tzinfo
from typing import BinaryIO
from zoneinfo import ZoneInfo

from PIL import Image

EXIF_IFD_TAG = 0x8769
EXIF_DATETIME = 0x0132
EXIF_DATETIME_ORIGINAL = 0x9003
EXIF_OFFSET_TIME = 0x9010
EXIF_OFFSET_TIME_ORIGINAL = 0x9011

EARLIEST_CAPTURE = datetime(1990, 1, 1, tzinfo=timezone.utc)
FUTURE_SKEW = timedelta(minutes=10)

_MAX_TEXT = 40
_EXIF_DATETIME = re.compile(r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})")
_EXIF_OFFSET = re.compile(r"([+-])(\d{2}):(\d{2})")

_MP4_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)
_MAX_TOP_LEVEL_BOXES = 64
_MAX_MOOV_CHILDREN = 256
_MAX_MVHD_BYTES = 4096


def configured_timezone(environ: Mapping[str, str] | None = None) -> tzinfo:
    """The zone a capture time without an offset is read in: ``TZ``, or UTC when unset or unknown."""
    name = (os.environ if environ is None else environ).get("TZ", "").strip().lstrip(":")
    if not name:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ValueError, OSError, KeyError):
        return timezone.utc


def _text(value: object) -> str | None:
    if isinstance(value, bytes):
        value = value.decode("ascii", errors="replace")
    if not isinstance(value, str) or len(value) > _MAX_TEXT:
        return None
    return value.strip().rstrip("\x00").strip()


def _offset(value: object) -> timezone | None:
    text = _text(value)
    match = _EXIF_OFFSET.fullmatch(text or "")
    if not match:
        return None
    sign, hours, minutes = match.groups()
    if int(hours) > 14 or int(minutes) > 59:
        return None
    delta = timedelta(hours=int(hours), minutes=int(minutes))
    return timezone(-delta if sign == "-" else delta)


def _plausible(moment: datetime, now: datetime) -> datetime | None:
    if moment < EARLIEST_CAPTURE or moment > now + FUTURE_SKEW:
        return None
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _exif_moment(value: object, offset: object, *, local_zone: tzinfo, now: datetime) -> datetime | None:
    match = _EXIF_DATETIME.fullmatch(_text(value) or "")
    if not match:
        return None
    try:
        wall = datetime(*(int(part) for part in match.groups()))
    except ValueError:
        return None
    if offset is not None:
        zone = _offset(offset)
        if zone is None:
            # An offset is present but unreadable: reading the time in another zone would be a guess.
            return None
        return _plausible(wall.replace(tzinfo=zone), now)
    return _plausible(wall.replace(tzinfo=local_zone), now)


def captured_at_from_exif(
    exif: Mapping[int, object], exif_ifd: Mapping[int, object], *, local_zone: tzinfo, now: datetime
) -> datetime | None:
    """The capture time in naive UTC, from ``DateTimeOriginal`` and then ``DateTime``; ``None`` if neither is valid."""
    original_offset = exif_ifd.get(EXIF_OFFSET_TIME_ORIGINAL, exif_ifd.get(EXIF_OFFSET_TIME))
    candidates = (
        (exif_ifd.get(EXIF_DATETIME_ORIGINAL), original_offset),
        (exif.get(EXIF_DATETIME), exif_ifd.get(EXIF_OFFSET_TIME)),
    )
    for value, offset in candidates:
        if value is None:
            continue
        moment = _exif_moment(value, offset, local_zone=local_zone, now=now)
        if moment is not None:
            return moment
    return None


def captured_at_from_image(image: Image.Image, *, local_zone: tzinfo, now: datetime) -> datetime | None:
    """The capture time of an opened Pillow image, or ``None`` when its EXIF holds none or is unreadable."""
    try:
        exif = image.getexif()
        exif_ifd = exif.get_ifd(EXIF_IFD_TAG)
    except (AttributeError, KeyError, TypeError, ValueError, OSError, struct.error):
        return None
    return captured_at_from_exif(exif, exif_ifd, local_zone=local_zone, now=now)


def _box_header(stream: BinaryIO, end: int) -> tuple[bytes, int, int] | None:
    """The next box's type, payload start and end, within ``end``; ``None`` at a malformed or final box."""
    start = stream.tell()
    header = stream.read(8)
    if len(header) < 8:
        return None
    size, kind = struct.unpack(">I4s", header)
    payload = start + 8
    if size == 1:
        large = stream.read(8)
        if len(large) < 8:
            return None
        size = struct.unpack(">Q", large)[0]
        payload = start + 16
    elif size == 0:
        size = end - start
    box_end = start + size
    if size < payload - start or box_end > end:
        return None
    return kind, payload, box_end


def captured_at_from_mp4(stream: BinaryIO, *, now: datetime) -> datetime | None:
    """The movie header's creation time in naive UTC, reading box headers only; ``None`` when absent or implausible."""
    try:
        stream.seek(0, os.SEEK_END)
        file_end = stream.tell()
        stream.seek(0)
        for _ in range(_MAX_TOP_LEVEL_BOXES):
            box = _box_header(stream, file_end)
            if box is None:
                return None
            kind, payload, box_end = box
            if kind == b"moov":
                return _creation_time_in_moov(stream, payload, box_end, now)
            stream.seek(box_end)
    except (OSError, ValueError, OverflowError, struct.error):
        return None
    return None


def _creation_time_in_moov(stream: BinaryIO, start: int, end: int, now: datetime) -> datetime | None:
    stream.seek(start)
    for _ in range(_MAX_MOOV_CHILDREN):
        box = _box_header(stream, end)
        if box is None:
            return None
        kind, payload, box_end = box
        if kind == b"mvhd":
            body = stream.read(min(box_end - payload, _MAX_MVHD_BYTES))
            if len(body) >= 12 and body[0] == 0:
                seconds = struct.unpack(">I", body[4:8])[0]
            elif len(body) >= 20 and body[0] == 1:
                seconds = struct.unpack(">Q", body[4:12])[0]
            else:
                return None
            if seconds == 0 or seconds > 2**40:
                return None
            return _plausible(_MP4_EPOCH + timedelta(seconds=seconds), now)
        stream.seek(box_end)
    return None
