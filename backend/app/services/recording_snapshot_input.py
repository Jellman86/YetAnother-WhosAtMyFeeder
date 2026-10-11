"""Select a higher-resolution recording frame aligned with Frigate's best snapshot."""

from __future__ import annotations

import asyncio
import math
import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from io import BytesIO

from PIL import Image
from typing import Any

import structlog

from app.config import settings
from app.services.classification_input_provenance import ClassificationInputProvenance
from app.utils.frigate_coordinates import (
    frigate_snapshot_crop_box,
    normalize_frigate_hint_box,
    restore_frigate_hint_box,
)
from app.utils.image_io import decode_image_bytes

log = structlog.get_logger()
RECORDING_SNAPSHOT_TIMEOUT_SECONDS = 5.0
# Frigate serves a recording frame only once its stretch of recording is written, 10 to 15 seconds
# after the moment on a live install. A caller that can wait retries this often until its deadline.
RECORDING_READY_RETRY_SECONDS = 3.0
# Not written yet, or Frigate too busy to answer within the bound: both pass, so a caller with a
# deadline tries again. Every other reason to keep the detection snapshot is final.
RETRYABLE_REASONS = frozenset({"recording_not_ready", "recording_slow"})
MAX_RECORDING_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_RECORDING_SNAPSHOT_PIXELS = 7680 * 4320


