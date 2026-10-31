"""Saved animal crops never replace full-frame model input or its privacy rules."""

import hashlib
import asyncio
from contextlib import suppress
from io import BytesIO
import math
import sqlite3

from PIL import Image
from fastapi import HTTPException
import httpx
import structlog

from app.models.garden_crop import CROP_BYTES_LIMIT, GardenCropEvidence

log = structlog.get_logger()


def build_saved_crop(
    image: bytes,
    *,
    box: tuple[float, float, float, float],
    expected_sha256: str,
    source_start: float,
    source_end: float,
    source_kind: str = "motion",
    frame_time: float | None = None,
) -> tuple[GardenCropEvidence, bytes]:
    """Decode and encode only in a worker thread; strip all source metadata."""
    if not image or len(image) > 16 * 1024 * 1024 or hashlib.sha256(image).hexdigest() != expected_sha256:
        raise ValueError("Animal crop source differs from its evidence or exceeds its limit")
    if len(box) != 4 or not all(math.isfinite(value) for value in box):
        raise ValueError("Invalid animal crop geometry")
    x, y, width, height = box
    if min(x, y) < 0 or min(width, height) <= 0 or x + width > 1 or y + height > 1:
        raise ValueError("Animal crop must be inside its source photo")
    with Image.open(BytesIO(image)) as source:
        frame_size = source.size
        if min(frame_size) <= 0 or frame_size[0] * frame_size[1] > 16_000_000:
            raise ValueError("Animal crop source exceeds the pixel limit")
        bounds = (
            math.floor(x * source.width + 1e-9),
            math.floor(y * source.height + 1e-9),
            math.ceil((x + width) * source.width - 1e-9),
            math.ceil((y + height) * source.height - 1e-9),
        )
        cropped = source.crop(bounds).convert("RGB")
    cropped.thumbnail((512, 512), Image.Resampling.LANCZOS)
    output = BytesIO()
    cropped.save(output, format="JPEG", quality=85)
    if output.tell() > CROP_BYTES_LIMIT:
        cropped.thumbnail((384, 384), Image.Resampling.LANCZOS)
        output = BytesIO()
        cropped.save(output, format="JPEG", quality=70)
    result = output.getvalue()
    if len(result) > CROP_BYTES_LIMIT:
        raise ValueError("Animal crop exceeds its byte limit")
    evidence = GardenCropEvidence(
        source_kind=source_kind,
        source_sha256=expected_sha256,
        crop_sha256=hashlib.sha256(result).hexdigest(),
        frame_size=frame_size,
        image_size=cropped.size,
        box_xywh=box,
        source_start=source_start,
        source_end=source_end,
        frame_time=frame_time,
    )
    return evidence, result


class GardenCropService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def collect_one(self) -> None:
        from app.database import get_db
        from app.services.garden_capture_policy import garden_collection_cameras
        from app.repositories.garden_repository import GardenRepository
        from app.services.classifier_service import garden_inference_pressure
        from app.services.garden_identification import bird_work_pending, garden_identification_service

        if self._lock.locked() or garden_identification_service.busy or bird_work_pending(garden_inference_pressure()):
            return
        async with get_db() as db:
            capture = await GardenRepository(db).next_crop(garden_collection_cameras())
        if capture is not None:
            await self.collect(capture.id)

    async def collect(self, capture_id: str) -> None:
        from app.database import get_db
        from app.repositories.garden_repository import GardenRepository
        from app.services import garden_motion_privacy
        from app.services.garden_capture_service import garden_capture_service
        from app.services.garden_capture_policy import garden_collection_cameras
        from app.services.frigate_client import frigate_client
        from app.services.broadcaster import broadcaster

        if self._lock.locked():
            return
        async with self._lock:
            generation = garden_motion_privacy.generation
            original = None
            try:
                async with asyncio.timeout(15):
                    original = await garden_capture_service.get(capture_id)
                    if (
                        original.status != "confirmed"
                        or original.crop
                        or original.camera not in garden_collection_cameras()
                    ):
                        return
                    if original.motion_source:
                        source = original.motion_source
                        image = await garden_capture_service.snapshot(capture_id)
                        box = source.box_xywh
                        expected = source.image_sha256
                        start, end, frame_time = source.clip_start, source.clip_end, None
                        source_kind = "motion"
                    else:
                        # Saved snapshot JPEGs may ignore crop=False. Only the clean
                        # best frame establishes the pixel space of the tracked box.
                        from app.services.recording_snapshot_input import _snapshot_alignment

                        event = await frigate_client.get_event(original.frigate_event)
                        if not event or event.get("camera") != original.camera:
                            raise ValueError("Garden crop event unavailable")
                        if event.get("false_positive") or str(event.get("label", "")).lower() in {"person", "human"}:
                            async with garden_motion_privacy.lock:
                                garden_motion_privacy.invalidate()
                                async with get_db() as db:
                                    await GardenRepository(db).block_capture(capture_id)
                            await broadcaster.broadcast({"type": "garden_history_changed"})
                            return
                        from app.config import settings

                        label = str(event.get("label", "")).lower()
                        # A domestic bird recorded from a bird event keeps Frigate's bird label.
                        if label not in settings.frigate.garden_labels and not (
                            original.domestic_route and label in settings.frigate.ingest_labels
                        ):
                            raise ValueError("Garden crop label is no longer enabled")
                        image, _ = await frigate_client.get_alignment_snapshot_with_error(
                            original.frigate_event, timeout=5
                        )
                        if not image:
                            raise ValueError("Garden clean snapshot unavailable")

                        def shape() -> tuple[int, int]:
                            with Image.open(BytesIO(image)) as photo:
                                return photo.size

                        alignment = _snapshot_alignment(event, await asyncio.to_thread(shape))
                        if alignment is None:
                            raise ValueError("Garden crop alignment unavailable")
                        frame_time, box = alignment
                        start, end = float(event["start_time"]), float(event["end_time"])
                        expected = hashlib.sha256(image).hexdigest()
                        source_kind = "frigate_clean"
                    evidence, cropped = await asyncio.to_thread(
                        build_saved_crop,
                        image,
                        box=box,
                        expected_sha256=expected,
                        source_start=start,
                        source_end=end,
                        source_kind=source_kind,
                        frame_time=frame_time,
                    )
                async with garden_motion_privacy.lock:
                    if (
                        generation != garden_motion_privacy.generation
                        or original.camera not in garden_collection_cameras()
                    ):
                        return
                    async with get_db() as db:
                        changed = await GardenRepository(db).save_crop(original, evidence, cropped)
                if changed:
                    await broadcaster.broadcast({"type": "garden_history_changed"})
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                TimeoutError,
                HTTPException,
                Image.DecompressionBombError,
                httpx.HTTPError,
                sqlite3.Error,
            ) as error:
                log.info("garden_crop_unavailable", capture_id=capture_id, reason=type(error).__name__)
                # Preview failure must never undo the presence/name decision.
                with suppress(sqlite3.Error):
                    async with garden_motion_privacy.lock:
                        if generation == garden_motion_privacy.generation and original is not None:
                            async with get_db() as db:
                                repo = GardenRepository(db)
                                if await repo.get(capture_id) == original:
                                    await repo.crop_unavailable(capture_id)


garden_crop_service = GardenCropService()
