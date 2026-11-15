"""GPU and CPU decode pick the same frames and return the same pixels as OpenCV's seek.

The fixtures are generated H.264 recordings of 300 frames with camera-like BT.709 tags:
limited range and full range (like the owner's greenhouse camera) at a constant 30 fps,
and one whose timestamps jitter on a 1/60 s grid at 30.14 fps (like the patio camera),
where OpenCV's seek returns a neighbouring frame. Each has its ffmpeg framecrc packet
listing beside it. The CPU half runs everywhere; the GPU half runs only where the Intel
image's decoder and a render node can decode, and is skipped elsewhere.
"""

import asyncio
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.services import garden_motion_decode as decode
from app.services.garden_motion_worker import software_samples

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "garden_motion").glob("garden_parity_*.mp4"))
CONSTANT_RATE = [path for path in FIXTURES if "jitter" not in path.stem]
LIVE = (0.1, 0.5, 0.9)
OFFLINE = tuple(i / 10 for i in range(1, 10))


def _reader(path: Path) -> cv2.VideoCapture:
    reader = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    assert reader.isOpened()
    return reader


def _scan_times(fps: float, count: float, fractions: tuple[float, ...]) -> list[float]:
    # The same arithmetic scan_clip uses for a ten-second window without pre-roll.
    duration = count / fps
    preroll = max(0.0, duration - 10)
    span = min(duration - preroll - 0.1, 10)
    return [preroll + span * fraction for fraction in fractions]


def _opencv_samples(
    path: Path, fractions: tuple[float, ...]
) -> tuple[list[float], list[int], list[np.ndarray], float, float]:
    reader = _reader(path)
    try:
        fps, count = reader.get(cv2.CAP_PROP_FPS), reader.get(cv2.CAP_PROP_FRAME_COUNT)
        times = _scan_times(fps, count, fractions)
        samples = list(software_samples(reader, times))
    finally:
        reader.release()
    return times, [int(index) for index, _ in samples], [frame for _, frame in samples], fps, count


def _sequential(path: Path) -> list[np.ndarray]:
    reader = _reader(path)
    frames = []
    try:
        while True:
            ok, frame = reader.read()
            if not ok:
                return frames
            frames.append(frame)
    finally:
        reader.release()


def _timeline(path: Path) -> decode.VideoTimeline:
    return decode.parse_timeline(path.with_suffix(".framecrc").read_text())


def test_every_fixture_and_its_packet_listing_are_present():
    assert [path.name for path in FIXTURES] == [
        "garden_parity_full.mp4",
        "garden_parity_jitter.mp4",
        "garden_parity_limited.mp4",
    ]
    assert all(path.with_suffix(".framecrc").is_file() for path in FIXTURES)


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda path: path.stem)
def test_the_replayed_seek_picks_the_frame_opencv_returns_for_every_frame_number(fixture):
    sequential = _sequential(fixture)
    timeline = _timeline(fixture)
    reader = _reader(fixture)
    mismatched, quirks = [], 0
    try:
        fps, count = reader.get(cv2.CAP_PROP_FPS), reader.get(cv2.CAP_PROP_FRAME_COUNT)
        for wanted in range(len(sequential) - 1):
            time = wanted / fps
            (target,) = decode.sample_frame_indices([time], fps=fps, count=count)
            (index, frame), *_ = list(software_samples(reader, [time]))
            (chosen,) = decode.opencv_seek_frames(timeline, [target], fps=fps)
            quirks += chosen != target
            if int(index) != target or not np.array_equal(frame, sequential[chosen]):
                mismatched.append(wanted)
    finally:
        reader.release()
    assert mismatched == []
    # The jittered recording really does make OpenCV return a frame other than the one it reports.
    assert (quirks > 0) == ("jitter" in fixture.stem)


@pytest.mark.parametrize("fixture", CONSTANT_RATE, ids=lambda path: path.stem)
@pytest.mark.parametrize("fractions", [LIVE, OFFLINE], ids=["live", "offline"])
def test_gpu_frame_selection_matches_the_frames_opencv_seeks_to(fixture, fractions):
    times, indices, frames, fps, count = _opencv_samples(fixture, fractions)
    assert fps == 30.0
    assert decode.sample_frame_indices(times, fps=fps, count=count) == indices
    sequential = _sequential(fixture)
    # Each seeked frame is the frame at its reported position, decoded in order.
    assert all(np.array_equal(frame, sequential[index]) for index, frame in zip(indices, frames))
    if fractions == LIVE:
        # 4.95 s at 30 fps is half a frame: OpenCV rounds it up, unlike Python's round().
        assert indices == [30, 149, 267] and round(times[1] * 30) == 148


def _gpu_decoder() -> decode.MotionDecoder:
    found = asyncio.run(decode.probe_motion_decoder())
    if found.state != "vaapi":
        pytest.skip(f"No usable VA-API decoder here ({found.state})")
    return found


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda path: path.stem)
@pytest.mark.parametrize("fractions", [LIVE, OFFLINE], ids=["live", "offline"])
def test_gpu_frames_are_pixel_identical_to_opencv(fixture, fractions):
    device = _gpu_decoder().device
    assert device is not None
    times, indices, frames, fps, count = _opencv_samples(fixture, fractions)
    reader = _reader(fixture)
    width, height = int(reader.get(cv2.CAP_PROP_FRAME_WIDTH)), int(reader.get(cv2.CAP_PROP_FRAME_HEIGHT))
    reader.release()
    timeline = decode.read_timeline(fixture)
    # The packaged decoder lists the same packets as the listing the CPU tests replay.
    assert timeline == _timeline(fixture)
    planned = decode.sample_frame_indices(times, fps=fps, count=count)
    chosen = decode.opencv_seek_frames(timeline, planned, fps=fps)
    gpu = list(decode.stream_frames(device, fixture, chosen, width=width, height=height))
    assert planned == indices
    differing = sum(int(np.count_nonzero(a != b)) for a, b in zip(gpu, frames))
    assert differing == 0