def _timestamp(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def validated_recording_alignment(value: Any) -> tuple[float, tuple[float, float, float, float]] | None:
    """Accept only an explicit timestamp and normalized in-frame box."""
    if not isinstance(value, dict):
        return None
    timestamp = _timestamp(value.get("frame_time"))
    raw_box = value.get("box")
    if not isinstance(raw_box, (list, tuple)) or any(
        isinstance(item, bool) or not isinstance(item, (int, float)) for item in raw_box
    ):
        return None
    box = normalize_frigate_hint_box(raw_box, (1, 1))
    if timestamp is None or box is None:
        return None
    left, top, width, height = box
    if left + width > 1.0 + 1e-9 or top + height > 1.0 + 1e-9:
        return None
    return timestamp, box


def _snapshot_alignment(
    event: dict[str, Any], image_size: tuple[int, int]
) -> tuple[float, tuple[float, float, float, float]] | None:
    snapshot = event.get("snapshot")
    payload = event.get("data")
    payload = payload if isinstance(payload, dict) else {}
    # MQTT pairs its best-frame timestamp and pixel box in snapshot. REST pairs
    # snapshot_frame_time with data.box; current MQTT after.box can have moved.
    if isinstance(snapshot, dict) and snapshot:
        timestamp = snapshot.get("frame_time")
        box = snapshot.get("box")
    else:
        timestamp = payload.get("snapshot_frame_time")
        box = payload.get("box")
    normalized = normalize_frigate_hint_box(box, image_size)
    alignment = validated_recording_alignment({"frame_time": timestamp, "box": normalized})
    if alignment is None:
        return None
    frame_time, _ = alignment
    start, end = _timestamp(event.get("start_time")), _timestamp(event.get("end_time"))
    if (start is not None and frame_time < start) or (end is not None and frame_time > end):
        return None
    return alignment


def _same_shape(data: bytes, size: tuple[int, int]) -> bool:
    try:
        with Image.open(BytesIO(data)) as header:
            width, height = header.size
    except Exception:
        return False
    return math.isclose(width / height, size[0] / size[1], rel_tol=0.01)


def _image_size(data: bytes) -> tuple[int, int]:
    if len(data) > MAX_RECORDING_SNAPSHOT_BYTES:
        raise ValueError("Recording snapshot exceeds the image budget")
    with Image.open(BytesIO(data)) as header:
        if header.width * header.height > MAX_RECORDING_SNAPSHOT_PIXELS:
            raise ValueError("Recording snapshot exceeds the pixel budget")
    with decode_image_bytes(data) as image:
        return image.size


def _prepare_recording_snapshot(data: bytes) -> tuple[bytes, tuple[int, int]]:
    size = _image_size(data)
    # Frigate's recording JPEG API uses FFmpeg's default MJPEG quality. Fetch a
    # lossless PNG instead, then retain the same JPEG quality as event inputs.
    with Image.open(BytesIO(data)) as image:
        if image.format == "JPEG":
            return data, size
        image.load()
        output = BytesIO()
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(output, format="JPEG", quality=95)
        return output.getvalue(), size


@dataclass(frozen=True)
class RecordingRead:
    """The image to classify, its provenance, and why: `recording_frame` when the recording was used."""

    snapshot: bytes | None
    provenance: ClassificationInputProvenance
    reason: str


def recording_frame_time(event_data: dict[str, Any] | None) -> float | None:
    """The moment Frigate's best snapshot shows, from an MQTT snapshot or a REST payload."""
    event = event_data if isinstance(event_data, dict) else {}
    snapshot = event.get("snapshot")
    if isinstance(snapshot, dict) and snapshot:
        return _timestamp(snapshot.get("frame_time"))
    payload = event.get("data")
    return _timestamp(payload.get("snapshot_frame_time")) if isinstance(payload, dict) else None


async def prefer_recording_snapshot(
    event_id: str,
    event_data: dict[str, Any] | None,
    snapshot: bytes | None,
    provenance: ClassificationInputProvenance,
    *,
    client: Any | None = None,
) -> tuple[bytes | None, ClassificationInputProvenance]:
    """Try one bounded frame read; keep the original on every unavailable/unsafe path."""
    result = await read_recording_snapshot(event_id, event_data, snapshot, provenance, client=client)
    return result.snapshot, result.provenance


async def read_recording_snapshot(
    event_id: str,
    event_data: dict[str, Any] | None,
    snapshot: bytes | None,
    provenance: ClassificationInputProvenance,
    *,
    client: Any | None = None,
    ready_by: float | None = None,
    now: Callable[[], float] | None = None,
    sleep: Callable[[float], Awaitable[Any]] | None = None,
) -> RecordingRead:
    """Read the recording frame, waiting until `ready_by` (epoch seconds) for one not yet written.

    Without a deadline a missing or slow recording is read once, as backfill and reclassification of
    past events need. Every other reason to keep the detection snapshot is final at once.
    """
    clock = now or time.time
    pause = sleep or asyncio.sleep
    while True:
        result = await _read_recording_snapshot_once(event_id, event_data, snapshot, provenance, client=client)
        if result.reason not in RETRYABLE_REASONS or ready_by is None:
            break
        remaining = ready_by - clock()
        if remaining <= 0:
            break
        await pause(min(RECORDING_READY_RETRY_SECONDS, remaining))
    if result.reason not in {"recording_frame", "not_requested"}:
        # Info, not debug: an owner who chose the recording frame needs to see why it was not used.
        log.info(
            "Recording frame not used; identifying from the detection snapshot",
            event_id=event_id,
            reason=result.reason,
        )
    return result


async def _read_recording_snapshot_once(
    event_id: str,
    event_data: dict[str, Any] | None,
    snapshot: bytes | None,
    provenance: ClassificationInputProvenance,
    *,
    client: Any | None = None,
) -> tuple[bytes | None, ClassificationInputProvenance]:
    """Try one bounded frame read; keep the original on every unavailable/unsafe path.

    A clean Frigate copy establishes the native detection coordinate space.
    Retained owner-selected photos are handled before this function by callers.
    """
    if settings.frigate.classification_image_source != "recording_snapshot" or not snapshot or provenance.is_cropped:
        return RecordingRead(snapshot, provenance, "not_requested")
    if provenance.input_source not in {"frigate_snapshot", "frigate_snapshot_uncropped"}:
        return RecordingRead(snapshot, provenance, "not_requested")
    event = event_data if isinstance(event_data, dict) else {}
    camera = event.get("camera")
    if not isinstance(camera, str) or not camera.strip():
        return RecordingRead(snapshot, provenance, "no_camera")
    from app.services.frigate_client import frigate_client

    selected_client = client if client is not None else frigate_client
    # A failed full-frame verification must not feed native coordinates to a
    # saved JPEG whose crop/resize policy is unknown, even if it is still usable.
    unaligned = ClassificationInputProvenance("frigate_snapshot_unaligned", False)
    detection_size: tuple[int, int] | None = None

    async def fallback(reason: str) -> RecordingRead:
        # Once the clean copy has fixed the full frame's shape, a detection snapshot of the same
        # shape is that full frame, so Frigate's box still locates the bird in it. Losing it would
        # identify a small bird from the whole scene, as every backfill past recording retention did.
        if detection_size is not None and await asyncio.to_thread(_same_shape, snapshot, detection_size):
            return RecordingRead(snapshot, provenance, reason)
        return RecordingRead(snapshot, unaligned, reason)

    try:
        # Saved event JPEGs can ignore crop/height query parameters after an
        # event ends. Only a clean copy establishes the native pixel space.
        # The deadline includes both reads, processing and connection-pool waits.
        async with asyncio.timeout(RECORDING_SNAPSHOT_TIMEOUT_SECONDS):
            clean, error = await selected_client.get_alignment_snapshot_with_error(
                event_id, timeout=RECORDING_SNAPSHOT_TIMEOUT_SECONDS
            )
            if not clean:
                log.debug("Clean snapshot unavailable; keeping detection snapshot", event_id=event_id, reason=error)
                return RecordingRead(snapshot, unaligned, "clean_snapshot_unavailable")
            detection_size = await asyncio.to_thread(_image_size, clean)
            alignment = _snapshot_alignment(event, detection_size)
            if alignment is None:
                return await fallback("snapshot_time_unknown")
            frame_time, box = alignment
            recording, error = await selected_client.get_recording_snapshot_with_error(
                camera, frame_time, timeout=RECORDING_SNAPSHOT_TIMEOUT_SECONDS
            )
            if not recording:
                log.debug("Recording snapshot unavailable; keeping detection snapshot", event_id=event_id, reason=error)
                # Frigate answers 404 until the stretch of recording holding the moment is written.
                reason = "recording_not_ready" if error == "recording_snapshot_http_404" else "recording_unavailable"
                return await fallback(reason)
            recording, recording_size = await asyncio.to_thread(_prepare_recording_snapshot, recording)
        dw, dh = detection_size
        rw, rh = recording_size
        # Equal size is accepted: a sub stream scaled up to the detect size is a blurrier copy of the
        # same view, and the recording frame is the native picture.
        if rw < dw or rh < dh:
            return await fallback("recording_smaller")
        if not math.isclose(rw / rh, dw / dh, rel_tol=0.01):
            return await fallback("recording_different_shape")
        detected_box = restore_frigate_hint_box(box, detection_size)
        crop_box = frigate_snapshot_crop_box(detected_box, detection_size) if detected_box else None
        crop_region = normalize_frigate_hint_box(crop_box, detection_size) if crop_box else None
        return RecordingRead(
            recording,
            ClassificationInputProvenance(
                "frigate_recording_snapshot",
                False,
                frame_time,
                box,
                crop_region,
                await asyncio.to_thread(lambda: hashlib.sha256(recording).hexdigest()),
            ),
            "recording_frame",
        )
    except TimeoutError:
        # Seen live when several birds arrive together and Frigate decodes several 4K frames at once.
        log.debug("Recording snapshot read ran past its bound", event_id=event_id)
        return await fallback("recording_slow")
    except Exception as exc:
        log.debug(
            "Recording snapshot unavailable; keeping detection snapshot", event_id=event_id, error=type(exc).__name__
        )
        return await fallback("recording_unavailable")
