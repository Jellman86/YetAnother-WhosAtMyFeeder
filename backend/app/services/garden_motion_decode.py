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
from collections.abc import Callable, Iterator
from contextlib import suppress
import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
from typing import Any, Literal

import numpy as np

from app.utils.child_signals import kill_child

FFMPEG = Path("/usr/local/bin/yawamf-ffmpeg")
RENDER_NODES = Path("/dev/dri")
RENDER_NODE = re.compile(r"/dev/dri/renderD[0-9]{3}")
PROBE_CLIP = Path(__file__).resolve().parents[1] / "assets" / "garden_decode_probe.mp4"
PROBE_SIZE = (128, 128)
PROBE_TIMEOUT_SECONDS = 10.0
# A 20 s, 1440p recording decodes on the GPU in about a second. This bounds one
# recording's decode so a hung GPU falls back to software inside the parent's 45 s deadline.
FRAME_TIMEOUT_SECONDS = 20.0
# Listing packets only demuxes, well under a second for a 48 MiB recording. Kept short so a
# listing timeout, a GPU timeout and a full CPU rescan still finish inside the 45 s deadline.
LISTING_TIMEOUT_SECONDS = 5.0
LISTING_BYTE_LIMIT = 1024 * 1024
# ffmpeg prints AV_NOPTS_VALUE for a packet without a timestamp.
_NO_TIMESTAMP = -(2**63)

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


_PR_SET_PDEATHSIG = 1


def owned_by_this_process() -> Callable[[], None] | None:
    """A pre-exec hook that ties the decoder's life to the process starting it.

    Bird pre-emption kills the motion worker, and a decoder stalled before its next pipe
    write would otherwise outlive it. The kernel sends the decoder SIGKILL when its parent
    exits, however it exits; checking the parent afterwards closes the race where it died
    before the hook ran. prctl is resolved before fork, so the child makes only system calls.
    """
    if sys.platform != "linux":
        return None
    # Python warns that pre-exec code is unsafe in a threaded process because the child may
    # need a lock another thread held at fork. This hook takes none: prctl is looked up here,
    # before fork, and the child only makes the prctl and getppid system calls, then execs.
    prctl = ctypes.CDLL(None, use_errno=True).prctl
    parent = os.getpid()

    def bind() -> None:
        if prctl(_PR_SET_PDEATHSIG, int(signal.SIGKILL), 0, 0, 0) != 0 or os.getppid() != parent:
            os._exit(127)

    return bind


class HardwareDecodeFailed(RuntimeError):
    """The GPU did not return the requested frames; the caller decodes them in software."""


class HardwareDecodeUnsupported(HardwareDecodeFailed):
    """This recording cannot be matched to OpenCV's frames on the GPU, so it is read in software.

    A property of the stream, not a fault of the GPU, so it does not count towards
    switching hardware decode off.
    """


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
    """The frame number OpenCV's reader seeks to, and reports, for each sample time.

    OpenCV 4.10 turns a millisecond position into ``(int64)(msec / 1000.0 * fps + 0.5)``,
    capped at the frame count: half a frame rounds up, where Python's ``round()`` rounds to
    even and chose another frame. The same operations in the same order give the same double.
    """
    return [min(int(count), max(0, int(time * 1000 / 1000.0 * fps + 0.5))) for time in times]


@dataclass(frozen=True)
class Packet:
    dts: int
    pts: int
    key: bool
    discard: bool = False


@dataclass(frozen=True)
class VideoTimeline:
    """A recording's video packets in decode order, with their stream time base in seconds."""

    time_base: float
    packets: tuple[Packet, ...]


TIMELINE_PACKET_LIMIT = 4096


def parse_timeline(text: str) -> VideoTimeline:
    """Read ffmpeg's framecrc listing of one stream-copied video stream, strictly and boundedly.

    Anything unreadable is a property of the recording, not a GPU fault, so it is
    ``HardwareDecodeUnsupported``: the recording is read in software without counting
    towards switching hardware decode off.
    """
    time_base: float | None = None
    packets: list[Packet] = []
    for line in text.splitlines():
        if line.startswith("#tb 0:"):
            numerator, _, denominator = line.split(":", 1)[1].strip().partition("/")
            if not numerator.isdigit() or not denominator.isdigit() or int(denominator) == 0:
                raise HardwareDecodeUnsupported("Recording time base is unreadable")
            time_base = int(numerator) / int(denominator)
        elif line and not line.startswith("#"):
            fields = [field.strip() for field in line.split(",")]
            if len(fields) < 6 or fields[0] != "0" or len(packets) >= TIMELINE_PACKET_LIMIT:
                raise HardwareDecodeUnsupported("Recording packet listing is unreadable")
            try:
                dts, pts = int(fields[1]), int(fields[2])
            except ValueError as error:
                raise HardwareDecodeUnsupported("Recording packet timestamps are unreadable") from error
            if _NO_TIMESTAMP in (dts, pts):
                raise HardwareDecodeUnsupported("Recording has a packet without a timestamp")
            # framecrc names flags (F=0x..) only when a packet is not exactly a keyframe, and
            # may append side data (S=..) after them.
            # Bit 0x1 is a keyframe; 0x4 marks a packet an edit list tells the decoder to drop.
            flags = [field for field in fields[6:] if field.startswith("F=0x")]
            try:
                value = int(flags[0][4:], 16) if flags else 0x1
            except ValueError as error:
                raise HardwareDecodeUnsupported("Recording packet flags are unreadable") from error
            packets.append(Packet(dts, pts, bool(value & 0x1), bool(value & 0x4)))
    if time_base is None or not packets:
        raise HardwareDecodeUnsupported("Recording has no video packets")
    return VideoTimeline(time_base, tuple(packets))


