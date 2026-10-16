"""Bounded recording selection and evidence identity, independent of bird ingest."""

import math
import re

import numpy as np

from app.models.garden_motion import (
    MotionSource,
    MOTION_CATCHUP_SECONDS,
    MOTION_QUEUE_LIMIT,
    MOTION_INTERVAL_SECONDS,
    MOTION_CATCHUP_INTERVAL_SECONDS,
)


# Owner review of 104 dismissed photos and 28 confirmed visitors (#641): fixtures
# changed at most 1.4x their surroundings, real animals at least 1.5x.
STILL_PROPOSAL_MOTION_RATIO = 1.4
_CHANGED_PIXEL_FLOOR = 1.0


def box_motion_ratio(frames: list[np.ndarray], box_xywh: object) -> float | None:
    """How much the box changes between sampled frames, relative to the ring around it.

    Frames are greyscale arrays of one shape. A ring one box-width wide cancels
    changes that affect the whole scene, such as infrared noise or exposure.
    None means the change could not be measured.
    """
    try:
        x, y, w, h = (float(value) for value in box_xywh)  # type: ignore[union-attr]
    except (TypeError, ValueError):
        return None
    if len(frames) < 2 or not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
        return None
    if x < 0 or y < 0 or x + w > 1.0001 or y + h > 1.0001:
        return None
    height, width = frames[0].shape[:2]
    if any(frame.shape[:2] != (height, width) for frame in frames):
        return None
    left, top = int(x * width), int(y * height)
    right, bottom = max(left + 1, int((x + w) * width)), max(top + 1, int((y + h) * height))
    box_w, box_h = right - left, bottom - top
    ring_left, ring_top = max(0, left - box_w), max(0, top - box_h)
    ring_right, ring_bottom = min(width, right + box_w), min(height, bottom + box_h)
    inside_change = ring_change = 0.0
    for earlier, later in zip(frames, frames[1:]):
        difference = np.abs(later.astype(np.float32) - earlier.astype(np.float32))
        inside_change = max(inside_change, float(difference[top:bottom, left:right].mean()))
        ring = difference[ring_top:ring_bottom, ring_left:ring_right]
        outside = np.ones(ring.shape, dtype=bool)
        outside[top - ring_top : bottom - ring_top, left - ring_left : right - ring_left] = False
        if outside.any():
            ring_change = max(ring_change, float(ring[outside].mean()))
    return inside_change / max(ring_change, _CHANGED_PIXEL_FLOOR)


def motion_scan_interval(outcome: str | None, queued_windows: int) -> int:
    if outcome in {"candidate", "no_candidate", "person_rejected", "still_rejected"} and queued_windows > 0:
        return MOTION_CATCHUP_INTERVAL_SECONDS
    return MOTION_INTERVAL_SECONDS


def motion_key(source: MotionSource) -> str:
    # Model changes and different sampled frames cannot resurrect the same clip.
    return source.key


def normalize_motion_cameras(value: object) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) > 100
        or any(not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", v) for v in value)
    ):
        raise ValueError("Motion cameras must be a list of at most 100 safe Frigate camera names")
    return list(dict.fromkeys(value))


def _number(value: object) -> bool:
    return type(value) in (float, int) and math.isfinite(value)


def choose_segment(records: object, *, after: float, now: float) -> tuple[float, float] | None:
    windows = recording_queue(records, after=after, now=now)
    return windows[0] if windows else None


def recording_queue(records: object, *, after: float, now: float) -> list[tuple[float, float]]:
    """Reconstruct a bounded oldest-first queue from retained recording metadata.

    Frigate returns overlapping records, including one that straddles the saved
    cursor. Merge overlaps before splitting so duplicate metadata cannot replay
    a sampled window. Only the completed cursor needs to survive a restart.
    """
    if not isinstance(records, list) or len(records) > 2048 or not _number(after) or not _number(now):
        return []
    floor = max(after, now - MOTION_CATCHUP_SECONDS, 0)
    candidates = []
    for record in records:
        if not isinstance(record, dict):
            continue
        start, end, motion = (record.get(k) for k in ("start_time", "end_time", "motion"))
        if not all(_number(v) for v in (start, end, motion)):
            continue
        if 0 < start < end <= now - 20 and end > floor and motion > 0:
            candidates.append((float(max(start, floor)), float(end)))
    merged: list[tuple[float, float]] = []
    for start, end in sorted(candidates):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    windows: list[tuple[float, float]] = []
    for start, end in merged:
        while end - start >= 0.1:
            stop = min(end, start + 10)
            windows.append((start, stop))
            if len(windows) == MOTION_QUEUE_LIMIT:
                return windows
            start = stop
    return windows


def camera_pressure(stats: object, camera: str) -> bool:
    if not isinstance(stats, dict) or not isinstance(cameras := stats.get("cameras"), dict):
        return True
    if camera not in cameras:
        return True
    for name, value in cameras.items():
        if not isinstance(value, dict):
            return True
        if name != camera and not value.get("detection_enabled"):
            continue
        fps, processed, skipped = (value.get(k) for k in ("camera_fps", "process_fps", "skipped_fps"))
        if not all(_number(v) for v in (fps, processed, skipped)):
            return True
        if fps <= 0 or processed < fps * 0.8 or not 0 <= skipped <= 0.5:
            return True
    return False
