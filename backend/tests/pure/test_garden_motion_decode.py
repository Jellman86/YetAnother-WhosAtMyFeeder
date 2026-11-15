"""Motion recordings decode on the Intel GPU only when a real decode proves it works."""

from pathlib import Path
import sys
import time

import pytest

from app.services import garden_motion_decode as decode


def test_sample_frames_are_the_nearest_frames_to_each_sample_time():
    # A 29.99 fps camera sampled at 10%, 50% and 90% of a 9.9 s span.
    assert decode.sample_frame_indices([0.99, 4.95, 8.91], fps=29.9945, count=300) == [30, 148, 267]


def test_sample_frames_never_point_past_the_last_frame():
    assert decode.sample_frame_indices([0.0, 9.99], fps=10, count=100) == [0, 99]


def test_frame_command_decodes_on_the_gpu_and_cannot_fall_back_to_software_inside_ffmpeg():
    command = decode.frame_command("/dev/dri/renderD128", Path("/tmp/x/clip.mp4"), [267, 30, 30, 149])
    assert command[0] == str(decode.FFMPEG)
    assert command[command.index("-init_hw_device") + 1] == "vaapi=va:/dev/dri/renderD128"
    assert command[command.index("-hwaccel") + 1] == "vaapi"
    assert command[command.index("-hwaccel_output_format") + 1] == "vaapi"
    chain = command[command.index("-vf") + 1]
    # Only hardware frames can be downloaded, so a silent software decode fails instead.
    assert chain.startswith("select=eq(n\\,30)+eq(n\\,149)+eq(n\\,267),hwdownload,format=nv12,")
    # OpenCV converts with the BT.601 matrix; the detector was qualified on that.
    assert "in_color_matrix=bt601" in chain and chain.endswith("format=bgr24")
    assert command[command.index("-frames:v") + 1] == "3"
    assert command[command.index("-i") + 1] == "/tmp/x/clip.mp4"
    assert command[-1] == "pipe:1" and "-nostdin" in command


@pytest.mark.parametrize("device", ["/dev/dri/card0", "/dev/dri/renderD128/../card0", "renderD128", "/tmp/renderD128"])
def test_only_render_nodes_are_accepted_as_decode_devices(device):
    with pytest.raises(ValueError):
        decode.frame_command(device, Path("clip.mp4"), [0])


def _python_ffmpeg(tmp_path: Path, body: str) -> Path:
    """A stand-in ffmpeg that writes raw frames to stdout the way the real pipe does."""
    ffmpeg = tmp_path / "ffmpeg-python"
    ffmpeg.write_text(f"#!{sys.executable}\nimport sys, time\nout = sys.stdout.buffer\n{body}\n")
    ffmpeg.chmod(0o755)
    return ffmpeg


FRAME = 4 * 2 * 3


def test_frames_arrive_in_recording_order_with_repeats_like_a_seeking_reader(tmp_path):
    ffmpeg = _python_ffmpeg(tmp_path, f"for shade in (1, 2, 3):\n    out.write(bytes([shade]) * {FRAME})")
    frames = decode.stream_frames(
        "/dev/dri/renderD128", Path("clip.mp4"), [30, 30, 149, 267], width=4, height=2, ffmpeg=ffmpeg
    )
    shades = [int(frame[0, 0, 0]) for frame in frames]
    assert shades == [1, 1, 2, 3]


def test_closing_early_stops_the_decode_instead_of_waiting_for_later_frames(tmp_path):
    # A person in the first sample ends the scan; the rest of the recording is never decoded.
    ffmpeg = _python_ffmpeg(tmp_path, f"out.write(bytes([1]) * {FRAME})\nout.flush()\ntime.sleep(30)")
    frames = decode.stream_frames("/dev/dri/renderD128", Path("clip.mp4"), [30, 149], width=4, height=2, ffmpeg=ffmpeg)
    started = time.monotonic()
    assert int(next(frames)[0, 0, 0]) == 1
    frames.close()
    assert time.monotonic() - started < 5


@pytest.mark.parametrize(
    "body",
    [f"out.write(bytes([1]) * {FRAME})", f"out.write(bytes([1]) * {FRAME + 5})\nsys.exit(1)", "sys.exit(1)"],
)
def test_a_short_or_failed_hardware_decode_is_reported_not_guessed(tmp_path, body):
    ffmpeg = _python_ffmpeg(tmp_path, body)
    frames = decode.stream_frames("/dev/dri/renderD128", Path("clip.mp4"), [30, 149], width=4, height=2, ffmpeg=ffmpeg)
    with pytest.raises(decode.HardwareDecodeFailed):
        list(frames)


