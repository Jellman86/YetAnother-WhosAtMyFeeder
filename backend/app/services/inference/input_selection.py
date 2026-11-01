"""Which image reaches a classifier, and what that image is.

Pure decisions over a `ClassificationInputContext`: Frigate hints aligned with a
video frame's clip timestamp, and the provenance results carry about the input
that was actually classified. Detector-driven crops stay with the classifier,
which owns the crop service.
"""

import math
from typing import Any, NamedTuple

from app.models.ai_models import ClassificationInputContext
from app.utils.frigate_coordinates import normalized_frigate_video_hint, photographed_track


class ClassifiedInputProvenance(NamedTuple):
    """What the image that reached model preprocessing was, as results report it."""

    input_source: str
    input_is_cropped: bool


def normalize_classification_input_context(input_context: Any | None) -> ClassificationInputContext:
    if isinstance(input_context, ClassificationInputContext):
        return input_context
    if input_context is None:
        return ClassificationInputContext()

    payload: dict[str, Any] = {}
    if isinstance(input_context, dict):
        payload = dict(input_context)
    else:
        model_dump = getattr(input_context, "model_dump", None)
        if callable(model_dump):
            try:
                dumped = model_dump()
            except Exception:
                dumped = None
            if isinstance(dumped, dict):
                payload = dumped
        elif hasattr(input_context, "__dict__"):
            payload = {key: value for key, value in vars(input_context).items() if not key.startswith("_")}

    try:
        return ClassificationInputContext.model_validate(payload)
    except Exception:
        return ClassificationInputContext()


def input_context_extra(input_context: ClassificationInputContext, key: str) -> Any | None:
    extra = getattr(input_context, "__pydantic_extra__", {}) or {}
    if key in extra:
        return extra.get(key)
    return getattr(input_context, key, None)


def frigate_path_points(raw_path_data: list[Any]) -> list[tuple[float, float, float]]:
    path_points: list[tuple[float, float, float]] = []
    for item in raw_path_data:
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
    return path_points


def frigate_snapshot_time(input_context: ClassificationInputContext) -> float | None:
    value = input_context_extra(input_context, "frigate_snapshot_frame_time")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None
    return float(value)


def photographed_track_window(
    input_context: ClassificationInputContext,
    image_size: tuple[int, int] | None,
) -> tuple[float, float]:
    """Time window in which Frigate's track still follows the photographed bird."""
    snapshot_time = frigate_snapshot_time(input_context)
    box = normalized_frigate_video_hint(input_context_extra(input_context, "frigate_box"))
    raw_path_data = input_context_extra(input_context, "frigate_path_data")
    if snapshot_time is None or box is None or not isinstance(raw_path_data, list):
        return -math.inf, math.inf
    _points, start, end = photographed_track(
        frigate_path_points(raw_path_data),
        box=box,
        snapshot_time=snapshot_time,
        image_size=image_size or (1, 1),
    )
    return start, end


def tracked_frigate_box_for_frame(
    input_context: ClassificationInputContext,
    *,
    frame_offset_seconds: float | None,
    image_size: tuple[int, int] | None = None,
) -> list[float] | None:
    """Align Frigate's tracked path with the actual clip timeline."""
    raw_path_data = input_context_extra(input_context, "frigate_path_data")
    raw_box = input_context_extra(input_context, "frigate_box")
    raw_clip_start = input_context_extra(input_context, "clip_start_timestamp")
    if (
        not isinstance(raw_path_data, list)
        or not isinstance(raw_box, (list, tuple))
        or len(raw_box) != 4
        or frame_offset_seconds is None
    ):
        return None
    try:
        clip_start = float(raw_clip_start)
        offset = float(frame_offset_seconds)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (clip_start, offset)) or offset < 0.0:
        return None
    if image_size is None:
        image_size = (1, 1)
    normalized_box = normalized_frigate_video_hint(raw_box)
    if normalized_box is None:
        return None
    _left, _top, width, height = normalized_box
    if width > 1.0 or height > 1.0:
        return None

    path_points = frigate_path_points(raw_path_data)
    if not path_points:
        return None

    target_timestamp = clip_start + offset
    snapshot_time = frigate_snapshot_time(input_context)
    if snapshot_time is not None:
        path_points, start, end = photographed_track(
            path_points, box=normalized_box, snapshot_time=snapshot_time, image_size=image_size
        )
        if not start <= target_timestamp < end:
            return None
    point_timestamp, bottom_center_x, bottom_y = min(
        path_points,
        key=lambda item: abs(item[0] - target_timestamp),
    )
    if abs(point_timestamp - target_timestamp) > 0.75:
        return None

    left = max(0.0, min(1.0 - width, bottom_center_x - width / 2.0))
    top = max(0.0, min(1.0 - height, bottom_y - height))
    return [left, top, width, height]


