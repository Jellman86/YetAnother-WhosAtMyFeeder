"""Select a higher-resolution recording frame aligned with Frigate's best snapshot."""

from __future__ import annotations

import asyncio
import math
import hashlib
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


async def prefer_recording_snapshot(
    event_id: str,
    event_data: dict[str, Any] | None,
    snapshot: bytes | None,
    provenance: ClassificationInputProvenance,
    *,
    client: Any | None = None,
) -> tuple[bytes | None, ClassificationInputProvenance]:
    """Try one bounded frame read; keep the original on every unavailable/unsafe path.

    Cropped or unknown inputs cannot establish the detection coordinate space.
    Retained owner-selected photos are handled before this function by callers.
    """
    if settings.frigate.classification_image_source != "recording_snapshot" or not snapshot or provenance.is_cropped:
        return snapshot, provenance
    if provenance.input_source not in {"frigate_snapshot", "frigate_snapshot_uncropped"}:
        return snapshot, provenance
    event = event_data if isinstance(event_data, dict) else {}
    camera = event.get("camera")
    if not isinstance(camera, str) or not camera.strip():
        return snapshot, provenance
    from app.services.frigate_client import frigate_client

    selected_client = client if client is not None else frigate_client
    try:
        detection_size = await asyncio.to_thread(_image_size, snapshot)
        alignment = _snapshot_alignment(event, detection_size)
        if alignment is None:
            return snapshot, provenance
        frame_time, box = alignment
        # Include connection-pool waits in the deadline. Never wait for Frigate
        # to persist a live recording segment before admitting the event.
        async with asyncio.timeout(RECORDING_SNAPSHOT_TIMEOUT_SECONDS):
            recording, error = await selected_client.get_recording_snapshot_with_error(
                camera, frame_time, timeout=RECORDING_SNAPSHOT_TIMEOUT_SECONDS
            )
            if not recording:
                log.debug("Recording snapshot unavailable; keeping detection snapshot", event_id=event_id, reason=error)
                return snapshot, provenance
            recording, recording_size = await asyncio.to_thread(_prepare_recording_snapshot, recording)
        dw, dh = detection_size
        rw, rh = recording_size
        if rw <= dw or rh <= dh or not math.isclose(rw / rh, dw / dh, rel_tol=0.01):
            return snapshot, provenance
        detected_box = restore_frigate_hint_box(box, detection_size)
        crop_box = frigate_snapshot_crop_box(detected_box, detection_size) if detected_box else None
        crop_region = normalize_frigate_hint_box(crop_box, detection_size) if crop_box else None
        return recording, ClassificationInputProvenance(
            "frigate_recording_snapshot",
            False,
            frame_time,
            box,
            crop_region,
            await asyncio.to_thread(lambda: hashlib.sha256(recording).hexdigest()),
        )
    except Exception as exc:
        log.debug(
            "Recording snapshot unavailable; keeping detection snapshot", event_id=event_id, error=type(exc).__name__
        )
        return snapshot, provenance
