"""Collect terminal Frigate animal events for explicit owner review only.

No classifier, bird repository, notification or external submission is used.
Snapshots remain with Frigate and are fetched only when an owner opens them.
"""

from datetime import datetime, timezone
import hashlib
import math

from fastapi import HTTPException

from app.config import settings
from app.database import get_db
from app.repositories.garden_repository import GardenCapture, GardenRepository
from app.services.frigate_client import frigate_client
from app.services.garden_capture_policy import safe_event_id, observation_time


class GardenCaptureService:
    def __init__(self) -> None:
        self.has_history = False

    async def initialize(self) -> None:
        async with get_db() as db:
            self.has_history = await GardenRepository(db).has_history()

    async def process(self, data: object) -> None:
        if not isinstance(data, dict):
            return
        after = data.get("after")
        if not isinstance(after, dict):
            return
        event_id = safe_event_id(after.get("id"))
        camera = after.get("camera")
        if not event_id:
            return
        camera = camera if isinstance(camera, str) else ""
        label = str(after.get("label") or "").strip().lower()
        bird = label in {value.lower() for value in settings.frigate.ingest_labels}
        rejected = bool(after.get("false_positive")) or label in {"person", "human"}
        if not settings.frigate.garden_cameras and not (rejected and self.has_history):
            return
        if rejected or (bird and camera in settings.frigate.garden_cameras):
            if rejected:
                from app.services import garden_motion_privacy

                # Invalid timestamps fail closed for existing media on this camera.
                start, end = after.get("start_time"), after.get("end_time")
                start = float(start) if type(start) in (int, float) and math.isfinite(start) else 0.0
                end = (
                    float(end)
                    if type(end) in (int, float) and math.isfinite(end)
                    else datetime.now(timezone.utc).timestamp()
                )
                async with garden_motion_privacy.lock:
                    garden_motion_privacy.invalidate()
                    async with get_db() as db:
                        await GardenRepository(db).block_motion_overlap(camera, start, max(start, end))
            async with get_db() as db:
                await GardenRepository(db).block(
                    event_id, create=rejected and camera in settings.frigate.garden_cameras
                )
            return
        if camera not in settings.frigate.garden_cameras:
            return
        if label not in settings.frigate.garden_labels:
            if self.has_history:
                async with get_db() as db:
                    await GardenRepository(db).block(event_id, create=False)
            return
        if str(data.get("type", "")).lower() != "end":
            return
        retention_days = settings.maintenance.retention_days if settings.maintenance.cleanup_enabled else 0
        observed_at = observation_time(after.get("start_time"), datetime.now(timezone.utc), retention_days)
        if observed_at is None:
            return
        self.has_history = True
        async with get_db() as db:
            await GardenRepository(db).capture(event_id, camera, label, observed_at, bool(after.get("has_snapshot")))

    async def get(self, capture_id: str) -> GardenCapture:
        async with get_db() as db:
            capture = await GardenRepository(db).get(capture_id)
        if capture is None:
            raise HTTPException(404, "Garden capture not found")
        return capture

    async def snapshot(self, capture_id: str) -> bytes:
        capture = await self.get(capture_id)
        if capture.motion_source:
            async with get_db() as db:
                image = await GardenRepository(db).motion_photo(capture_id)
            await self.get(capture_id)
            if not image:
                raise HTTPException(404, "This motion photo has expired")
            if hashlib.sha256(image).hexdigest() != capture.motion_source.image_sha256:
                raise HTTPException(409, "The motion photo differs from its recorded evidence")
            return image
        if not capture.has_snapshot or not safe_event_id(capture.frigate_event):
            raise HTTPException(404, "This capture has no snapshot")
        image = await frigate_client.get_snapshot(capture.frigate_event, crop=False)
        # A person/false-positive update may arrive while Frigate is responding.
        await self.get(capture_id)
        if not image:
            raise HTTPException(404, "Frigate no longer has this snapshot")
        return image


garden_capture_service = GardenCaptureService()
