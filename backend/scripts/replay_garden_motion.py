"""Replay a complete local recording with the current CPU motion worker.

Diagnostic only: no settings, database, network, review decisions or notifications.
Run native inference under an external deadline/resource/bird-pressure supervisor.
FFmpeg remuxes packets; every requested frame must decode identically before any
inference. Unsupported seek/timestamp layouts fail rather than re-encode evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from app.services.garden_model_runtime import digest  # noqa: E402
from app.services.garden_motion_worker import scan_clip  # noqa: E402


@dataclass(frozen=True)
class Window:
    start_frame: int
    frames: int
    fps: float

    @property
    def duration(self) -> float:
        return self.frames / self.fps


def plan_windows(count: int, fps: float) -> list[Window]:
    if not math.isfinite(fps) or not 0 < fps <= 120 or count <= 0 or not 0.1 <= count / fps <= 600:
        raise ValueError("Replay requires 0.1 to 600 seconds of video at up to 120 fps")
    minimum, maximum = math.ceil(fps * 0.1), math.floor(fps * 10)
    if maximum < minimum:
        raise ValueError("Recording cannot form a bounded motion window")
    lengths = [min(maximum, count - start) for start in range(0, count, maximum)]
    if lengths[-1] < minimum:
        moved = minimum - lengths[-1]
        lengths[-2] -= moved
        lengths[-1] += moved
    windows, start = [], 0
    for length in lengths:
        windows.append(Window(start, length, fps))
        start += length
    return windows


def remux(ffmpeg: Path, source: Path, destination: Path, window: Window) -> None:
    subprocess.run(
        [
            str(ffmpeg),
            "-nostdin",
            "-v",
            "error",
            "-ss",
            str(window.start_frame / window.fps),
            "-i",
            str(source),
            "-t",
            str(window.duration),
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "copy",
            str(destination),
        ],
        check=True,
        timeout=60,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def verify_window(source: Path, clip: Path, window: Window) -> list[str]:
    original = cv2.VideoCapture(str(source), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    copied = cv2.VideoCapture(str(clip), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    try:
        if not original.isOpened() or not copied.isOpened():
            raise ValueError("Could not decode replay recording")
        for reader in (original, copied):
            if not math.isclose(reader.get(cv2.CAP_PROP_FPS), window.fps, abs_tol=1e-6):
                raise ValueError("Remux changed recording timing")
        original.set(cv2.CAP_PROP_POS_FRAMES, window.start_frame)
        hashes = []
        for index in range(window.frames):
            ok_source, a = original.read()
            ok_copy, b = copied.read()
            if not ok_source or not ok_copy:
                raise ValueError("Could not decode every requested replay frame")
            for reader, frame in ((original, window.start_frame + index), (copied, index)):
                timestamp = reader.get(cv2.CAP_PROP_POS_MSEC) / 1000
                if not math.isfinite(timestamp) or abs(timestamp - frame / window.fps) > 0.51 / window.fps:
                    raise ValueError("Replay requires unchanged constant-frame-rate timing")
            if not np.array_equal(a, b):
                raise ValueError("Remux changed source pixels or frame alignment")
            rgb = cv2.cvtColor(a, cv2.COLOR_BGR2RGB)
            hashes.append(hashlib.sha256(rgb.tobytes()).hexdigest())
        return hashes
    finally:
        original.release()
        copied.release()


def verify_result(result: dict[str, Any], hashes: list[str]) -> None:
    if result["outcome"] == "candidate":
        index = result["frame_index"]
        if (
            not isinstance(index, int)
            or not 0 <= index < len(hashes)
            or result["sampled_frame_sha256"] != hashes[index]
        ):
            raise ValueError("Worker result does not bind the original source frame")
    elif result["outcome"] not in {"no_candidate", "person_rejected", "still_rejected"}:
        raise ValueError("Unexpected motion worker result")


def new_output(root: Path) -> None:
    root.mkdir(mode=0o700)


def write_json(path: Path, value: Any) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def replay_recording(
    source: Path,
    model: Path,
    bundle: dict[str, Any],
    ffmpeg: Path,
    thresholds: list[float],
    root: Path,
    *,
    samples_per_window: list[int] | None = None,
) -> dict:
    policies = [3] if samples_per_window is None else samples_per_window
    if (
        not 1 <= len(policies) <= 2
        or any(type(count) is not int or count not in (3, 9) for count in policies)
        or len(set(policies)) != len(policies)
    ):
        raise ValueError("Replay sampling requires distinct three/nine-sample policies")
    cv2.setNumThreads(1)
    reader = cv2.VideoCapture(str(source), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    try:
        fps, count = reader.get(cv2.CAP_PROP_FPS), reader.get(cv2.CAP_PROP_FRAME_COUNT)
        width, height = reader.get(cv2.CAP_PROP_FRAME_WIDTH), reader.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if not all(math.isfinite(v) and v > 0 for v in (fps, count, width, height)) or width * height > 16_000_000:
            raise ValueError("Recording has invalid or oversized dimensions")
        if count != int(count):
            raise ValueError("Recording must identify an integral frame count")
        windows = plan_windows(int(count), fps)
    finally:
        reader.release()
    report: dict[str, Any] = {
        "source_sha256": digest(source),
        "model_sha256": bundle["model_sha256"],
        "fps": fps,
        "frames": int(count),
        "size": [int(width), int(height)],
        "thresholds": thresholds,
        "sampling": "current motion worker: three samples per window, not inference on every frame"
        if policies == [3]
        else "offline three/nine-sample comparison; live collector remains at three samples",
        "samples_per_window": policies,
        "scope": "offline detector only; no Frigate person-overlap veto, persistence, identification or visits",
        "windows": [],
    }
    for number, window in enumerate(windows):
        write_json(
            root / f"window-{number:03d}-started.json", {"start_frame": window.start_frame, "frames": window.frames}
        )
        with tempfile.TemporaryDirectory(prefix="window-", dir=root) as temporary:
            clip, photo = Path(temporary) / "clip.mp4", Path(temporary) / "photo.jpg"
            remux(ffmpeg, source, clip, window)
            if clip.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("Lossless remux exceeds live worker's 16 MiB recording limit")
            hashes = verify_window(source, clip, window)
            payload = dict(
                model=str(model),
                clip=str(clip),
                photo=str(photo),
                duration=window.duration,
                clip_sha256=digest(clip),
                model_sha256=bundle["model_sha256"],
                names=bundle["names"],
            )
            results = []
            for threshold in thresholds:
                for count in policies:
                    photo.unlink(missing_ok=True)
                    started = time.monotonic()
                    result = scan_clip(payload | {"animal_confidence": threshold}, samples_per_window=count)
                    elapsed = time.monotonic() - started
                    verify_result(result, hashes)
                    if result["outcome"] == "candidate":
                        result["source_frame_index"] = window.start_frame + result["frame_index"]
                    results.append(
                        {
                            "animal_confidence": threshold,
                            "samples_per_window": count,
                            "elapsed_seconds": round(elapsed, 6),
                            **result,
                        }
                    )
            row = {
                "start_frame": window.start_frame,
                "frames": window.frames,
                "duration": window.duration,
                "clip_sha256": payload["clip_sha256"],
                "original_frames_verified": len(hashes),
                "results": results,
            }
            write_json(root / f"window-{number:03d}-result.json", row)
            report["windows"].append(row)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, default=BACKEND / "app/assets/garden_md1000_cedar.json")
    parser.add_argument("--ffmpeg", type=Path, required=True)
    parser.add_argument("--thresholds", type=float, nargs="+", default=[0.5, 0.6])
    parser.add_argument("--samples-per-window", type=int, nargs="+", choices=(3, 9), default=[3])
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    source, model = args.source.resolve(), args.model.resolve()
    if not source.is_file() or source.stat().st_size > 256 * 1024 * 1024:
        parser.error("Source must be a local recording up to 256 MiB")
    if not re.fullmatch(r"[0-9a-f]{64}", args.source_sha256) or digest(source) != args.source_sha256:
        parser.error("Source checksum differs from the recorded provenance")
    if not 1 <= len(args.thresholds) <= 6 or any(not 0.5 <= v <= 0.95 for v in args.thresholds):
        parser.error("Provide 1 to 6 animal thresholds from 0.5 to 0.95")
    if len(args.samples_per_window) != len(set(args.samples_per_window)):
        parser.error("Replay sampling policies must not be repeated")
    bundle = json.loads(args.bundle.read_text())
    if bundle["names"] != ["animal", "person", "vehicle"] or digest(model) != bundle["model_sha256"]:
        parser.error("Model differs from the current Cedar bundle")
    new_output(args.root)
    report = replay_recording(
        source,
        model,
        bundle,
        args.ffmpeg.resolve(),
        args.thresholds,
        args.root,
        samples_per_window=args.samples_per_window,
    )
    write_json(args.root / "complete.json", report)


if __name__ == "__main__":
    main()
