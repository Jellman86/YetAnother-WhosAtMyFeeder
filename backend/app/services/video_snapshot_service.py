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
from app.services.archive_service import archive_service
from app.services.media_cache import media_cache
from app.utils.canonical_species import should_hide_species_label
from app.utils.blocked_species import is_blocked_species

log = structlog.get_logger()


def _label_key(value: object) -> str:
    return " ".join(str(value or "").replace("_", " ").split()).casefold()


def extract_video_snapshot(clip_path: Path, evidence: dict[str, Any]) -> tuple[Image.Image, Image.Image] | None:
    """Decode one verified moment, retaining its exact crop geometry without ML."""
    from app.services.classifier_service import _read_selected_video_frames

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
    elif evidence.get("input_is_cropped") and evidence.get("input_source") in {
        "model_crop",
        "frigate_hint_crop",
        "frigate_region_crop",
    }:
        return None
    capture = cv2.VideoCapture(str(clip_path))
    try:
        if not capture.isOpened() or frame_index >= int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0):
            return None
        _, decoded, frame = next(iter(_read_selected_video_frames(capture, [frame_index])))
        if not decoded:
            return None
        scene = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).convert("RGB")
        if scene.size != dimensions:
            return None
        return (scene.crop(tuple(box)) if box is not None else scene), scene
    finally:
        capture.release()


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
                "crop_strategy": "video_evidence",
                "selected": selected,
                "classifier_label": result["label"] if selected else None,
                "classifier_score": evidence["score"] if selected else None,
                "ranking_score": evidence["score"] if selected else 0,
                "snapshot_source": source if selected else "video_evidence_full_frame",
                "image_ref": f"{candidate_id}__image",
                "thumbnail_ref": f"{candidate_id}__thumb",
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


async def retained_snapshot_candidate(
    event_id: str, photo: bytes | None, metadata: dict[str, Any], existing: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Keep the prior photograph before replacement; the caller holds its commit lock."""
    if not photo:
        return None
    for old in existing:
        if old.get("image_ref") and await media_cache.get_snapshot(old["image_ref"]) == photo:
            return None
    digest = hashlib.sha256(photo).hexdigest()[:12]
    candidate_id = f"{event_id}__retained_snapshot__{digest}"
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
        "image_bytes": photo,
        "thumbnail_bytes": thumbnail,
    }


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
        and float(current.get("classifier_score") or 0) >= max(0.6, settings.classification.threshold)
        and current.get("image_ref")
    ):
        current_bytes = await media_cache.get_snapshot(current["image_ref"])
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
    selected = next(candidate for candidate in candidates if candidate["selected"])
    async with media_cache._media_write_lease(event_id), media_cache._snapshot_commit_lock(event_id):
        metadata = await media_cache.get_snapshot_metadata(event_id) or {}
        if metadata.get("manual_selection"):
            return "manual_selection_preserved"
        previous_photo = await media_cache.get_snapshot(event_id)
        async with get_db() as db:
            existing = await DetectionRepository(db).list_snapshot_candidates(event_id)
        retained = await retained_snapshot_candidate(event_id, previous_photo, metadata, existing)
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
            new_ids = {item["candidate_id"] for item in candidates}
            rows = [{**item, "selected": False} for item in existing if item["candidate_id"] not in new_ids]
            for candidate in candidates:
                await media_cache._write_bytes_atomic(
                    media_cache._snapshot_path(candidate["image_ref"]), candidate["image_bytes"]
                )
                await media_cache._write_snapshot_metadata(candidate["image_ref"], source="snapshot_candidate")
                if candidate.get("thumbnail_ref") and candidate.get("thumbnail_bytes"):
                    await media_cache.cache_thumbnail(
                        candidate["thumbnail_ref"], candidate["thumbnail_bytes"], source="snapshot_candidate"
                    )
                rows.append(
                    {key: value for key, value in candidate.items() if key not in {"image_bytes", "thumbnail_bytes"}}
                )
            photo_path = media_cache._snapshot_path(event_id)
            metadata_path = media_cache._snapshot_metadata_path(event_id)
            try:
                await media_cache._write_bytes_atomic(photo_path, selected["image_bytes"])
                await media_cache._write_snapshot_metadata(event_id, source=selected["snapshot_source"])
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
    if (
        not settings.media_cache.enabled
        or not settings.media_cache.cache_snapshots
        or not isinstance(evidence, dict)
        or not media_cache._available
    ):
        return "disabled_or_no_evidence"
    if should_hide_species_label(result.get("label")):
        return "weak_evidence"
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
