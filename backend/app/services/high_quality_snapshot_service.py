"""Asynchronous replacement of event snapshots using frames extracted from Frigate clips."""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import sys
import tempfile
import hashlib
import time
from io import BytesIO
from collections import Counter, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np
import structlog
from PIL import Image

from app.config import settings
from app.services.bird_crop_service import bird_crop_service
from app.services.frigate_client import frigate_client
from app.services.hq_classification_refinement import (
    HQ_REFINEMENT_MIN_TEMPORAL_SEPARATION_SECONDS,
    choose_hq_classification_refinement,
    crop_labels_with_independent_support,
)
from app.services.media_cache import media_cache
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.utils.canonical_species import should_hide_species_label
from app.utils.classifier_labels import normalize_classifier_label
from app.utils.tasks import create_background_task
from app.utils.image_io import decode_image_bytes

log = structlog.get_logger()


def _write_temp_clip(contents: bytes) -> Path:
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(contents)
        return Path(tmp.name)


HQ_HINT_CROP_EXPAND_RATIO = 0.36
HQ_MODEL_CROP_EXTRA_EXPAND_RATIO = 0.18
HQ_MAX_CROP_SCORING_FRAMES = 3
HQ_MAX_PERSISTED_CANDIDATES = 8
HQ_RECONCILE_LOOKBACK_HOURS = 6
HQ_RECONCILE_LIMIT = 100
HQ_RECONCILE_INTERVAL_SECONDS = 300
HQ_CANDIDATE_INFERENCE_QUEUE_TIMEOUT_SECONDS = 30.0
HQ_MIN_CROP_EDGE_PIXELS = 160
HQ_MIN_CROP_AREA_PIXELS = 25_000
HQ_MODEL_CROP_MIN_CLASSIFIER_ADVANTAGE = 0.02
HQ_CLIP_REPLACEMENT_MIN_CLASSIFIER_ADVANTAGE = 0.02
HQ_PATH_HINT_MAX_DISTANCE_SECONDS = 0.75
HQ_PROCESSING_PIPELINE = "high_quality_snapshot"
# Four total attempts over roughly one hour. Event media is normally ready in
# seconds; continued absence after this bounded window is terminal unless an
# owner explicitly regenerates it with newly available media.
HQ_RETRY_DELAYS_SECONDS = (300.0, 900.0, 2700.0)

DEFAULT_CROP_SOURCE_PRIORITY = "frigate_hints_first"

# Retained for compatibility with older API clients. High-quality snapshot generation now evaluates
# every available crop source automatically; this order is only used by legacy callers.
CROP_SOURCE_ORDERS: dict[str, tuple[str, ...]] = {
    "frigate_hints_first": ("frigate_hint_crop", "model_crop", "full_frame"),
    "crop_model_first": ("model_crop", "frigate_hint_crop", "full_frame"),
    "crop_model_only": ("model_crop", "full_frame"),
    "frigate_hints_only": ("frigate_hint_crop", "full_frame"),
}


def crop_source_order(priority: str) -> tuple[str, ...]:
    """Ordered crop sources for a priority setting; unknown values use the default order."""
    return CROP_SOURCE_ORDERS.get(
        str(priority or "").strip().lower(),
        CROP_SOURCE_ORDERS[DEFAULT_CROP_SOURCE_PRIORITY],
    )


