import re
from collections.abc import Iterable


def normalize_classifier_label(label: str | None) -> str:
    text = str(label or '').strip()
    if not text:
        return text

    parts = [part for part in text.split('_') if part]
    if len(parts) < 2 or not parts[0].isdigit():
        return text

    taxonomy_parts = parts[1:]

    # Find the rightmost all-lowercase token — this is the species epithet.
    # Scientific names follow the pattern: Genus species [subspecies ...].
    # Common-name words appended after the scientific name always start with an
    # uppercase letter, so the last all-lowercase token marks the species end.
    species_end = None
    for idx in range(len(taxonomy_parts) - 1, -1, -1):
        if taxonomy_parts[idx].islower():
            species_end = idx
            break

    if species_end is None:
        return text

    # Walk left across any consecutive lowercase tokens (subspecies epithets).
    species_start = species_end
    while species_start > 0 and taxonomy_parts[species_start - 1].islower():
        species_start -= 1

    # The genus is the PascalCase token immediately before the lowercase run.
    if species_start == 0 or not taxonomy_parts[species_start - 1][:1].isupper():
        return text

    genus_idx = species_start - 1
    normalized = ' '.join(taxonomy_parts[genus_idx:species_end + 1]).strip()
    return normalized or text


def normalize_classifier_labels(labels: Iterable[str]) -> list[str]:
    return [normalize_classifier_label(label) for label in labels]


def collapse_classifier_label(label: str | None, *, strategy: str | None = None) -> str:
    normalized = normalize_classifier_label(label)
    strategy_name = str(strategy or "").strip().lower()
    if strategy_name == "strip_trailing_parenthetical":
        collapsed = re.sub(r"\s*\([^)]*\)\s*$", "", normalized).strip()
        return collapsed or normalized
    return normalized


def build_grouped_classifier_labels(
    labels: Iterable[str],
    *,
    strategy: str | None = None,
) -> list[str]:
    return [collapse_classifier_label(label, strategy=strategy) for label in labels]
