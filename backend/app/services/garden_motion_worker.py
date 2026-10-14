"""One bounded CPU recording scan. Parent supervises deadline and bird priority.

No application settings, database, network, species identification or reporting.
"""

import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import cv2

from app.services.garden_detector_runtime import detector_input, decode_candidates
from app.services.garden_model_runtime import Runtime, digest
from app.models.garden_motion import MOTION_PADDING_SECONDS


def scan_clip(payload: dict[str, Any]) -> dict[str, Any]:
    model, clip, photo = (Path(payload[name]).resolve() for name in ("model", "clip", "photo"))
    duration_limit = float(payload["duration"])
    if not 0.1 <= duration_limit <= 10 or photo.parent != clip.parent:
        raise ValueError("Motion scan requires bounded temporary recording and photo paths")
    if clip.stat().st_size > 16 * 1024 * 1024 or digest(clip) != payload["clip_sha256"]:
        raise ValueError("Motion recording exceeds its limit or differs from its checksum")
    if digest(model) != payload["model_sha256"]:
        raise ValueError("Garden detector differs from its pinned model")
    cv2.setNumThreads(1)
    reader = cv2.VideoCapture(str(clip), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    try:
        width, height = reader.get(cv2.CAP_PROP_FRAME_WIDTH), reader.get(cv2.CAP_PROP_FRAME_HEIGHT)
        fps, count = reader.get(cv2.CAP_PROP_FPS), reader.get(cv2.CAP_PROP_FRAME_COUNT)
        if not all(math.isfinite(v) and v > 0 for v in (width, height, fps, count)):
            raise ValueError("Motion recording has no valid dimensions or frame rate")
        duration = count / fps
        if width * height > 16_000_000 or fps > 120 or not 0.1 <= duration <= duration_limit + MOTION_PADDING_SECONDS:
            raise ValueError("Motion recording exceeds its pixel or duration limit")
        runtime = Runtime(model, "cpu")
        best = None
        for fraction in (0.1, 0.5, 0.9):
            reader.set(cv2.CAP_PROP_POS_MSEC, min(duration - 0.1, duration_limit) * fraction * 1000)
            ok, frame = reader.read()
            if not ok:
                raise ValueError("Motion recording could not decode a sample")
            index = reader.get(cv2.CAP_PROP_POS_FRAMES) - 1
            if not math.isfinite(index) or not 0 <= index <= 1200 or index / fps > duration_limit:
                raise ValueError("Motion recording did not identify a bounded sample frame")
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            tensor, meta = detector_input(rgb)
            candidates = decode_candidates(
                runtime.infer(tensor), meta, payload["names"], payload.get("animal_confidence", 0.5)
            )
            if any(label == "person" for label, _, _ in candidates):
                # A later person sample revokes earlier animal proposals too.
                return {"outcome": "person_rejected"}
            animals = [candidate for candidate in candidates if candidate[0] == "animal"]
            if animals and (best is None or animals[0][1] > best[0][1]):
                best = (
                    animals[0],
                    frame.copy(),
                    int(index),
                    float(index / fps),
                    hashlib.sha256(rgb.tobytes()).hexdigest(),
                    hashlib.sha256(tensor.tobytes()).hexdigest(),
                )
        if best is None:
            return {"outcome": "no_candidate"}
        candidate, frame, frame_index, offset, frame_hash, tensor_hash = best
        # Stored evidence is deliberately small; box coordinates are normalized.
        h, w = frame.shape[:2]
        scale = min(1.0, 1280 / max(w, h))
        if scale < 1:
            frame = cv2.resize(frame, (max(1, round(w * scale)), max(1, round(h * scale))))
        for quality in (90, 80, 65):
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if ok and encoded.nbytes <= 512 * 1024:
                image = encoded.tobytes()
                photo.write_bytes(image)
                return {
                    "outcome": "candidate",
                    "frame_index": frame_index,
                    "frame_offset": offset,
                    "detector_score": candidate[1],
                    "box_xywh": candidate[2],
                    "image_sha256": hashlib.sha256(image).hexdigest(),
                    "devices": runtime.actual,
                    "detector_input_sha256": tensor_hash,
                    "sampled_frame_sha256": frame_hash,
                }
        raise ValueError("Motion photo could not fit its byte limit")
    finally:
        reader.release()


def main() -> None:
    payload = json.loads(sys.stdin.buffer.readline(8192))
    result = scan_clip(payload)
    sys.stdout.write("MOTION_RESULT:" + json.dumps(result, allow_nan=False) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
