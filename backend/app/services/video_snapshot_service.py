"""Keep a visit's photograph aligned with its accepted video evidence."""

import asyncio
import hashlib
from io import BytesIO
import math
import json
from pathlib import Path
from typing import Any

import cv2
from PIL import Image
import structlog

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.repositories.processing_job_repository import ProcessingJobRepository
from app.repositories.bird_observation_repository import BirdObservationRepository
from app.utils.api_datetime import serialize_storage_datetime, utc_naive_now
from app.utils.photo_retention import MAX_EARLIER_PHOTO_CHOICES, merge_photo_choices
from app.services.archive_service import archive_service
from app.services.media_cache import media_cache, validate_film_alignment
from app.services.photo_choice_actions import photo_choice_lock
from app.utils.canonical_species import should_hide_species_label
from app.utils.blocked_species import is_blocked_species
from app.services.photo_presence import (
    DETECTOR_PHOTO_STRATEGY,
    has_localized_bird,
    has_reusable_bird_presence,
    has_confident_photo_species,
)

log = structlog.get_logger()


def _label_key(value: object) -> str:
    return " ".join(str(value or "").replace("_", " ").split()).casefold()


def _verified_moment(
    evidence: object,
) -> tuple[int, tuple[int, int], tuple[int, int, int, int] | None] | None:
    """Return the frame, frame size and crop a piece of evidence claims, or None when it is not trustworthy."""
    if not isinstance(evidence, dict):
        return None
    frame_index = evidence.get("frame_index")
    dimensions = (evidence.get("frame_width"), evidence.get("frame_height"))
    if type(frame_index) is not int or frame_index < 0:
        return None
    if any(type(size) is not int or size <= 0 for size in dimensions) or math.prod(dimensions) > 64_000_000:
        return None
    score = evidence.get("score")
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not math.isfinite(score)
        or not 0 <= score <= 1
    ):
        return None
    box = evidence.get("crop_box")
    if box is not None:
        if (
            not isinstance(box, (list, tuple))
            or len(box) != 4
            or any(type(coordinate) is not int for coordinate in box)
        ):
            return None
        left, top, right, bottom = box
        if not 0 <= left < right <= dimensions[0] or not 0 <= top < bottom <= dimensions[1]:
            return None
        return frame_index, dimensions, (left, top, right, bottom)
    if evidence.get("input_is_cropped") and evidence.get("input_source") in {
        "model_crop",
        "frigate_hint_crop",
        "frigate_region_crop",
    }:
        return None
    return frame_index, dimensions, None


def extract_video_snapshots(clip_path: Path, evidences: list[object]) -> list[tuple[Image.Image, Image.Image] | None]:
    """Decode several verified moments in one forward pass, keeping each one's exact crop geometry."""
    from app.services.classifier_service import _read_selected_video_frames

    moments = [_verified_moment(evidence) for evidence in evidences]
    extracted: list[tuple[Image.Image, Image.Image] | None] = [None] * len(evidences)
    if not any(moments):
        return extracted
    capture = cv2.VideoCapture(str(clip_path))
    try:
        if not capture.isOpened():
            return extracted
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        wanted = sorted({moment[0] for moment in moments if moment is not None and moment[0] < frame_count})
        scenes: dict[int, Image.Image] = {}
        for frame_index, decoded, frame in _read_selected_video_frames(capture, wanted):
            if decoded:
                scenes[frame_index] = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGB")
        for position, moment in enumerate(moments):
            if moment is None:
                continue
            frame_index, dimensions, box = moment
            scene = scenes.get(frame_index)
            if scene is None or scene.size != dimensions:
                continue
            extracted[position] = (scene.crop(box) if box is not None else scene), scene
        return extracted
    finally:
        capture.release()


def extract_video_snapshot(clip_path: Path, evidence: dict[str, Any]) -> tuple[Image.Image, Image.Image] | None:
    """Decode one verified moment, retaining its exact crop geometry without ML."""
    return extract_video_snapshots(clip_path, [evidence])[0]


