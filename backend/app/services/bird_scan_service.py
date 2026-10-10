"""Bounded, durable additional-bird scans of an explicitly retained whole scene."""

import asyncio
from dataclasses import replace
import hashlib
from collections.abc import Callable
from typing import Any

import structlog

from app.config import settings
from app.database import get_db
from app.repositories.bird_observation_repository import BirdObservationRepository
from app.repositories.bird_scan_repository import BirdScanJob, BirdScanNotFoundError, BirdScanRepository
from app.repositories.detection_repository import DetectionRepository
from app.services.bird_crop_service import bird_crop_service
from app.services.bird_observation_selection import BirdObservationSelection, select_bird_observations
from app.services.high_quality_snapshot_service import high_quality_snapshot_service
from app.services.media_cache import media_cache
from app.services.photo_choice_actions import photo_choice_lock
from app.utils.image_io import decode_image_bytes


log = structlog.get_logger()
MAX_PENDING_SCANS = 100
SCAN_TIMEOUT_SECONDS = 180


def _utc_iso(value: str | None) -> str | None:
    """SQLite CURRENT_TIMESTAMP is UTC without a zone; say so, or a browser reads it as local time."""
    if not value:
        return None
    return value.replace(" ", "T") + ("" if value.endswith("Z") or "+" in value else "Z")


class BirdScanUnavailable(ValueError):
    """A public reason code; never include provider exceptions or private paths."""


