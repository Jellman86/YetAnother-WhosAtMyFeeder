"""Opt-in, low-rate motion proposals; birds and explicit owner review take priority."""

import asyncio
from collections.abc import Callable
from contextlib import suppress
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from typing import Any

import aiofiles
from fastapi import HTTPException
import httpx
import structlog

from app.config import settings
from app.database import get_db
from app.models.garden_motion import (
    GardenMotionStatus,
    MotionSource,
    MOTION_PADDING_SECONDS,
    MOTION_INTERVAL_SECONDS,
    MOTION_CATCHUP_SECONDS,
)
from app.repositories.garden_detector_catalog import GardenDetectorCatalog
from app.repositories.garden_repository import GardenRepository
from app.services import garden_motion_privacy
from app.services.classifier_service import garden_inference_pressure
from app.services.frigate_client import frigate_client, FrigateEventsFetchError
from app.services.garden_capture_service import garden_capture_service
from app.services.garden_identification import (
    GardenBusy,
    GardenCleanupFailed,
    bird_work_pending,
    garden_identification_service,
    supervise_worker,
    MODEL_BASE_URL,
)
from app.services.garden_model_runtime import digest
from app.services.garden_motion_policy import recording_queue, camera_pressure, motion_scan_interval
from app.services.model_manager import MODELS_DIR
from app.utils.api_datetime import utc_naive_now
from app.utils.python_subprocess import python_subprocess_launch

log = structlog.get_logger()


