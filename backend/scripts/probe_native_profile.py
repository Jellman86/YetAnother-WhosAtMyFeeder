"""One explicitly requested, externally monitored native-profile diagnostic child."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any
from collections.abc import Callable

from app.services.native_crash_quarantine import NativeCrashQuarantine, NativeCrashQuarantinedError
from app.services.native_profile_probe_result import ProfileProbeFailure, failure_details

if TYPE_CHECKING:
    import numpy as np
    from PIL import Image
    from app.services.classifier_service import ClassifierService
    from app.services.bird_crop_service import BirdCropService


def validate_vectors(vectors: list[np.ndarray], *, require_variation: bool = True) -> None:
    import numpy as np

    if len(vectors) < 3:
        raise ProfileProbeFailure("missing_outputs")
    rows = [np.asarray(vector, dtype=np.float64).reshape(-1) for vector in vectors]
    if any(row.size < 2 or not np.isfinite(row).all() or float(np.ptp(row)) < 1e-8 for row in rows):
        raise ProfileProbeFailure("invalid_outputs")
    if len({row.size for row in rows}) != 1:
        raise ProfileProbeFailure("output_dimensions_changed")
    if require_variation and all(np.allclose(rows[0], row, rtol=1e-5, atol=1e-7) for row in rows[1:]):
        raise ProfileProbeFailure("indistinguishable_photos")


def validate_predictions(predictions: list[dict[str, Any]]) -> None:
    if not predictions:
        raise ProfileProbeFailure("no_pipeline_result")
    for prediction in predictions:
        score = prediction.get("score")
        if not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 < score <= 1:
            raise ProfileProbeFailure("invalid_scores")


class ExactProfileProbePolicy(NativeCrashQuarantine):
    """Bypass only the captured configuration inside this disposable probe."""

    def __init__(
        self, getter: Callable[[], dict[str, Any]], captured: dict[str, Any], *, root: Path | None = None
    ) -> None:
        super().__init__(getter, root=root)
        self._captured_key = self._key(captured)

    def guard(self, profile: dict[str, Any] | None = None, **_kwargs: Any) -> dict[str, Any]:
        current = self._profile_getter() if profile is None else profile
        if self._key(current) != self._captured_key:
            raise NativeCrashQuarantinedError("The diagnostic configuration changed")
        return current

    def record(self, profile: dict[str, Any] | None, exit_code: int | None) -> bool:
        return False

    def record_retirement(self, profile: dict[str, Any] | None, error_code: str, detail: str) -> bool:
        return False


def _assert_identity(service: ClassifierService, profile: dict[str, Any]) -> None:
    identity = service.runtime_identity()
    if (
        identity.get("active_provider") != profile["provider"]
        or identity.get("model_sha256") != profile["model_sha256"]
        or service.latest_runtime_recovery() is not None
        or NativeCrashQuarantine._key(service._native_launch_profile()) != NativeCrashQuarantine._key(profile)
    ):
        raise ProfileProbeFailure("profile_changed")


def _video_frames(path: str) -> list[Image.Image]:
    import cv2
    from PIL import Image
    from app.utils.image_io import MAX_IMAGE_PIXELS

    capture = cv2.VideoCapture(path)
    try:
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if not capture.isOpened() or count < 3 or min(width, height) < 1 or width * height > MAX_IMAGE_PIXELS:
            raise ProfileProbeFailure("invalid_clip")
        frames = []
        for index in (0, (count - 1) // 2, min(count - 1, int(count * 0.9))):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok or frame is None or frame.shape[0] * frame.shape[1] > MAX_IMAGE_PIXELS:
                raise ProfileProbeFailure("video_decode_failed")
            frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        return frames
    finally:
        capture.release()


def check_crop_tier(crop: BirdCropService, image: Image.Image, tier: str) -> None:
    from app.services.bird_crop_service import detector_scan_failed

    result, available = crop._generate_crop_for_tier(image, tier)
    try:
        if not available or detector_scan_failed(result):
            raise ProfileProbeFailure("crop_check_failed")
    finally:
        selected = result.get("crop_image")
        if selected is not None and selected is not image:
            selected.close()


def run(payload: dict[str, Any]) -> dict[str, Any]:
    from app.services.classifier_service import ClassifierService
    from app.services.native_profile_revalidation import auxiliary_components
    from app.utils.image_io import load_rgb_image

    profile = payload["profile"]
    service = ClassifierService(
        worker_process_mode=True, crash_quarantine_factory=lambda getter: ExactProfileProbePolicy(getter, profile)
    )
    components = auxiliary_components(profile)
    if any(component.startswith("crop:") for component in components):
        service._bird_crop_service.strict_provider = True
    vectors = []
    checked = set()
    for path in payload["images"]:
        try:
            image = load_rgb_image(path)
        except (OSError, ValueError):
            raise ProfileProbeFailure("invalid_photo") from None
        try:
            validate_predictions(service.classify(image))
            vector, _ = service._classify_raw_with_runtime_recovery(image)
            vectors.append(vector)
            for component in components:
                if component.startswith("crop:"):
                    check_crop_tier(service._bird_crop_service, image, component.split(":", 1)[1])
                elif component == "wildlife":
                    validate_predictions(service.classify_wildlife(image))
                checked.add(component)
            _assert_identity(service, profile)
        finally:
            image.close()
    validate_vectors(vectors)
    frames = _video_frames(payload["video"])
    try:
        frame_vectors = [service._classify_raw_with_runtime_recovery(frame)[0] for frame in frames]
        validate_vectors(frame_vectors, require_variation=False)
    finally:
        for frame in frames:
            frame.close()
    validate_predictions(
        service.classify_video(payload["video"], max_frames=max(3, int(profile.get("video_frames", 3))))
    )
    _assert_identity(service, profile)
    return {
        "profile_fingerprint": NativeCrashQuarantine._key(profile),
        "model_sha256": profile["model_sha256"],
        "active_provider": profile["provider"],
        "images_checked": len(vectors),
        "video_frames_checked": len(frame_vectors),
        "finite": True,
        "nondegenerate": True,
        "pipeline_checked": True,
        "auxiliary_checked": sorted(checked),
    }


def main() -> int:
    import ctypes
    import resource

    parent = os.getppid()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, 9, 0, 0, 0) != 0 or parent <= 1 or os.getppid() != parent:
        raise RuntimeError("Parent-death process protection is unavailable")
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError("The diagnostic launch manifest exceeded its bound")
    payload = json.loads(raw)
    try:
        result = run(payload)
        exit_code = 0
    except NativeCrashQuarantinedError:
        result = {"failure": {"reason": "profile_changed"}}
        exit_code = 1
    except Exception as error:
        result = {"failure": failure_details(error)}
        exit_code = 1
    Path(payload["result"]).write_text(json.dumps(result))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
