from __future__ import annotations

import json
from typing import Any


def normalize_sub_label(value: Any) -> str | None:
    """Normalize Frigate sub_label payloads into a single displayable label string."""
    if value is None:
        return None

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None

        # Defensive: recover from accidentally persisted JSON array strings.
        if candidate.startswith("[") and candidate.endswith("]"):
            try:
                parsed = json.loads(candidate)
            except (TypeError, ValueError):
                return candidate
            normalized = normalize_sub_label(parsed)
            return normalized if normalized is not None else candidate

        return candidate

    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                normalized = normalize_sub_label(item)
                if normalized:
                    return normalized

        for item in value:
            if isinstance(item, (list, tuple, dict)):
                normalized = normalize_sub_label(item)
                if normalized:
                    return normalized
        return None

    if isinstance(value, dict):
        for key in ("label", "name", "value"):
            normalized = normalize_sub_label(value.get(key))
            if normalized:
                return normalized
        return None

    return None
