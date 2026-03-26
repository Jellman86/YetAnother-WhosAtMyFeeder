from __future__ import annotations

from typing import Iterable, Sequence

from app.config_models import BlockedSpeciesEntry, normalize_blocked_species_entries
from app.utils.classifier_labels import collapse_classifier_label


def _normalized_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text.casefold() if text else None


def _candidate_texts(values: Iterable[str | None]) -> set[str]:
    normalized: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        normalized.add(text.casefold())
        collapsed = collapse_classifier_label(text, strategy="strip_trailing_parenthetical").strip()
        if collapsed:
            normalized.add(collapsed.casefold())
    return normalized


def normalize_blocked_species_list(entries: Sequence[BlockedSpeciesEntry | dict] | None) -> list[BlockedSpeciesEntry]:
    return normalize_blocked_species_entries(list(entries or []))


def is_blocked_species(
    *,
    blocked_labels: Sequence[str] | None,
    blocked_species: Sequence[BlockedSpeciesEntry | dict] | None,
    label: str | None = None,
    scientific_name: str | None = None,
    common_name: str | None = None,
    taxa_id: int | None = None,
    extra_labels: Iterable[str | None] = (),
) -> bool:
    blocked_label_set = _candidate_texts(blocked_labels or [])
    candidate_text_set = _candidate_texts([label, scientific_name, common_name, *list(extra_labels)])

    if blocked_label_set.intersection(candidate_text_set):
        return True

    structured_entries = normalize_blocked_species_list(blocked_species)
    if taxa_id is not None and any(entry.taxa_id == taxa_id for entry in structured_entries if entry.taxa_id is not None):
        return True

    for entry in structured_entries:
        structured_texts = _candidate_texts([entry.scientific_name, entry.common_name])
        if structured_texts.intersection(candidate_text_set):
            return True

    return False