def _jpeg(image: Image.Image, *, thumbnail: bool = False) -> bytes:
    image = image.copy()
    if thumbnail:
        image.thumbnail((320, 240))
    output = BytesIO()
    image.save(output, "JPEG", quality=85 if thumbnail else 95)
    return output.getvalue()


def _candidates(
    event_id: str,
    result: dict[str, Any],
    evidence: dict[str, Any],
    images: tuple[Image.Image, Image.Image],
    clip_variant: str,
) -> list[dict[str, Any]]:
    portrait, scene = images
    cropped = bool(evidence.get("input_is_cropped"))
    source = "video_evidence_crop" if cropped else "video_evidence_full_frame"
    crop_mode = (
        evidence.get("input_source")
        if evidence.get("input_source") in {"frigate_region_crop", "frigate_hint_crop"}
        else "model_crop"
    )
    roles = (
        [("full_frame", scene, False)] if not cropped else [("full_frame", scene, False), (crop_mode, portrait, True)]
    )
    rows = []
    created_at = serialize_storage_datetime(utc_naive_now())
    for mode, image, selected in roles:
        selected = selected or not cropped
        image_bytes = _jpeg(image)
        digest = hashlib.sha256(
            f"{event_id}:video_evidence:{clip_variant}:{mode}:{evidence.get('crop_box')}".encode() + image_bytes
        ).hexdigest()[:10]
        candidate_id = f"{event_id}__{mode}__f{evidence['frame_index']}__{digest}"
        rows.append(
            {
                "candidate_id": candidate_id,
                "frame_index": evidence["frame_index"],
                "frame_offset_seconds": evidence.get("frame_offset_seconds"),
                "source_mode": mode,
                "clip_variant": clip_variant,
                "crop_box": evidence.get("crop_box") if selected and cropped else None,
                "crop_strategy": DETECTOR_PHOTO_STRATEGY if has_localized_bird(evidence) else "video_evidence",
                "crop_confidence": evidence.get("detector_confidence"),
                "selected": selected,
                "classifier_label": result["label"] if selected else None,
                "classifier_score": evidence["score"] if selected else None,
                "ranking_score": evidence["score"] if selected else 0,
                "snapshot_source": source if selected else "video_evidence_full_frame",
                "image_ref": f"{candidate_id}__image",
                "thumbnail_ref": f"{candidate_id}__thumb",
                "content_sha256": hashlib.sha256(image_bytes).hexdigest(),
                "created_at": created_at,
                "image_bytes": image_bytes,
                "thumbnail_bytes": _jpeg(image, thumbnail=True),
            }
        )
    return rows


def _retained_thumbnail(image_bytes: bytes) -> bytes | None:
    try:
        from app.utils.image_io import decode_image_bytes

        return _jpeg(decode_image_bytes(image_bytes, convert_rgb=True), thumbnail=True)
    except Exception:
        return None


async def _cached_candidate_photo(reference: str) -> bytes | None:
    try:
        return await media_cache.get_snapshot(reference)
    except Exception as exc:
        log.warning("Snapshot candidate could not be read", reference=reference, error=str(exc))
        return None


