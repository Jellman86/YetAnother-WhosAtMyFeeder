"""Bounded recording selection and evidence identity, independent of bird ingest."""

import math
import re

from app.models.garden_motion import MotionSource, MOTION_CATCHUP_SECONDS, MOTION_QUEUE_LIMIT


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
