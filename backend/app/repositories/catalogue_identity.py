"""Filtering by catalogue identity, the opaque ``species_id`` bird history and Garden share."""

from collections.abc import Collection


def species_ids_condition(species_ids: Collection[int] | None, column: str) -> tuple[str | None, list[int]]:
    """A catalogue-identity filter: None when absent, and matching nothing when the set is empty."""
    if species_ids is None:
        return None, []
    ids = sorted({int(species_id) for species_id in species_ids})
    if not ids:
        return "1 = 0", []
    return f"{column} IN ({','.join('?' * len(ids))})", ids
