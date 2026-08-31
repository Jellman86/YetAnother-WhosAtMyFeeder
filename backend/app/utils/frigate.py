from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FrigateSubLabel:
    """Normalized Frigate sublabel and its optional classifier confidence."""

    label: str | None
    score: float | None


def _normalize_sub_label_score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score) or score < 0.0 or score > 1.0:
        return None
    return score


def parse_sub_label(value: Any) -> FrigateSubLabel:
    """Parse every Frigate sublabel shape without conflating object score.

    Current Frigate MQTT payloads commonly use ``[label, confidence]`` while
    historical data and integrations may provide a plain string, JSON-encoded
    list, or mapping. Invalid confidence never invalidates an otherwise usable
    label.
    """
    if value is None:
        return FrigateSubLabel(None, None)

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return FrigateSubLabel(None, None)
        if candidate[:1] in {"[", "{"} and candidate[-1:] in {
            "]",
            "}",
        }:
            try:
                return parse_sub_label(json.loads(candidate))
            except (TypeError, ValueError):
                pass
        return FrigateSubLabel(candidate, None)

    if isinstance(value, (list, tuple)):
        label: str | None = None
        nested_score: float | None = None
        for item in value:
            parsed = parse_sub_label(item)
            if parsed.label:
                label = parsed.label
                nested_score = parsed.score
                break
        direct_score = _normalize_sub_label_score(value[1]) if len(value) > 1 else None
        return FrigateSubLabel(label, direct_score if direct_score is not None else nested_score)

    if isinstance(value, dict):
        parsed_label = FrigateSubLabel(None, None)
        for key in ("label", "name", "value", "subLabel", "sub_label"):
            parsed_label = parse_sub_label(value.get(key))
            if parsed_label.label:
                break
        score = None
        for key in ("score", "confidence", "subLabelScore", "sub_label_score"):
            score = _normalize_sub_label_score(value.get(key))
            if score is not None:
                break
        return FrigateSubLabel(parsed_label.label, score if score is not None else parsed_label.score)

    return FrigateSubLabel(None, None)


def normalize_sub_label(value: Any) -> str | None:
    """Normalize Frigate sub_label payloads into a single displayable label string."""
    return parse_sub_label(value).label


def normalize_ingest_labels(labels: Any) -> list[str]:
    """The Frigate labels YA-WAMF acts on, lowercased and deduplicated.

    An empty configuration falls back to `bird`: a list that admits nothing
    would silently kill every detection, which no one configures on purpose.
    """
    normalized: list[str] = []
    for label in labels or []:
        text = str(label or "").strip().lower()
        if text and text not in normalized:
            normalized.append(text)
    return normalized or ["bird"]


def is_ingest_label(label: Any, configured: list[str]) -> bool:
    text = str(label or "").strip().lower()
    return bool(text) and text in configured