def video_frame_input_context(
    input_context: ClassificationInputContext,
    *,
    frame_offset_seconds: float | None,
    image_size: tuple[int, int] | None = None,
) -> ClassificationInputContext:
    """Return crop hints that are valid at this frame's clip timestamp.

    A Frigate event's top-level box describes one tracked instant. Reusing it
    across a full-visit recording repeatedly classifies the same background
    patch after a fleeting bird has moved away. Precise hints require a
    known clip origin and aligned path data. A broader spatial prior remains
    useful when the exact frame timing is unknown.
    """
    frame_context_payload = dict(input_context.model_dump())
    clip_variant = str(input_context_extra(input_context, "clip_variant") or "event").strip().lower()
    # A spatial prior survives unknown pre-capture timing and also constrains
    # full-visit recordings. Include the observed path so a moving bird is
    # not excluded merely because the final region covers its last position.
    subject_region = normalized_frigate_video_hint(
        input_context_extra(input_context, "frigate_region")
    ) or normalized_frigate_video_hint(input_context_extra(input_context, "frigate_box"))
    for key in ("frigate_box", "frigate_region"):
        if normalized_frigate_video_hint(frame_context_payload.get(key)) is None:
            frame_context_payload.pop(key, None)
    raw_path_data = input_context_extra(input_context, "frigate_path_data")
    if subject_region is not None:
        normalized_region = subject_region
        tracked_size = normalized_frigate_video_hint(input_context_extra(input_context, "frigate_box"))
        if normalized_region is not None and tracked_size is not None and isinstance(raw_path_data, list):
            left, top, width, height = normalized_region
            right, bottom = left + width, top + height
            # A track that moved on to another bird must not stretch the event's subject to it.
            track_start, track_end = photographed_track_window(input_context, image_size)
            for item in raw_path_data:
                if (
                    not isinstance(item, (list, tuple))
                    or not item
                    or not isinstance(item[0], (list, tuple))
                    or len(item[0]) < 2
                ):
                    continue
                if math.isfinite(track_start) or math.isfinite(track_end):
                    timestamp = item[1] if len(item) > 1 else None
                    if (
                        isinstance(timestamp, bool)
                        or not isinstance(timestamp, (int, float))
                        or not track_start <= timestamp < track_end
                    ):
                        continue
                x, y = item[0][:2]
                if (
                    isinstance(x, bool)
                    or isinstance(y, bool)
                    or not isinstance(x, (int, float))
                    or not isinstance(y, (int, float))
                ):
                    continue
                if not math.isfinite(x) or not math.isfinite(y) or not 0 <= x <= 1 or not 0 <= y <= 1:
                    continue
                left, top = min(left, x - tracked_size[2] / 2), min(top, y - tracked_size[3])
                right, bottom = max(right, x + tracked_size[2] / 2), max(bottom, y)
            left, top, right, bottom = max(0, left), max(0, top), min(1, right), min(1, bottom)
            subject_region = [left, top, right - left, bottom - top]
        frame_context_payload["event_subject_region"] = subject_region
    requires_time_aligned_hint = (
        clip_variant == "recording"
        or bool(raw_path_data)
        or input_context_extra(input_context, "clip_start_timestamp") is None
    )
    if requires_time_aligned_hint:
        frame_context_payload.pop("frigate_box", None)
        frame_context_payload.pop("frigate_region", None)
        tracked_box = tracked_frigate_box_for_frame(
            input_context,
            frame_offset_seconds=frame_offset_seconds,
            image_size=image_size,
        )
        if tracked_box is not None:
            frame_context_payload["frigate_box"] = tracked_box
    return normalize_classification_input_context(frame_context_payload)


def resolved_classification_input_provenance(
    *,
    input_context: ClassificationInputContext,
    crop_diagnostics: dict[str, Any],
) -> ClassifiedInputProvenance:
    """Describe the image that actually reached model preprocessing."""
    supplied_source = str(input_context_extra(input_context, "input_source") or "").strip().lower()
    if bool(crop_diagnostics.get("crop_applied")):
        crop_reason = str(crop_diagnostics.get("crop_reason") or "").strip().lower()
        if crop_reason in {"frigate_box", "frigate_region", "frigate_snapshot_scaled_crop"}:
            if supplied_source == "frigate_recording_snapshot":
                return ClassifiedInputProvenance("recording_snapshot_frigate_hint_crop", True)
            return ClassifiedInputProvenance("snapshot_frigate_hint_crop", True)
        return ClassifiedInputProvenance("snapshot_model_crop", True)
    if supplied_source:
        return ClassifiedInputProvenance(supplied_source, bool(input_context.is_cropped))
    if bool(input_context.is_cropped):
        return ClassifiedInputProvenance("provided_crop", True)
    return ClassifiedInputProvenance("full_frame", False)


def attach_classification_input_provenance(
    results: list[dict],
    *,
    input_context: ClassificationInputContext,
    crop_diagnostics: dict[str, Any],
) -> list[dict]:
    provenance = resolved_classification_input_provenance(
        input_context=input_context,
        crop_diagnostics=crop_diagnostics,
    )
    for result in results:
        if not isinstance(result, dict):
            continue
        result["input_source"] = provenance.input_source
        result["input_is_cropped"] = provenance.input_is_cropped
        for key in ("input_box", "input_frame_size"):
            if key in crop_diagnostics:
                result[key] = crop_diagnostics[key]
        if not crop_diagnostics.get("crop_applied") or crop_diagnostics.get("source_same_frame"):
            frame_time = input_context_extra(input_context, "recording_frame_time")
            if frame_time is not None:
                result["input_frame_time"] = frame_time
            frame_hash = input_context_extra(input_context, "source_image_sha256")
            if frame_hash:
                result["input_frame_sha256"] = frame_hash
    return results