async def retained_snapshot_candidate(
    event_id: str,
    photo: bytes | None,
    metadata: dict[str, Any],
    existing: list[dict[str, Any]],
    *,
    replaced_candidate_ids: set[str] | None = None,
    photo_content_sha256: str | None = None,
) -> dict[str, Any] | None:
    """Keep the prior photograph before replacement; the caller holds its commit lock."""
    if not photo:
        return None
    content_sha256 = photo_content_sha256 or await asyncio.to_thread(lambda: hashlib.sha256(photo).hexdigest())
    candidate_id = f"{event_id}__retained_snapshot__{content_sha256[:12]}"
    replaced_candidate_ids = replaced_candidate_ids or set()
    created_at = serialize_storage_datetime(utc_naive_now())
    for old in existing:
        if old.get("content_sha256") == content_sha256 and old.get("image_ref"):
            if await asyncio.to_thread(media_cache._snapshot_path(old["image_ref"]).is_file):
                if old["candidate_id"] not in replaced_candidate_ids:
                    return None
                created_at = min(created_at, str(old.get("created_at") or created_at))
    legacy = [old for old in existing if not old.get("content_sha256") and old.get("image_ref")]
    legacy.sort(
        key=lambda row: (
            row.get("candidate_id") == candidate_id,
            bool(row.get("selected")),
            str(row.get("created_at") or ""),
        ),
        reverse=True,
    )
    for old in legacy[:MAX_EARLIER_PHOTO_CHOICES]:
        if await _cached_candidate_photo(old["image_ref"]) == photo:
            old["content_sha256"] = content_sha256
            if old["candidate_id"] not in replaced_candidate_ids:
                return None
            created_at = min(created_at, str(old.get("created_at") or created_at))
    thumbnail = await asyncio.to_thread(_retained_thumbnail, photo)
    return {
        "candidate_id": candidate_id,
        "frame_index": 0,
        "frame_offset_seconds": None,
        "source_mode": "retained_photo",
        "clip_variant": "retained_snapshot",
        "classifier_label": None,
        "classifier_score": None,
        "ranking_score": 0,
        "selected": False,
        "snapshot_source": metadata.get("source") or "cached_snapshot_unknown",
        "image_ref": f"{candidate_id}__image",
        "thumbnail_ref": f"{candidate_id}__thumb" if thumbnail else None,
        "content_sha256": content_sha256,
        "created_at": created_at,
        "image_bytes": photo,
        "thumbnail_bytes": thumbnail,
        "film_alignment": metadata.get("film_alignment"),
    }


async def prune_unreferenced_photo_files(existing: list[dict[str, Any]], retained: list[dict[str, Any]]) -> None:
    """Delete superseded candidate files only after their row replacement commits."""
    for field, delete in (("image_ref", media_cache.delete_snapshot), ("thumbnail_ref", media_cache.delete_thumbnail)):
        kept = {row.get(field) for row in retained if row.get(field)}
        stale = {row.get(field) for row in existing if row.get(field)} - kept
        for reference in sorted(stale):
            try:
                await delete(reference)
            except Exception as exc:
                log.warning("Unable to prune earlier photo file", reference=reference, error=str(exc))


async def _snapshot_preservation_outcome(
    event_id: str,
    result: dict[str, Any],
    metadata: dict[str, Any],
    existing: list[dict[str, Any]],
    repo: DetectionRepository,
    *,
    automatic: bool,
) -> str | None:
    from app.services.high_quality_snapshot_service import HQ_PROCESSING_PIPELINE

    if metadata.get("manual_selection"):
        return "manual_selection_preserved"
    state = await ProcessingJobRepository(repo.db).get(HQ_PROCESSING_PIPELINE, event_id)
    if state and state.last_error == "storage_evicted":
        return "storage_evicted"
    detection = await repo.get_by_frigate_event(event_id)
    if detection is None or (automatic and detection.manual_tagged) or detection.is_hidden:
        return "owner_identification_preserved"
    if is_blocked_species(
        blocked_labels=settings.classification.blocked_labels,
        blocked_species=settings.classification.blocked_species,
        label=result.get("label"),
        scientific_name=detection.scientific_name,
        common_name=detection.common_name,
        taxa_id=detection.taxa_id,
        extra_labels=[detection.category_name, detection.display_name],
    ):
        return "blocked_species"
    expected = {
        _label_key(getattr(detection, field, None))
        for field in ("category_name", "scientific_name", "common_name", "display_name")
    }
    if _label_key(result.get("label")) not in expected:
        return "primary_identity_preserved"
    current = next((item for item in existing if item.get("selected")), None)
    if (
        current
        and (
            settings.media_cache.high_quality_event_snapshots
            or str(metadata.get("source") or "").startswith("video_evidence_")
        )
        and _label_key(current.get("classifier_label")) in expected
        and has_confident_photo_species(current, threshold=settings.classification.threshold)
        and current.get("image_ref")
        and has_reusable_bird_presence(current)
    ):
        current_bytes = await _cached_candidate_photo(current["image_ref"])
        if current_bytes and current_bytes == await media_cache.get_snapshot(event_id):
            return "matching_photo_preserved"
    return None


