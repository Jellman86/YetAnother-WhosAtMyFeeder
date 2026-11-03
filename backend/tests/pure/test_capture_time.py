import io
import struct
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from PIL import Image

from app.services.capture_time import (
    EXIF_DATETIME,
    EXIF_DATETIME_ORIGINAL,
    EXIF_IFD_TAG,
    EXIF_OFFSET_TIME,
    EXIF_OFFSET_TIME_ORIGINAL,
    captured_at_from_exif,
    captured_at_from_image,
    captured_at_from_mp4,
    configured_timezone,
)

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc)
LONDON = ZoneInfo("Europe/London")
MP4_EPOCH_OFFSET = 2_082_844_800  # seconds from 1904-01-01 to 1970-01-01


def _captured(exif: dict | None = None, exif_ifd: dict | None = None, zone=LONDON):
    return captured_at_from_exif(exif or {}, exif_ifd or {}, local_zone=zone, now=NOW)


def test_no_exif_has_no_capture_time() -> None:
    assert _captured() is None


def test_original_time_with_its_offset_is_converted_to_utc() -> None:
    captured = _captured(exif_ifd={EXIF_DATETIME_ORIGINAL: "2026:05:01 08:15:30", EXIF_OFFSET_TIME_ORIGINAL: "+02:00"})

    assert captured == datetime(2026, 5, 1, 6, 15, 30)


def test_original_time_falls_back_to_the_general_offset() -> None:
    captured = _captured(exif_ifd={EXIF_DATETIME_ORIGINAL: "2026:01:10 09:00:00", EXIF_OFFSET_TIME: "-05:00"})

    assert captured == datetime(2026, 1, 10, 14, 0, 0)


def test_time_without_offset_is_local_time_in_the_configured_zone() -> None:
    # 1 May is British Summer Time, so 08:15 in London is 07:15 UTC.
    assert _captured(exif_ifd={EXIF_DATETIME_ORIGINAL: "2026:05:01 08:15:00"}) == datetime(2026, 5, 1, 7, 15)
    # January is GMT.
    assert _captured(exif_ifd={EXIF_DATETIME_ORIGINAL: "2026:01:01 08:15:00"}) == datetime(2026, 1, 1, 8, 15)


def test_general_datetime_is_used_when_the_original_is_missing() -> None:
    captured = _captured(exif={EXIF_DATETIME: "2025:12:24 16:45:00"}, exif_ifd={EXIF_OFFSET_TIME: "+00:00"})

    assert captured == datetime(2025, 12, 24, 16, 45)


def test_a_garbage_original_falls_back_to_a_valid_general_datetime() -> None:
    captured = _captured(
        exif={EXIF_DATETIME: "2025:12:24 16:45:00"}, exif_ifd={EXIF_DATETIME_ORIGINAL: "not a date at all"}
    )

    assert captured == datetime(2025, 12, 24, 16, 45)


@pytest.mark.parametrize(
    "value",
    [
        "garbage",
        "0000:00:00 00:00:00",
        "    :  :     :  :  ",
        "2026:13:01 08:00:00",
        "2026:02:30 08:00:00",
        "2026:05:01 25:00:00",
        b"\xff\xfe\x00binary",
        12345,
        "2026:05:01 08:00:00" + "9" * 500,
    ],
)
def test_malformed_values_are_ignored(value: object) -> None:
    assert _captured(exif_ifd={EXIF_DATETIME_ORIGINAL: value}) is None


def test_a_malformed_offset_is_ignored_rather_than_guessed() -> None:
    assert (
        _captured(exif_ifd={EXIF_DATETIME_ORIGINAL: "2026:05:01 08:00:00", EXIF_OFFSET_TIME_ORIGINAL: "+25:00"}) is None
    )


def test_future_times_beyond_a_small_skew_are_rejected() -> None:
    assert (
        _captured(exif_ifd={EXIF_DATETIME_ORIGINAL: "2027:01:01 00:00:00", EXIF_OFFSET_TIME_ORIGINAL: "+00:00"}) is None
    )
    # A camera clock a few minutes fast is tolerated.
    assert _captured(
        exif_ifd={EXIF_DATETIME_ORIGINAL: "2026:10:31 12:03:00", EXIF_OFFSET_TIME_ORIGINAL: "+00:00"}
    ) == datetime(2026, 10, 31, 12, 3)


