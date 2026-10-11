"""Read the scientific and common names in a combined classifier label."""

import re

SCIENTIFIC_NAME_PATTERN = re.compile(r"^[A-Z][a-z]+(?: [a-z][a-z-]+){1,3}$")


def looks_like_scientific_name(value: str | None) -> bool:
    return bool(value and SCIENTIFIC_NAME_PATTERN.match(value.strip()))


def split_species_alias_parts(label: str | None) -> tuple[str | None, str | None]:
    raw = str(label or "").strip()
    if not raw.endswith(")") or "\n" in raw:
        return None, None
    start = raw.find("(")
    if start <= 0:
        return None, None
    left, right = raw[:start].strip(), raw[start + 1 : -1].strip()
    if not left or not right:
        return None, None
    return left, right


def parse_species_alias_label(label: str | None) -> tuple[str | None, str | None]:
    left, right = split_species_alias_parts(label)
    if not left or not right:
        return None, None
    left_is_scientific = looks_like_scientific_name(left)
    right_is_scientific = looks_like_scientific_name(right)
    if left_is_scientific and not right_is_scientific:
        return left, right
    if right_is_scientific and not left_is_scientific:
        return right, left
    return None, None