def test_a_hung_hardware_decode_is_stopped_at_its_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(decode, "FRAME_TIMEOUT_SECONDS", 0.5)
    ffmpeg = _python_ffmpeg(tmp_path, "time.sleep(30)")
    started = time.monotonic()
    with pytest.raises(decode.HardwareDecodeFailed):
        list(decode.stream_frames("/dev/dri/renderD128", Path("clip.mp4"), [0], width=4, height=2, ffmpeg=ffmpeg))
    assert time.monotonic() - started < 5


def test_a_missing_decoder_binary_is_a_hardware_failure(tmp_path):
    frames = decode.stream_frames(
        "/dev/dri/renderD128", Path("clip.mp4"), [0], width=4, height=2, ffmpeg=tmp_path / "missing"
    )
    with pytest.raises(decode.HardwareDecodeFailed):
        next(frames)


def test_samples_out_of_recording_order_are_refused():
    with pytest.raises(ValueError, match="order"):
        next(decode.stream_frames("/dev/dri/renderD128", Path("clip.mp4"), [149, 30], width=4, height=2))


def _fake_ffmpeg(tmp_path: Path, script: str) -> Path:
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("#!/bin/sh\n" + script + "\n")
    ffmpeg.chmod(0o755)
    return ffmpeg


def _render_nodes(tmp_path: Path, *names: str) -> Path:
    dri = tmp_path / "dri"
    dri.mkdir()
    for name in names:
        (dri / name).touch()
    return dri


@pytest.mark.asyncio
async def test_an_image_without_the_decoder_reports_it_is_not_packaged(tmp_path):
    result = await decode.probe_motion_decoder(ffmpeg=tmp_path / "missing", dri=_render_nodes(tmp_path, "renderD128"))
    assert result.state == "not_packaged" and result.decoder == "software" and result.device is None


@pytest.mark.asyncio
async def test_a_container_without_a_render_node_reports_the_missing_device(tmp_path):
    ffmpeg = _fake_ffmpeg(tmp_path, "exit 0")
    result = await decode.probe_motion_decoder(ffmpeg=ffmpeg, dri=_render_nodes(tmp_path, "card0"))
    assert result.state == "no_render_node" and result.decoder == "software"


@pytest.mark.asyncio
async def test_the_first_render_node_that_decodes_the_probe_clip_is_chosen(tmp_path, monkeypatch):
    width, height = decode.PROBE_SIZE
    # The fake decoder fails on renderD128 and returns one whole probe frame on renderD129.
    ffmpeg = _fake_ffmpeg(
        tmp_path,
        f'case "$*" in *renderD129*) head -c {width * height * 3} /dev/zero; exit 0;; esac; exit 1',
    )
    dri = _render_nodes(tmp_path, "renderD128", "renderD129", "card1")
    monkeypatch.setattr(decode, "RENDER_NODE", __import__("re").compile(rf"{dri}/renderD[0-9]{{3}}"))
    result = await decode.probe_motion_decoder(ffmpeg=ffmpeg, dri=dri)
    assert result.state == "vaapi" and result.decoder == "vaapi"
    assert result.device == str(dri / "renderD129")


@pytest.mark.asyncio
@pytest.mark.parametrize("script", ["exit 1", "head -c 10 /dev/zero; exit 0", "sleep 5"])
async def test_a_render_node_that_cannot_decode_the_probe_clip_keeps_cpu_decode(tmp_path, monkeypatch, script):
    ffmpeg = _fake_ffmpeg(tmp_path, script)
    dri = _render_nodes(tmp_path, "renderD128")
    monkeypatch.setattr(decode, "RENDER_NODE", __import__("re").compile(rf"{dri}/renderD[0-9]{{3}}"))
    result = await decode.probe_motion_decoder(ffmpeg=ffmpeg, dri=dri, timeout=0.5)
    assert result.state == "probe_failed" and result.decoder == "software" and result.device is None


def test_every_decoder_state_explains_itself_in_plain_words():
    for state in decode.DECODER_MESSAGES:
        message = decode.MotionDecoder(state, "/dev/dri/renderD128" if state == "vaapi" else None).message
        assert message.endswith(".") and "  " not in message
    assert "Intel GPU" in decode.MotionDecoder("vaapi", "/dev/dri/renderD128").message
    assert "/dev/dri" in decode.MotionDecoder("no_render_node").message


def test_the_probe_clip_is_a_tiny_checked_in_h264_recording():
    assert decode.PROBE_CLIP.is_file()
    data = decode.PROBE_CLIP.read_bytes()
    assert len(data) < 16 * 1024 and b"ftyp" in data[:16] and b"avc1" in data