async def _snapshot_preflight(event_id: str, result: dict[str, Any], *, automatic: bool) -> str | None:
    # An affirmative preservation decision needs no decoding or write reservation.
    # Any staged replacement repeats these checks under the final commit lock.
    async with media_cache._media_write_lease(event_id), media_cache._snapshot_commit_lock(event_id):
        metadata = await media_cache.get_snapshot_metadata(event_id) or {}
        async with get_db() as db:
            repo = DetectionRepository(db)
            existing = await repo.list_snapshot_candidates(event_id)
            return await _snapshot_preservation_outcome(event_id, result, metadata, existing, repo, automatic=automatic)


async def _commit_video_snapshot(
    event_id: str,
    result: dict[str, Any],
    evidence: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    automatic: bool,
) -> str:
    async with photo_choice_lock(event_id):
        return await _commit_video_snapshot_unlocked(event_id, result, evidence, candidates, automatic=automatic)


async def _commit_video_snapshot_unlocked(
    event_id: str,
    result: dict[str, Any],
    evidence: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    automatic: bool,
) -> str:
    selected = next(candidate for candidate in candidates if candidate["selected"])
    async with media_cache._media_write_lease(event_id), media_cache._snapshot_commit_lock(event_id):
        metadata = await media_cache.get_snapshot_metadata(event_id) or {}
        if metadata.get("manual_selection"):
            return "manual_selection_preserved"
        from app.services.high_quality_snapshot_service import high_quality_snapshot_service

        if not await high_quality_snapshot_service._available_photo_candidates(event_id, [selected]):
            return "photo_choice_removed"
        previous_photo = await media_cache.get_snapshot(event_id)
        async with get_db() as db:
            existing = await DetectionRepository(db).list_snapshot_candidates(event_id)
        legacy_removed_hashes = {}
        for row in existing:
            if row.get("photo_hidden") and not row.get("content_sha256") and row.get("image_ref"):
                image = await media_cache.get_snapshot(row["image_ref"])
                if image:
                    legacy_removed_hashes[row["candidate_id"]] = await asyncio.to_thread(
                        lambda: hashlib.sha256(image).hexdigest()
                    )
        existing = [
            {**row, "content_sha256": legacy_removed_hashes.get(row["candidate_id"], row.get("content_sha256"))}
            for row in existing
        ]
        displayed_photo_sha256 = (
            await asyncio.to_thread(lambda: hashlib.sha256(previous_photo).hexdigest()) if previous_photo else None
        )
        retained = await retained_snapshot_candidate(
            event_id,
            previous_photo,
            metadata,
            existing,
            replaced_candidate_ids={item["candidate_id"] for item in candidates},
            photo_content_sha256=displayed_photo_sha256,
        )
        async with get_db() as db:
            # Reserve identity while the already-encoded files are committed. A
            # correction cannot slip between this check and the photo write.
            await db.execute("BEGIN IMMEDIATE")
            repo = DetectionRepository(db)
            preserved = await _snapshot_preservation_outcome(
                event_id, result, metadata, existing, repo, automatic=automatic
            )
            if preserved is not None:
                return preserved
            if retained is not None:
                candidates.append(retained)
            birds = await BirdObservationRepository(db).list_for_event(event_id)
            rows = merge_photo_choices(
                existing,
                candidates,
                reviewed_frames={(bird["clip_variant"], bird["frame_index"]) for bird in birds},
                manual_candidate_id=metadata.get("manual_candidate_id"),
                displayed_photo_sha256=displayed_photo_sha256,
            )
            rows = [
                {key: value for key, value in item.items() if key not in {"image_bytes", "thumbnail_bytes"}}
                for item in rows
            ]
            for candidate in candidates:
                await media_cache._write_bytes_atomic(
                    media_cache._snapshot_path(candidate["image_ref"]), candidate["image_bytes"]
                )
                await media_cache._write_snapshot_metadata(
                    candidate["image_ref"],
                    source="snapshot_candidate",
                    image_bytes=candidate["image_bytes"],
                    film_alignment=candidate.get("film_alignment"),
                )
                if candidate.get("thumbnail_ref") and candidate.get("thumbnail_bytes"):
                    await media_cache.cache_thumbnail(
                        candidate["thumbnail_ref"], candidate["thumbnail_bytes"], source="snapshot_candidate"
                    )
            photo_path = media_cache._snapshot_path(event_id)
            metadata_path = media_cache._snapshot_metadata_path(event_id)
            try:
                await media_cache._write_bytes_atomic(photo_path, selected["image_bytes"])
                await media_cache._write_snapshot_metadata(
                    event_id,
                    source=selected["snapshot_source"],
                    image_bytes=selected["image_bytes"],
                    film_alignment=selected.get("film_alignment"),
                )
                for candidate_id, digest in legacy_removed_hashes.items():
                    await repo.bind_legacy_snapshot_candidate_dismissal(event_id, candidate_id, digest)
                await repo.replace_snapshot_candidates(event_id, rows)
            except BaseException:
                if previous_photo is not None:
                    await media_cache._write_bytes_atomic(photo_path, previous_photo)
                else:
                    await media_cache._complete_file_operation(photo_path.unlink, True)
                if metadata:
                    await media_cache._write_bytes_atomic(metadata_path, json.dumps(metadata).encode())
                else:
                    await media_cache._complete_file_operation(metadata_path.unlink, True)
                raise
            await prune_unreferenced_photo_files(existing, rows)
            await media_cache.delete_thumbnail(event_id)
    await archive_service.refresh_photograph(event_id)
    log.info(
        "Video evidence photograph replaced",
        event_id=event_id,
        frame_index=evidence["frame_index"],
        source=selected["snapshot_source"],
    )
    return "replaced"


