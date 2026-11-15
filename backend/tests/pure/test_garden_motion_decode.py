"""Motion recordings decode on the Intel GPU only when a real decode proves it works."""

from pathlib import Path
import sys
import time

import pytest

from app.services import garden_motion_decode as decode


def test_sample_frames_are_the_nearest_frames_to_each_sample_time():
    # A 29.99 fps camera sampled at 10%, 50% and 90% of a 9.9 s span.
    assert decode.sample_frame_indices([0.99, 4.95, 8.91], fps=29.9945, count=300) == [30, 148, 267]


def test_half_frame_sample_times_round_up_exactly_as_opencv_seeks():
    # OpenCV seeks to (int64)(msec * fps * 0.001 + 0.5); Python's round() would pick 148.
    assert decode.sample_frame_indices([4.95], fps=30.0, count=300) == [149]
    assert decode.sample_frame_indices([0.05, 0.15, 0.25], fps=10.0, count=100) == [1, 2, 3]


def test_sample_frame_numbers_are_capped_at_the_frame_count_like_opencv():
    assert decode.sample_frame_indices([0.0, 9.99], fps=10, count=100) == [0, 100]


def _framecrc(packets: list[tuple[int, int, str]], time_base: str = "1/90000") -> str:
    lines = [f"#tb 0: {time_base}", "#media_type 0: video", "#codec_id 0: h264"]
    for dts, pts, extra in packets:
        lines.append(f"0, {dts:>10}, {pts:>10}, 3000, 1000, 0x12345678{extra}")
    return "\n".join(lines) + "\n"


def _cfr(count: int, *, keyframe_every: int, step: int = 3000) -> decode.VideoTimeline:
    rows = [(i * step, i * step, "" if i % keyframe_every == 0 else ", F=0x0") for i in range(count)]
    return decode.parse_timeline(_framecrc(rows))


def test_the_packet_listing_reads_time_base_timestamps_and_keyframes():
    text = _framecrc([(0, 0, ""), (3000, 3000, ", F=0x0"), (6000, 6000, ", S=1, 8, 0xabc"), (9000, 9000, ", F=0x5")])
    timeline = decode.parse_timeline(text)
    assert timeline.time_base == 1 / 90000
    assert [(p.dts, p.pts, p.key) for p in timeline.packets] == [
        (0, 0, True),
        (3000, 3000, False),
        (6000, 6000, True),
        (9000, 9000, True),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "",
        "#tb 0: 1/0\n0, 0, 0, 1, 1, 0x0\n",
        "#tb 0: 1/90000\n",
        "#tb 0: 1/90000\n0, x, 0, 1, 1, 0x0\n",
        "#tb 0: 1/90000\n1, 0, 0, 1, 1, 0x0\n",
        "#tb 0: 1/90000\n0, 0, 0, 1, 1, 0x0, F=0xZZ\n",
    ],
)
def test_an_unreadable_packet_listing_is_a_property_of_the_file_not_a_gpu_failure(text):
    with pytest.raises(decode.HardwareDecodeUnsupported):
        decode.parse_timeline(text)


def test_a_packet_without_a_timestamp_is_refused_explicitly():
    missing = -9223372036854775808
    with pytest.raises(decode.HardwareDecodeUnsupported, match="timestamp"):
        decode.parse_timeline(_framecrc([(0, 0, ""), (missing, missing, ", F=0x0")]))


def test_packets_flagged_discard_are_read_from_the_listing():
    timeline = decode.parse_timeline(_framecrc([(0, 0, ", F=0x5"), (3000, 3000, ", F=0x4"), (6000, 6000, ", F=0x0")]))
    assert [(p.key, p.discard) for p in timeline.packets] == [(True, True), (False, True), (False, False)]


def test_a_recording_with_discarded_packets_is_left_to_the_cpu():
    # OpenCV's decoder never returns discarded packets, so counting them would run ahead of it.
    rows = [(0, 0, ", F=0x5"), (3000, 3000, ", F=0x4"), (6000, 6000, "")] + [
        (i * 3000, i * 3000, ", F=0x0") for i in range(3, 100)
    ]
    with pytest.raises(decode.HardwareDecodeUnsupported, match="discard"):
        decode.opencv_seek_frames(decode.parse_timeline(_framecrc(rows)), [30], fps=30.0)


def test_an_unbounded_packet_listing_is_refused():
    with pytest.raises(decode.HardwareDecodeUnsupported):
        decode.parse_timeline(_framecrc([(i, i, "") for i in range(decode.TIMELINE_PACKET_LIMIT + 1)]))


def test_on_a_constant_rate_recording_opencv_returns_the_frame_it_reports():
    timeline = _cfr(300, keyframe_every=150)
    assert decode.opencv_seek_frames(timeline, [0, 1, 30, 149, 267], fps=30.0) == [0, 1, 30, 149, 267]


