"""Bounded SpeciesNet checks for new Garden captures, subordinate to birds."""

import asyncio
from contextlib import suppress
from datetime import timedelta
import hashlib
import sqlite3
import time

from fastapi import HTTPException
import httpx
import structlog

from app.models.inference_execution import InferenceExecution
from app.config import settings
from app.database import get_db
from app.models.garden import (
    GardenAutomaticCheck,
    GardenDomesticRoute,
    GardenIdentification,
    GardenPresenceMass,
)
from app.repositories.garden_repository import GardenCapture, GardenRepository
from app.services import garden_motion_privacy
from app.services.broadcaster import broadcaster
from app.services.garden_notifications import garden_notification_service
from app.services.classifier_service import garden_inference_pressure
from app.services.frigate_client import frigate_client
from app.services.garden_capture_policy import garden_collection_cameras
from app.services.garden_capture_service import garden_capture_service
from app.services.garden_crop_service import garden_crop_service, build_saved_crop
from app.services.garden_media_cache import garden_media_cache
from app.services.garden_identification import (
    GardenBusy,
    GardenCleanupFailed,
    bird_work_pending,
    garden_identification_service,
    identification_from_predictions,
    normalize_country,
    worker_failure_fields,
)
from app.services.garden_motion import garden_motion_service
from app.services.garden_automatic_policy import (
    NamingResult,
    automatic_check_dismisses,
    finish_automatic_check,
    plan_automatic_check,
)
from app.services.garden_automatic_runtime import GardenAutomaticRuntime, candidate_providers
from app.services.garden_domestic_birds import camera_watches_birds, domestic_bird_for_speciesnet, garden_bird_route
from app.services.garden_visitors import GardenPolicy, presence_outcome
from app.utils.api_datetime import utc_naive_now
from app.utils.frigate_coordinates import normalized_frigate_video_hint

log = structlog.get_logger()


def top_output_id(predictions: object, outputs: list[dict]) -> str | None:
    """The SpeciesNet output id of the top result, or None when the worker gave no usable ranking."""
    if not isinstance(predictions, list) or not predictions:
        return None
    first = predictions[0]
    if not isinstance(first, list) or len(first) != 2 or type(first[0]) is not int:
        return None
    return outputs[first[0]]["id"] if 0 <= first[0] < len(outputs) else None


def naming_result(suggestion: GardenIdentification | None) -> NamingResult:
    if suggestion is None:
        return "person"
    if suggestion.automatic:
        return "named"
    return {"low_confidence": "low_confidence", "bird_excluded": "bird"}.get(suggestion.reason, "unresolved")


