"""When a capture counts as owner confirmed: a person named a species for it.

``manual_tagged`` is set by an owner's species pick, an owner-confirmed upload and an
owner-requested video reclassification, so all three confirm. Tagging a capture as Unknown
Bird, or as any label the Explorer shows as Unknown Bird, confirms nothing. The visit badge,
the capture badge and the Explorer's Owner confirmed filter all read this one rule.
"""

import aiosqlite

from app.utils.canonical_species import UNKNOWN_BIRD_DISPLAY_LABEL, user_facing_species_label

OWNER_NAMED_SPECIES_SQL_FUNCTION = "yawamf_owner_named_species"


def _text(value: object) -> str | None:
    return None if value is None else str(value)


def owner_named_species(display_name: object, category_name: object) -> int:
    """1 when the presenter would show a species name rather than Unknown Bird, else 0.

    This is the function SQL calls, so a query and the presenter cannot disagree about
    whitespace, case or a configured unknown label.
    """
    shown = user_facing_species_label(_text(display_name), raw_label=_text(category_name))
    return int(shown != UNKNOWN_BIRD_DISPLAY_LABEL)


def is_owner_confirmed(manual_tagged: object, display_name: str | None, category_name: str | None) -> bool:
    """An owner named a species: the capture would not be shown as Unknown Bird."""
    return bool(manual_tagged) and owner_named_species(display_name, category_name) == 1


async def owner_confirmed_sql(db: aiosqlite.Connection, alias: str = "d") -> str:
    """``is_owner_confirmed`` as a SQL condition on detection columns under ``alias``.

    The function is registered on the connection that runs the query. It reads the configured
    unknown labels when called, so it is not declared deterministic to SQLite; within one
    statement it answers the same for the same row.
    """
    await db.create_function(OWNER_NAMED_SPECIES_SQL_FUNCTION, 2, owner_named_species)
    return (
        f"({alias}.manual_tagged = 1 AND "
        f"{OWNER_NAMED_SPECIES_SQL_FUNCTION}({alias}.display_name, {alias}.category_name) = 1)"
    )
