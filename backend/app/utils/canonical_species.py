import re
from collections.abc import Iterable

from app.config import settings


# Canonical label rewrites: map misspelled/variant model output to the
# correct form expected by iNaturalist / eBird.  Applied before taxonomy
# lookup so that stale cache misses caused by typos are avoided.
_LABEL_REWRITES: dict[str, str] = {
    "pallass grasshopper warbler": "Pallas's grasshopper warbler",
    "pallass gull": "Pallas's gull",
    "pallass leaf warbler": "Pallas's leaf warbler",
    "pallass reed bunting": "Pallas's reed bunting",
    "menetriess warbler": "Menetries's warbler",
    "raddes accentor": "Radde's accentor",
    "raddes warbler": "Radde's warbler",
    "ruppells vulture": "Rüppell's vulture",
    "ruppells warbler": "Rüppell's warbler",
}


def rewrite_label(label: str | None) -> str:
    """Return the canonical form of *label*, or *label* unchanged."""
    if not label:
        return label or ""
    key = label.strip().casefold()
    return _LABEL_REWRITES.get(key, label)


UNKNOWN_BIRD_DISPLAY_LABEL = "Unknown Bird"
UNKNOWN_RAW_LABEL = "Unknown"
ABSTENTION_SPECIES_LABELS = (
    "No detection",
    "No detections",
    "No data",
    "No result",
    "No results",
    "No classification",
    "No classifications",
    "No bird",
    "Not a bird",
    "Unclassified",
    "Unidentified",
    "Unidentified bird",
    "N/A",
    "None",
    "Null",
)
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
    values = [
        UNKNOWN_BIRD_DISPLAY_LABEL,
        UNKNOWN_RAW_LABEL,
        *ABSTENTION_SPECIES_LABELS,
        *(settings.classification.unknown_bird_labels or []),
    ]
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


def user_facing_species_fields(
    *,
    display_name: str | None,
    category_name: str | None,
    scientific_name: str | None = None,
    common_name: str | None = None,
    taxa_id: int | None = None,
    extra_unknown_labels: Iterable[str] | None = None,
) -> dict[str, str | int | None]:
    public_display_name = user_facing_species_label(
        display_name,
        raw_label=category_name,
        extra_unknown_labels=extra_unknown_labels,
    )
    if public_display_name == UNKNOWN_BIRD_DISPLAY_LABEL:
        return {
            "display_name": UNKNOWN_BIRD_DISPLAY_LABEL,
            "category_name": UNKNOWN_BIRD_DISPLAY_LABEL,
            "scientific_name": None,
            "common_name": None,
            "taxa_id": None,
        }
    return {
        "display_name": str(display_name or "").strip() or public_display_name,
        "category_name": str(category_name or "").strip() or public_display_name,
        "scientific_name": scientific_name,
        "common_name": common_name,
        "taxa_id": taxa_id,
    }


def looks_like_specific_scientific_name(value: str | None) -> bool:
    return bool(value and _SPECIFIC_SCIENTIFIC_NAME_RE.match(str(value).strip()))