async def replace_video_snapshot(
    event_id: str, clip_path: Path, result: dict[str, Any], *, clip_variant: str, automatic: bool = True
) -> str:
    """Best effort baseline photo, independent of optional expensive HQ scanning."""
    evidence = result.get("_video_snapshot_evidence")
    if not settings.media_cache.enabled:
        return "media_cache_disabled"
    if not settings.media_cache.cache_snapshots:
        return "snapshot_caching_disabled"
    if not media_cache._available:
        return "media_cache_unavailable"
    if not isinstance(evidence, dict):
        return "bird_presence_unconfirmed"
    if should_hide_species_label(result.get("label")):
        return "weak_evidence"
    if not has_localized_bird(evidence):
        return "bird_presence_unconfirmed"
    try:
        score = evidence.get("score")
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(score)
            or score > 1
            or score < max(0.6, settings.classification.threshold)
        ):
            return "weak_evidence"
        preserved = await _snapshot_preflight(event_id, result, automatic=automatic)
        if preserved is not None:
            return preserved
        images = await asyncio.to_thread(extract_video_snapshot, clip_path, evidence)
        if images is None:
            return "frame_extract_failed"
        candidates = await asyncio.to_thread(_candidates, event_id, result, evidence, images, clip_variant)
        commit = asyncio.create_task(
            _commit_video_snapshot(event_id, result, evidence, candidates, automatic=automatic),
            name="video_snapshot_commit",
        )
        cancellation = None
        while not commit.done():
            try:
                await asyncio.shield(commit)
            except asyncio.CancelledError as exc:
                cancellation = exc
            except Exception:
                break
        if cancellation is not None:
            if not commit.cancelled():
                commit.exception()
            raise cancellation
        return commit.result()
    except Exception as exc:
        log.warning("Video evidence photograph could not be updated", event_id=event_id, error=str(exc))
        return "snapshot_replace_failed"


def _identity_photo_candidates(candidates: list[dict[str, Any]], labels: set[str]) -> list[dict[str, Any]]:
    supported = [
        candidate
        for candidate in candidates
        if has_reusable_bird_presence(candidate)
        and not candidate.get("photo_hidden")
        and not (candidate.get("source_mode") == "full_frame" and candidate.get("input_is_cropped"))
    ]
    matching = [
        candidate
        for candidate in supported
        if _label_key(candidate.get("classifier_label")) in labels
        and has_confident_photo_species(candidate, threshold=settings.classification.threshold)
    ]
    scenes = [
        candidate
        for candidate in supported
        if candidate.get("source_mode") == "full_frame"
        and not candidate.get("input_is_cropped")
        and candidate.get("snapshot_source") != "hq_candidate_frigate_snapshot_fallback"
    ]
    return matching + [candidate for candidate in scenes if candidate not in matching]