class GardenAutomaticReviewService:
    def __init__(self) -> None:
        self.task: asyncio.Task | None = None
        self.runtime = GardenAutomaticRuntime()

    async def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self._run(), name="garden_automatic_review")

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
            self.task = None

    async def _run(self) -> None:
        while True:
            try:
                await self.process_once()
                await garden_crop_service.collect_one()
                # Keeps newly confirmed media and backfills older captures, one per cycle;
                # the sweep removes files that a dismissal or revocation elsewhere released.
                await garden_media_cache.collect_one()
                await garden_media_cache.sweep()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                log.warning("garden_automatic_cycle_failed", error_type=type(error).__name__)
                garden_identification_service.automatic_message = (
                    "Automatic check unavailable. Photos stay in Needs review."
                )
            await asyncio.sleep(10)

    async def _input_box(self, capture: GardenCapture) -> tuple[float, float, float, float] | None:
        if capture.motion_source:
            return capture.motion_source.box_xywh
        event = await frigate_client.get_event(capture.frigate_event)
        if not event or event.get("camera") != capture.camera:
            raise HTTPException(404, "Capture metadata unavailable")
        label = str(event.get("label", "")).lower()
        if event.get("false_positive") or label in {"person", "human"}:
            async with get_db() as db:
                await GardenRepository(db).block_capture(capture.id)
            await broadcaster.broadcast({"type": "garden_history_changed"})
            raise GardenBusy("Capture revoked by Frigate")
        if label not in settings.frigate.garden_labels or label in settings.frigate.ingest_labels:
            raise HTTPException(409, "Capture label no longer enabled")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        box = normalized_frigate_video_hint(data.get("box"))
        if box and box[0] + box[2] <= 1 and box[1] + box[3] <= 1:
            return box
        return None

    async def process_once(self) -> None:
        service = garden_identification_service
        cameras = garden_collection_cameras()
        if not cameras or service.busy or service.error or bird_work_pending(garden_inference_pressure()):
            return
        retry_before = (utc_naive_now() - timedelta(minutes=5)).isoformat()
        async with get_db() as db:
            original = await GardenRepository(db).next_automatic_check(
                cameras,
                retry_before,
                policy_version=1 if settings.frigate.garden_automatic_naming else None,
                country=normalize_country(settings.location.country)
                if settings.frigate.garden_automatic_naming
                else None,
            )
        if original is None:
            service.automatic_message = (
                "No automatic check is due. Unavailable checks remain in Needs review until their retry."
            )
            return
        clear = await garden_motion_service._camera_clear(original.camera)
        if not clear or service.busy or bird_work_pending(garden_inference_pressure()):
            return
        service.busy = True
        generation = garden_motion_privacy.generation
        review_generation = service._photo_review_generation
        guard_time = time.monotonic()
        watcher: asyncio.Task | None = None
        changed = False
        named_saved = False
        named: GardenIdentification | None = None

        def blocked() -> bool:
            return (
                original.camera not in garden_collection_cameras()
                or generation != garden_motion_privacy.generation
                or review_generation != service._photo_review_generation
                or bird_work_pending(garden_inference_pressure())
                or not clear
                or time.monotonic() - guard_time > 2
            )

        async def watch() -> None:
            nonlocal clear, guard_time
            while True:
                clear = await garden_motion_service._camera_clear(original.camera)
                guard_time = time.monotonic()
                if not clear:
                    return
                await asyncio.sleep(0.5)

        try:
            watcher = asyncio.create_task(watch())
            service.automatic_message = (
                "Checking a Garden candidate with SpeciesNet. New devices are compared with CPU first; "
                "bird inference takes priority."
            )
            box = await self._input_box(original)
            if box is None:
                raise HTTPException(409, "A tracked snapshot crop is unavailable")
            variant = "4.0.3a"
            if blocked():
                raise GardenBusy("Automatic check paused for birds or camera pressure")
            await service.ensure_model(variant)
            bundle = await asyncio.to_thread(service.catalog.load)
            image = await garden_capture_service.snapshot(original.id)
            image_sha = hashlib.sha256(image).hexdigest()
            payload = {
                "mode": "automatic",
                "variant": variant,
                "provider": "cpu",
                "model": str(service.model_path(variant)),
                "model_sha256": bundle["model_sha256"][variant],
                "package_sha256": bundle["package_sha256"],
                "box": list(box) if box else None,
            }
            requested_provider = candidate_providers()[0]
            automatic_naming = settings.frigate.garden_automatic_naming
            naming_threshold = settings.frigate.garden_naming_threshold
            country = normalize_country(settings.location.country)
            declared = frozenset(settings.frigate.garden_domestic_birds)
            watches_birds = camera_watches_birds(original.camera, settings.frigate.camera)
            native, provider = await self.runtime.run(image, payload, blocked, service._run_photo_worker)
            mass = GardenPresenceMass.model_validate(native["assessment"]["mass"])
            human_winner = native["assessment"]["human_winner"]
            if type(human_winner) is not bool:
                raise ValueError("Automatic check did not meet its runtime contract")
            if native.get("package_sha256") != bundle["package_sha256"]:
                raise ValueError("Automatic check mapping changed")
            presence = presence_outcome(mass.model_dump(), human_winner)
            domestic = domestic_bird_for_speciesnet(top_output_id(native.get("predictions"), bundle.get("outputs", [])))
            bird_route = garden_bird_route(domestic, declared, camera_watches_birds=watches_birds)
            plan = plan_automatic_check(
                presence, bird_route, automatic_naming=automatic_naming, country_known=country is not None
            )
            outcome, decision_reason = plan.outcome, plan.decision_reason
            named: GardenIdentification | None = None
            route: GardenDomesticRoute | None = None
            naming_score: float | None = None
            if plan.run_naming and country:
                # The species threshold is authoritative even below the coarse animal-presence floor.
                suggestion = identification_from_predictions(
                    native.get("predictions"),
                    bundle,
                    policy=GardenPolicy(min_confidence=naming_threshold, domestic_birds=declared),
                    country=country,
                    variant=variant,
                    provider=provider,
                    devices=native["devices"],
                    model_sha256=payload["model_sha256"],
                    image_sha256=image_sha,
                    box=box,
                    frame_size=tuple(native["frame_size"]),
                    review="accepted",
                    automatic=True,
                )
                outcome, decision_reason = finish_automatic_check(plan, naming_result(suggestion), bird_route)
                if suggestion is not None and suggestion.automatic:
                    named = suggestion
                    kept = domestic_bird_for_speciesnet(suggestion.taxon_id)
                    if kept in declared and suggestion.name:
                        route = GardenDomesticRoute(
                            domestic_bird=kept,
                            origin="garden_check",
                            source_label=suggestion.name,
                            source_score=suggestion.score,
                            source_model="garden-speciesnet-" + variant,
                            routed_at=utc_naive_now().isoformat() + "Z",
                        )
                naming_score = suggestion.score if suggestion else None
            if (automatic_naming, naming_threshold, country, declared, watches_birds) != (
                settings.frigate.garden_automatic_naming,
                settings.frigate.garden_naming_threshold,
                normalize_country(settings.location.country),
                frozenset(settings.frigate.garden_domestic_birds),
                camera_watches_birds(original.camera, settings.frigate.camera),
            ):
                raise GardenBusy("Automatic naming settings changed during inference")
            if await self._input_box(original) != box:
                raise GardenBusy("The detector crop changed during the check")
            current_image = await garden_capture_service.snapshot(original.id)
            current_bundle = await asyncio.to_thread(service.catalog.load)
            if hashlib.sha256(current_image).hexdigest() != image_sha or bundle != current_bundle:
                raise GardenBusy("Automatic check evidence changed")
            saved_crop = None
            if named is not None and original.motion_source:
                try:
                    saved_crop = await asyncio.to_thread(
                        build_saved_crop,
                        image,
                        box=box,
                        expected_sha256=image_sha,
                        source_start=original.motion_source.clip_start,
                        source_end=original.motion_source.clip_end,
                    )
                except (OSError, ValueError) as error:
                    log.info("garden_crop_encoding_unavailable", reason=type(error).__name__)
            async with garden_motion_privacy.lock:
                current = await garden_capture_service.get(original.id)
                if blocked() or current != original:
                    raise GardenBusy("Automatic check context changed")
                async with get_db() as db:
                    repo = GardenRepository(db)
                    if outcome == "human_rejected":
                        await repo.block_capture(original.id)
                        changed = True
                        service.automatic_message = (
                            "A Garden capture was removed because the check found person evidence."
                        )
                    else:
                        result = GardenAutomaticCheck(
                            outcome=outcome,
                            checked_at=utc_naive_now().isoformat(),
                            policy_version=1 if automatic_naming else 0,
                            decision_reason=decision_reason,
                            domestic_candidate=domestic if domestic and domestic not in declared else None,
                            naming_score=naming_score,
                            naming_threshold=naming_threshold,
                            execution=InferenceExecution(
                                model_id="garden-speciesnet-" + variant,
                                provider=provider,
                                requested_provider=requested_provider,
                                devices=native["devices"],
                                checked_at=utc_naive_now().isoformat() + "Z",
                                fallback_reason="accelerator_unavailable"
                                if provider == "cpu" and requested_provider != "cpu"
                                else None,
                            ),
                            image_sha256=image_sha,
                            variant=variant,
                            model_sha256=payload["model_sha256"],
                            package_sha256=bundle["package_sha256"],
                            mass=mass,
                            box_xywh=box,
                            devices=native["devices"],
                        )
                        if named is not None:
                            changed = await repo.save_automatic_naming(
                                original,
                                result,
                                named,
                                route=route,
                                **({"crop": saved_crop} if saved_crop else {}),
                            )
                            named_saved = changed
                            service.automatic_message = (
                                "Automatic check named an animal; it is in Confirmed animals, where you can correct it."
                            )
                        else:
                            changed = await repo.save_automatic_check(original, result)
                            service.automatic_message = (
                                "Automatic check excluded this capture; it is in Dismissed and can be restored."
                                if automatic_check_dismisses(outcome, decision_reason)
                                else "Automatic check finished. The capture remains in Needs review."
                            )
            if provider == "cpu" and candidate_providers()[0] != "cpu":
                service.automatic_message += (
                    " CPU fallback was used; the preferred accelerator has not passed its current Garden check."
                )
        except GardenBusy:
            service.automatic_message = "Automatic check paused. It will resume when birds and cameras are idle."
        except GardenCleanupFailed:
            service.error = "Garden worker did not stop. Restart the application before running more Garden work."
        except (
            OSError,
            ValueError,
            RuntimeError,
            TypeError,
            KeyError,
            TimeoutError,
            sqlite3.Error,
            HTTPException,
            httpx.HTTPError,
        ) as error:
            log.warning(
                "garden_automatic_check_failed", error_type=type(error).__name__, **worker_failure_fields(error)
            )
            service.automatic_message = (
                "Automatic check unavailable. The photo stays in Needs review; retry after five minutes."
            )
            if not blocked():
                async with garden_motion_privacy.lock:
                    if not blocked():
                        async with get_db() as db:
                            changed = await GardenRepository(db).save_automatic_check(
                                original,
                                GardenAutomaticCheck(
                                    outcome="unavailable",
                                    checked_at=utc_naive_now().isoformat(),
                                ),
                            )
        finally:
            if watcher is not None:
                watcher.cancel()
                with suppress(asyncio.CancelledError):
                    await watcher
            service.busy = False
        if changed:
            await broadcaster.broadcast({"type": "garden_history_changed"})
            if named_saved:
                await garden_notification_service.schedule(original.id)


garden_automatic_review_service = GardenAutomaticReviewService()
