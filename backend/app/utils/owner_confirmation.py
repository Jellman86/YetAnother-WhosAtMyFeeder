"""When a capture counts as owner confirmed: a person named a species for it.

``manual_tagged`` is set by an owner's species pick, an owner-confirmed upload and an
owner-requested video reclassification, so all three confirm. Tagging a capture as Unknown
Bird, or as any label the Explorer shows as Unknown Bird, confirms nothing. The visit badge,
the capture badge and the Explorer's Owner confirmed filter all read this one rule.
"""

from app.utils.canonical_species import (
    UNKNOWN_BIRD_DISPLAY_LABEL,
    hidden_species_exact_labels,
    hidden_species_substrings,
    user_facing_species_label,
)

# SQLite's TRIM removes only spaces unless told otherwise; Python's strip removes these too.
_SQL_WHITESPACE = "char(32, 9, 10, 13)"


def is_owner_confirmed(manual_tagged: object, display_name: str | None, category_name: str | None) -> bool:
    """An owner named a species: the capture would not be shown as Unknown Bird."""
    if not manual_tagged:
        return False
    return user_facing_species_label(display_name, raw_label=category_name) != UNKNOWN_BIRD_DISPLAY_LABEL


def owner_confirmed_sql(alias: str = "d") -> tuple[str, list[str]]:
    """``is_owner_confirmed`` as a SQL condition on a row with detection columns under ``alias``."""
    labels = sorted({" ".join(str(label).casefold().split()) for label in hidden_species_exact_labels()} - {""})
    fragments = [str(fragment).strip().casefold() for fragment in hidden_species_substrings() if str(fragment).strip()]
    placeholders = ",".join("?" for _ in labels)
    display = f"COALESCE({alias}.display_name, '')"
    category = f"COALESCE({alias}.category_name, '')"
    clauses = [f"{alias}.manual_tagged = 1", f"TRIM({display}, {_SQL_WHITESPACE}) <> ''"]
    params: list[str] = []
    for column in (display, category):
        if labels:
            clauses.append(f"LOWER(TRIM({column}, {_SQL_WHITESPACE})) NOT IN ({placeholders})")
            params.extend(labels)
        for fragment in fragments:
            clauses.append(f"LOWER({column}) NOT LIKE ?")
            params.append(f"%{fragment}%")
    return "(" + " AND ".join(clauses) + ")", params