async def reconcile_snapshot_identity(
    event_id: str,
    *,
    clip_path: Path | None = None,
    event_data: dict[str, Any] | None = None,
    clip_variant: str = "event",
    clip_start_timestamp: float | None = None,
    automatic: bool = True,
) -> str:
    """Settle an abstaining run's photograph without creating a species verdict."""
    if not settings.media_cache.enabled:
        return "media_cache_disabled"
    if not settings.media_cache.cache_snapshots:
        return "snapshot_caching_disabled"
    if not media_cache._available:
        return "media_cache_unavailable"
    try:
        async with get_db() as db:
            repo = DetectionRepository(db)
            detection = await repo.get_by_frigate_event(event_id)
            if detection is None:
                return "owner_identification_preserved"
            label = detection.category_name
            labels = {
                _label_key(getattr(detection, field, None))
                for field in ("category_name", "scientific_name", "common_name", "display_name")
                if not should_hide_species_label(getattr(detection, field, None))
            }
            existing = await repo.list_snapshot_candidates(event_id)
        result = {"label": label}
        preserved = await _snapshot_preflight(event_id, result, automatic=automatic)
        if preserved is not None:
            return preserved
        candidates = _identity_photo_candidates(existing, labels)
        for scan_clip in (False, True):
            if scan_clip:
                if clip_path is None or not settings.media_cache.high_quality_event_snapshots:
                    break
                from app.services.high_quality_snapshot_service import high_quality_snapshot_service

                # Metadata alone cannot prove a retained photo remains usable.
                # After exhausting cached images, make one evidence-only scan.
                bundle = await high_quality_snapshot_service.generate_snapshot_candidates_from_clip_path(
                    event_id,
                    clip_path,
                    event_data=event_data,
                    clip_variant=clip_variant,
                    clip_start_timestamp=clip_start_timestamp,
                )
                candidates = _identity_photo_candidates(bundle.get("candidates") or [], labels)
            for candidate in candidates:
                photo = candidate.get("image_bytes")
                if not photo and candidate.get("image_ref"):
                    reference = candidate["image_ref"]
                    async with media_cache._snapshot_commit_lock(reference):
                        photo = await _cached_candidate_photo(reference)
                        metadata = (await media_cache.get_snapshot_metadata(reference) or {}) if photo else {}
                        # Database rows omit this sidecar proof. Read it with the JPEG and seal it
                        # to those bytes before a retained choice is staged for replacement.
                        alignment = validate_film_alignment(metadata.get("film_alignment"), photo) if photo else None
                    candidate = {**candidate, "film_alignment": alignment}
                if not photo:
                    continue
                thumbnail = await asyncio.to_thread(_retained_thumbnail, photo)
                if thumbnail is None:
                    continue
                staged = {
                    **candidate,
                    "selected": True,
                    "image_bytes": photo,
                    "thumbnail_bytes": thumbnail,
                    "thumbnail_ref": candidate.get("thumbnail_ref") or f"{candidate['candidate_id']}__thumb",
                }
                commit = asyncio.create_task(
                    _commit_video_snapshot(event_id, result, candidate, [staged], automatic=automatic),
                    name="abstained_snapshot_commit",
                )
                cancellation = None
                while not commit.done():
                    try:
                        await asyncio.shield(commit)
                    except asyncio.CancelledError as exc:
                        cancellation = exc
                    except Exception:
                        break
                if cancellation is not None:
                    if not commit.cancelled():
                        commit.exception()
                    raise cancellation
                outcome = commit.result()
                if outcome == "photo_choice_removed":
                    continue
                if outcome == "replaced" and not (
                    _label_key(candidate.get("classifier_label")) in labels
                    and has_confident_photo_species(candidate, threshold=settings.classification.threshold)
                ):
                    return "full_frame_fallback"
                return outcome
        return "bird_presence_unconfirmed"
    except Exception as exc:
        log.warning("Abstaining photograph reconciliation failed", event_id=event_id, error=str(exc))
        return "snapshot_replace_failed"
