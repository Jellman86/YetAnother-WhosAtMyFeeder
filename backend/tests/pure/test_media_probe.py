"""Reading a clip's video sample format straight out of the MP4 container.

Safari refuses HEVC tagged `hev1` in a <video> element while QuickTime plays it
happily, so "it plays when I download it" does not clear the packaging. This
lets a diagnostics bundle answer the question instead of asking the reporter to
install ffprobe.
"""

import struct

import pytest

from app.services.media_probe import probe_video_sample_format


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + kind + payload


def stsd(sample_format: bytes) -> bytes:
    entry = struct.pack(">I", 8 + 78) + sample_format + b"\x00" * 78
    return box(b"stsd", b"\x00\x00\x00\x00" + struct.pack(">I", 1) + entry)


def video_track(sample_format: bytes) -> bytes:
    hdlr = box(b"hdlr", b"\x00" * 8 + b"vide" + b"\x00" * 12)
    stbl = box(b"stbl", stsd(sample_format))
    minf = box(b"minf", stbl)
    mdia = box(b"mdia", hdlr + minf)
    return box(b"trak", mdia)


def audio_track() -> bytes:
    hdlr = box(b"hdlr", b"\x00" * 8 + b"soun" + b"\x00" * 12)
    stbl = box(b"stbl", stsd(b"mp4a"))
    minf = box(b"minf", stbl)
    mdia = box(b"mdia", hdlr + minf)
    return box(b"trak", mdia)


def mp4(*traks: bytes, ftyp: bytes = b"isom") -> bytes:
    return box(b"ftyp", ftyp + b"\x00\x00\x02\x00" + ftyp) + box(b"moov", b"".join(traks))


@pytest.mark.parametrize(
    ("sample_format", "codec", "safari_compatible"),
    [
        (b"hvc1", "hevc", True),
        (b"hev1", "hevc", False),
        (b"avc1", "h264", True),
        (b"avc3", "h264", True),
    ],
)
def test_reads_the_video_sample_format(sample_format: bytes, codec: str, safari_compatible: bool):
    result = probe_video_sample_format(mp4(video_track(sample_format)))

    assert result.codec_tag == sample_format.decode()
    assert result.codec == codec
    assert result.safari_compatible is safari_compatible


def test_reads_the_video_track_not_the_audio_track():
    result = probe_video_sample_format(mp4(audio_track(), video_track(b"hev1")))

    assert result.codec_tag == "hev1"
    assert result.codec == "hevc"


def test_reports_an_unrecognised_format_without_guessing_at_compatibility():
    result = probe_video_sample_format(mp4(video_track(b"av01")))

    assert result.codec_tag == "av01"
    assert result.codec is None
    assert result.safari_compatible is None


def test_says_so_when_the_prefix_does_not_carry_the_index():
    """A clip written without faststart keeps `moov` at the end."""
    trailing = box(b"ftyp", b"isom" + b"\x00" * 8) + box(b"mdat", b"\x00" * 64)

    result = probe_video_sample_format(trailing)

    assert result.codec_tag is None
    assert result.safari_compatible is None
    assert "moov" in result.note


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x00\x00",
        b"\x00\x00\x00\x08free",
        b"\xff\xff\xff\xffmoov",
        struct.pack(">I", 8) + b"moov",
        struct.pack(">I", 0) + b"moov",
        struct.pack(">I", 999999) + b"moov" + b"\x00" * 4,
    ],
)
def test_never_raises_on_truncated_or_hostile_input(payload: bytes):
    result = probe_video_sample_format(payload)

    assert result.codec_tag is None
    assert result.safari_compatible is None


def test_survives_a_box_that_claims_to_contain_itself():
    # size 8 means an empty box; a parser that does not advance would spin here.
    nested = box(b"moov", box(b"trak", struct.pack(">I", 8) + b"mdia"))

    result = probe_video_sample_format(nested)

    assert result.codec_tag is None


def test_handles_a_64_bit_box_header():
    inner = video_track(b"hvc1")
    payload = struct.pack(">I", 1) + b"moov" + struct.pack(">Q", 16 + len(inner)) + inner
    result = probe_video_sample_format(box(b"ftyp", b"isom" + b"\x00" * 8) + payload)

    assert result.codec_tag == "hvc1"


# ── The bounded collector ────────────────────────────────────────────────────

import app.services.media_probe as media_probe  # noqa: E402


@pytest.fixture
def probe_env(monkeypatch):
    """Stub the three external reads so each failure path can be exercised."""

    state = {"event": "evt-1", "cached": None, "frigate": None}

    async def fake_event(_timeout):
        return state["event"]

    async def fake_cached(_event_id, _max_bytes):
        return state["cached"]

    async def fake_frigate(_event_id, _max_bytes, _timeout):
        return state["frigate"]

    monkeypatch.setattr(media_probe, "_recent_event_with_clip", fake_event)
    monkeypatch.setattr(media_probe, "_read_cached_prefix", fake_cached)
    monkeypatch.setattr(media_probe, "_read_frigate_prefix", fake_frigate)
    return state


@pytest.mark.asyncio
async def test_prefers_the_cached_clip_over_a_network_read(probe_env):
    probe_env["cached"] = mp4(video_track(b"hvc1"))
    probe_env["frigate"] = mp4(video_track(b"hev1"))

    result = await media_probe.collect_video_sample_diagnostic()

    assert result["source"] == "media_cache"
    assert result["codec_tag"] == "hvc1"
    assert result["available"] is True


@pytest.mark.asyncio
async def test_falls_back_to_frigate_when_nothing_is_cached(probe_env):
    probe_env["frigate"] = mp4(video_track(b"hev1"))

    result = await media_probe.collect_video_sample_diagnostic()

    assert result["source"] == "frigate"
    assert result["codec_tag"] == "hev1"
    assert result["safari_compatible"] is False
    assert "apple_compatibility" in result["note"]


@pytest.mark.asyncio
async def test_says_it_could_not_tell_rather_than_failing_the_export(probe_env):
    result = await media_probe.collect_video_sample_diagnostic()

    assert result["available"] is False
    assert result["event_id"] == "evt-1"
    assert result["safari_compatible"] is None


@pytest.mark.asyncio
async def test_reports_honestly_when_there_is_no_event_to_sample(probe_env):
    probe_env["event"] = None

    result = await media_probe.collect_video_sample_diagnostic()

    assert result["available"] is False
    assert result["event_id"] is None
    assert result["codec_tag"] is None


@pytest.mark.asyncio
async def test_probe_never_escapes_and_fails_the_bundle(monkeypatch):
    """A diagnostics export must survive a probe that goes wrong."""

    async def explode(*_args, **_kwargs):
        raise RuntimeError("frigate is on fire")

    monkeypatch.setattr(media_probe, "_collect_video_sample", explode)

    result = await media_probe.collect_video_sample_diagnostic()

    assert result["available"] is False
    assert result["codec_tag"] is None
    assert result["safari_compatible"] is None


@pytest.mark.parametrize(
    "hostile",
    ["../../etc/passwd", "evt/../..", "evt?x=1", "evt id", "e" * 65, "", "evt#frag"],
)
def test_rejects_an_event_id_that_would_not_be_safe_in_a_url(hostile):
    assert media_probe._is_safe_event_id(hostile) is False


@pytest.mark.parametrize("good", ["1786898087.273197-5p93eu", "manual_abc-123", "a.b_c-d"])
def test_accepts_the_ids_frigate_actually_produces(good):
    assert media_probe._is_safe_event_id(good) is True
