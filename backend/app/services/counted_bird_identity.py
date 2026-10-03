"""Resolve a counted bird's name without changing its original crop evidence."""

import math
from typing import Any

from app.utils.canonical_species import should_hide_species_label
from app.utils.species_aliases import looks_like_scientific_name


def _key(value: object) -> str:
    return " ".join(str(value or "").replace("_", " ").split()).casefold()


def _score(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value) if math.isfinite(value) and 0 <= value <= 1 else 0.0


def _box(value: object) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value):
        return None
    left, top, right, bottom = value
    return tuple(value) if 0 <= left < right and 0 <= top < bottom else None


def _overlap(bird: dict, candidate: dict) -> float:
    if (bird.get("clip_variant"), bird.get("frame_index")) != (
        candidate.get("clip_variant"),
        candidate.get("frame_index"),
    ):
        return 0.0
    left, right = _box(bird.get("crop_box")), _box(candidate.get("crop_box"))
    if left is None or right is None:
        return 0.0
    area = (left[2] - left[0]) * (left[3] - left[1])
    intersection = max(0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0, min(left[3], right[3]) - max(left[1], right[1])
    )
    return intersection / area


def species_aliases_from_taxonomy(rows: list[tuple[str, str | None, str | None]]) -> dict[str, str | None]:
    """Only unique cached common names identify a scientific species."""
    identities: dict[str, set[str]] = {}
    scientific: dict[str, str] = {}
    for name, common, manual_common in rows:
        if not looks_like_scientific_name(name) or should_hide_species_label(name):
            continue
        scientific[_key(name)] = name
        for alias in (name, common, manual_common):
            if alias and not should_hide_species_label(alias):
                identities.setdefault(_key(alias), set()).add(name)
    aliases = {key: next(iter(names)) if len(names) == 1 else None for key, names in identities.items()}
    return aliases | scientific


def resolve_bird_identities(
    birds: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    detection: dict[str, Any],
    *,
    threshold: float,
    species_aliases: dict[str, str | None] | None = None,
) -> list[dict[str, Any]]:
    """Only the uniquely localized tracked bird may borrow the accepted visit identity.

    A selected photograph does not identify a bird. Only Frigate's retained tracked
    box anchors the association, and even an excluded bird makes overlap ambiguous.
    """
    names = {_key(detection.get(k)) for k in ("category_name", "scientific_name", "common_name", "display_name")}
    names.discard("")
    accepted = detection.get("scientific_name") or detection.get("category_name") or detection.get("display_name")
    accepted_score = _score(detection.get("score"))
    accepted_known = bool(accepted) and not should_hide_species_label(accepted)
    parent_usable = accepted_known and (bool(detection.get("manual_tagged")) or accepted_score >= threshold)
    aliases = dict(species_aliases or {})
    parent_scientific = detection.get("scientific_name")
    if looks_like_scientific_name(parent_scientific) and not should_hide_species_label(parent_scientific):
        for name in names:
            # A cached ambiguous/common alias must not override another known
            # species merely because it shares this visit's display text.
            if name not in aliases or _key(aliases[name]) == _key(parent_scientific):
                aliases[name] = parent_scientific
    parent_identity = aliases.get(_key(accepted), accepted)
    associated: set[int] = set()
    for hint in candidates:
        if hint.get("source_mode") != "frigate_hint_crop":
            continue
        matches = [index for index, bird in enumerate(birds) if _overlap(bird, hint) >= 0.2]
        if len(matches) == 1 and _overlap(birds[matches[0]], hint) >= 0.8:
            associated.add(matches[0])
    # Conflicting tracked boxes must not turn two birds into the primary bird.
    if len(associated) != 1:
        associated.clear()
    resolved = []
    for index, original in enumerate(birds):
        bird = dict(original)
        source = "manual" if bird.get("manual_species") else "crop"
        score = None if source == "manual" else _score(bird.get("classifier_score"))
        if (
            not bird.get("manual_species")
            and not bird.get("is_hidden")
            and should_hide_species_label(bird.get("species"))
        ):
            label = bird.get("classifier_label")
            if label and not should_hide_species_label(label):
                label_key = _key(label)
                if _score(bird.get("classifier_score")) >= threshold:
                    bird["species"] = label
                elif (
                    parent_usable
                    and index in associated
                    and label_key in names
                    and (
                        label_key not in aliases
                        or (
                            aliases[label_key] is not None
                            and parent_identity is not None
                            and _key(aliases[label_key]) == _key(parent_identity)
                        )
                    )
                ):
                    bird["species"] = accepted
                    source = "visit"
                    score = None if detection.get("manual_tagged") else accepted_score
        bird["identity_source"] = source
        bird["identity_score"] = score
        effective_species = aliases.get(_key(bird.get("species")))
        if effective_species:
            bird["species"] = effective_species
            bird["scientific_name"] = effective_species
        if (
            accepted_known
            and _key(bird.get("species")) in names
            and not (_key(bird.get("species")) in aliases and aliases[_key(bird.get("species"))] is None)
        ):
            bird["common_name"] = detection.get("common_name")
            bird["scientific_name"] = detection.get("scientific_name")
        resolved.append(bird)
    return resolved
