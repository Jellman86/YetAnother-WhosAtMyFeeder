"""Convert Frigate localisation hints into image crop coordinates."""

from __future__ import annotations

import math
from typing import Any


def normalize_frigate_hint_box(
    raw_hint: Any,
    image_size: tuple[int, int],
) -> tuple[float, float, float, float] | None:
    """Return a normalized ``(left, top, width, height)`` box.

    Frigate's REST event representation uses normalized ``x, y, width,
    height`` values, while the live MQTT event payload uses pixel ``left,
    top, right, bottom`` values. The value range distinguishes those contracts:
    a tuple wholly inside zero-to-one is normalized; every other valid tuple is
    interpreted as pixel corners.
    """
    if not isinstance(raw_hint, (list, tuple)) or len(raw_hint) != 4:
        return None
    if any(isinstance(value, bool) for value in raw_hint):
        return None
    try:
        first, second, third, fourth = (float(value) for value in raw_hint)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (first, second, third, fourth)):
        return None

    image_width, image_height = image_size
    if image_width <= 0 or image_height <= 0:
        return None

    normalized_xywh = all(0.0 <= value <= 1.0 for value in (first, second, third, fourth))
    if normalized_xywh:
        left, top, width, height = first, second, third, fourth
    else:
        left = first / image_width
        top = second / image_height
        width = (third - first) / image_width
        height = (fourth - second) / image_height

    if left < 0.0 or top < 0.0 or width <= 0.0 or height <= 0.0:
        return None
    return left, top, width, height


def restore_frigate_hint_box(
    raw_hint: Any,
    image_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    """Return a clipped pixel ``(left, top, right, bottom)`` box."""
    normalized_box = normalize_frigate_hint_box(raw_hint, image_size)
    if normalized_box is None:
        return None

    left, top, width, height = normalized_box
    image_width, image_height = image_size
    left *= image_width
    top *= image_height
    right = left + width * image_width
    bottom = top + height * image_height

    left_i = max(0, min(image_width, int(math.floor(left))))
    top_i = max(0, min(image_height, int(math.floor(top))))
    right_i = max(0, min(image_width, int(math.ceil(right))))
    bottom_i = max(0, min(image_height, int(math.ceil(bottom))))
    if right_i <= left_i or bottom_i <= top_i:
        return None
    return left_i, top_i, right_i, bottom_i
