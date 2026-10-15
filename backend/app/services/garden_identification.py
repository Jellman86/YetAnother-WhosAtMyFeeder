"""Explicit owner suggestions, with disposable inference subordinate to birds."""

import asyncio
from collections.abc import Callable
from contextlib import suppress
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import sqlite3
import sys
from typing import Any

import aiofiles
from fastapi import HTTPException
import httpx
import pycountry
import structlog

from app.config import settings
from app.database import get_db
from app.models.garden import (
    GardenIdentification,
    GardenIdentificationStatus,
    GardenIdentifyRequest,
    GardenModelStatus,
    GardenPhotoCheckRequest,
    GardenPhotoCheck,
    GardenPhotoMass,
)
from app.repositories.garden_catalog import GardenCatalog, taxon_identity
from app.repositories.garden_repository import GardenRepository
from app.services.classifier_service import garden_inference_pressure
from app.services.frigate_client import frigate_client
from app.services import garden_motion_privacy
from app.services.garden_capture_service import garden_capture_service
from app.services.garden_model_runtime import digest
from app.services.garden_visitors import GardenPolicy, Taxon, decide_prediction
from app.services.model_manager import MODELS_DIR
from app.utils.api_datetime import utc_naive_now
from app.utils.frigate_coordinates import normalized_frigate_video_hint
from app.utils.python_subprocess import python_subprocess_launch

log = structlog.get_logger()
MODEL_SIZES = {"4.0.3a": 223998782, "4.0.3b": 223999179}
MODEL_BASE_URL = "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models"


def normalize_country(value: str | None) -> str | None:
    name = " ".join((value or "").split())
    name = {"uk": "GBR", "great britain": "GBR"}.get(name.casefold(), name)
    if not name:
        return None
    try:
        return pycountry.countries.lookup(name).alpha_3
    except LookupError:
        return None


def bird_work_pending(status: dict | None) -> bool:
    if status is None:
        return True
    if any(
        status.get(priority, {}).get(key, 0) for priority in ("live", "background") for key in ("queued", "running")
    ):
        return True
    if status.get("native_work_pending"):
        return True
    if not all(isinstance(status.get(priority), dict) for priority in ("live", "background")):
        return True
    return any(
        pool.get("busy")
        or pool.get("circuit_open")
        or pool.get("last_exit_reason") == "native_runtime_quarantined"
        or (pool.get("last_runtime_recovery") or {}).get("status") in {"recovering", "failed"}
        for pool in status.get("worker_pools", {}).values()
        if isinstance(pool, dict)
    )


class GardenBusy(RuntimeError):
    pass


class GardenCleanupFailed(RuntimeError):
    pass


async def _stop_worker(process: Any) -> None:
    if process.returncode is None:
        with suppress(ProcessLookupError):
            process.terminate()
    try:
        await asyncio.wait_for(process.wait(), 2)
    except TimeoutError:
        with suppress(ProcessLookupError):
            process.kill()
        try:
            await asyncio.wait_for(process.wait(), 2)
        except TimeoutError as error:
            raise GardenCleanupFailed("Garden worker did not stop") from error


async def supervise_worker(
    process: Any,
    blocked: Callable[[], bool],
    *,
    payload: bytes | None = None,
    timeout_seconds: float = 120,
    poll_seconds: float = 0.1,
) -> bytes:
    completion = asyncio.create_task(process.communicate(payload) if payload is not None else process.communicate())
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            if blocked():
                raise GardenBusy("Bird inference needs the hardware. Try again when it is idle.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Garden identification exceeded its deadline")
            done, _ = await asyncio.wait({completion}, timeout=min(poll_seconds, remaining))
            if done:
                output, _ = completion.result()
                if process.returncode != 0 or len(output) > 65536:
                    raise ValueError("Requested garden runtime failed")
                return output
    finally:
        # Request cancellation cannot leave a native call using the device.
        cleanup = asyncio.create_task(_stop_worker(process))
        try:
            while not cleanup.done():
                with suppress(asyncio.CancelledError):
                    await asyncio.shield(cleanup)
            cleanup.result()
        finally:
            if not completion.done():
                completion.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await completion


