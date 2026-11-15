"""Decode a motion recording's few sampled frames on the Intel GPU when the image can.

The Intel image ships a minimal ffmpeg built only to decode H.264 and HEVC through
VA-API. Hardware decode returns the same YUV pixels as software decode, so the samples
are unchanged; what changes is the CPU spent reaching them. Seeking a 1440p recording
three times decodes every frame from the previous keyframe, which in software is most
of a scan's decode cost. Images without that binary, or hosts where a real test decode
fails, keep decoding in software through OpenCV.

The parent proves hardware decode once with ``probe_motion_decoder``; the motion
worker then calls ``stream_frames`` for each recording.
"""

import asyncio
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import threading
from typing import Literal

import numpy as np

FFMPEG = Path("/usr/local/bin/yawamf-ffmpeg")
RENDER_NODES = Path("/dev/dri")
RENDER_NODE = re.compile(r"/dev/dri/renderD[0-9]{3}")
PROBE_CLIP = Path(__file__).resolve().parents[1] / "assets" / "garden_decode_probe.mp4"
PROBE_SIZE = (128, 128)
PROBE_TIMEOUT_SECONDS = 10.0
# A 20 s, 1440p recording decodes on the GPU in about a second. This bounds one
# recording's decode so a hung GPU falls back to software inside the parent's 45 s deadline.
FRAME_TIMEOUT_SECONDS = 20.0

DecoderState = Literal["vaapi", "not_packaged", "no_render_node", "probe_failed", "decode_failed"]

DECODER_MESSAGES: dict[DecoderState, str] = {
    "vaapi": "Motion recordings decode on the Intel GPU ({device}).",
    "not_packaged": (
        "This image has no hardware video decoder, so motion recordings decode on the CPU. "
        "The Intel image decodes them on the GPU."
    ),
    "no_render_node": (
        "No GPU render device is available in /dev/dri, so motion recordings decode on the CPU. "
        "Pass /dev/dri through to the container to decode them on the Intel GPU."
    ),
    "probe_failed": (
        "The Intel GPU could not decode a test recording, so motion recordings decode on the CPU. "
        "Check that /dev/dri is passed through and that the container user is in its render group."
    ),
    "decode_failed": (
        "The Intel GPU stopped decoding motion recordings, so they decode on the CPU until the next restart."
    ),
}


class HardwareDecodeFailed(RuntimeError):
    """The GPU did not return the requested frames; the caller decodes them in software."""


@dataclass(frozen=True)
class MotionDecoder:
    state: DecoderState
    device: str | None = None

    @property
    def decoder(self) -> Literal["vaapi", "software"]:
        return "vaapi" if self.state == "vaapi" else "software"

    @property
    def message(self) -> str:
        return DECODER_MESSAGES[self.state].format(device=self.device)


def sample_frame_indices(times: list[float], *, fps: float, count: float) -> list[int]:
    """The frame nearest each sample time, as a frame-accurate reader would return it."""
    last = max(0, int(count) - 1)
    return [min(last, max(0, round(time * fps))) for time in times]


def frame_command(device: str, clip: Path, indices: list[int], *, ffmpeg: Path = FFMPEG) -> list[str]:
    if not RENDER_NODE.fullmatch(device):
        raise ValueError("Hardware decode needs a GPU render node")
    unique = sorted(set(indices))
    select = "+".join(f"eq(n\\,{index})" for index in unique)
    return [
        str(ffmpeg),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-threads",
        "1",
        "-filter_threads",
        "1",
        "-init_hw_device",
        f"vaapi=va:{device}",
        "-hwaccel",
        "vaapi",
        "-hwaccel_device",
        "va",
        "-hwaccel_output_format",
        "vaapi",
        "-i",
        str(clip),
        "-vf",
        # hwdownload accepts only GPU frames, so ffmpeg cannot quietly decode in software.
        # OpenCV's reader converts with the BT.601 matrix; matching it keeps the samples the
        # detector was qualified on.
        f"select={select},hwdownload,format=nv12,scale=in_color_matrix=bt601:flags=bicubic,format=bgr24",
        "-fps_mode",
        "passthrough",
        "-frames:v",
        str(len(unique)),
        "-f",
        "rawvideo",
        "pipe:1",
    ]


def stream_frames(
    device: str, clip: Path, indices: list[int], *, width: int, height: int, ffmpeg: Path = FFMPEG
) -> Iterator[np.ndarray]:
    """BGR frames at ``indices`` (non-decreasing, repeats allowed), each as soon as it decodes.

    Closing the iterator early, as a person in the first sample does, stops the decode, so
    an early veto costs no more than software's single seek. The motion worker is a
    synchronous child, so this blocks it, never the API; if the worker is killed, ffmpeg's
    next write meets a closed pipe and it exits.
    """
    if indices != sorted(indices):
        raise ValueError("Hardware decode returns frames in recording order")
    size = width * height * 3
    try:
        process = subprocess.Popen(
            frame_command(device, clip, indices, ffmpeg=ffmpeg),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise HardwareDecodeFailed(type(error).__name__) from error
    deadline = threading.Timer(FRAME_TIMEOUT_SECONDS, process.kill)
    deadline.start()
    try:
        latest: tuple[int, np.ndarray] | None = None
        for index in indices:
            if latest is None or latest[0] != index:
                data = process.stdout.read(size) if process.stdout else b""
                if len(data) != size:
                    raise HardwareDecodeFailed("Hardware decode ended before every sampled frame")
                latest = (index, np.frombuffer(data, np.uint8).reshape(height, width, 3))
            yield latest[1]
    finally:
        deadline.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()
        if process.stdout:
            process.stdout.close()


async def _decodes_probe_clip(command: list[str], timeout: float) -> bool:
    process = await asyncio.create_subprocess_exec(
        *command, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        with suppress(ProcessLookupError):
            process.kill()
        await process.wait()
        return False
    width, height = PROBE_SIZE
    return process.returncode == 0 and len(output) == width * height * 3


async def probe_motion_decoder(
    *, ffmpeg: Path = FFMPEG, dri: Path = RENDER_NODES, timeout: float = PROBE_TIMEOUT_SECONDS
) -> MotionDecoder:
    """Hardware decode is used only after it decodes a real H.264 clip on a render node."""
    if not await asyncio.to_thread(ffmpeg.is_file):
        return MotionDecoder("not_packaged")
    nodes = await asyncio.to_thread(
        lambda: sorted(str(node) for node in dri.glob("renderD*") if re.fullmatch(r"renderD[0-9]{3}", node.name))
    )
    if not nodes:
        return MotionDecoder("no_render_node")
    for node in nodes:
        try:
            if await _decodes_probe_clip(frame_command(node, PROBE_CLIP, [0], ffmpeg=ffmpeg), timeout):
                return MotionDecoder("vaapi", node)
        except (OSError, ValueError):
            continue
    return MotionDecoder("probe_failed")