def test_times_before_1990_are_rejected() -> None:
    assert (
        _captured(exif_ifd={EXIF_DATETIME_ORIGINAL: "1989:12:31 23:59:59", EXIF_OFFSET_TIME_ORIGINAL: "+00:00"}) is None
    )


def test_byte_values_with_a_trailing_nul_are_read() -> None:
    captured = _captured(
        exif_ifd={EXIF_DATETIME_ORIGINAL: b"2026:05:01 08:15:00\x00", EXIF_OFFSET_TIME_ORIGINAL: b"+01:00"}
    )

    assert captured == datetime(2026, 5, 1, 7, 15)


def test_capture_time_is_read_from_a_real_jpeg() -> None:
    exif = Image.Exif()
    exif[EXIF_DATETIME] = "2026:05:02 10:00:00"
    sub = exif.get_ifd(EXIF_IFD_TAG)
    sub[EXIF_DATETIME_ORIGINAL] = "2026:05:01 08:15:30"
    sub[EXIF_OFFSET_TIME_ORIGINAL] = "+02:00"
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (40, 90, 60)).save(buffer, format="JPEG", exif=exif.tobytes())
    buffer.seek(0)

    with Image.open(buffer) as image:
        assert captured_at_from_image(image, local_zone=LONDON, now=NOW) == datetime(2026, 5, 1, 6, 15, 30)


def test_a_jpeg_without_exif_has_no_capture_time() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16)).save(buffer, format="JPEG")
    buffer.seek(0)

    with Image.open(buffer) as image:
        assert captured_at_from_image(image, local_zone=LONDON, now=NOW) is None


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def _mvhd(creation_unix: int, *, version: int = 0) -> bytes:
    created = creation_unix + MP4_EPOCH_OFFSET
    if version == 1:
        body = struct.pack(">B3xQQIQ", 1, created, created, 1000, 0)
    else:
        body = struct.pack(">B3xIIII", 0, created, created, 1000, 0)
    return _box(b"mvhd", body + b"\x00" * 80)


def _mp4(*boxes: bytes) -> io.BytesIO:
    return io.BytesIO(_box(b"ftyp", b"isom\x00\x00\x02\x00isomiso2") + b"".join(boxes))


def test_video_creation_time_is_read_from_the_movie_header() -> None:
    created = int(datetime(2026, 6, 3, 5, 30, tzinfo=timezone.utc).timestamp())
    video = _mp4(_box(b"free", b"\x00" * 32), _box(b"moov", _box(b"udta", b"") + _mvhd(created)))

    assert captured_at_from_mp4(video, now=NOW) == datetime(2026, 6, 3, 5, 30)


def test_video_creation_time_reads_a_version_one_header() -> None:
    created = int(datetime(2026, 6, 3, 5, 30, tzinfo=timezone.utc).timestamp())

    assert captured_at_from_mp4(_mp4(_box(b"moov", _mvhd(created, version=1))), now=NOW) == datetime(2026, 6, 3, 5, 30)


def test_an_unset_video_creation_time_is_ignored() -> None:
    # Many encoders write zero, which is 1904.
    video = _mp4(_box(b"moov", _mvhd(-MP4_EPOCH_OFFSET)))

    assert captured_at_from_mp4(video, now=NOW) is None


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x00\x00",
        struct.pack(">I4s", 4, b"moov"),
        struct.pack(">I4s", 0xFFFFFFFF, b"moov") + b"\x00" * 8,
        struct.pack(">I4s", 1, b"moov") + struct.pack(">Q", 2**63),
        _box(b"moov", struct.pack(">I4s", 12, b"mvhd") + b"\x00\x00\x00\x00"),
        b"\x00" * 64,
    ],
)
def test_truncated_or_hostile_video_headers_are_ignored(payload: bytes) -> None:
    assert captured_at_from_mp4(io.BytesIO(payload), now=NOW) is None


def test_a_future_video_creation_time_is_rejected() -> None:
    created = int(datetime(2030, 1, 1, tzinfo=timezone.utc).timestamp())

    assert captured_at_from_mp4(_mp4(_box(b"moov", _mvhd(created))), now=NOW) is None


def test_configured_timezone_reads_tz_and_falls_back_to_utc() -> None:
    assert configured_timezone({"TZ": "Europe/London"}) == ZoneInfo("Europe/London")
    assert configured_timezone({"TZ": "Not/AZone"}) == timezone.utc
    assert configured_timezone({"TZ": "../../etc/passwd"}) == timezone.utc
    assert configured_timezone({}) == timezone.utc
