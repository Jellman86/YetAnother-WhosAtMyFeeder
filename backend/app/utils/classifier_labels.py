from collections.abc import Iterable


def normalize_classifier_label(label: str | None) -> str:
    text = str(label or '').strip()
    if not text:
        return text

    parts = [part for part in text.split('_') if part]
    if len(parts) < 2 or not parts[0].isdigit():
        return text

    taxonomy_parts = parts[1:]
    scientific_start = None
    for idx in range(len(taxonomy_parts) - 1, -1, -1):
        token = taxonomy_parts[idx]
        if token[:1].isupper() and any(ch.islower() for ch in token[1:]):
            scientific_start = idx
            break

    if scientific_start is None:
        return text

    normalized = ' '.join(taxonomy_parts[scientific_start:]).strip()
    return normalized or text


def normalize_classifier_labels(labels: Iterable[str]) -> list[str]:
    return [normalize_classifier_label(label) for label in labels]