def test_on_jittered_timestamps_opencv_returns_the_frame_before_the_one_it_reports():
    # The keyframe at position 120 arrived 22 ms late, so its timestamp numbers it 121.
    rows = [(i * 3000, i * 3000, "" if i % 60 == 0 else ", F=0x0") for i in range(300)]
    rows[120] = (120 * 3000 + 2000, 120 * 3000 + 2000, "")
    timeline = decode.parse_timeline(_framecrc(rows))
    assert int(30.0 * ((120 * 3000 + 2000) / 90000) + 0.5) == 121
    # Seeks anchored on that keyframe report frame 148 but return position 147; seeks
    # anchored on the punctual keyframe at 240 are unaffected.
    assert decode.opencv_seek_frames(timeline, [30, 148, 267], fps=30.0) == [30, 147, 267]


def test_a_recording_that_reorders_frames_keeps_decoding_in_software():
    rows = [(0, 0, ""), (3000, 9000, ", F=0x0"), (6000, 3000, ", F=0x0"), (9000, 6000, ", F=0x0")]
    with pytest.raises(decode.HardwareDecodeUnsupported, match="reorders"):
        decode.opencv_seek_frames(decode.parse_timeline(_framecrc(rows)), [2], fps=30.0)


def test_a_recording_that_does_not_start_on_a_keyframe_keeps_decoding_in_software():
    rows = [(0, 0, ", F=0x0"), (3000, 3000, "")]
    with pytest.raises(decode.HardwareDecodeUnsupported, match="keyframe"):
        decode.opencv_seek_frames(decode.parse_timeline(_framecrc(rows)), [1], fps=30.0)


def test_a_sample_past_the_last_frame_is_left_to_software_which_reports_it_unreadable():
    with pytest.raises(decode.HardwareDecodeFailed, match="last frame"):
        decode.opencv_seek_frames(_cfr(100, keyframe_every=50), [100], fps=10.0)


def test_the_packet_listing_command_reads_timestamps_without_decoding():
    command = decode.packet_command(Path("/tmp/x/clip.mp4"))
    assert command[command.index("-c") + 1] == "copy" and command[command.index("-f") + 1] == "framecrc"
    assert "-copyts" in command and command[command.index("-map") + 1] == "0:v:0"
    assert "-hwaccel" not in command and command[-1] == "pipe:1"


def test_frame_command_decodes_on_the_gpu_and_cannot_fall_back_to_software_inside_ffmpeg():
    command = decode.frame_command("/dev/dri/renderD128", Path("/tmp/x/clip.mp4"), [267, 30, 30, 149])
    assert command[0] == str(decode.FFMPEG)
    assert command[command.index("-init_hw_device") + 1] == "vaapi=va:/dev/dri/renderD128"
    assert command[command.index("-hwaccel") + 1] == "vaapi"
    assert command[command.index("-hwaccel_output_format") + 1] == "vaapi"
    chain = command[command.index("-vf") + 1]
    # Only hardware frames can be downloaded, so a silent software decode fails instead.
    assert chain.startswith("select=eq(n\\,30)+eq(n\\,149)+eq(n\\,267),hwdownload,format=nv12,")
    # OpenCV converts planar YUV 4:2:0 with BT.601 and bicubic scaling; converting NV12
    # directly takes a different swscale path and changes pixels.
    assert chain.endswith(",format=nv12,format=yuv420p,scale=in_color_matrix=bt601:flags=bicubic,format=bgr24")
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


def _stalled_ffmpeg(tmp_path: Path) -> tuple[Path, Path]:
    """A decoder that records its PID and hangs before writing, like a stuck GPU."""
    pid_file = tmp_path / "decoder.pid"
    ffmpeg = _python_ffmpeg(
        tmp_path, f"open({str(pid_file)!r}, 'w').write(str(__import__('os').getpid()))\ntime.sleep(60)"
    )
    return ffmpeg, pid_file


def _decoder_pid(pid_file: Path) -> int:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if pid_file.exists() and pid_file.read_text():
            return int(pid_file.read_text())
        time.sleep(0.05)
    raise AssertionError("The stand-in decoder never started")


