"""Parse Frigate's tracked path and place the tracked box at a point on it.

Frigate's ``path_data`` is a list of ``[[x, y], timestamp]`` entries. ``x, y`` is the
tracked box's bottom-centre in normalised frame coordinates. The payload is untrusted,
so malformed entries are skipped rather than raised.
"""

import math
from typing import Any

# (timestamp, x, y)
PathPoint = tuple[float, float, float]


def compact_frigate_path_data(raw_path_data: list[Any], *, limit: int) -> list[list[Any]]:
    """Keep at most ``limit`` well-shaped ``[[x, y], timestamp]`` entries for storage.

    Values are kept as received; parsing happens when the path is read.
    """
    path_data: list[list[Any]] = []
    for item in raw_path_data[:limit]:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        point = item[0]
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            path_data.append([list(point[:2]), item[1]])
    return path_data


def frigate_path_points(raw_path_data: Any, *, within_frame: bool = True) -> list[PathPoint]:
    """Finite ``(timestamp, x, y)`` points, by default only those inside the frame."""
    path_points: list[PathPoint] = []
    for item in raw_path_data or []:
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
        if not all(math.isfinite(value) for value in (x, y, timestamp)):
            continue
        if within_frame and not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            continue
        path_points.append((timestamp, x, y))
    return path_points


def nearest_path_point(
    path_points: list[PathPoint], target_timestamp: float, *, max_distance_seconds: float
) -> PathPoint | None:
    """The point closest in time to ``target_timestamp``, unless none is close enough."""
    if not path_points:
        return None
    nearest = min(path_points, key=lambda item: abs(item[0] - target_timestamp))
    if abs(nearest[0] - target_timestamp) > max_distance_seconds:
        return None
    return nearest


def box_at_path_point(point: PathPoint, *, width: float, height: float) -> list[float]:
    """A normalised ``[left, top, width, height]`` box whose bottom-centre sits on ``point``."""
    _timestamp, bottom_center_x, bottom_y = point
    left = max(0.0, min(1.0 - width, bottom_center_x - width / 2.0))
    top = max(0.0, min(1.0 - height, bottom_y - height))
    return [left, top, width, height]
