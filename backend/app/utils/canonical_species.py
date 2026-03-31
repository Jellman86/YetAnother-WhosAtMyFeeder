import re
from collections.abc import Iterable

from app.config import settings


UNKNOWN_BIRD_DISPLAY_LABEL = "Unknown Bird"
_LABEL_SPACE_RE = re.compile(r"\s+")
_SPECIFIC_SCIENTIFIC_NAME_RE = re.compile(r"^[A-Z][a-z-]+(?: [a-z][a-z-]+){1,3}$")
_NONCANONICAL_EXACT = {
    "life",
    "life (life)",
}
_NONCANONICAL_SUBSTRINGS = (
    " and allies",
)


def _normalize_label_key(value: str | None) -> str:
    normalized = str(value or "").strip().casefold()
    return _LABEL_SPACE_RE.sub(" ", normalized)


def unknown_species_labels(extra_labels: Iterable[str] | None = None) -> list[str]:
    values = [UNKNOWN_BIRD_DISPLAY_LABEL, *(settings.classification.unknown_bird_labels or [])]
    if extra_labels:
        values.extend(str(value) for value in extra_labels if str(value).strip())

    labels: list[str] = []
    seen: set[str] = set()
    for candidate in values:
        text = str(candidate or "").strip()
        key = _normalize_label_key(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        labels.append(text)
    return labels


def hidden_species_exact_labels(extra_labels: Iterable[str] | None = None) -> list[str]:
    values = [
        *unknown_species_labels(extra_labels),
        *sorted(_NONCANONICAL_EXACT),
    ]
    labels: list[str] = []
    seen: set[str] = set()
    for candidate in values:
        text = str(candidate or "").strip()
        key = _normalize_label_key(text)
        if not text or not key or key in seen:
            continue
        seen.add(key)
        labels.append(text)
    return labels


def hidden_species_substrings() -> tuple[str, ...]:
    return _NONCANONICAL_SUBSTRINGS


def is_unknown_species_label(value: str | None, *, extra_labels: Iterable[str] | None = None) -> bool:
    normalized = _normalize_label_key(value)
    if not normalized:
        return False
    return normalized in {
        _normalize_label_key(label)
        for label in unknown_species_labels(extra_labels)
    }


def is_noncanonical_species_label(value: str | None) -> bool:
    normalized = _normalize_label_key(value)
    if not normalized:
        return False
    if normalized in _NONCANONICAL_EXACT:
        return True
    return any(fragment in normalized for fragment in _NONCANONICAL_SUBSTRINGS)


def should_hide_species_label(
    value: str | None,
    *,
    extra_unknown_labels: Iterable[str] | None = None,
) -> bool:
    return is_unknown_species_label(value, extra_labels=extra_unknown_labels) or is_noncanonical_species_label(value)


def user_facing_species_label(
    display_name: str | None,
    *,
    raw_label: str | None = None,
    extra_unknown_labels: Iterable[str] | None = None,
) -> str:
    if should_hide_species_label(display_name, extra_unknown_labels=extra_unknown_labels):
        return UNKNOWN_BIRD_DISPLAY_LABEL
    if raw_label and should_hide_species_label(raw_label, extra_unknown_labels=extra_unknown_labels):
        return UNKNOWN_BIRD_DISPLAY_LABEL
    return str(display_name or "").strip() or UNKNOWN_BIRD_DISPLAY_LABEL


def looks_like_specific_scientific_name(value: str | None) -> bool:
    return bool(value and _SPECIFIC_SCIENTIFIC_NAME_RE.match(str(value).strip()))