class GardenIdentificationService:
    def __init__(self) -> None:
        self.catalog = GardenCatalog()
        self.models = Path(MODELS_DIR) / "garden"
        self.busy = False
        self.error: str | None = None
        self._photo_review_generation = 0

    async def initialize(self) -> None:
        try:
            await asyncio.to_thread(self.catalog.initialize)
        except (OSError, ValueError, sqlite3.Error) as error:
            # Optional garden data must not take bird readiness down with it.
            # status() reports catalogue availability and inference fails closed.
            log.warning("garden_catalogue_unavailable", error_type=type(error).__name__)

    def model_path(self, variant: str) -> Path:
        if variant not in MODEL_SIZES:
            raise ValueError("Unsupported garden model")
        return self.models / f"speciesnet-{variant}.onnx"

    async def status(self) -> GardenIdentificationStatus:
        ready = True
        try:
            await asyncio.to_thread(self.catalog.load)
        except (OSError, ValueError, sqlite3.Error):
            ready = False

        def installed(variant: str) -> bool:
            try:
                return self.model_path(variant).stat().st_size == MODEL_SIZES[variant]
            except OSError:
                return False

        models = await asyncio.to_thread(
            lambda: [
                GardenModelStatus(variant=v, installed=installed(v), size_bytes=size) for v, size in MODEL_SIZES.items()
            ]
        )
        return GardenIdentificationStatus(
            country=normalize_country(settings.location.country),
            catalogue_ready=ready,
            busy=self.busy,
            models=models,
            error=self.error,
        )

    async def install(self, variant: str) -> GardenIdentificationStatus:
        path = self.model_path(variant)
        if self.busy:
            raise HTTPException(409, "Another garden operation is running")
        self.busy = True
        staging: Path | None = None
        try:
            bundle = await asyncio.to_thread(self.catalog.load)
            expected = bundle["model_sha256"][variant]
            verified = await asyncio.to_thread(path.is_file) and await asyncio.to_thread(digest, path) == expected
            if not verified:
                await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
                descriptor, temporary = await asyncio.to_thread(tempfile.mkstemp, prefix=".garden-", dir=path.parent)
                os.close(descriptor)
                staging = Path(temporary)
                checksum = hashlib.sha256()
                size = 0
                async with asyncio.timeout(180), httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
                    async with client.stream("GET", f"{MODEL_BASE_URL}/speciesnet-{variant}.onnx") as response:
                        response.raise_for_status()
                        async with aiofiles.open(staging, "wb") as output:
                            async for chunk in response.aiter_bytes(1024 * 1024):
                                size += len(chunk)
                                if size > MODEL_SIZES[variant]:
                                    raise ValueError("Garden model exceeds its declared size")
                                checksum.update(chunk)
                                await output.write(chunk)
                if size != MODEL_SIZES[variant] or checksum.hexdigest() != expected:
                    raise ValueError("Garden model checksum mismatch")
                await asyncio.to_thread(os.replace, staging, path)
        except (OSError, ValueError, TimeoutError, sqlite3.Error, httpx.HTTPError) as error:
            log.warning("garden_model_install_failed", error_type=type(error).__name__)
            raise HTTPException(503, "Garden model could not be downloaded and verified. Try again.") from error
        finally:
            if staging is not None:
                await asyncio.to_thread(staging.unlink, missing_ok=True)
            self.busy = False
        return await self.status()

    async def review(self, capture_id: str, action: str) -> None:
        capture = await garden_capture_service.get(capture_id)
        image_hash = None
        if action == "accept":
            suggestion = capture.identification
            if capture.status != "confirmed" or capture.camera not in settings.frigate.garden_cameras or not suggestion:
                raise HTTPException(409, "Confirm animal presence on an enabled garden camera first")
            image = await garden_capture_service.snapshot(capture_id)
            image_hash = hashlib.sha256(image).hexdigest()
            if suggestion.image_sha256 != image_hash:
                raise HTTPException(
                    409, "The photo changed. Request a new suggestion before confirming identification."
                )
        async with get_db() as db:
            changed = await GardenRepository(db).review_identification(
                capture_id,
                "accepted" if action == "accept" else "dismissed",
                expected_image_sha256=image_hash,
                expected=capture.identification,
            )
        if not changed:
            raise HTTPException(409, "No reviewable identification. Refresh the capture first.")

    def invalidate_photo_checks(self) -> None:
        """An owner review invalidates in-flight advice, including review/restore cycles."""
        self._photo_review_generation += 1

    async def check_photo(self, capture_id: str, request: GardenPhotoCheckRequest) -> GardenPhotoCheck:
        if self.error:
            raise HTTPException(503, self.error)
        if self.busy:
            raise HTTPException(409, "Another garden operation is running")
        self.busy = True
        privacy_generation = garden_motion_privacy.generation
        review_generation = self._photo_review_generation
        try:
            return await self._check_photo(capture_id, request, privacy_generation, review_generation)
        except GardenBusy as error:
            raise HTTPException(409, str(error)) from error
        except GardenCleanupFailed as error:
            self.error = "Garden worker did not stop. Garden checks are unavailable until the application restarts."
            raise HTTPException(503, self.error) from error
        except (OSError, ValueError, RuntimeError, TypeError, KeyError, TimeoutError, sqlite3.Error) as error:
            log.warning("garden_photo_check_failed", error_type=type(error).__name__)
            raise HTTPException(
                503, "The photo check failed. Check the installed crop model and provider, then retry."
            ) from error
        finally:
            self.busy = False

    async def _check_photo(
        self,
        capture_id: str,
        request: GardenPhotoCheckRequest,
        privacy_generation: int,
        review_generation: int,
    ) -> GardenPhotoCheck:
        capture = await garden_capture_service.get(capture_id)
        source = capture.motion_source
        if (
            capture.status != "pending"
            or not capture.has_snapshot
            or source is None
            or capture.camera not in settings.frigate.garden_cameras
            or source.camera != capture.camera
        ):
            raise HTTPException(
                409, "Photo checks require an available pending motion photo on an enabled garden camera"
            )
        if source.image_sha256 != request.image_sha256:
            raise HTTPException(409, "The displayed photo changed. Refresh before checking it.")
        image = await garden_capture_service.snapshot(capture_id)
        if hashlib.sha256(image).hexdigest() != request.image_sha256:
            raise HTTPException(409, "The displayed photo changed. Refresh before checking it.")
        bundle = await asyncio.to_thread(self.catalog.load)
        path = self.model_path("4.0.3a")
        if not await asyncio.to_thread(path.is_file):
            raise HTTPException(409, "Download the tracked-crop garden model first")

        def blocked() -> bool:
            return (
                garden_motion_privacy.generation != privacy_generation
                or self._photo_review_generation != review_generation
                or capture.camera not in settings.frigate.garden_cameras
                or bird_work_pending(garden_inference_pressure())
            )

        payload = {
            "mode": "preview",
            "variant": "4.0.3a",
            "model": str(path),
            "model_sha256": bundle["model_sha256"]["4.0.3a"],
            "package_sha256": bundle["package_sha256"],
            "provider": request.provider,
            "box": list(source.box_xywh),
        }
        native = await self._run_photo_worker(image, payload, blocked)
        if native.get("package_sha256") != bundle["package_sha256"]:
            raise ValueError("Photo check package differs from the requested catalogue")
        preview = native["preview"]
        mass = GardenPhotoMass.model_validate(preview["mass"])
        suggestion = preview["suggestion"]
        if suggestion not in {"bird", "mammal", "uncertain", "human_rejected"}:
            raise ValueError("Invalid photo check suggestion")
        if type(preview.get("human_winner")) is not bool:
            raise ValueError("Photo check omitted its human-winner decision")
        human_evidence = (
            preview["human_winner"] or mass.human >= GardenPolicy().human_threshold or suggestion == "human_rejected"
        )
        if not human_evidence and suggestion in {"bird", "mammal"} and getattr(mass, suggestion) < 0.8:
            raise ValueError("Photo check suggestion conflicts with complete probability mass")
        devices = native["devices"]
        expected = {
            "cpu": "CPUExecutionProvider",
            "cuda": "CUDAExecutionProvider",
            "intel_cpu": "CPU",
            "intel_gpu": "GPU",
            "intel_npu": "NPU",
        }[request.provider]
        if (
            not isinstance(devices, list)
            or not devices
            or len(devices) > 8
            or any(not isinstance(device, str) for device in devices)
            or devices[0].split(".")[0] != expected
            or (request.provider.startswith("intel_") and any(device.split(".")[0] != expected for device in devices))
        ):
            raise ValueError("Photo check did not execute the requested provider")
        frame_size = native["frame_size"]
        if (
            not isinstance(frame_size, (list, tuple))
            or len(frame_size) != 2
            or any(type(x) is not int or x <= 0 for x in frame_size)
        ):
            raise ValueError("Invalid photo check frame size")
        async with garden_motion_privacy.lock:
            current = await garden_capture_service.get(capture_id)
            current_image = await garden_capture_service.snapshot(capture_id)
            current_bundle = await asyncio.to_thread(self.catalog.load)
            if (
                blocked()
                or current.status != "pending"
                or not current.has_snapshot
                or current.camera != capture.camera
                or current.motion_source != source
                or hashlib.sha256(current_image).hexdigest() != request.image_sha256
                or current_bundle["package_sha256"] != bundle["package_sha256"]
                or current_bundle["model_sha256"]["4.0.3a"] != payload["model_sha256"]
            ):
                raise HTTPException(409, "The capture changed during the photo check. Refresh before trying again.")
            return GardenPhotoCheck(
                capture_id=capture_id,
                image_sha256=request.image_sha256,
                suggestion="unavailable" if human_evidence else suggestion,
                mass=None if human_evidence else mass,
                provider=request.provider,
                devices=devices,
                model_sha256=payload["model_sha256"],
                package_sha256=bundle["package_sha256"],
                box_xywh=source.box_xywh,
                frame_size=frame_size,
            )

    @staticmethod
    async def _run_photo_worker(image: bytes, payload: dict, blocked: Callable[[], bool]) -> dict:
        if len(image) > 16 * 1024 * 1024:
            raise ValueError("Garden snapshot exceeds the byte limit")
        if blocked():
            raise GardenBusy("The photo context changed or bird inference needs the hardware. Try again when idle.")
        temporary = await asyncio.to_thread(tempfile.mkdtemp, prefix="yawamf-garden-")
        try:
            image_path = Path(temporary) / "snapshot.jpg"
            async with aiofiles.open(image_path, "wb") as output:
                await output.write(image)
            payload = {**payload, "image": str(image_path)}
            if blocked():
                raise GardenBusy("The photo context changed or bird inference needs the hardware. Try again when idle.")
            environment = {**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}
            executable, environment = python_subprocess_launch(environment)
            process = await asyncio.create_subprocess_exec(
                executable,
                "-m",
                "app.services.garden_worker",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=environment,
            )
            output = await supervise_worker(process, blocked, payload=json.dumps(payload).encode() + b"\n")
        finally:
            import shutil

            pending_error = sys.exc_info()[1]
            cleanup = asyncio.create_task(asyncio.to_thread(shutil.rmtree, temporary))
            interrupted = False
            try:
                while not cleanup.done():
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        interrupted = True
                cleanup.result()
            except OSError:
                if pending_error is None and not interrupted:
                    raise
                # An unreaped native worker must remain quarantined even if
                # deleting its private temporary image also fails.
                log.warning("garden_photo_temporary_cleanup_failed")
            if interrupted and pending_error is None:
                raise asyncio.CancelledError
        lines = [line[len(b"GARDEN_RESULT:") :] for line in output.splitlines() if line.startswith(b"GARDEN_RESULT:")]
        if len(lines) != 1:
            raise ValueError("Garden worker returned no valid result")
        native = json.loads(lines[0])
        if not isinstance(native, dict):
            raise ValueError("Invalid garden worker result")
        return native

    async def identify(self, capture_id: str, request: GardenIdentifyRequest) -> None:
        if self.error:
            raise HTTPException(503, self.error)
        if self.busy:
            raise HTTPException(409, "Another garden operation is running")
        self.busy = True
        try:
            await self._identify(capture_id, request)
        except GardenBusy as error:
            raise HTTPException(409, str(error)) from error
        except GardenCleanupFailed as error:
            self.error = (
                "Garden worker did not stop. Garden identification is unavailable until the application restarts."
            )
            raise HTTPException(503, self.error) from error
        except (OSError, ValueError, RuntimeError, TypeError, KeyError, TimeoutError, sqlite3.Error) as error:
            log.warning("garden_identification_failed", error_type=type(error).__name__)
            raise HTTPException(
                503, "Garden identification failed on the selected provider. Check the model and provider, then retry."
            ) from error
        finally:
            self.busy = False

    async def _identify(self, capture_id: str, request: GardenIdentifyRequest) -> None:
        capture = await garden_capture_service.get(capture_id)
        if capture.camera not in settings.frigate.garden_cameras or capture.status != "confirmed":
            raise HTTPException(409, "Enable this garden camera and confirm animal presence first")
        if capture.identification and capture.identification.review == "accepted":
            raise HTTPException(409, "Dismiss the confirmed identification before requesting another suggestion")
        country = normalize_country(settings.location.country)
        if country is None:
            raise HTTPException(409, "Set a recognised country or ISO country code in Settings → Location first")
        bundle = await asyncio.to_thread(self.catalog.load)
        path = self.model_path(request.variant)
        if not await asyncio.to_thread(path.is_file):
            raise HTTPException(409, "Download the selected garden model first")

        def blocked() -> bool:
            return bird_work_pending(garden_inference_pressure())

        if blocked():
            raise GardenBusy("Bird inference needs the hardware. Try again when it is idle.")
        event_label = capture.label
        if capture.motion_source:
            box = capture.motion_source.box_xywh if request.variant == "4.0.3a" else None
        else:
            event = await frigate_client.get_event(capture.frigate_event)
            if not event or event.get("camera") != capture.camera:
                raise HTTPException(404, "Frigate no longer has this capture")
            if event.get("false_positive") or event.get("label") in {"person", "human"}:
                async with get_db() as db:
                    await GardenRepository(db).block_capture(capture.id)
                raise HTTPException(404, "Garden capture no longer available")
            event_label = str(event.get("label", "")).lower()
            if event_label not in settings.frigate.garden_labels:
                raise HTTPException(409, "Frigate's current label is not an enabled garden animal")
            # REST data.box describes Frigate's representative snapshot in normalized XYWH.
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            box = normalized_frigate_video_hint(data.get("box")) if request.variant == "4.0.3a" else None
        if request.variant == "4.0.3a" and (box is None or box[0] + box[2] > 1 or box[1] + box[3] > 1):
            raise HTTPException(409, "A tracked snapshot crop is unavailable. Choose the whole-image model.")
        image = await garden_capture_service.snapshot(capture_id)
        payload = {
            "model": str(path),
            "model_sha256": bundle["model_sha256"][request.variant],
            "variant": request.variant,
            "provider": request.provider,
            "box": box,
        }
        native = await self._run_photo_worker(image, payload, blocked)
        outputs = [Taxon(v["id"], v["name"], tuple(v["ranks"])) for v in bundle["outputs"]]
        predictions = native["predictions"]
        if (
            len(predictions) != 5
            or len({i for i, _ in predictions}) != 5
            or any(type(i) is not int or not 0 <= i < len(outputs) for i, _ in predictions)
        ):
            raise ValueError("Invalid garden worker output indices")
        decision = decide_prediction(
            [(outputs[i], score) for i, score in predictions],
            GardenPolicy(),
            country=country,
            taxonomy=[Taxon(v["id"], v["name"], tuple(v["ranks"])) for v in bundle["taxonomy"]],
            geofence=bundle["geofence"],
        )
        if decision.reason == "human_rejected":
            async with get_db() as db:
                await GardenRepository(db).block_capture(capture.id)
            raise HTTPException(404, "Garden capture no longer available")
        taxon = decision.taxon
        binding = bundle["bindings"].get(taxon.id) if taxon else None
        identity = taxon_identity({"name": taxon.name, "ranks": taxon.ranks}) if taxon else None
        result = GardenIdentification(
            outcome="suggestion" if taxon and binding else "unknown",
            reason=decision.reason if not taxon or binding else "unresolved_identity",
            taxon_id=taxon.id if taxon else None,
            species_id=binding,
            name=taxon.name if taxon else None,
            rank=identity[1] if identity else None,
            score=decision.score if taxon else predictions[0][1],
            geofenced=decision.geofenced,
            country=country,
            variant=request.variant,
            provider=request.provider,
            devices=native["devices"],
            model_sha256=payload["model_sha256"],
            package_sha256=bundle["package_sha256"],
            image_sha256=hashlib.sha256(image).hexdigest(),
            output_index=predictions[0][0],
            input_kind="tracked_crop" if box else "whole_image",
            box_xywh=box,
            frame_size=native["frame_size"],
            identified_at=utc_naive_now().isoformat() + "Z",
        )
        if (
            normalize_country(settings.location.country) != country
            or capture.camera not in settings.frigate.garden_cameras
            or (not capture.motion_source and event_label not in settings.frigate.garden_labels)
        ):
            raise HTTPException(409, "Garden camera or location changed. Request a new suggestion.")
        async with get_db() as db:
            saved = await GardenRepository(db).save_identification(capture, result)
        if not saved:
            raise HTTPException(409, "The capture changed during identification. Refresh before trying again.")


garden_identification_service = GardenIdentificationService()