def _gone(pid: int, seconds: float = 5.0) -> bool:
    """True once the process no longer exists or is a zombie waiting for its new parent to reap it."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            return True
        if state == "Z":
            return True
        time.sleep(0.05)
    return False


@pytest.mark.skipif(sys.platform != "linux", reason="Decoder ownership is kernel-enforced on Linux")
@pytest.mark.parametrize("stop", ["SIGKILL", "SIGTERM"])
def test_a_stalled_decoder_dies_with_a_motion_worker_that_is_stopped(tmp_path, stop):
    import os
    import signal
    import subprocess

    ffmpeg, pid_file = _stalled_ffmpeg(tmp_path)
    # A stand-in motion worker blocked reading its first GPU frame, as bird pre-emption finds it.
    script = (
        "from pathlib import Path\n"
        "from app.services.garden_motion_decode import stream_frames\n"
        f"next(stream_frames('/dev/dri/renderD128', Path('clip.mp4'), [0], width=4, height=2, ffmpeg=Path({str(ffmpeg)!r})))\n"
    )
    backend = Path(decode.__file__).resolve().parents[2]
    worker = subprocess.Popen(
        [sys.executable, "-c", script], cwd=backend, env={**os.environ, "PYTHONPATH": str(backend)}
    )
    try:
        pid = _decoder_pid(pid_file)
        worker.send_signal(getattr(signal, stop))
        worker.wait(timeout=10)
        assert _gone(pid), "The decoder outlived the worker that started it"
    finally:
        if worker.poll() is None:
            worker.kill()
            worker.wait()


@pytest.mark.skipif(sys.platform != "linux", reason="Decoder ownership is kernel-enforced on Linux")
def test_closing_a_stalled_decode_kills_and_reaps_the_decoder(tmp_path):
    import threading

    ffmpeg, pid_file = _stalled_ffmpeg(tmp_path)
    frames = decode.stream_frames("/dev/dri/renderD128", Path("clip.mp4"), [0], width=4, height=2, ffmpeg=ffmpeg)
    failures = []
    reader = threading.Thread(target=lambda: failures.extend(_drain(frames)))
    reader.start()
    pid = _decoder_pid(pid_file)
    # Retiring the decode from outside, as the worker deadline does, ends the blocked read.
    import os
    import signal

    os.kill(pid, signal.SIGKILL)
    reader.join(10)
    assert not reader.is_alive() and failures == ["HardwareDecodeFailed"]
    assert _gone(pid)


def _drain(frames) -> list[str]:
    try:
        list(frames)
    except decode.HardwareDecodeFailed:
        return ["HardwareDecodeFailed"]
    return []


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "linux", reason="Decoder ownership is kernel-enforced on Linux")
async def test_cancelling_the_startup_probe_kills_and_reaps_its_decoder(tmp_path, monkeypatch):
    import asyncio

    ffmpeg, pid_file = _stalled_ffmpeg(tmp_path)
    dri = _render_nodes(tmp_path, "renderD128")
    monkeypatch.setattr(decode, "RENDER_NODE", __import__("re").compile(rf"{dri}/renderD[0-9]{{3}}"))
    probe = asyncio.create_task(decode.probe_motion_decoder(ffmpeg=ffmpeg, dri=dri, timeout=60))
    deadline = time.monotonic() + 10
    while not (pid_file.exists() and pid_file.read_text()) and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    pid = int(pid_file.read_text())
    probe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await probe
    assert _gone(pid, seconds=1.0)


def test_the_listing_reads_at_most_its_limit_then_stops_and_reaps_the_lister(tmp_path):
    # An over-long listing is refused at the limit instead of being buffered whole. The
    # stand-in writes a bounded 2 MB and then hangs, so even a buffering reader holds only
    # that much before its deadline: a test must never be able to exhaust the host's memory.
    pid_file = tmp_path / "lister.pid"
    ffmpeg = _python_ffmpeg(
        tmp_path,
        f"open({str(pid_file)!r}, 'w').write(str(__import__('os').getpid()))\n"
        "out.write(b'0, 0, 0, 1, 1, 0x0\\n' * 110000)\nout.flush()\ntime.sleep(30)",
    )
    started = time.monotonic()
    with pytest.raises(decode.HardwareDecodeUnsupported, match="too long"):
        decode.read_timeline(Path("clip.mp4"), ffmpeg=ffmpeg)
    assert time.monotonic() - started < 5
    assert _gone(int(pid_file.read_text()), seconds=1.0)


def test_a_lister_that_hangs_or_crashes_is_a_hardware_failure_that_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(decode, "LISTING_TIMEOUT_SECONDS", 0.5)
    for body in ("time.sleep(30)", "sys.exit(3)"):
        ffmpeg = _python_ffmpeg(tmp_path, body)
        with pytest.raises(decode.HardwareDecodeFailed) as raised:
            decode.read_timeline(Path("clip.mp4"), ffmpeg=ffmpeg)
        assert not isinstance(raised.value, decode.HardwareDecodeUnsupported)


def test_the_worst_case_gpu_scan_fits_well_inside_the_worker_deadline():
    from app.services.garden_motion import MOTION_WORKER_TIMEOUT_SECONDS

    # Listing, then a GPU decode that times out, then the CPU rescans the recording and runs
    # three detector samples: about 15 s of CPU work on a slow host.
    assert decode.LISTING_TIMEOUT_SECONDS + decode.FRAME_TIMEOUT_SECONDS + 15 <= MOTION_WORKER_TIMEOUT_SECONDS