def opencv_seek_frames(timeline: VideoTimeline, targets: list[int], *, fps: float) -> list[int]:
    """The decoded frame OpenCV 4.10 returns after seeking to each frame number.

    OpenCV seeks backward to the keyframe at or before ``target - 16`` frames, numbers that
    keyframe from its timestamp, then counts decoded frames from there. On a camera whose
    timestamps jitter, such as one at 30.14 fps on a 1/60 s grid, the keyframe's timestamp
    number differs from its position, so OpenCV returns a frame or two either side of the
    one it reports. Replaying its arithmetic here makes the GPU return the same frame.
    Recordings that reorder frames are refused, so they keep decoding in software, as are
    recordings with packets marked for discard: OpenCV's decoder never returns those, so
    counting them would run ahead of its frame count.
    """
    packets = timeline.packets
    if any(packet.discard for packet in packets):
        raise HardwareDecodeUnsupported("Recording has packets marked for discard by an edit list")
    if any(later.pts <= earlier.pts or later.dts < earlier.dts for earlier, later in zip(packets, packets[1:])):
        raise HardwareDecodeUnsupported("Recording reorders frames")
    start = packets[0].pts

    def number(index: int) -> int:
        packet = packets[index]
        stamp = packet.pts if packet.pts != 0 else packet.dts
        return int(fps * ((stamp - start) * timeline.time_base) + 0.5)

    first = number(0)
    keyframes = [index for index, packet in enumerate(packets) if packet.key]
    if not keyframes or keyframes[0] != 0:
        raise HardwareDecodeUnsupported("Recording does not start on a keyframe")

    def seek(frame: int) -> int:
        stamp = start + int(frame / fps / timeline.time_base + 0.5)
        chosen = 0
        for index in keyframes:
            if packets[index].dts <= stamp:
                chosen = index
        return chosen

    chosen_frames = []
    for target in targets:
        if target < 2:
            chosen = seek(0) + target
        else:
            delta = 16
            while True:
                earlier = max(target - delta, 0)
                keyframe = seek(earlier)
                found = number(keyframe) - first
                if 0 <= found <= target - 1:
                    chosen = keyframe + target - found
                    break
                if earlier == 0:
                    raise HardwareDecodeUnsupported("OpenCV's seek for this recording cannot be reproduced")
                delta = delta * 2 if delta < 16 else delta * 3 // 2
        if chosen >= len(packets):
            raise HardwareDecodeUnsupported("Sample lies past the recording's last frame")
        chosen_frames.append(chosen)
    if chosen_frames != sorted(chosen_frames):
        raise HardwareDecodeUnsupported("OpenCV's seek would return these samples out of order")
    return chosen_frames


def packet_command(clip: Path, *, ffmpeg: Path = FFMPEG) -> list[str]:
    # Stream copy reads timestamps without decoding; -copyts keeps them as the demuxer sees them.
    return [
        str(ffmpeg),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-copyts",
        "-i",
        str(clip),
        "-map",
        "0:v:0",
        "-c",
        "copy",
        "-f",
        "framecrc",
        "pipe:1",
    ]


def read_timeline(clip: Path, *, ffmpeg: Path = FFMPEG) -> VideoTimeline:
    """The recording's packet timestamps, read through a bounded pipe.

    At most ``LISTING_BYTE_LIMIT`` bytes are read; a longer listing is refused and ffmpeg is
    killed and reaped, so an odd recording cannot make the worker buffer without bound. A
    hung or crashed lister is a hardware-path failure; an over-long listing is the file's.
    """
    try:
        process = subprocess.Popen(
            packet_command(clip, ffmpeg=ffmpeg),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            preexec_fn=owned_by_this_process(),
        )
    except OSError as error:
        raise HardwareDecodeFailed(type(error).__name__) from error
    timed_out = threading.Event()

    def stop() -> None:
        timed_out.set()
        process.kill()

    deadline = threading.Timer(LISTING_TIMEOUT_SECONDS, stop)
    deadline.start()
    try:
        output = process.stdout.read(LISTING_BYTE_LIMIT + 1) if process.stdout else b""
        if len(output) > LISTING_BYTE_LIMIT:
            raise HardwareDecodeUnsupported("Recording packet listing is too long")
        returncode = process.wait()
    finally:
        deadline.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()
        if process.stdout:
            process.stdout.close()
    if timed_out.is_set():
        raise HardwareDecodeFailed("Recording packet listing timed out")
    if returncode != 0:
        raise HardwareDecodeFailed(f"Recording packet listing exited with status {returncode}")
    return parse_timeline(output.decode("ascii", "replace"))


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
        # OpenCV's reader converts planar YUV 4:2:0 to BGR with bicubic swscale and the BT.601
        # matrix. Converting the GPU's NV12 straight to BGR takes another swscale path and
        # changed pixels; going through yuv420p first returns OpenCV's exact pixels.
        f"select={select},hwdownload,format=nv12,format=yuv420p,scale=in_color_matrix=bt601:flags=bicubic,format=bgr24",
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
            preexec_fn=owned_by_this_process(),
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


async def _reap(process: Any) -> None:
    """Kill the probe's decoder if it is still running and wait until it has exited."""
    if process.returncode is None:
        with suppress(ProcessLookupError):
            kill_child(process)
    # Shielded so a second cancellation cannot leave the child unreaped.
    await asyncio.shield(process.wait())


async def _decodes_probe_clip(command: list[str], timeout: float) -> bool:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        preexec_fn=owned_by_this_process(),
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        return False
    finally:
        # Covers a timeout and cancellation alike, such as shutdown during the startup check.
        await _reap(process)
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