class HighQualitySnapshotService:
    """Best-effort background replacement of cached snapshots from event clips."""

    INITIAL_DELAY_SECONDS = 2
    MAX_CLIP_RETRIES = 4
    CLIP_RETRY_INTERVAL_SECONDS = 2
    CLIP_FETCH_TIMEOUT_SECONDS = 10.0
    MAX_PENDING_QUEUE = 32
    MAX_DEFERRED_EVENTS = 128
    MAX_CONCURRENT_TASKS = 2

    def __init__(self):
        self._active_ids: set[str] = set()
        self._queued_ids: set[str] = set()
        self._deferred_ids: set[str] = set()
        self._deferred_order: deque[str] = deque()
        self._job_timestamps: dict[str, tuple[float, float]] = {}
        self._completed_ids: set[str] = set()
        self._final_refresh_ids: set[str] = set()
        self._crop_event_hints: dict[str, dict[str, Any]] = {}
        self._pending_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self.MAX_PENDING_QUEUE)
        self._worker_tasks: list[asyncio.Task] = []
        self._running = False
        self._reconcile_task: asyncio.Task | None = None
        self._reconciled_total = 0
        self._scheduled_total = 0
        self._duplicate_requests = 0
        self._disabled_requests = 0
        self._queue_full_rejections = 0
        self._queue_full_deferrals = 0
        self._outcomes: Counter[str] = Counter()
        self._selected_sources: Counter[str] = Counter()
        self._classification_refinements: Counter[str] = Counter()
        self._last_result: dict[str, str] | None = None

    def enabled(self) -> bool:
        return bool(
            settings.media_cache.enabled
            and settings.media_cache.cache_snapshots
            and settings.media_cache.high_quality_event_snapshots
            and (settings.frigate.clips_enabled or settings.frigate.recording_clip_enabled)
        )

    def _automatic_crop_enabled(self) -> bool:
        """HQ snapshots always attempt the best crop; the old crop flag is compatibility-only."""
        return bool(
            getattr(settings.media_cache, "high_quality_event_snapshots", False)
            or getattr(settings.media_cache, "high_quality_event_snapshot_bird_crop", False)
        )

    def schedule_replacement(self, event_id: str, event_data: Optional[dict[str, Any]] = None) -> bool:
        """Schedule background replacement if enabled and not already active."""
        if not self.enabled():
            self._disabled_requests += 1
            return False

        self._cleanup_completed_workers()
        self._store_crop_event_hints(event_id, event_data)
        if event_id in self._active_ids or event_id in self._queued_ids or event_id in self._deferred_ids:
            self._duplicate_requests += 1
            return False

        self._ensure_workers_started()
        if not self._enqueue_pending(event_id):
            if not self._defer_event(event_id):
                self._crop_event_hints.pop(event_id, None)
                return False
        self._scheduled_total += 1
        return True

    def schedule_final_replacement(self, event_id: str, event_data: dict[str, Any]) -> bool:
        """Queue an ended event even when an earlier live-event pass is still running."""
        if not self.enabled():
            self._disabled_requests += 1
            return False

        self._cleanup_completed_workers()
        self._store_crop_event_hints(event_id, event_data)
        self._final_refresh_ids.add(event_id)
        self._completed_ids.discard(event_id)

        if event_id in self._queued_ids or event_id in self._deferred_ids:
            # The queued pass has not consumed its hints yet, so the freshly
            # stored final metadata is enough; a second queue entry is wasteful.
            return False
        if event_id in self._active_ids:
            if not self._defer_event(event_id):
                self._final_refresh_ids.discard(event_id)
                self._crop_event_hints.pop(event_id, None)
                return False
            self._scheduled_total += 1
            return True

        self._ensure_workers_started()
        if not self._enqueue_pending(event_id):
            if not self._defer_event(event_id):
                self._final_refresh_ids.discard(event_id)
                self._crop_event_hints.pop(event_id, None)
                return False
        self._scheduled_total += 1
        return True

    async def process_event(self, event_id: str) -> str:
        """Process one event and persist its bounded retry outcome."""
        result = await self._process_event_once(event_id)
        await self._persist_processing_outcome(event_id, result)
        return result

    async def _process_event_once(self, event_id: str) -> str:
        """Fetch the clip, derive a frame, and atomically replace the cached snapshot."""
        if not self.enabled():
            self._crop_event_hints.pop(event_id, None)
            return self._record_outcome(event_id, "disabled")

        event_data = self._pop_crop_event_hints(event_id)
        clip_variant = "event"
        clip_bytes, clip_error = await self._wait_for_clip(event_id)
        if not clip_bytes:
            clip_bytes = await self._load_recording_clip_bytes(event_id)
            clip_variant = "recording"

        if event_data is None:
            event_data = await self._load_event_data_for_crop(event_id)
        snapshot_event_data = event_data if clip_variant == "event" else None
        selected_candidate = None
        classification_candidates: list[dict[str, Any]] = []
        try:
            if clip_bytes:
                candidate_bundle = await self.generate_snapshot_candidates_from_clip_bytes(
                    event_id,
                    clip_bytes,
                    event_data=event_data,
                    clip_variant=clip_variant,
                )
            else:
                final_candidates = await self._load_final_frigate_snapshot_candidates(event_id, event_data)
                candidate_bundle = await self._score_and_select_snapshot_candidates(event_id, final_candidates)
            if candidate_bundle:
                candidates = candidate_bundle.get("candidates") or []
                await self._persist_snapshot_candidates(event_id, candidates)
                classification_candidates = candidates
                selected_candidate = candidate_bundle.get("selected_candidate")
        except Exception as e:
            log.warning("High-quality snapshot candidate generation failed", event_id=event_id, error=str(e))

        if isinstance(selected_candidate, dict) and selected_candidate.get("image_bytes"):
            image_bytes = selected_candidate["image_bytes"]
            crop_applied = str(selected_candidate.get("source_mode") or "full_frame") != "full_frame"
            snapshot_source = str(
                selected_candidate.get("snapshot_source")
                or ("high_quality_bird_crop" if crop_applied else "high_quality_snapshot")
            )
            self._selected_sources[str(selected_candidate.get("source_mode") or "full_frame")] += 1
        else:
            if not clip_bytes:
                return self._record_outcome(event_id, clip_error or "clip_unavailable")
            try:
                image_bytes = await asyncio.to_thread(
                    self._extract_snapshot_from_clip,
                    clip_bytes,
                    snapshot_event_data,
                    clip_variant,
                )
            except Exception as e:
                log.warning("High-quality snapshot extraction failed", event_id=event_id, error=str(e))
                return self._record_outcome(event_id, "frame_extract_failed")
            image_bytes, crop_applied = await asyncio.to_thread(
                self._maybe_crop_snapshot_bytes,
                event_id,
                image_bytes,
                snapshot_event_data,
            )
            snapshot_source = "high_quality_bird_crop" if crop_applied else "high_quality_snapshot"

        replaced = await media_cache.replace_snapshot(
            event_id,
            image_bytes,
            source=snapshot_source,
        )
        if not replaced:
            return self._record_outcome(event_id, "snapshot_replace_failed")

        await self._apply_classification_refinement(event_id, classification_candidates)
        log.info("High-quality snapshot replaced", event_id=event_id, size=len(image_bytes), source=snapshot_source)
        return self._record_outcome(event_id, "bird_crop_replaced" if crop_applied else "replaced")

    async def _load_recording_clip_bytes(self, event_id: str) -> Optional[bytes]:
        """Fall back to the full-visit recording clip when the event clip is unavailable."""
        if not settings.frigate.recording_clip_enabled:
            return None

        cached_path = media_cache.get_recording_clip_path(event_id)
        if cached_path and await asyncio.to_thread(cached_path.exists):
            try:
                return await asyncio.to_thread(cached_path.read_bytes)
            except Exception as e:
                log.warning(
                    "Failed to read cached recording clip for HQ snapshot fallback", event_id=event_id, error=str(e)
                )

        try:
            from app.routers.proxy import _fetch_recording_clip_ready, _get_valid_cached_recording_clip_path
        except Exception as e:
            log.warning(
                "Failed to import recording clip helpers for HQ snapshot fallback", event_id=event_id, error=str(e)
            )
            return None

        try:
            cached_path, _camera_name, _start_ts, _end_ts = await _get_valid_cached_recording_clip_path(event_id, "en")
            if cached_path and await asyncio.to_thread(cached_path.exists):
                return await asyncio.to_thread(cached_path.read_bytes)

            ready = await _fetch_recording_clip_ready(event_id, "en")
            if not ready:
                return None

            cached_path, _camera_name, _start_ts, _end_ts = await _get_valid_cached_recording_clip_path(event_id, "en")
            if cached_path and await asyncio.to_thread(cached_path.exists):
                return await asyncio.to_thread(cached_path.read_bytes)
        except Exception as e:
            log.warning("High-quality snapshot recording fallback failed", event_id=event_id, error=str(e))
            return None

        return None

    async def replace_from_clip_bytes(
        self,
        event_id: str,
        clip_bytes: bytes,
        event_data: Optional[dict[str, Any]] = None,
        *,
        clip_variant: str = "event",
    ) -> str:
        """Best-effort replacement using clip bytes already fetched by another workflow."""
        tmp_path = await asyncio.to_thread(_write_temp_clip, clip_bytes)
        try:
            return await self.replace_from_clip_path(
                event_id,
                tmp_path,
                event_data,
                clip_variant=clip_variant,
            )
        finally:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(tmp_path.unlink, missing_ok=True)

    async def replace_from_clip_path(
        self,
        event_id: str,
        clip_path: Path,
        event_data: Optional[dict[str, Any]] = None,
        *,
        clip_variant: str = "event",
    ) -> str:
        """Best-effort replacement from a clip already on disk; the caller owns the file (#341)."""
        if not self.enabled():
            return self._record_outcome(event_id, "disabled")

        self._cleanup_completed_workers()
        if event_id in self._active_ids:
            self._crop_event_hints.pop(event_id, None)
            self._duplicate_requests += 1
            return self._record_outcome(event_id, "duplicate")

        self._active_ids.add(event_id)
        self._mark_job_active(event_id)
        try:
            crop_event_data = (
                event_data if isinstance(event_data, dict) else await self._load_event_data_for_crop(event_id)
            )
            snapshot_event_data = crop_event_data if clip_variant == "event" else None
            selected_candidate = None
            classification_candidates: list[dict[str, Any]] = []
            try:
                candidate_bundle = await self.generate_snapshot_candidates_from_clip_path(
                    event_id,
                    Path(clip_path),
                    event_data=crop_event_data,
                    clip_variant=clip_variant,
                )
                if candidate_bundle:
                    candidates = candidate_bundle.get("candidates") or []
                    await self._persist_snapshot_candidates(event_id, candidates)
                    classification_candidates = candidates
                    selected_candidate = candidate_bundle.get("selected_candidate")
            except Exception as e:
                log.warning("High-quality snapshot candidate generation failed", event_id=event_id, error=str(e))

            if isinstance(selected_candidate, dict) and selected_candidate.get("image_bytes"):
                image_bytes = selected_candidate["image_bytes"]
                crop_applied = str(selected_candidate.get("source_mode") or "full_frame") != "full_frame"
                snapshot_source = str(
                    selected_candidate.get("snapshot_source")
                    or ("high_quality_bird_crop" if crop_applied else "high_quality_snapshot")
                )
                self._selected_sources[str(selected_candidate.get("source_mode") or "full_frame")] += 1
            else:
                try:
                    image_bytes = await asyncio.to_thread(
                        self._extract_snapshot_from_clip_path,
                        Path(clip_path),
                        snapshot_event_data,
                        clip_variant,
                    )
                except Exception as e:
                    log.warning("High-quality snapshot extraction failed", event_id=event_id, error=str(e))
                    return self._record_outcome(event_id, "frame_extract_failed")
                image_bytes, crop_applied = await asyncio.to_thread(
                    self._maybe_crop_snapshot_bytes,
                    event_id,
                    image_bytes,
                    snapshot_event_data,
                )
                snapshot_source = "high_quality_bird_crop" if crop_applied else "high_quality_snapshot"

            replaced = await media_cache.replace_snapshot(
                event_id,
                image_bytes,
                source=snapshot_source,
            )
            if not replaced:
                return self._record_outcome(event_id, "snapshot_replace_failed")

            await self._apply_classification_refinement(event_id, classification_candidates)
            if event_id not in self._final_refresh_ids and (
                event_id in self._queued_ids or event_id in self._deferred_ids
            ):
                self._completed_ids.add(event_id)

            log.info(
                "High-quality snapshot replaced from clip",
                event_id=event_id,
                size=len(image_bytes),
                source=snapshot_source,
            )
            result = self._record_outcome(event_id, "bird_crop_replaced" if crop_applied else "replaced")
            await self._persist_processing_outcome(event_id, result)
            return result
        finally:
            self._active_ids.discard(event_id)
            self._promote_deferred_events()
            self._forget_finished_job(event_id)

    async def _load_preferred_frame_indices(
        self,
        event_id: str,
        *,
        clip_variant: str,
    ) -> Optional[list[int]]:
        """Return stored top-frame indices for this event, or None to use default sampling."""
        try:
            async with get_db() as db:
                frames = await DetectionRepository(db).list_video_top_frames(event_id)
        except Exception:
            return None
        if not frames:
            return None
        matching = [f for f in frames if f.get("clip_variant") == clip_variant]
        if matching:
            source = matching
        elif clip_variant == "event":
            # Rows created before clip provenance was persisted refer to the
            # original event clip. They are not safe recording-frame offsets.
            source = [f for f in frames if not f.get("clip_variant")]
        else:
            source = []
        if not source:
            return None
        return [int(f["frame_index"]) for f in source]

    async def generate_snapshot_candidates_from_clip_bytes(
        self,
        event_id: str,
        clip_bytes: bytes,
        *,
        event_data: Optional[dict[str, Any]] = None,
        clip_variant: str = "event",
    ) -> dict[str, Any]:
        tmp_path = await asyncio.to_thread(_write_temp_clip, clip_bytes)
        try:
            return await self.generate_snapshot_candidates_from_clip_path(
                event_id,
                tmp_path,
                event_data=event_data,
                clip_variant=clip_variant,
            )
        finally:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(tmp_path.unlink, missing_ok=True)

    async def generate_snapshot_candidates_from_clip_path(
        self,
        event_id: str,
        clip_path: Path,
        *,
        event_data: Optional[dict[str, Any]] = None,
        clip_variant: str = "event",
    ) -> dict[str, Any]:
        """Candidate generation against a clip already on disk; the caller owns the file (#341)."""
        preferred_indices = await self._load_preferred_frame_indices(event_id, clip_variant=clip_variant)

        raw_candidates: list[dict[str, Any]] = []
        extraction_error: Exception | None = None
        try:
            raw_candidates = await asyncio.to_thread(
                self._extract_snapshot_candidate_payloads_from_clip_path,
                Path(clip_path),
                event_id=event_id,
                event_data=event_data,
                clip_variant=clip_variant,
                override_frame_indices=preferred_indices,
            )
        except Exception as exc:
            extraction_error = exc
            log.warning(
                "High-quality clip candidate extraction failed; trying final Frigate snapshot",
                event_id=event_id,
                error=str(exc),
            )

        raw_candidates.extend(await self._load_final_frigate_snapshot_candidates(event_id, event_data))
        if not raw_candidates and extraction_error is not None:
            raise extraction_error

        return await self._score_and_select_snapshot_candidates(event_id, raw_candidates)

    async def _score_and_select_snapshot_candidates(
        self,
        event_id: str,
        raw_candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Score, select, and bound candidates independent of their media source."""
        scored: list[dict[str, Any]] = []
        for candidate in raw_candidates:
            enriched = await self._score_snapshot_candidate(candidate)
            if enriched is not None:
                scored.append(enriched)

        if not scored:
            return {"selected_candidate": None, "candidates": []}

        ranked = self._rank_snapshot_candidates(scored)
        expected_labels = await self._load_expected_species_labels(event_id)
        selected_candidate = self._select_canonical_snapshot_candidate(
            ranked,
            expected_labels=expected_labels,
        )
        persisted = self._select_persisted_candidates(
            ranked,
            selected_candidate=selected_candidate,
        )
        selected_candidate_id = str((selected_candidate or {}).get("candidate_id") or "")
        for candidate in persisted:
            candidate["selected"] = (
                bool(selected_candidate_id) and str(candidate.get("candidate_id") or "") == selected_candidate_id
            )
        return {
            "selected_candidate": selected_candidate,
            "candidates": persisted,
        }

    def _select_persisted_candidates(
        self,
        ranked: list[dict[str, Any]],
        *,
        selected_candidate: Optional[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Retain leaders plus the canonical and auditable Frigate baselines."""
        if len(ranked) <= HQ_MAX_PERSISTED_CANDIDATES:
            return list(ranked)

        persisted = list(ranked[:HQ_MAX_PERSISTED_CANDIDATES])
        best_full_frame = next(
            (item for item in ranked if str(item.get("source_mode") or "full_frame") == "full_frame"),
            None,
        )
        final_snapshot_candidates = [
            item for item in ranked if str(item.get("clip_variant") or "") == "frigate_snapshot"
        ]
        best_final_snapshot = max(
            final_snapshot_candidates,
            key=lambda item: float(item.get("ranking_score") or 0.0),
            default=None,
        )
        final_full_frame = next(
            (
                item
                for item in final_snapshot_candidates
                if str(item.get("source_mode") or "full_frame") == "full_frame"
            ),
            None,
        )
        required = [
            item
            for item in (selected_candidate, best_full_frame, best_final_snapshot, final_full_frame)
            if item is not None
        ]
        required_ids = {str(item.get("candidate_id") or "") for item in required}
        persisted_ids = {str(item.get("candidate_id") or "") for item in persisted}
        for candidate in required:
            candidate_id = str(candidate.get("candidate_id") or "")
            if candidate_id in persisted_ids:
                continue
            replacement_index = next(
                (
                    index
                    for index in range(len(persisted) - 1, -1, -1)
                    if str(persisted[index].get("candidate_id") or "") not in required_ids
                ),
                None,
            )
            if replacement_index is None:
                break
            persisted_ids.discard(str(persisted[replacement_index].get("candidate_id") or ""))
            persisted[replacement_index] = candidate
            persisted_ids.add(candidate_id)
        return self._rank_snapshot_candidates(persisted)

    async def _load_expected_species_labels(self, event_id: str) -> set[str]:
        try:
            async with get_db() as db:
                detection = await DetectionRepository(db).get_by_frigate_event(event_id)
        except Exception:
            return set()
        if detection is None:
            return set()
        labels = {
            self._candidate_label_key(value)
            for value in (
                getattr(detection, "display_name", None),
                getattr(detection, "category_name", None),
                getattr(detection, "scientific_name", None),
                getattr(detection, "common_name", None),
            )
            if value and not should_hide_species_label(value)
        }
        labels.discard("")
        return labels

    @staticmethod
    def _candidate_label_key(value: Any) -> str:
        return " ".join(normalize_classifier_label(str(value or "")).replace("_", " ").split()).casefold()

    @staticmethod
    def _crop_has_usable_detail(candidate: dict[str, Any]) -> bool:
        try:
            width = int(candidate.get("image_width") or 0)
            height = int(candidate.get("image_height") or 0)
        except (TypeError, ValueError):
            return False
        return min(width, height) >= HQ_MIN_CROP_EDGE_PIXELS and width * height >= HQ_MIN_CROP_AREA_PIXELS

    def _select_canonical_snapshot_candidate(
        self,
        candidates: list[dict[str, Any]],
        *,
        expected_labels: set[str] | None = None,
    ) -> Optional[dict[str, Any]]:
        """Choose a crop without replacing Frigate's final best frame on marginal evidence."""
        if not candidates:
            return None

        final_snapshot_candidates = [
            item for item in candidates if str(item.get("clip_variant") or "").strip() == "frigate_snapshot"
        ]
        clip_candidates = [
            item for item in candidates if str(item.get("clip_variant") or "").strip() != "frigate_snapshot"
        ]
        if not final_snapshot_candidates:
            return self._select_best_trusted_candidate(candidates, expected_labels=expected_labels)

        final_snapshot = self._select_best_trusted_candidate(
            final_snapshot_candidates,
            expected_labels=expected_labels,
        )
        clip_candidate = self._select_best_trusted_candidate(
            clip_candidates,
            expected_labels=expected_labels,
        )
        if final_snapshot is None:
            return clip_candidate
        if clip_candidate is None:
            return final_snapshot
        if self._clip_candidate_materially_improves_final_snapshot(
            clip_candidate,
            final_snapshot,
            expected_labels=expected_labels,
        ):
            return clip_candidate
        return final_snapshot

    def _select_best_trusted_candidate(
        self,
        candidates: list[dict[str, Any]],
        *,
        expected_labels: set[str] | None = None,
    ) -> Optional[dict[str, Any]]:
        """Choose the strongest identity-safe candidate within one media source."""
        if not candidates:
            return None
        full_frames = [item for item in candidates if str(item.get("source_mode") or "full_frame") == "full_frame"]
        usable_crops = [
            item
            for item in candidates
            if str(item.get("source_mode") or "full_frame") != "full_frame" and self._crop_has_usable_detail(item)
        ]

        normalized_expected = {
            self._candidate_label_key(label) for label in (expected_labels or set()) if self._candidate_label_key(label)
        }
        if normalized_expected:
            full_frames = [
                item
                for item in full_frames
                if not self._candidate_label_key(item.get("classifier_label"))
                or self._candidate_label_key(item.get("classifier_label")) in normalized_expected
            ]
            usable_crops = [
                item
                for item in usable_crops
                if self._candidate_label_key(item.get("classifier_label")) in normalized_expected
            ]
        else:
            supported_labels = crop_labels_with_independent_support(usable_crops)
            usable_crops = [
                item
                for item in usable_crops
                if self._candidate_label_key(item.get("classifier_label")) in supported_labels
            ]

        pool = full_frames + usable_crops
        if not pool:
            pool = candidates
        selected = max(pool, key=lambda item: float(item.get("ranking_score") or 0.0))
        if str(selected.get("source_mode") or "") != "model_crop":
            return selected

        frigate_crops = [item for item in usable_crops if str(item.get("source_mode") or "") == "frigate_hint_crop"]
        if not frigate_crops:
            return selected
        best_frigate = max(
            frigate_crops,
            key=lambda item: (
                self._finite_candidate_score(item.get("classifier_score")),
                float(item.get("ranking_score") or 0.0),
            ),
        )
        model_score = self._finite_candidate_score(selected.get("classifier_score"))
        frigate_score = self._finite_candidate_score(best_frigate.get("classifier_score"))
        same_label = self._candidate_label_key(selected.get("classifier_label")) == self._candidate_label_key(
            best_frigate.get("classifier_label")
        )
        if same_label and model_score + 1e-9 >= frigate_score + HQ_MODEL_CROP_MIN_CLASSIFIER_ADVANTAGE:
            return selected

        baseline_pool = [item for item in pool if str(item.get("source_mode") or "") != "model_crop"]
        return max(baseline_pool, key=lambda item: float(item.get("ranking_score") or 0.0))

    def _clip_candidate_materially_improves_final_snapshot(
        self,
        clip_candidate: dict[str, Any],
        final_snapshot: dict[str, Any],
        *,
        expected_labels: set[str] | None,
    ) -> bool:
        """Require identity agreement and a real classifier gain over Frigate's best frame."""
        clip_label = self._candidate_label_key(clip_candidate.get("classifier_label"))
        final_label = self._candidate_label_key(final_snapshot.get("classifier_label"))
        normalized_expected = {
            self._candidate_label_key(label) for label in (expected_labels or set()) if self._candidate_label_key(label)
        }

        if normalized_expected:
            if clip_label not in normalized_expected:
                return False
            # A clip that recovers the expected identity may replace an explicitly
            # contradictory final-frame result. The score still has to be non-zero.
            if final_label and final_label not in normalized_expected:
                return self._finite_candidate_score(clip_candidate.get("classifier_score")) > 0.0
        elif not clip_label or clip_label != final_label:
            return False

        clip_score = self._finite_candidate_score(clip_candidate.get("classifier_score"))
        final_score = self._finite_candidate_score(final_snapshot.get("classifier_score"))
        return clip_score + 1e-9 >= final_score + HQ_CLIP_REPLACEMENT_MIN_CLASSIFIER_ADVANTAGE

    @staticmethod
    def _finite_candidate_score(value: Any) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        return score if math.isfinite(score) else 0.0

    def _rank_snapshot_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rank candidates by score (highest first) for persistence and manual selection.

        The canonical event image is chosen separately by crop-source preference
        (`_select_canonical_snapshot_candidate`); this ordering only decides which candidates are
        persisted and the order alternates are offered in.
        """
        return sorted(candidates, key=lambda item: float(item.get("ranking_score") or 0.0), reverse=True)

    def _extract_snapshot_candidate_payloads_from_clip_path(
        self,
        clip_path: Path,
        *,
        event_id: str,
        event_data: Optional[dict[str, Any]] = None,
        clip_variant: str = "event",
        override_frame_indices: Optional[list[int]] = None,
    ) -> list[dict[str, Any]]:
        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            raise ValueError(f"Unable to open clip for snapshot extraction: {clip_path}")

        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            if override_frame_indices is not None:
                safe_count = max(frame_count, 1)
                fallback_indices = self._candidate_frame_indices(
                    frame_count=frame_count,
                    fps=fps,
                    event_data=event_data,
                    clip_variant=clip_variant,
                )
                candidate_indices = self._select_temporally_diverse_frame_indices(
                    [*override_frame_indices, *fallback_indices],
                    frame_count=safe_count,
                    fps=fps,
                    max_samples=HQ_MAX_CROP_SCORING_FRAMES,
                )
            else:
                candidate_indices = self._candidate_frame_indices(
                    frame_count=frame_count,
                    fps=fps,
                    event_data=event_data,
                    clip_variant=clip_variant,
                )[:HQ_MAX_CROP_SCORING_FRAMES]
            seen: set[str] = set()
            used_frame_indices: list[int] = []
            results: list[dict[str, Any]] = []
            for target_frame_index in candidate_indices:
                decoded = self._read_temporally_independent_frame(
                    cap,
                    target_frame_index=target_frame_index,
                    frame_count=frame_count,
                    fps=fps,
                    used_frame_indices=used_frame_indices,
                )
                if decoded is None:
                    continue
                frame_index, frame = decoded
                used_frame_indices.append(frame_index)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                base_image = Image.fromarray(rgb_frame).convert("RGB")
                frame_offset_seconds = (float(frame_index) / fps) if fps > 0 else None
                frame_event_data = self._event_hints_for_frame(
                    event_data,
                    frame_offset_seconds=frame_offset_seconds,
                    clip_variant=clip_variant,
                )
                for source_mode, candidate_image, crop_result in self._candidate_images_for_frame(
                    base_image,
                    event_data=frame_event_data,
                    event_id=event_id,
                ):
                    image_bytes = self._encode_pil_to_jpeg_bytes(candidate_image)
                    candidate_id = self._build_snapshot_candidate_id(
                        event_id,
                        frame_index=frame_index,
                        source_mode=source_mode,
                    )
                    if candidate_id in seen:
                        continue
                    seen.add(candidate_id)
                    thumbnail_ref = f"{candidate_id}__thumb"
                    image_ref = f"{candidate_id}__image"
                    results.append(
                        {
                            "candidate_id": candidate_id,
                            "frame_index": int(frame_index),
                            "frame_offset_seconds": frame_offset_seconds,
                            "source_mode": source_mode,
                            "clip_variant": clip_variant,
                            "crop_box": (crop_result or {}).get("box") if isinstance(crop_result, dict) else None,
                            "crop_confidence": (crop_result or {}).get("confidence")
                            if isinstance(crop_result, dict)
                            else None,
                            "crop_strategy": (crop_result or {}).get("strategy")
                            if isinstance(crop_result, dict)
                            else None,
                            "thumbnail_ref": thumbnail_ref,
                            "image_ref": image_ref,
                            "snapshot_source": f"hq_candidate_{source_mode}",
                            "image_width": int(candidate_image.width),
                            "image_height": int(candidate_image.height),
                            "frame_width": int(base_image.width),
                            "frame_height": int(base_image.height),
                            "image_bytes": image_bytes,
                            "thumbnail_bytes": self._thumbnail_bytes_for_candidate(candidate_image),
                        }
                    )
            return results
        finally:
            cap.release()

    def _candidate_images_for_frame(
        self,
        image: Image.Image,
        *,
        event_data: Optional[dict[str, Any]],
        event_id: str,
    ) -> list[tuple[str, Image.Image, Optional[dict[str, Any]]]]:
        candidates: list[tuple[str, Image.Image, Optional[dict[str, Any]]]] = [("full_frame", image, None)]
        hint_result = self._crop_from_event_hints(image, event_data)
        hint_image = hint_result.get("crop_image") if isinstance(hint_result, dict) else None
        if isinstance(hint_image, Image.Image):
            candidates.append(("frigate_hint_crop", hint_image, hint_result))
        if self._automatic_crop_enabled() and self._bird_crop_model_available():
            hint_box = hint_result.get("box") if isinstance(hint_result, dict) else None
            if isinstance(hint_box, (list, tuple)) and len(hint_box) == 4:
                model_result = self._crop_candidate_from_bird_model(
                    image,
                    event_id=event_id,
                    search_box=tuple(int(value) for value in hint_box),
                )
            else:
                model_result = self._crop_candidate_from_bird_model(image, event_id=event_id)
            model_image = model_result.get("crop_image") if isinstance(model_result, dict) else None
            if isinstance(model_image, Image.Image):
                candidates.append(("model_crop", model_image, model_result))
        return candidates

    async def _load_final_frigate_snapshot_candidates(
        self,
        event_id: str,
        event_data: Optional[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Build a protected baseline from Frigate's completed-event best snapshot.

        Frigate continually updates an event's best snapshot while tracking. We
        only use this baseline once the event has a concrete end time, ensuring
        a live intermediate image is never mistaken for the final best frame.
        """
        if not isinstance(event_data, dict) or event_data.get("end_time") is None:
            return []

        clean_copy_available = False
        try:
            snapshot_bytes, error = await frigate_client.get_clean_snapshot_with_error(event_id, timeout=8.0)
            clean_copy_available = bool(snapshot_bytes)
            if not snapshot_bytes:
                snapshot_bytes, regular_error = await frigate_client.get_snapshot_with_error(
                    event_id,
                    crop=False,
                    quality=95,
                    timeout=8.0,
                )
                error = regular_error or error
        except Exception as exc:
            log.debug("Final Frigate snapshot fetch failed", event_id=event_id, error=str(exc))
            return []
        if not snapshot_bytes:
            log.debug(
                "Final Frigate snapshot unavailable for HQ baseline",
                event_id=event_id,
                reason=error or "snapshot_unavailable",
            )
            return []

        try:
            image = await asyncio.to_thread(decode_image_bytes, snapshot_bytes, convert_rgb=True)
        except Exception as exc:
            log.warning("Final Frigate snapshot decode failed", event_id=event_id, error=str(exc))
            return []

        candidates = [
            self._build_final_snapshot_candidate_payload(
                event_id,
                image,
                source_mode="full_frame",
                input_is_cropped=not clean_copy_available,
                snapshot_source=(
                    "hq_candidate_full_frame" if clean_copy_available else "hq_candidate_frigate_snapshot_fallback"
                ),
            )
        ]
        # Frigate ignores snapshot.jpg query parameters after an event ends, so
        # a regular snapshot may already be cropped or resized by its config.
        # Only apply normalized event coordinates to the guaranteed full-size
        # clean copy.
        crop_result = self._crop_from_final_frigate_box(image, event_data) if clean_copy_available else None
        crop_image = crop_result.get("crop_image") if isinstance(crop_result, dict) else None
        if isinstance(crop_image, Image.Image):
            candidates.append(
                self._build_final_snapshot_candidate_payload(
                    event_id,
                    crop_image,
                    source_mode="frigate_hint_crop",
                    frame_size=image.size,
                    crop_result=crop_result,
                )
            )
        return candidates

    def _build_final_snapshot_candidate_payload(
        self,
        event_id: str,
        image: Image.Image,
        *,
        source_mode: str,
        frame_size: tuple[int, int] | None = None,
        crop_result: Optional[dict[str, Any]] = None,
        input_is_cropped: bool | None = None,
        snapshot_source: str | None = None,
    ) -> dict[str, Any]:
        """Create a persisted candidate row for Frigate's final still image."""
        digest = hashlib.sha1(f"{event_id}:frigate_snapshot:{source_mode}".encode("utf-8")).hexdigest()[:10]
        candidate_id = f"{event_id}__{source_mode}__final__{digest}"
        frame_width, frame_height = frame_size or image.size
        encoded = self._encode_pil_to_jpeg_bytes(image)
        return {
            "candidate_id": candidate_id,
            "frame_index": 0,
            "frame_offset_seconds": None,
            "source_mode": source_mode,
            "clip_variant": "frigate_snapshot",
            "crop_box": (crop_result or {}).get("box") if isinstance(crop_result, dict) else None,
            "crop_confidence": None,
            "crop_strategy": (crop_result or {}).get("strategy") if isinstance(crop_result, dict) else None,
            "thumbnail_ref": f"{candidate_id}__thumb",
            "image_ref": f"{candidate_id}__image",
            "snapshot_source": snapshot_source or f"hq_candidate_{source_mode}",
            "input_is_cropped": input_is_cropped,
            "image_width": int(image.width),
            "image_height": int(image.height),
            "frame_width": int(frame_width),
            "frame_height": int(frame_height),
            "image_bytes": encoded,
            "thumbnail_bytes": self._thumbnail_bytes_for_candidate(image),
        }

    def _crop_from_final_frigate_box(
        self,
        image: Image.Image,
        event_data: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Crop the final snapshot from Frigate's final tracked box only."""
        raw_snapshot = event_data.get("snapshot")
        snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else {}
        raw_payload = event_data.get("data")
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        box = self._restore_frigate_hint_box(snapshot.get("box") or payload.get("box"), image.size)
        if box is None:
            return None
        expanded = self._expand_hint_box(box, image.size)
        if expanded is None:
            return None
        return {
            "crop_image": image.crop(expanded),
            "box": expanded,
            "confidence": None,
            "reason": "frigate_final_box",
            "strategy": "frigate_final_box",
        }

    def _event_hints_for_frame(
        self,
        event_data: Optional[dict[str, Any]],
        *,
        frame_offset_seconds: Optional[float],
        clip_variant: str,
    ) -> Optional[dict[str, Any]]:
        """Return a Frigate hint translated to the tracked position at this frame.

        Event clips share Frigate's event timeline, so path points can move the
        tracked box safely. Full-visit recordings may begin before the event and
        partial recordings may begin late; without an explicit clip-start
        timestamp, applying the event box to that different timeline would be
        misleading, so recording frames rely on the model detector instead.
        """

        if not isinstance(event_data, dict):
            return None
        if str(clip_variant or "event").strip().lower() != "event":
            return None
        raw_payload = event_data.get("data")
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        path_points: list[tuple[float, float, float]] = []
        for item in payload.get("path_data") or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            point = item[0]
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                x = float(point[0])
                y = float(point[1])
                timestamp = float(item[1])
            except (TypeError, ValueError):
                continue
            if all(math.isfinite(value) for value in (x, y, timestamp)) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                path_points.append((timestamp, x, y))
        if not path_points:
            return event_data
        try:
            start_time = float(event_data.get("start_time"))
            offset = float(frame_offset_seconds)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(start_time) or not math.isfinite(offset) or offset < 0.0:
            return None
        target_timestamp = start_time + offset
        point_timestamp, bottom_center_x, bottom_y = min(
            path_points,
            key=lambda item: abs(item[0] - target_timestamp),
        )
        if abs(point_timestamp - target_timestamp) > HQ_PATH_HINT_MAX_DISTANCE_SECONDS:
            return None

        raw_box = payload.get("box")
        if not isinstance(raw_box, (list, tuple)) or len(raw_box) != 4:
            return None
        try:
            _left, _top, width, height = [float(value) for value in raw_box]
        except (TypeError, ValueError):
            return None
        if (
            not all(math.isfinite(value) for value in (width, height))
            or not (0.0 < width <= 1.0)
            or not (0.0 < height <= 1.0)
        ):
            return None

        # Frigate path_data stores the tracked box's bottom-centre point.
        left = max(0.0, min(1.0 - width, bottom_center_x - width / 2.0))
        top = max(0.0, min(1.0 - height, bottom_y - height))
        adjusted_payload = dict(payload)
        adjusted_payload["box"] = [left, top, width, height]
        adjusted_event = dict(event_data)
        adjusted_event["data"] = adjusted_payload
        return adjusted_event

    async def _score_snapshot_candidate(self, candidate: dict[str, Any]) -> Optional[dict[str, Any]]:
        image_bytes = candidate.get("image_bytes")
        if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
            return None
        try:
            image = await asyncio.to_thread(decode_image_bytes, bytes(image_bytes), convert_rgb=True)
        except Exception:
            return None

        classifier_score = 0.0
        classifier_label = None
        classifier_index = None
        try:
            classifier_module = sys.modules.get("app.services.classifier_service")
            classifier = (
                getattr(classifier_module, "_classifier_instance", None) if classifier_module is not None else None
            )
            if classifier is not None and callable(getattr(classifier, "classify_async_background", None)):
                results = await classifier.classify_async_background(
                    image,
                    input_context={
                        "is_cropped": (
                            bool(candidate.get("input_is_cropped"))
                            if candidate.get("input_is_cropped") is not None
                            else candidate.get("source_mode") != "full_frame"
                        )
                    },
                    queue_timeout_seconds=HQ_CANDIDATE_INFERENCE_QUEUE_TIMEOUT_SECONDS,
                )
                if results:
                    top_result = results[0]
                    classifier_label = top_result.get("label")
                    classifier_score = float(top_result.get("score") or 0.0)
                    classifier_index = int(top_result.get("index") or 0)
        except Exception as e:
            log.debug(
                "Snapshot candidate classifier scoring failed", candidate_id=candidate.get("candidate_id"), error=str(e)
            )

        grayscale = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
        sharpness = float(cv2.Laplacian(grayscale, cv2.CV_64F).var())
        sharpness_score = min(1.0, math.log1p(max(0.0, sharpness)) / math.log1p(1000.0))
        exposure_score = float(((grayscale >= 8) & (grayscale <= 247)).mean())
        resolution_score = min(1.0, math.sqrt(image.width * image.height) / 512.0)
        image_quality_score = (sharpness_score * 0.45) + (exposure_score * 0.35) + (resolution_score * 0.20)
        ranking_score = (classifier_score * 0.85) + (image_quality_score * 0.15)

        enriched = dict(candidate)
        enriched["classifier_label"] = classifier_label
        enriched["classifier_score"] = classifier_score
        enriched["classifier_index"] = classifier_index
        enriched["image_quality_score"] = image_quality_score
        enriched["ranking_score"] = ranking_score
        return enriched

    async def _apply_classification_refinement(self, event_id: str, candidates: list[dict[str, Any]]) -> bool:
        """Promote a trustworthy crop consensus through the canonical detection write path."""
        # Avoid a database lookup when candidate scoring did not produce enough usable evidence.
        crop_votes = [
            item
            for item in candidates
            if str(item.get("source_mode") or "full_frame") != "full_frame"
            and str(item.get("clip_variant") or "") != "frigate_snapshot"
            and item.get("classifier_label")
            and item.get("classifier_index") is not None
        ]
        if not crop_labels_with_independent_support(crop_votes):
            self._classification_refinements["insufficient_evidence"] += 1
            return False

        try:
            async with get_db() as db:
                detection = await DetectionRepository(db).get_by_frigate_event(event_id)
            if detection is None:
                self._classification_refinements["detection_missing"] += 1
                return False

            from app.services.model_manager import model_manager

            model_spec = dict(model_manager.get_active_model_spec() or {})
            recommended_threshold = float(model_spec.get("recommended_threshold", 0.65) or 0.65)
            decision = choose_hq_classification_refinement(
                detection=detection,
                candidates=candidates,
                minimum_score=recommended_threshold,
            )
            if decision is None:
                self._classification_refinements["policy_rejected"] += 1
                return False

            classifier_module = sys.modules.get("app.services.classifier_service")
            classifier = (
                getattr(classifier_module, "_classifier_instance", None) if classifier_module is not None else None
            )
            if classifier is None:
                self._classification_refinements["classifier_unavailable"] += 1
                return False

            from app.services.detection_service import DetectionService

            applied = await DetectionService(classifier).apply_video_result(
                frigate_event=event_id,
                video_label=decision.label,
                video_score=decision.score,
                video_index=decision.index,
                video_provider=str(getattr(classifier, "_active_inference_provider", "") or "") or None,
                video_backend=str(getattr(classifier, "_inference_backend", "") or "") or None,
                video_model_id=str(model_spec.get("model_id") or "") or None,
                persist_video_result=False,
            )
            outcome = "promoted" if applied else "recorded"
            self._classification_refinements[outcome] += 1
            log.info(
                "High-quality crop consensus applied",
                event_id=event_id,
                candidate_id=decision.candidate_id,
                source_mode=decision.source_mode,
                label=decision.label,
                score=decision.score,
                median_score=decision.median_score,
                supporting_frames=decision.supporting_frame_count,
                reason=decision.reason,
                promoted=bool(applied),
                model_id=model_spec.get("model_id"),
                preprocessing=model_spec.get("preprocessing"),
            )
            return bool(applied)
        except Exception as exc:
            self._classification_refinements["failed"] += 1
            log.warning("High-quality crop classification refinement failed", event_id=event_id, error=str(exc))
            return False

    async def _persist_snapshot_candidates(self, event_id: str, candidates: list[dict[str, Any]]) -> None:
        stale_image_refs: list[str] = []
        stale_thumbnail_refs: list[str] = []
        async with get_db() as db:
            repo = DetectionRepository(db)
            existing = await repo.list_snapshot_candidates(event_id)
            existing_image_refs = {
                str(item.get("image_ref") or "").strip()
                for item in existing
                if str(item.get("image_ref") or "").strip()
            }
            existing_thumbnail_refs = {
                str(item.get("thumbnail_ref") or "").strip()
                for item in existing
                if str(item.get("thumbnail_ref") or "").strip()
            }
            new_image_refs = {
                str(item.get("image_ref") or "").strip()
                for item in candidates
                if str(item.get("image_ref") or "").strip()
            }
            new_thumbnail_refs = {
                str(item.get("thumbnail_ref") or "").strip()
                for item in candidates
                if str(item.get("thumbnail_ref") or "").strip()
            }
            stale_image_refs = sorted(existing_image_refs - new_image_refs)
            stale_thumbnail_refs = sorted(existing_thumbnail_refs - new_thumbnail_refs)

        for candidate in candidates:
            image_ref = str(candidate.get("image_ref") or "")
            thumbnail_ref = str(candidate.get("thumbnail_ref") or "")
            image_bytes = candidate.get("image_bytes")
            thumbnail_bytes = candidate.get("thumbnail_bytes")
            if image_ref and isinstance(image_bytes, (bytes, bytearray)):
                await media_cache.cache_snapshot(image_ref, bytes(image_bytes), source="snapshot_candidate")
            if thumbnail_ref and isinstance(thumbnail_bytes, (bytes, bytearray)):
                await media_cache.cache_thumbnail(thumbnail_ref, bytes(thumbnail_bytes), source="snapshot_candidate")

        persisted_rows: list[dict[str, Any]] = []
        for candidate in candidates:
            row = dict(candidate)
            row.pop("image_bytes", None)
            row.pop("thumbnail_bytes", None)
            persisted_rows.append(row)
        async with get_db() as db:
            repo = DetectionRepository(db)
            await repo.replace_snapshot_candidates(event_id, persisted_rows)
        for image_ref in stale_image_refs:
            await media_cache.delete_snapshot(image_ref)
        for thumbnail_ref in stale_thumbnail_refs:
            await media_cache.delete_thumbnail(thumbnail_ref)

    def _thumbnail_bytes_for_candidate(self, image: Image.Image, *, max_size: int = 240) -> bytes:
        thumb = image.copy()
        thumb.thumbnail((max_size, max_size))
        return self._encode_pil_to_jpeg_bytes(thumb, quality=82)

    def _encode_pil_to_jpeg_bytes(self, image: Image.Image, *, quality: Optional[int] = None) -> bytes:
        buffer = BytesIO()
        image.convert("RGB").save(
            buffer,
            format="JPEG",
            quality=int(quality or settings.media_cache.high_quality_event_snapshot_jpeg_quality),
            optimize=True,
        )
        return buffer.getvalue()

    def _build_snapshot_candidate_id(self, event_id: str, *, frame_index: int, source_mode: str) -> str:
        digest = hashlib.sha1(f"{event_id}:{frame_index}:{source_mode}".encode("utf-8")).hexdigest()[:10]
        return f"{event_id}__{source_mode}__f{frame_index}__{digest}"

    async def wait_for_idle(self) -> None:
        """Wait for all scheduled replacement tasks to complete."""
        while True:
            self._promote_deferred_events()
            await self._pending_queue.join()
            self._promote_deferred_events()
            if not self._active_ids and self._pending_queue.qsize() == 0 and not self._deferred_ids:
                return
            await asyncio.sleep(0.01)

    async def start(self) -> None:
        """Start bounded recovery for snapshot jobs lost during a restart."""
        if self._running:
            return
        self._running = True
        self._reconcile_task = create_background_task(
            self._reconcile_loop(),
            name="high_quality_snapshot_reconcile",
        )

    async def reconcile_recent_detections(self) -> int:
        """Schedule recent detections that have neither HQ output nor generated candidates."""
        if not self.enabled():
            return 0
        now = datetime.now(timezone.utc)
        async with get_db() as db:
            repo = DetectionRepository(db)
            detections = await repo.get_recent_full_visit_candidates(
                detected_before=now,
                detected_after=now - timedelta(hours=HQ_RECONCILE_LOOKBACK_HOURS),
                limit=HQ_RECONCILE_LIMIT,
            )

        scheduled = 0
        for detection in detections:
            event_id = str(detection.frigate_event or "").strip()
            if not event_id or event_id.startswith("manual_"):
                continue
            metadata = await media_cache.get_snapshot_metadata(event_id)
            source = str((metadata or {}).get("source") or "").strip()
            if source in {"high_quality_snapshot", "high_quality_bird_crop"} or source.startswith("hq_candidate_"):
                continue
            async with get_db() as db:
                if await DetectionRepository(db).list_snapshot_candidates(event_id):
                    continue
            if not await self._processing_retry_allowed(event_id, now=now):
                continue
            if self.schedule_replacement(event_id):
                scheduled += 1
        self._reconciled_total += scheduled
        return scheduled

    async def _reconcile_loop(self) -> None:
        try:
            await asyncio.sleep(30)
            while self._running:
                try:
                    await self.reconcile_recent_detections()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("High-quality snapshot recovery failed", error=str(exc))
                await asyncio.sleep(HQ_RECONCILE_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            return

    async def stop(self) -> None:
        """Cancel and clear all active tasks for tests or shutdown."""
        self._running = False
        current_loop = asyncio.get_running_loop()
        tasks = list(self._worker_tasks)
        if self._reconcile_task is not None:
            tasks.append(self._reconcile_task)
        cancellable_tasks = [
            t for t in tasks if self._task_belongs_to_current_open_loop(t, current_loop) and not t.done()
        ]
        for task in cancellable_tasks:
            task.cancel()
        # Only await tasks that belong to the current event loop; tasks from a
        # previous (now-closed) loop cannot be cancelled or gathered safely and
        # are simply discarded from service state.
        if cancellable_tasks:
            await asyncio.gather(*cancellable_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        self._reconcile_task = None
        self._active_ids.clear()
        self._queued_ids.clear()
        self._deferred_ids.clear()
        self._deferred_order.clear()
        self._job_timestamps.clear()
        self._completed_ids.clear()
        self._final_refresh_ids.clear()
        self._crop_event_hints.clear()
        self._pending_queue = asyncio.Queue(maxsize=self.MAX_PENDING_QUEUE)
        self._queue_full_rejections = 0
        self._queue_full_deferrals = 0
        self._scheduled_total = 0
        self._duplicate_requests = 0
        self._disabled_requests = 0
        self._outcomes.clear()
        self._selected_sources.clear()
        self._classification_refinements.clear()
        self._reconciled_total = 0
        self._last_result = None

    @staticmethod
    def _task_belongs_to_current_open_loop(task: asyncio.Task, current_loop: asyncio.AbstractEventLoop) -> bool:
        try:
            task_loop = task.get_loop()
        except Exception:
            return False
        return task_loop is current_loop and not task_loop.is_closed()

    async def reset_state(self) -> None:
        await self.stop()

    async def _worker_loop(self, worker_index: int) -> None:
        while True:
            queue = self._pending_queue
            event_id = await queue.get()
            self._queued_ids.discard(event_id)
            if event_id in self._completed_ids and event_id not in self._final_refresh_ids:
                self._completed_ids.discard(event_id)
                self._crop_event_hints.pop(event_id, None)
                self._duplicate_requests += 1
                self._record_outcome(event_id, "duplicate")
                queue.task_done()
                continue
            if event_id in self._active_ids:
                self._crop_event_hints.pop(event_id, None)
                self._duplicate_requests += 1
                self._record_outcome(event_id, "duplicate")
                queue.task_done()
                continue
            self._final_refresh_ids.discard(event_id)
            self._active_ids.add(event_id)
            self._mark_job_active(event_id)
            try:
                await self.process_event(event_id)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(
                    "High-quality snapshot worker failed",
                    worker=worker_index,
                    event_id=event_id,
                    error=str(e),
                    exc_info=True,
                )
                self._record_outcome(event_id, "worker_exception")
                await self._persist_processing_outcome(event_id, "worker_exception")
            finally:
                self._active_ids.discard(event_id)
                queue.task_done()
                self._promote_deferred_events()
                self._forget_finished_job(event_id)

    def _ensure_workers_started(self) -> None:
        self._cleanup_completed_workers()
        while len(self._worker_tasks) < self.MAX_CONCURRENT_TASKS:
            worker_index = len(self._worker_tasks)
            task = create_background_task(
                self._worker_loop(worker_index),
                name=f"high_quality_snapshot_worker:{worker_index}",
            )
            self._worker_tasks.append(task)

    def _cleanup_completed_workers(self) -> None:
        alive_tasks: list[asyncio.Task] = []
        for task in self._worker_tasks:
            if task.done():
                if task.cancelled():
                    log.debug("High-quality snapshot worker cancelled", task=task.get_name())
                elif task.exception():
                    log.error("High-quality snapshot worker crashed", task=task.get_name(), error=str(task.exception()))
            else:
                alive_tasks.append(task)
        self._worker_tasks = alive_tasks

    def get_status(self) -> dict:
        self._cleanup_completed_workers()
        return {
            "enabled": self.enabled(),
            "active": len(self._active_ids),
            "queue_size": self._pending_queue.qsize(),
            "deferred": len(self._deferred_ids),
            "workers": len(self._worker_tasks),
            "recovery_running": self._running,
            "reconciled_total": self._reconciled_total,
            "scheduled_total": self._scheduled_total,
            "duplicate_requests": self._duplicate_requests,
            "disabled_requests": self._disabled_requests,
            "queue_full_rejections": self._queue_full_rejections,
            "queue_full_deferrals": self._queue_full_deferrals,
            "crop_hints": len(self._crop_event_hints),
            "final_refreshes": len(self._final_refresh_ids),
            "outcomes": dict(self._outcomes),
            "selected_sources": dict(self._selected_sources),
            "classification_refinements": dict(self._classification_refinements),
            "crop_policy": "best_available",
            "last_result": self._last_result,
        }

    def get_jobs_snapshot(self) -> list[dict[str, object]]:
        jobs: list[dict[str, object]] = []
        for event_id in sorted(self._active_ids):
            jobs.append(
                {
                    "id": f"high_quality_snapshot:{event_id}",
                    "event_id": event_id,
                    "kind": "high_quality_snapshot",
                    "source": "automatic",
                    "status": "running",
                    "phase": "selecting_best_frame",
                    "current": 0,
                    "total": 0,
                    "unit": "items",
                    "route": f"/events?detection={event_id}",
                    **self._job_timestamp_fields(event_id),
                    "error": None,
                }
            )
        for event_id in sorted(self._queued_ids | self._deferred_ids):
            jobs.append(
                {
                    "id": f"high_quality_snapshot:{event_id}",
                    "event_id": event_id,
                    "kind": "high_quality_snapshot",
                    "source": "automatic",
                    "status": "queued",
                    "phase": "waiting",
                    "current": 0,
                    "total": 0,
                    "unit": "items",
                    "route": f"/events?detection={event_id}",
                    **self._job_timestamp_fields(event_id),
                    "error": None,
                }
            )
        return jobs

    def _enqueue_pending(self, event_id: str) -> bool:
        try:
            self._pending_queue.put_nowait(event_id)
        except asyncio.QueueFull:
            return False
        self._queued_ids.add(event_id)
        self._mark_job_queued(event_id)
        return True

    def _defer_event(self, event_id: str) -> bool:
        """Bound overflow memory while leaving the detection itself intact for reconciliation."""
        if len(self._deferred_ids) >= self.MAX_DEFERRED_EVENTS:
            self._queue_full_rejections += 1
            log.warning(
                "High-quality snapshot overflow queue is full",
                event_id=event_id,
                pending=self._pending_queue.qsize(),
                deferred=len(self._deferred_ids),
            )
            return False
        self._deferred_ids.add(event_id)
        self._deferred_order.append(event_id)
        self._mark_job_queued(event_id)
        self._queue_full_deferrals += 1
        return True

    def _mark_job_queued(self, event_id: str) -> None:
        now = time.time()
        self._job_timestamps.setdefault(event_id, (now, now))

    def _mark_job_active(self, event_id: str) -> None:
        now = time.time()
        created_at, _updated_at = self._job_timestamps.get(event_id, (now, now))
        self._job_timestamps[event_id] = (created_at, now)

    def _forget_finished_job(self, event_id: str) -> None:
        if event_id not in self._active_ids and event_id not in self._queued_ids and event_id not in self._deferred_ids:
            self._job_timestamps.pop(event_id, None)

    def _job_timestamp_fields(self, event_id: str) -> dict[str, str]:
        now = time.time()
        created_at, updated_at = self._job_timestamps.setdefault(event_id, (now, now))
        return {
            "created_at": datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat(),
            "updated_at": datetime.fromtimestamp(updated_at, tz=timezone.utc).isoformat(),
        }

    def _promote_deferred_events(self) -> None:
        while self._deferred_order:
            if self._pending_queue.full():
                return

            event_id = self._deferred_order.popleft()
            if event_id not in self._deferred_ids:
                continue

            self._deferred_ids.discard(event_id)
            if event_id in self._completed_ids and event_id not in self._final_refresh_ids:
                self._completed_ids.discard(event_id)
                self._crop_event_hints.pop(event_id, None)
                self._duplicate_requests += 1
                self._record_outcome(event_id, "duplicate")
                continue
            if event_id in self._active_ids or event_id in self._queued_ids:
                self._crop_event_hints.pop(event_id, None)
                self._duplicate_requests += 1
                self._record_outcome(event_id, "duplicate")
                continue
            if not self._enqueue_pending(event_id):
                self._deferred_ids.add(event_id)
                self._deferred_order.appendleft(event_id)
                return

    async def _wait_for_clip(self, event_id: str) -> tuple[Optional[bytes], Optional[str]]:
        """Poll Frigate for clip availability with bounded retries."""
        await asyncio.sleep(self.INITIAL_DELAY_SECONDS)

        last_error: Optional[str] = None
        for attempt in range(self.MAX_CLIP_RETRIES + 1):
            clip_bytes, error = await frigate_client.get_clip_with_error(
                event_id,
                timeout=self.CLIP_FETCH_TIMEOUT_SECONDS,
            )
            if clip_bytes:
                return clip_bytes, None
            last_error = error or "clip_unavailable"
            if attempt >= self.MAX_CLIP_RETRIES:
                break
            await asyncio.sleep(self.CLIP_RETRY_INTERVAL_SECONDS * (2**attempt))
        return None, last_error

    def _extract_snapshot_from_clip(
        self,
        clip_bytes: bytes,
        event_data: Optional[dict[str, Any]] = None,
        clip_variant: str = "event",
    ) -> bytes:
        """Write clip bytes to a temp file and extract a representative JPEG frame."""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(clip_bytes)
            tmp_path = Path(tmp.name)

        try:
            return self._extract_snapshot_from_clip_path(
                tmp_path,
                event_data=event_data,
                clip_variant=clip_variant,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass

    def _store_crop_event_hints(self, event_id: str, event_data: Optional[dict[str, Any]]) -> None:
        hints = self._extract_crop_event_hints(event_data)
        if hints:
            self._crop_event_hints[event_id] = hints

    def _pop_crop_event_hints(self, event_id: str) -> Optional[dict[str, Any]]:
        return self._crop_event_hints.pop(event_id, None)

    def _extract_crop_event_hints(self, event_data: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not isinstance(event_data, dict):
            return None
        raw_payload = event_data.get("data")
        if not isinstance(raw_payload, dict):
            return None
        payload: dict[str, Any] = {}
        for key in ("box", "region"):
            raw_hint = raw_payload.get(key)
            if isinstance(raw_hint, (list, tuple)) and len(raw_hint) == 4:
                payload[key] = list(raw_hint)
        raw_path_data = raw_payload.get("path_data")
        if isinstance(raw_path_data, list):
            path_data = []
            for item in raw_path_data[:50]:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    point, timestamp = item[0], item[1]
                    if isinstance(point, (list, tuple)) and len(point) >= 2:
                        path_data.append([list(point[:2]), timestamp])
            if path_data:
                payload["path_data"] = path_data

        hints: dict[str, Any] = {"data": payload} if payload else {}
        raw_snapshot = event_data.get("snapshot")
        if isinstance(raw_snapshot, dict):
            snapshot: dict[str, Any] = {}
            raw_box = raw_snapshot.get("box")
            if isinstance(raw_box, (list, tuple)) and len(raw_box) == 4:
                snapshot["box"] = list(raw_box)
            frame_time = raw_snapshot.get("frame_time")
            if frame_time is not None:
                snapshot["frame_time"] = frame_time
            if snapshot:
                hints["snapshot"] = snapshot
        for key in ("start_time", "end_time"):
            value = event_data.get(key)
            if value is not None:
                hints[key] = value
        return hints or None

    async def _load_event_data_for_crop(self, event_id: str) -> Optional[dict[str, Any]]:
        """Fetch event metadata only when it can improve HQ bird-crop accuracy."""
        if not self._automatic_crop_enabled():
            return None

        try:
            event_data, error = await frigate_client.get_event_with_error(event_id, timeout=8.0)
        except Exception as e:
            log.debug("High-quality bird crop event metadata fetch failed", event_id=event_id, error=str(e))
            return None

        if not isinstance(event_data, dict):
            log.debug(
                "High-quality bird crop event metadata unavailable",
                event_id=event_id,
                reason=error or "event_unavailable",
            )
            return None
        return event_data

    def _maybe_crop_snapshot_bytes(
        self,
        event_id: str,
        image_bytes: bytes,
        event_data: Optional[dict[str, Any]] = None,
    ) -> tuple[bytes, bool]:
        """Optionally run the crop detector against the HQ frame, falling back to the frame."""
        if not self._automatic_crop_enabled():
            return image_bytes, False
        if not self._background_crop_work_allowed():
            log.debug("Skipping high-quality bird crop while classifier or MQTT pressure is active", event_id=event_id)
            return image_bytes, False

        try:
            with Image.open(BytesIO(image_bytes)) as img:
                source_image = img.convert("RGB")
        except Exception as e:
            log.warning("High-quality bird crop source decode failed", event_id=event_id, error=str(e))
            return image_bytes, False

        crop_result = self._crop_snapshot_best_available(source_image, event_data=event_data, event_id=event_id)

        crop_image = crop_result.get("crop_image") if isinstance(crop_result, dict) else None
        if not isinstance(crop_image, Image.Image):
            log.debug(
                "High-quality bird crop unavailable; keeping full HQ frame",
                event_id=event_id,
                reason=(crop_result or {}).get("reason") if isinstance(crop_result, dict) else "invalid_crop_result",
            )
            return image_bytes, False

        try:
            output = BytesIO()
            crop_image.convert("RGB").save(
                output,
                format="JPEG",
                quality=int(settings.media_cache.high_quality_event_snapshot_jpeg_quality),
                optimize=True,
            )
            log.debug(
                "High-quality bird crop applied",
                event_id=event_id,
                reason=str(crop_result.get("reason") or "crop"),
                crop_box=crop_result.get("box"),
            )
            return output.getvalue(), True
        except Exception as e:
            log.warning("High-quality bird crop encode failed", event_id=event_id, error=str(e))
            return image_bytes, False

    def _bird_crop_source_priority(self) -> str:
        configured = (
            str(getattr(settings.classification, "bird_crop_source_priority", DEFAULT_CROP_SOURCE_PRIORITY) or "")
            .strip()
            .lower()
        )
        return configured if configured in CROP_SOURCE_ORDERS else DEFAULT_CROP_SOURCE_PRIORITY

    def _crop_snapshot_by_priority(
        self,
        image: Image.Image,
        *,
        event_data: Optional[dict[str, Any]],
        event_id: str,
    ) -> Optional[dict[str, Any]]:
        last_result: Optional[dict[str, Any]] = None
        for source_mode in crop_source_order(self._bird_crop_source_priority()):
            if source_mode == "full_frame":
                break
            if source_mode == "model_crop":
                if not self._bird_crop_model_available():
                    continue
                result = self._crop_from_bird_model(image, event_id=event_id)
            else:  # frigate_hint_crop
                result = self._crop_from_event_hints(image, event_data)
            if self._has_crop_image(result):
                return result
            if result is not None:
                last_result = result
        return last_result

    def _crop_snapshot_best_available(
        self,
        image: Image.Image,
        *,
        event_data: Optional[dict[str, Any]],
        event_id: str,
    ) -> Optional[dict[str, Any]]:
        """Prefer Frigate's tracked-object crop, then use the detector, then the full frame."""
        hint_result = self._crop_from_event_hints(image, event_data)
        if self._has_crop_image(hint_result):
            return hint_result
        if self._bird_crop_model_available():
            model_result = self._crop_from_bird_model(image, event_id=event_id)
            if model_result is not None:
                return model_result
        return hint_result

    def _crop_from_bird_model(self, image: Image.Image, *, event_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        try:
            crop_result = bird_crop_service.generate_crop(image, detector_tier="accurate")
        except Exception as e:
            log.warning("High-quality bird crop generation failed", event_id=event_id, error=str(e))
            return None
        if not self._has_crop_image(crop_result):
            return crop_result if isinstance(crop_result, dict) else None
        return self._expand_model_crop_context(image, crop_result)

    def _crop_candidate_from_bird_model(
        self,
        image: Image.Image,
        *,
        event_id: Optional[str] = None,
        search_box: tuple[int, int, int, int] | None = None,
    ) -> Optional[dict[str, Any]]:
        """Generate an evidence-only crop while retaining the full-frame peer."""
        guided_generator = getattr(bird_crop_service, "generate_guided_classification_candidate_crop", None)
        guided_declared = callable(
            getattr(type(bird_crop_service), "generate_guided_classification_candidate_crop", None)
        )
        if search_box is not None and callable(guided_generator) and guided_declared:
            try:
                crop_result = guided_generator(image, search_box=search_box)
            except Exception as e:
                log.warning("High-quality guided bird crop generation failed", event_id=event_id, error=str(e))
                crop_result = None
            if self._has_crop_image(crop_result):
                return self._expand_model_crop_context(image, crop_result)
            if isinstance(crop_result, dict):
                return crop_result

        candidate_generator = getattr(bird_crop_service, "generate_classification_candidate_crop", None)
        declared_on_type = callable(getattr(type(bird_crop_service), "generate_classification_candidate_crop", None))
        if not callable(candidate_generator) or not declared_on_type:
            return self._crop_from_bird_model(image, event_id=event_id)
        try:
            crop_result = candidate_generator(image)
        except Exception as e:
            log.warning("High-quality bird crop candidate generation failed", event_id=event_id, error=str(e))
            return None
        if not self._has_crop_image(crop_result):
            return crop_result if isinstance(crop_result, dict) else None
        return self._expand_model_crop_context(image, crop_result)

    @staticmethod
    def _has_crop_image(crop_result: Any) -> bool:
        return isinstance(crop_result, dict) and isinstance(crop_result.get("crop_image"), Image.Image)

    def _expand_model_crop_context(self, image: Image.Image, crop_result: dict[str, Any]) -> dict[str, Any]:
        box = self._normalize_crop_box(crop_result.get("box"), image.size)
        if box is None:
            return crop_result
        expanded = self._expand_box_by_ratio(
            box,
            image.size,
            expand_ratio=HQ_MODEL_CROP_EXTRA_EXPAND_RATIO,
            min_crop_size=1,
        )
        if expanded is None or expanded == box:
            return crop_result
        updated = dict(crop_result)
        updated["crop_image"] = image.crop(expanded)
        updated["box"] = expanded
        return updated

    def _normalize_crop_box(
        self,
        raw_box: Any,
        image_size: tuple[int, int],
    ) -> Optional[tuple[int, int, int, int]]:
        if not isinstance(raw_box, (list, tuple)) or len(raw_box) != 4:
            return None
        try:
            left = float(raw_box[0])
            top = float(raw_box[1])
            right = float(raw_box[2])
            bottom = float(raw_box[3])
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (left, top, right, bottom)):
            return None
        image_width, image_height = image_size
        left_i = max(0, min(image_width, int(math.floor(left))))
        top_i = max(0, min(image_height, int(math.floor(top))))
        right_i = max(0, min(image_width, int(math.ceil(right))))
        bottom_i = max(0, min(image_height, int(math.ceil(bottom))))
        if right_i <= left_i or bottom_i <= top_i:
            return None
        return left_i, top_i, right_i, bottom_i

    def _crop_from_event_hints(
        self,
        image: Image.Image,
        event_data: Optional[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        raw_payload = (event_data or {}).get("data") if isinstance(event_data, dict) else None
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        for hint_key, reason in (("box", "frigate_box"), ("region", "frigate_region")):
            box = self._restore_frigate_hint_box(payload.get(hint_key), image.size)
            if box is None:
                continue
            expanded = self._expand_hint_box(box, image.size)
            if expanded is None:
                continue
            return {
                "crop_image": image.crop(expanded),
                "box": expanded,
                "confidence": None,
                "reason": reason,
            }
        return None

    def _restore_frigate_hint_box(
        self,
        raw_hint: Any,
        image_size: tuple[int, int],
    ) -> Optional[tuple[int, int, int, int]]:
        if not isinstance(raw_hint, (list, tuple)) or len(raw_hint) != 4:
            return None
        try:
            left = float(raw_hint[0])
            top = float(raw_hint[1])
            width = float(raw_hint[2])
            height = float(raw_hint[3])
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (left, top, width, height)):
            return None

        image_width, image_height = image_size
        normalized = 0.0 <= left <= 1.0 and 0.0 <= top <= 1.0 and 0.0 <= width <= 1.0 and 0.0 <= height <= 1.0
        if normalized:
            left *= float(image_width)
            top *= float(image_height)
            width *= float(image_width)
            height *= float(image_height)

        right = left + width
        bottom = top + height
        if right <= left or bottom <= top:
            return None
        left_i = max(0, min(image_width, int(math.floor(left))))
        top_i = max(0, min(image_height, int(math.floor(top))))
        right_i = max(0, min(image_width, int(math.ceil(right))))
        bottom_i = max(0, min(image_height, int(math.ceil(bottom))))
        if right_i <= left_i or bottom_i <= top_i:
            return None
        return left_i, top_i, right_i, bottom_i

    def _expand_hint_box(
        self,
        box: tuple[int, int, int, int],
        image_size: tuple[int, int],
    ) -> Optional[tuple[int, int, int, int]]:
        left, top, right, bottom = box
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None
        expand_ratio = HQ_HINT_CROP_EXPAND_RATIO
        min_crop_size = 96
        try:
            crop_policy = bird_crop_service.get_effective_crop_policy()
        except Exception:
            crop_policy = None
        try:
            raw_expand_ratio = getattr(bird_crop_service, "hint_expand_ratio", None)
            if isinstance(raw_expand_ratio, bool):
                raw_expand_ratio = None
            if isinstance(raw_expand_ratio, (int, float, str)):
                expand_ratio = max(0.0, float(raw_expand_ratio))
        except Exception:
            expand_ratio = HQ_HINT_CROP_EXPAND_RATIO
        try:
            if isinstance(crop_policy, dict):
                min_crop_size = max(1, int(crop_policy.get("min_crop_size", min_crop_size)))
            else:
                min_crop_size = max(1, int(getattr(bird_crop_service, "min_crop_size", min_crop_size)))
        except Exception:
            min_crop_size = 96

        return self._expand_box_by_ratio(
            box,
            image_size,
            expand_ratio=expand_ratio,
            min_crop_size=min_crop_size,
        )

    def _expand_box_by_ratio(
        self,
        box: tuple[int, int, int, int],
        image_size: tuple[int, int],
        *,
        expand_ratio: float,
        min_crop_size: int,
    ) -> Optional[tuple[int, int, int, int]]:
        left, top, right, bottom = box
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            return None

        pad_x = int(round(width * max(0.0, expand_ratio)))
        pad_y = int(round(height * max(0.0, expand_ratio)))
        expanded_left = max(0, left - pad_x)
        expanded_top = max(0, top - pad_y)
        expanded_right = min(int(image_size[0]), right + pad_x)
        expanded_bottom = min(int(image_size[1]), bottom + pad_y)
        crop_width = expanded_right - expanded_left
        crop_height = expanded_bottom - expanded_top
        if crop_width < min_crop_size or crop_height < min_crop_size:
            return None
        if expanded_right <= expanded_left or expanded_bottom <= expanded_top:
            return None
        return expanded_left, expanded_top, expanded_right, expanded_bottom

    def _candidate_frame_indices(
        self,
        *,
        frame_count: int,
        fps: float,
        event_data: Optional[dict[str, Any]] = None,
        clip_variant: str = "event",
    ) -> list[int]:
        if frame_count <= 0:
            return [0]

        target_indices = []
        if str(clip_variant or "event").strip().lower() == "event":
            target_indices = self._target_frame_indices_from_event_path(
                frame_count=frame_count,
                fps=fps,
                event_data=event_data,
            )
        mid = frame_count // 2
        center_weighted_anchors = [mid, frame_count // 4, (frame_count * 3) // 4]
        if not math.isfinite(fps) or fps <= 0.0:
            return [(target_indices or center_weighted_anchors)[0]]

        path_candidates = list(target_indices)
        if len(path_candidates) >= 2:
            path_candidates.append(int(round((min(path_candidates) + max(path_candidates)) / 2.0)))
        selected = self._select_temporally_diverse_frame_indices(
            path_candidates or center_weighted_anchors,
            frame_count=frame_count,
            fps=fps,
            max_samples=HQ_MAX_CROP_SCORING_FRAMES,
        )
        min_gap = self._minimum_temporal_frame_gap(fps)
        for anchor in center_weighted_anchors:
            if len(selected) >= HQ_MAX_CROP_SCORING_FRAMES:
                break
            if all(abs(anchor - chosen) >= min_gap for chosen in selected):
                selected.append(anchor)
        return selected

    @staticmethod
    def _minimum_temporal_frame_gap(fps: float) -> int:
        if not math.isfinite(fps) or fps <= 0.0:
            return 1
        return max(1, int(math.ceil(fps * HQ_REFINEMENT_MIN_TEMPORAL_SEPARATION_SECONDS)))

    def _select_temporally_diverse_frame_indices(
        self,
        raw_indices: list[int],
        *,
        frame_count: int,
        fps: float,
        max_samples: int,
    ) -> list[int]:
        """Select relevant frame targets while maximizing temporal diversity.

        The first target retains upstream relevance ordering (for example the
        tracked path point nearest the Frigate box centre). Later targets are
        chosen by farthest-point sampling, with preference order breaking ties.
        If FPS is unknown, only one evidence slot is returned because temporal
        independence cannot be proven.
        """

        if max_samples <= 0 or frame_count <= 0:
            return []
        normalized: list[int] = []
        seen: set[int] = set()
        for raw_index in raw_indices:
            try:
                index = max(0, min(frame_count - 1, int(raw_index)))
            except (TypeError, ValueError):
                continue
            if index in seen:
                continue
            seen.add(index)
            normalized.append(index)
        if not normalized:
            return [0]
        if not math.isfinite(fps) or fps <= 0.0:
            return normalized[:1]

        min_gap = self._minimum_temporal_frame_gap(fps)
        selected = [normalized[0]]
        while len(selected) < max_samples:
            eligible = [
                (rank, index)
                for rank, index in enumerate(normalized)
                if index not in selected and all(abs(index - chosen) >= min_gap for chosen in selected)
            ]
            if not eligible:
                break
            _rank, next_index = max(
                eligible,
                key=lambda item: (min(abs(item[1] - chosen) for chosen in selected), -item[0]),
            )
            selected.append(next_index)
        return selected

    def _read_temporally_independent_frame(
        self,
        cap: Any,
        *,
        target_frame_index: int,
        frame_count: int,
        fps: float,
        used_frame_indices: list[int],
    ) -> Optional[tuple[int, Any]]:
        """Decode one evidence slot, using neighbours only as same-slot fallbacks."""

        safe_count = max(frame_count, 1)
        min_gap = self._minimum_temporal_frame_gap(fps)
        tried: set[int] = set()
        for delta in (0, -1, 1, -2, 2):
            frame_index = max(0, min(safe_count - 1, int(target_frame_index) + delta))
            if frame_index in tried:
                continue
            tried.add(frame_index)
            if any(abs(frame_index - used) < min_gap for used in used_frame_indices):
                continue
            if frame_count > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            actual_index = frame_index
            with contextlib.suppress(Exception):
                position = float(cap.get(cv2.CAP_PROP_POS_FRAMES) or 0.0)
                if math.isfinite(position) and position >= 1.0:
                    actual_index = max(0, min(safe_count - 1, int(round(position - 1.0))))
            if any(abs(actual_index - used) < min_gap for used in used_frame_indices):
                continue
            return actual_index, frame
        return None

    def _target_frame_indices_from_event_path(
        self,
        *,
        frame_count: int,
        fps: float,
        event_data: Optional[dict[str, Any]],
    ) -> list[int]:
        if frame_count <= 0 or fps <= 0.0 or not isinstance(event_data, dict):
            return []
        try:
            start_time = float(event_data.get("start_time"))
        except (TypeError, ValueError):
            return []
        if not math.isfinite(start_time):
            return []

        raw_payload = event_data.get("data")
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        path_points: list[tuple[float, float, float]] = []
        for item in payload.get("path_data") or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            point = item[0]
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                x = float(point[0])
                y = float(point[1])
                timestamp = float(item[1])
            except (TypeError, ValueError):
                continue
            if math.isfinite(x) and math.isfinite(y) and math.isfinite(timestamp):
                path_points.append((timestamp, x, y))
        if not path_points:
            return []

        ordered_timestamps = self._ordered_path_timestamps_for_crop(payload, path_points)
        clip_duration_seconds = float(frame_count) / float(fps)
        indices: list[int] = []
        for target_time in ordered_timestamps:
            offset_seconds = max(0.0, target_time - start_time)
            offset_seconds = min(offset_seconds, max(0.0, clip_duration_seconds))
            indices.append(int(round(offset_seconds * fps)))
        return indices

    def _ordered_path_timestamps_for_crop(
        self,
        payload: dict[str, Any],
        path_points: list[tuple[float, float, float]],
    ) -> list[float]:
        ordered: list[float] = []
        seen: set[float] = set()

        def add_timestamp(timestamp: float) -> None:
            if timestamp in seen:
                return
            seen.add(timestamp)
            ordered.append(timestamp)

        box_bottom_center = self._normalized_box_bottom_center(payload)
        if box_bottom_center is not None:
            bottom_center_x, bottom_y = box_bottom_center
            normalized_points = [item for item in path_points if 0.0 <= item[1] <= 1.0 and 0.0 <= item[2] <= 1.0]
            for timestamp, _x, _y in sorted(
                normalized_points,
                key=lambda item: ((item[1] - bottom_center_x) ** 2 + (item[2] - bottom_y) ** 2, item[0]),
            ):
                add_timestamp(timestamp)

        by_time = sorted(path_points, key=lambda item: item[0])
        fallback_indices = [len(by_time) // 2, len(by_time) - 1, 0]
        for index in fallback_indices:
            add_timestamp(by_time[index][0])
        return ordered

    def _normalized_box_bottom_center(self, payload: dict[str, Any]) -> Optional[tuple[float, float]]:
        raw_box = payload.get("box")
        if not isinstance(raw_box, (list, tuple)) or len(raw_box) != 4:
            return None
        try:
            x, y, width, height = [float(value) for value in raw_box]
        except (TypeError, ValueError):
            return None
        if not all(math.isfinite(value) for value in (x, y, width, height)):
            return None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 < width <= 1.0 and 0.0 < height <= 1.0):
            return None
        return x + width / 2.0, y + height

    def _extract_snapshot_from_clip_path(
        self,
        clip_path: Path,
        event_data: Optional[dict[str, Any]] = None,
        clip_variant: str = "event",
    ) -> bytes:
        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            raise ValueError(f"Unable to open clip for snapshot extraction: {clip_path}")

        try:
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            candidate_indices = self._candidate_frame_indices(
                frame_count=frame_count,
                fps=fps,
                event_data=event_data,
                clip_variant=clip_variant,
            )
            score_crops = bool(
                self._automatic_crop_enabled()
                and self._bird_crop_model_available()
                and self._background_crop_work_allowed()
            )

            seen: set[int] = set()
            first_readable: bytes | None = None
            best_crop_frame: tuple[float, bytes] | None = None
            crop_frames_scored = 0
            for frame_index in candidate_indices:
                if frame_index in seen:
                    continue
                seen.add(frame_index)
                if frame_count > 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = cap.read()
                if ok and frame is not None:
                    encoded_ok, encoded = cv2.imencode(
                        ".jpg",
                        frame,
                        [
                            int(cv2.IMWRITE_JPEG_QUALITY),
                            int(settings.media_cache.high_quality_event_snapshot_jpeg_quality),
                        ],
                    )
                    if not encoded_ok:
                        raise ValueError("Failed to encode extracted frame as JPEG")
                    encoded_bytes = encoded.tobytes()
                    if first_readable is None:
                        first_readable = encoded_bytes
                    if not score_crops:
                        return encoded_bytes

                    if crop_frames_scored < HQ_MAX_CROP_SCORING_FRAMES:
                        crop_frames_scored += 1
                        crop_score = self._score_frame_for_bird_crop(frame, frame_order=crop_frames_scored)
                        if crop_score is not None and (best_crop_frame is None or crop_score > best_crop_frame[0]):
                            best_crop_frame = (crop_score, encoded_bytes)
                    if crop_frames_scored >= HQ_MAX_CROP_SCORING_FRAMES and first_readable is not None:
                        break

            if best_crop_frame is not None:
                return best_crop_frame[1]
            if first_readable is not None:
                return first_readable

            raise ValueError("No readable frame found in clip")
        finally:
            cap.release()

    def _score_frame_for_bird_crop(self, frame: Any, *, frame_order: int) -> Optional[float]:
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb_frame).convert("RGB")
        except Exception as e:
            log.debug("High-quality crop frame conversion failed", error=str(e))
            return None

        crop_result = self._crop_candidate_from_bird_model(image)
        if not self._has_crop_image(crop_result):
            return None
        return self._score_crop_result(crop_result, image.size, frame_order=frame_order)

    def _bird_crop_model_available(self) -> bool:
        get_status = getattr(bird_crop_service, "get_status", None)
        if not callable(get_status):
            return True
        try:
            status = get_status()
        except Exception:
            return True
        if not isinstance(status, dict):
            return True
        installed = status.get("installed")
        if installed is False:
            return False
        enabled = status.get("enabled_for_runtime")
        if enabled is False:
            return False
        return True

    def _background_crop_work_allowed(self) -> bool:
        """Keep optional HQ crop inference out of issue-33 pressure paths."""
        return self._mqtt_pressure_allows_background_crop() and self._classifier_pressure_allows_background_crop()

    def _mqtt_pressure_allows_background_crop(self) -> bool:
        try:
            from app.services.mqtt_service import mqtt_service

            status = mqtt_service.get_status() or {}
        except Exception:
            return True
        if not isinstance(status, dict):
            return True
        pressure_level = str(status.get("pressure_level") or "normal").lower()
        if pressure_level in {"elevated", "high", "critical"}:
            return False
        if bool(status.get("under_pressure")):
            return False
        if bool(status.get("backlog_wait_active")):
            return False
        if bool(status.get("recent_handler_slot_wait_exhaustion")):
            return False
        return True

    def _classifier_pressure_allows_background_crop(self) -> bool:
        try:
            classifier_module = sys.modules.get("app.services.classifier_service")
            if classifier_module is None:
                return True
            classifier = getattr(classifier_module, "_classifier_instance", None)
            if classifier is None:
                return True
            get_admission_status = getattr(classifier, "get_admission_status", None)
            if not callable(get_admission_status):
                return True
            status = get_admission_status() or {}
        except Exception:
            return True
        if not isinstance(status, dict):
            return True

        live = status.get("live") if isinstance(status.get("live"), dict) else {}
        background = status.get("background") if isinstance(status.get("background"), dict) else {}
        live_busy = self._safe_status_int(live.get("queued")) > 0 or self._safe_status_int(live.get("running")) > 0
        background_busy = (
            self._safe_status_int(background.get("queued")) > 0 or self._safe_status_int(background.get("running")) > 0
        )
        if live_busy or background_busy:
            return False
        if bool(status.get("background_throttled")):
            return False
        return True

    @staticmethod
    def _safe_status_int(value: Any) -> int:
        try:
            parsed = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return max(0, parsed)

    def _score_crop_result(
        self,
        crop_result: dict[str, Any],
        image_size: tuple[int, int],
        *,
        frame_order: int,
    ) -> Optional[float]:
        crop_image = crop_result.get("crop_image")
        if not isinstance(crop_image, Image.Image):
            return None
        confidence = self._finite_float(crop_result.get("confidence"))
        if confidence is None:
            confidence = 0.5

        box = self._normalize_crop_box(crop_result.get("box"), image_size)
        image_area = max(1, int(image_size[0]) * int(image_size[1]))
        if box is not None:
            crop_area = max(1, (box[2] - box[0]) * (box[3] - box[1]))
        else:
            crop_area = max(1, int(crop_image.width) * int(crop_image.height))
        area_bonus = min(0.05, crop_area / image_area * 0.05)
        order_penalty = max(0, frame_order - 1) * 0.001
        return confidence + area_bonus - order_penalty

    @staticmethod
    def _finite_float(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(parsed):
            return None
        return parsed

    def _record_outcome(self, event_id: str, result: str) -> str:
        self._outcomes[result] += 1
        self._last_result = {"event_id": event_id, "result": result}
        return result

    async def _processing_retry_allowed(self, event_id: str, *, now: datetime) -> bool:
        try:
            async with get_db() as db:
                state = await ProcessingJobRepository(db).get(HQ_PROCESSING_PIPELINE, event_id)
        except Exception as exc:
            # Database observability must not disable a best-effort media path.
            log.warning("Unable to read HQ snapshot retry state", event_id=event_id, error=str(exc))
            return True
        return state is None or state.can_attempt(now)

    async def _persist_processing_outcome(self, event_id: str, result: str) -> None:
        if result in {"disabled", "duplicate"}:
            return
        try:
            async with get_db() as db:
                repo = ProcessingJobRepository(db)
                if result in {"replaced", "bird_crop_replaced"}:
                    await repo.record_success(HQ_PROCESSING_PIPELINE, event_id)
                    return
                state = await repo.record_failure(
                    HQ_PROCESSING_PIPELINE,
                    event_id,
                    error=result,
                    retry_delays_seconds=HQ_RETRY_DELAYS_SECONDS,
                )
        except Exception as exc:
            log.warning(
                "Unable to persist HQ snapshot retry state",
                event_id=event_id,
                result=result,
                error=str(exc),
            )
            return
        log.info(
            "Recorded HQ snapshot retry state",
            event_id=event_id,
            result=result,
            status=state.status,
            attempt_count=state.attempt_count,
            retry_after=state.retry_after.isoformat() if state.retry_after else None,
        )


high_quality_snapshot_service = HighQualitySnapshotService()