class GardenMotionService:
    def __init__(self) -> None:
        self.catalog = GardenDetectorCatalog()
        self.path = Path(MODELS_DIR) / "garden" / "md1000-cedar.onnx"
        self.task: asyncio.Task | None = None
        self.scanning = False
        self.last_scan_at: str | None = None
        self.last_outcome: str | None = None
        self.message = "Enable a garden camera and download the motion detector to start."
        self.next_scan = 0.0
        self.interval_seconds = MOTION_INTERVAL_SECONDS
        self.camera_index = 0
        self.queued_windows = 0
        self.queue_camera: str | None = None
        self.queue_checked_at: str | None = None

    def cameras(self) -> list[str]:
        return [
            camera for camera in settings.frigate.garden_motion_cameras if camera in settings.frigate.garden_cameras
        ]

    async def status(self) -> GardenMotionStatus:
        ready, installed = False, False
        try:
            bundle = await asyncio.to_thread(self.catalog.load)
            ready = True
            installed = await asyncio.to_thread(
                lambda: self.path.is_file() and self.path.stat().st_size == bundle["model_bytes"]
            )
        except (OSError, ValueError, sqlite3.Error):
            pass
        cameras = self.cameras()
        state = (
            "unavailable"
            if garden_identification_service.error or not ready
            else "disabled"
            if not cameras
            else "scanning"
            if self.scanning
            else "waiting"
        )
        message = garden_identification_service.error or self.message
        if garden_identification_service.error:
            message = garden_identification_service.error
        elif not ready:
            message = "Garden detector data is unavailable. Check startup diagnostics and restart after restoring the catalogue."
        elif not cameras:
            message = "Motion collection is off. Enable it for a garden camera to collect review photos."
        elif not installed:
            message = "Download the Cedar motion detector to start collecting review photos."
        return GardenMotionStatus(
            cameras=cameras,
            installed=installed,
            catalogue_ready=ready,
            busy=garden_identification_service.busy,
            state=state,
            message=message,
            animal_confidence=settings.frigate.garden_motion_confidence,
            last_scan_at=self.last_scan_at,
            last_outcome=self.last_outcome,
            interval_seconds=self.interval_seconds if self.queue_camera in cameras else MOTION_INTERVAL_SECONDS,
            queued_windows=self.queued_windows if self.queue_camera in cameras else 0,
            queue_camera=self.queue_camera if self.queue_camera in cameras else None,
            queue_checked_at=self.queue_checked_at if self.queue_camera in cameras else None,
        )

    async def install(self) -> GardenMotionStatus:
        if garden_identification_service.error:
            raise HTTPException(503, garden_identification_service.error)
        if garden_identification_service.busy:
            raise HTTPException(409, "Another garden operation is running")
        garden_identification_service.busy = True
        temporary: str | None = None
        try:
            bundle = await asyncio.to_thread(self.catalog.load)
            verified = (
                await asyncio.to_thread(self.path.is_file)
                and await asyncio.to_thread(digest, self.path) == bundle["model_sha256"]
            )
            if not verified:
                await asyncio.to_thread(self.path.parent.mkdir, parents=True, exist_ok=True)
                descriptor, temporary = await asyncio.to_thread(
                    tempfile.mkstemp, dir=self.path.parent, prefix=".motion-"
                )
                os.close(descriptor)
                checksum, size = hashlib.sha256(), 0
                async with asyncio.timeout(180), httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                    async with client.stream("GET", f"{MODEL_BASE_URL}/md1000-cedar.onnx") as response:
                        response.raise_for_status()
                        async with aiofiles.open(temporary, "wb") as output:
                            async for chunk in response.aiter_bytes(1024 * 1024):
                                size += len(chunk)
                                if size > bundle["model_bytes"]:
                                    raise ValueError("Motion detector exceeds its declared size")
                                checksum.update(chunk)
                                await output.write(chunk)
                if size != bundle["model_bytes"] or checksum.hexdigest() != bundle["model_sha256"]:
                    raise ValueError("Motion detector checksum mismatch")
                await asyncio.to_thread(os.replace, temporary, self.path)
        except (OSError, ValueError, sqlite3.Error, TimeoutError, httpx.HTTPError) as error:
            log.warning("garden_motion_install_failed", error_type=type(error).__name__)
            raise HTTPException(503, "Motion detector could not be downloaded and verified. Try again.") from error
        finally:
            if temporary:
                await asyncio.to_thread(Path(temporary).unlink, missing_ok=True)
            garden_identification_service.busy = False
        return await self.status()

    async def start(self) -> None:
        if self.task is not None:
            return
        try:
            await asyncio.to_thread(self.catalog.initialize)
        except (OSError, ValueError, sqlite3.Error) as error:
            log.warning("garden_motion_catalogue_unavailable", error_type=type(error).__name__)
        self.task = asyncio.create_task(self._run(), name="garden_motion_collector")

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None

    async def _run(self) -> None:
        while True:
            cycle_started = time.monotonic()
            try:
                async with get_db() as db:
                    await GardenRepository(db).expire_motion_photos()
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.warning("garden_motion_cycle_failed", error_type=type(error).__name__)
                self.message = "Motion collection could not finish. It will retry automatically."
                self.interval_seconds = MOTION_INTERVAL_SECONDS
            next_cycle = max(cycle_started + self.interval_seconds, self.next_scan)
            await asyncio.sleep(max(1.0, next_cycle - time.monotonic()))

    async def _person_overlap(self, camera: str, start: float, end: float) -> bool:
        start -= MOTION_PADDING_SECONDS
        end += MOTION_PADDING_SECONDS
        for label in ("person", "human"):
            # No lower time bound: a long-running person can start before this clip.
            events = await frigate_client.list_events(
                camera=camera, label=label, before=end, has_snapshot=False, limit=100
            )
            if len(events) >= 100:
                return True
            for event in events:
                event_start, event_end = event.get("start_time"), event.get("end_time")
                if type(event_start) not in (float, int) or not math.isfinite(event_start):
                    return True
                if event_end is None:
                    return True
                if type(event_end) not in (float, int) or not math.isfinite(event_end):
                    return True
                if event_start <= end and event_end >= start:
                    return True
        return False

    async def _camera_clear(self, camera: str) -> bool:
        try:
            response = await frigate_client.get("api/stats", timeout=1)
            response.raise_for_status()
            return not camera_pressure(response.json(), camera)
        except (ValueError, httpx.HTTPError):
            return False

    async def _native(self, payload: dict[str, Any], blocked: Callable[[], bool]) -> dict[str, Any]:
        environment = {**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
        executable, environment = python_subprocess_launch(environment)
        process = await asyncio.create_subprocess_exec(
            executable,
            "-m",
            "app.services.garden_motion_worker",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=environment,
        )
        output = await supervise_worker(
            process, blocked, payload=json.dumps(payload).encode() + b"\n", timeout_seconds=45
        )
        if len(output) > 64 * 1024:
            raise ValueError("Motion worker result exceeds its limit")
        lines = [line[len(b"MOTION_RESULT:") :] for line in output.splitlines() if line.startswith(b"MOTION_RESULT:")]
        if len(lines) != 1:
            raise ValueError("Motion worker returned no unique result")
        result = json.loads(lines[0])
        if not isinstance(result, dict) or result.get("outcome") not in {
            "candidate",
            "person_rejected",
            "no_candidate",
            "still_rejected",
        }:
            raise ValueError("Motion worker returned an invalid outcome")
        if result["outcome"] == "candidate" and result.get("devices") != ["CPUExecutionProvider"]:
            raise ValueError("Motion worker did not use its requested CPU provider")
        return result

    async def scan_once(self) -> None:
        cameras = self.cameras()
        if not cameras or garden_identification_service.busy or garden_identification_service.error:
            self.interval_seconds = MOTION_INTERVAL_SECONDS
            return
        if time.monotonic() < self.next_scan:
            return
        if bird_work_pending(garden_inference_pressure()):
            self.interval_seconds = MOTION_INTERVAL_SECONDS
            self.message = "Waiting for bird inference to become idle."
            return
        scan_started = time.monotonic()
        garden_identification_service.busy = True
        self.scanning = True
        self.last_outcome = None
        temporary: str | None = None
        watcher: asyncio.Task | None = None
        camera = cameras[self.camera_index % len(cameras)]
        self.camera_index += 1
        guard_time, clear = time.monotonic(), False
        generation = garden_motion_privacy.generation
        animal_confidence = settings.frigate.garden_motion_confidence

        def blocked() -> bool:
            return (
                bird_work_pending(garden_inference_pressure())
                or camera not in self.cameras()
                or not clear
                or time.monotonic() - guard_time > 2
                or generation != garden_motion_privacy.generation
                or animal_confidence != settings.frigate.garden_motion_confidence
            )

        async def watch() -> None:
            nonlocal guard_time, clear
            while True:
                clear = await self._camera_clear(camera)
                guard_time = time.monotonic()
                if not clear:
                    return
                await asyncio.sleep(0.5)

        try:
            async with get_db() as db:
                if await GardenRepository(db).motion_storage_full():
                    self.message = "Motion photo storage is full. Dismiss a capture or wait for photos to expire."
                    self.last_outcome = "storage_full"
                    return
            bundle = await asyncio.to_thread(self.catalog.load)
            if not await asyncio.to_thread(self.path.is_file):
                self.message = "Download the motion detector first."
                return
            clear = await self._camera_clear(camera)
            guard_time = time.monotonic()
            if blocked():
                raise GardenBusy("Waiting for Frigate cameras and bird inference to become idle.")
            now = time.time()
            async with get_db() as db:
                cursor = await GardenRepository(db).motion_cursor(camera)
            response = await frigate_client.get(
                f"api/{camera}/recordings",
                params={"after": max(cursor or 0, now - MOTION_CATCHUP_SECONDS), "before": now - 20},
                timeout=5,
            )
            response.raise_for_status()
            windows = recording_queue(response.json(), after=cursor or now - MOTION_CATCHUP_SECONDS, now=now)
            self.queued_windows = len(windows)
            self.queue_camera = camera
            self.queue_checked_at = utc_naive_now().isoformat() + "Z"
            if not windows:
                self.message = "No recent completed motion recordings to scan."
                self.last_outcome = "no_recording"
                return
            start, end = windows[0]
            self.last_scan_at = utc_naive_now().isoformat() + "Z"
            if await self._person_overlap(camera, start, end):
                self.last_outcome = "person_rejected"
                self.message = (
                    "A person was detected or could not be ruled out in this recording. No photo was retained."
                )
                async with get_db() as db:
                    await GardenRepository(db).advance_motion_cursor(camera, end)
                self.queued_windows -= 1
                self.queue_checked_at = utc_naive_now().isoformat() + "Z"
                return
            temporary = await asyncio.to_thread(tempfile.mkdtemp, prefix="yawamf-motion-")
            clip, photo = Path(temporary) / "clip.mp4", Path(temporary) / "photo.jpg"
            watcher = asyncio.create_task(watch())
            await frigate_client.download_motion_recording(camera, start, end, clip)
            if blocked():
                raise GardenBusy("Motion scan paused for birds or camera pressure.")
            payload = dict(
                model=str(self.path),
                clip=str(clip),
                photo=str(photo),
                duration=end - start,
                clip_sha256=await asyncio.to_thread(digest, clip),
                model_sha256=bundle["model_sha256"],
                names=bundle["names"],
                animal_confidence=animal_confidence,
            )
            result = await self._native(payload, blocked)
            if blocked():
                raise GardenBusy("Motion scan paused for birds or camera pressure.")
            if await self._person_overlap(camera, start, end):
                result = {"outcome": "person_rejected"}
            async with garden_motion_privacy.lock:
                if blocked():
                    raise GardenBusy("Motion source changed during the scan.")
                async with get_db() as db:
                    repo = GardenRepository(db)
                    if result["outcome"] == "candidate":
                        source = MotionSource(
                            camera=camera,
                            clip_start=start,
                            clip_end=end,
                            clip_sha256=payload["clip_sha256"],
                            detector_sha256=bundle["model_sha256"],
                            animal_confidence=animal_confidence,
                            **{
                                key: result[key]
                                for key in (
                                    "frame_index",
                                    "frame_offset",
                                    "detector_score",
                                    "box_xywh",
                                    "image_sha256",
                                    "detector_input_sha256",
                                    "sampled_frame_sha256",
                                )
                            },
                        )
                        async with aiofiles.open(photo, "rb") as image:
                            data = await image.read(512 * 1024 + 1)
                        saved = await repo.capture_motion(source, data)
                        garden_capture_service.has_history = True
                        if saved is None:
                            self.message = "Review storage is full or this recording was already collected."
                            self.last_outcome = "not_stored"
                            return
                    else:
                        await repo.advance_motion_cursor(camera, end)
            self.queued_windows -= 1
            self.queue_checked_at = utc_naive_now().isoformat() + "Z"
            self.last_outcome = result["outcome"]
            if result["outcome"] == "candidate":
                self.message = "Review photo collected. Confirm animal presence before requesting a species suggestion."
            elif result["outcome"] == "still_rejected":
                self.message = "Recording scanned; the detected shape did not move, so no review photo was retained."
            else:
                self.message = "Recording scanned; no review photo retained."
        except GardenBusy as error:
            self.message = str(error)
            self.last_outcome = "paused"
        except GardenCleanupFailed:
            garden_identification_service.error = (
                "Garden worker did not stop. Restart the application before collecting more garden photos."
            )
        except (
            OSError,
            ValueError,
            RuntimeError,
            KeyError,
            TypeError,
            sqlite3.Error,
            TimeoutError,
            httpx.HTTPError,
            FrigateEventsFetchError,
        ) as error:
            log.warning("garden_motion_scan_failed", error_type=type(error).__name__)
            self.message = (
                "Motion scan failed. Check Frigate recordings and the detector download; it will retry automatically."
            )
            self.last_outcome = "failed"
        finally:
            if watcher is not None:
                watcher.cancel()
                with suppress(asyncio.CancelledError):
                    await watcher
            if temporary:
                await asyncio.to_thread(shutil.rmtree, temporary)
            self.scanning = False
            garden_identification_service.busy = False
            finished = time.monotonic()
            self.interval_seconds = motion_scan_interval(self.last_outcome, self.queued_windows)
            self.next_scan = (
                finished + 30 if self.last_outcome == "failed" else max(scan_started + self.interval_seconds, finished)
            )


garden_motion_service = GardenMotionService()
