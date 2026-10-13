"""Bounded recording selection and evidence identity, independent of bird ingest."""

import math
import re

from app.models.garden_motion import MotionSource


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
    if not isinstance(records, list) or len(records) > 2048 or not _number(after) or not _number(now):
        return None
    candidates = []
    for record in records:
        if not isinstance(record, dict):
            continue
        start, end, motion = (record.get(k) for k in ("start_time", "end_time", "motion"))
        if not all(_number(v) for v in (start, end, motion)):
            continue
        if max(after, now - 600) <= start < end <= now - 20 and motion > 0:
            candidates.append((float(start), float(min(end, start + 10))))
    return min(candidates) if candidates else None


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