async def _native_call(function: Callable, *args: Any, **kwargs: Any) -> Any:
    """A cancelled await cannot release pixels still owned by a native thread."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task, return_exceptions=True)
        raise


def _full_scene(candidate: dict[str, Any]) -> bool:
    return bool(
        candidate.get("source_mode") == "full_frame"
        and candidate.get("crop_box") is None
        and candidate.get("snapshot_source") != "hq_candidate_frigate_snapshot_fallback"
        and candidate.get("image_ref")
        and not candidate.get("photo_hidden")
        and isinstance(candidate.get("clip_variant"), str)
        and type(candidate.get("frame_index")) is int
    )


class BirdScanService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._wake = asyncio.Event()
        self._admission = asyncio.Lock()
        # What the running scan is doing, keyed by event and claim revision, so a status read can
        # say "naming 2 of 5" instead of only "running". In memory: it describes live work only.
        self._progress: dict[str, tuple[int, dict[str, Any]]] = {}

    def _report(self, job: BirdScanJob, stage: str, *, done: int | None = None, total: int | None = None) -> None:
        self._progress[job.event_id] = (job.revision, {"stage": stage, "stage_done": done, "stage_total": total})

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        async with get_db() as db:
            await BirdScanRepository(db).recover_running()
        self._wake = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="additional-bird-scans")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _run(self) -> None:
        while True:
            try:
                self._wake.clear()
                if await self.run_next():
                    continue
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=5)
                except TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Additional bird scan queue unavailable")
                await asyncio.sleep(5)

    async def _candidate(self, event_id: str, candidate_id: str) -> dict[str, Any] | None:
        async with get_db() as db:
            repository = DetectionRepository(db)
            if await repository.get_by_frigate_event(event_id) is None:
                raise BirdScanNotFoundError("Detection not found")
            candidates = await repository.list_snapshot_candidates(event_id)
        return next((item for item in candidates if item["candidate_id"] == candidate_id), None)

    async def _availability(self, event_id: str, candidate: dict[str, Any] | None) -> tuple[str | None, str | None]:
        if candidate is None or not _full_scene(candidate):
            return "full_scene_unavailable", None
        version = await media_cache.get_cached_image_version(candidate["image_ref"])
        if version is None:
            return "full_scene_unavailable", None
        if not await asyncio.to_thread(high_quality_snapshot_service._bird_crop_model_available):
            return "crop_model_unavailable", version
        async with get_db() as db:
            birds = await BirdObservationRepository(db).list_for_event(event_id)
        if any(
            (bird["manual_species"] or bird["is_hidden"])
            and (bird["clip_variant"], bird["frame_index"]) != (candidate["clip_variant"], candidate["frame_index"])
            for bird in birds
        ):
            return "reviewed_other_frame", version
        return None, version

    async def get_status(
        self, event_id: str, candidate_id: str, *, expected_media_version: str | None = None
    ) -> dict[str, Any]:
        candidate = await self._candidate(event_id, candidate_id)
        reason, version = await self._availability(event_id, candidate)
        async with get_db() as db:
            job = await BirdScanRepository(db).get(event_id)
        matches = bool(
            job
            and candidate
            and job.candidate_id == candidate_id
            and job.media_version == version
            and (job.image_ref, job.clip_variant, job.frame_index)
            == (candidate.get("image_ref"), candidate.get("clip_variant"), candidate.get("frame_index"))
        )
        if job and job.status in {"queued", "running"} and not matches:
            reason = "scan_in_progress"
        if expected_media_version is not None and version != expected_media_version:
            reason, matches = "media_changed", False
        progress: dict[str, Any] = {}
        if job and matches and job.status == "running":
            revision, live = self._progress.get(event_id, (None, {}))
            progress = {**(live if revision == job.revision else {}), "started_at": _utc_iso(job.started_at)}
        elif job and matches and job.status == "queued":
            async with get_db() as db:
                progress = {"queue_ahead": await BirdScanRepository(db).ahead_of(event_id)}
        return {
            **progress,
            "event_id": event_id,
            "candidate_id": candidate_id,
            "status": job.status if job and matches else "not_scanned",
            "available": reason is None,
            "unavailable_reason": reason,
            "error": job.error if job and matches else None,
            "result_count": job.result_count if job and matches else None,
            "retained_previous": job.retained_previous if job and matches else False,
            "updated_at": str(job.updated_at) if job and matches else None,
        }

    async def enqueue(
        self, event_id: str, candidate_id: str, *, force: bool = False, expected_media_version: str | None = None
    ) -> dict[str, Any]:
        async with self._admission:
            candidate = await self._candidate(event_id, candidate_id)
            reason, version = await self._availability(event_id, candidate)
            if reason or candidate is None:
                raise BirdScanUnavailable(reason or "full_scene_unavailable")
            if expected_media_version is not None and version != expected_media_version:
                raise BirdScanUnavailable("media_changed")
            content = await media_cache.get_snapshot(candidate["image_ref"])
            after = await media_cache.get_cached_image_version(candidate["image_ref"])
            if not content or after != version:
                raise BirdScanUnavailable("media_changed")
            digest = await asyncio.to_thread(lambda: hashlib.sha256(content).hexdigest())
            if candidate.get("content_sha256") and candidate["content_sha256"] != digest:
                raise BirdScanUnavailable("media_changed")
            async with get_db() as db:
                repository = BirdScanRepository(db)
                current = await repository.get(event_id)
                already_active = current is not None and current.status in {"queued", "running"}
                cached = (
                    current is not None
                    and current.status == "completed"
                    and not force
                    and (
                        current.candidate_id,
                        current.content_sha256,
                        current.media_version,
                        current.image_ref,
                        current.clip_variant,
                        current.frame_index,
                    )
                    == (
                        candidate_id,
                        digest,
                        version,
                        candidate["image_ref"],
                        candidate["clip_variant"],
                        candidate["frame_index"],
                    )
                )
                if not already_active and not cached and await repository.pending_count() >= MAX_PENDING_SCANS:
                    raise BirdScanUnavailable("queue_full")
                await repository.enqueue(
                    event_id,
                    candidate_id=candidate_id,
                    image_ref=candidate["image_ref"],
                    content_sha256=digest,
                    media_version=version,
                    clip_variant=candidate["clip_variant"],
                    frame_index=candidate["frame_index"],
                    force=force,
                )
            self._wake.set()
        return await self.get_status(event_id, candidate_id)

    async def run_next(self) -> bool:
        async with get_db() as db:
            job = await BirdScanRepository(db).claim_next()
        if job is None:
            return False
        try:
            async with asyncio.timeout(SCAN_TIMEOUT_SECONDS):
                self._report(job, "detecting")
                content = await self._read_job_scene(job)
                selection = await self._analyze_scene(job, content)
                self._report(job, "saving")
                async with photo_choice_lock(job.event_id):
                    await self._read_job_scene(job)
                    await self._persist(job, selection)
        except asyncio.CancelledError:
            # Persisted running work is requeued with a fresh revision at startup.
            raise
        except BirdScanNotFoundError:
            pass  # A deleted capture must never be resurrected by a late completion.
        except Exception as exc:
            error = str(exc) if isinstance(exc, BirdScanUnavailable) else "scan_failed"
            async with get_db() as db:
                await BirdScanRepository(db).fail(
                    job.event_id, job.revision, expected_generation=job.generation, error=error
                )
            log.warning("Additional bird scan failed", event_id=job.event_id, reason=error)
        finally:
            if self._progress.get(job.event_id, (None,))[0] == job.revision:
                self._progress.pop(job.event_id, None)
        return True

    async def _read_job_scene(self, job: BirdScanJob) -> bytes:
        candidate = await self._candidate(job.event_id, job.candidate_id)
        if (
            not candidate
            or not _full_scene(candidate)
            or (candidate["image_ref"], candidate["clip_variant"], candidate["frame_index"])
            != (job.image_ref, job.clip_variant, job.frame_index)
        ):
            raise BirdScanUnavailable("media_changed")
        content = await media_cache.get_snapshot(job.image_ref)
        version = await media_cache.get_cached_image_version(job.image_ref)
        digest = await asyncio.to_thread(lambda: hashlib.sha256(content).hexdigest()) if content else None
        if digest != job.content_sha256 or version != job.media_version:
            raise BirdScanUnavailable("media_changed")
        return content

    async def _persist(self, job: BirdScanJob, selection: BirdObservationSelection) -> None:
        async with get_db() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                observations = BirdObservationRepository(db)
                existing = await observations.list_for_event(job.event_id)
                changed = await BirdScanRepository(db).complete(
                    job.event_id,
                    job.revision,
                    expected_generation=job.generation,
                    result_count=len(selection.birds),
                    retained_previous=bool(existing and not selection.birds),
                    commit=False,
                )
                if not changed:
                    await db.rollback()
                    return
                if selection.birds and not await observations._replace_generated_locked(job.event_id, selection):
                    raise BirdScanUnavailable("reviewed_other_frame")
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    async def _analyze_scene(self, job: BirdScanJob, content: bytes) -> BirdObservationSelection:
        image = await _native_call(decode_image_bytes, content, convert_rgb=True)
        try:
            results = await _native_call(
                bird_crop_service.generate_classification_candidate_crops,
                image,
                max_crops=8 if settings.media_cache.bird_scan_mode == "intensive" else 3,
                raise_on_error=True,
            )
            full = {
                "candidate_id": job.candidate_id,
                "source_mode": "full_frame",
                "image_bytes": content,
                "clip_variant": job.clip_variant,
                "frame_index": job.frame_index,
                "frame_width": image.width,
                "frame_height": image.height,
                "input_is_cropped": False,
            }
            scored = [full]
            self._report(job, "naming", done=0, total=len(results))
            for index, result in enumerate(results):
                crop = result.get("crop_image")
                if crop is None:
                    continue
                candidate = {
                    **full,
                    "candidate_id": f"{job.candidate_id}__scan__{index}",
                    "source_mode": "model_crop",
                    "image_bytes": await _native_call(high_quality_snapshot_service._encode_pil_to_jpeg_bytes, crop),
                    "crop_box": result.get("box"),
                    "detector_box": result.get("detector_box"),
                    "crop_confidence": result.get("confidence"),
                    "crop_strategy": result.get("strategy"),
                    "observation_boxes": result.get("observation_boxes"),
                    "input_is_cropped": True,
                }
                enriched = await high_quality_snapshot_service._score_snapshot_candidate(candidate)
                if enriched is not None:
                    scored.append(enriched)
                self._report(job, "naming", done=index + 1, total=len(results))
            self._report(job, "counting")
            if len(scored) == 1:
                # No species crop is not evidence of an empty scene. Count lower-confidence
                # detector boxes too, using the same threshold as the automatic path.
                boxes = await _native_call(bird_crop_service.detect_observation_boxes, image, raise_on_error=True)
                observations = [
                    {
                        **full,
                        "candidate_id": f"{job.candidate_id}__observed__{index}",
                        "source_mode": "model_observation",
                        "crop_box": item["box"],
                        "crop_confidence": item["confidence"],
                        "classifier_score": 0.0,
                    }
                    for index, item in enumerate(boxes)
                ]
            else:
                observations = await high_quality_snapshot_service._detect_count_candidates(scored)
            rechecked = await high_quality_snapshot_service._recheck_weak_count_candidates(
                scored, observations=observations
            )
            selection = select_bird_observations(scored + observations + rechecked, selected_candidate=None)
            # Every persisted observation names its exact retained scene. Synthetic scored
            # crops are not added as photo choices and cannot change the owner's photograph.
            return replace(
                selection,
                birds=tuple(
                    replace(bird, candidate_id=f"{job.candidate_id}__observed__{index}")
                    for index, bird in enumerate(selection.birds)
                ),
            )
        finally:
            image.close()

    async def record_automatic(self, event_id: str, bundle: dict[str, Any]) -> None:
        """Publish automatic counts and their scene status together, behind manual work."""
        selection = bundle.get("bird_selection")
        if not bundle.get("additional_bird_scan_performed") or not isinstance(selection, BirdObservationSelection):
            return
        candidates = bundle.get("candidates") or []
        scene_id = selection.full_frame_candidate_id
        if scene_id is None:
            selected = bundle.get("selected_candidate") or {}
            frame = (
                (selection.clip_variant, selection.frame_index)
                if selection.birds
                else (selected.get("clip_variant"), selected.get("frame_index"))
            )
            full = [
                item
                for item in candidates
                if _full_scene(item) and (item.get("clip_variant"), item.get("frame_index")) == frame
            ]
            if len(full) == 1:
                scene_id = full[0]["candidate_id"]
        if scene_id is None:
            # Preserve the legacy one-frame observation policy when no unambiguous
            # retained scene exists; never call this a successful scan of another photo.
            await self._record_unretained_automatic(event_id, bundle, selection)
            return
        candidate = await self._candidate(event_id, scene_id)
        if not candidate or not _full_scene(candidate):
            await self._record_unretained_automatic(event_id, bundle, selection)
            return
        if selection.birds and (selection.clip_variant, selection.frame_index) != (
            candidate["clip_variant"],
            candidate["frame_index"],
        ):
            return
        analyzed = next(
            (item for item in bundle.get("automatic_scan_scenes", []) if item.get("candidate_id") == scene_id), None
        )
        if analyzed is None:
            await self._record_unretained_automatic(event_id, bundle, selection)
            return
        if (analyzed.get("clip_variant"), analyzed.get("frame_index")) != (
            candidate["clip_variant"],
            candidate["frame_index"],
        ):
            return
        analyzed_bytes = analyzed.get("image_bytes")
        analyzed_digest = (
            await asyncio.to_thread(lambda: hashlib.sha256(analyzed_bytes).hexdigest())
            if isinstance(analyzed_bytes, (bytes, bytearray))
            else analyzed.get("content_sha256")
        )
        # Candidate IDs describe a moment, not immutable pixels. Retention can keep
        # an older choice with the same ID, so prove the persisted pixels were scored.
        if not analyzed_digest:
            return
        content = await media_cache.get_snapshot(candidate["image_ref"])
        version = await media_cache.get_cached_image_version(candidate["image_ref"])
        if not content or not version:
            return
        digest = await asyncio.to_thread(lambda: hashlib.sha256(content).hexdigest())
        if digest != analyzed_digest or (candidate.get("content_sha256") and candidate["content_sha256"] != digest):
            return
        async with get_db() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                observations = BirdObservationRepository(db)
                existing = await observations.list_for_event(event_id)
                changed = await BirdScanRepository(db).record_automatic_completed(
                    event_id,
                    candidate_id=scene_id,
                    image_ref=candidate["image_ref"],
                    content_sha256=digest,
                    media_version=version,
                    clip_variant=candidate["clip_variant"],
                    frame_index=candidate["frame_index"],
                    expected_revision=bundle.get("automatic_scan_expected_revision"),
                    expected_generation=bundle.get("automatic_scan_expected_generation"),
                    result_count=len(selection.birds),
                    retained_previous=bool(existing and not selection.birds),
                    commit=False,
                )
                if not changed:
                    await db.rollback()
                    return
                if selection.birds and not await observations._replace_generated_locked(event_id, selection):
                    await db.rollback()
                    return
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    async def _record_unretained_automatic(
        self, event_id: str, bundle: dict[str, Any], selection: BirdObservationSelection
    ) -> None:
        # Legacy observations without retained pixels remain useful, but cannot
        # supersede a durable scan whose status names different evidence.
        if (
            bundle.get("automatic_scan_expected_revision") is not None
            or bundle.get("automatic_scan_expected_generation") is not None
        ):
            return
        async with get_db() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                if await BirdScanRepository(db).get(event_id) is None and selection.birds:
                    await BirdObservationRepository(db)._replace_generated_locked(event_id, selection)
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    async def schedule_retained_scene(self, event_id: str) -> None:
        """Video evidence also retains full scenes when the optional HQ pipeline is off."""
        if not settings.media_cache.automatic_multi_bird_scan or settings.media_cache.high_quality_event_snapshots:
            return
        try:
            async with get_db() as db:
                candidates = await DetectionRepository(db).list_snapshot_candidates(event_id)
            selected = next((item for item in candidates if item.get("selected")), None)
            if selected is None:
                return
            full = [
                item
                for item in candidates
                if _full_scene(item)
                and (item["clip_variant"], item["frame_index"]) == (selected["clip_variant"], selected["frame_index"])
            ]
            if len(full) == 1:
                await self.enqueue(event_id, full[0]["candidate_id"])
        except Exception:
            # Discovery is enrichment; admission cannot undo a saved target photograph.
            log.warning("Automatic additional-bird scan was not queued", event_id=event_id)


bird_scan_service = BirdScanService()
