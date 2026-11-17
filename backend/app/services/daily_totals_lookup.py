"""Which canonical keys a species' daily totals and lost captures are kept under (#949).

Totals are matched by identity, never by the name a request happens to use: a taxonomy rename moves
the name but not the catalogue's ``species_id``, and Unknown bird follows the same hidden-label
rule as the live count.
"""

from __future__ import annotations

import asyncio

import aiosqlite

from app.config import settings
from app.repositories.daily_totals_repository import DailyTotalsRepository
from app.services.species_catalog_resolver import species_catalog_resolver
from app.utils.canonical_species import should_hide_species_label

UNKNOWN_BIRD = "Unknown Bird"


def _is_unknown_label(label: str) -> bool:
    return should_hide_species_label(label, extra_unknown_labels=settings.classification.unknown_bird_labels)


async def species_history_keys(
    db: aiosqlite.Connection, species_name: str, *, aliases: tuple[str, ...] = (), taxa_id: int | None = None
) -> set[str]:
    repo = DailyTotalsRepository(db)
    if species_name == UNKNOWN_BIRD:
        return await repo.unknown_species_keys(_is_unknown_label)
    names = {species_name, *aliases}
    species_ids: set[int] = set()
    for name in names:
        species_ids.update(await repo.species_ids_named(name))
        catalogue_id, _status = await asyncio.to_thread(species_catalog_resolver.resolve_scientific_name, name)
        if catalogue_id is not None:
            species_ids.add(int(catalogue_id))
    synonyms = set()
    for name in names:
        synonyms.update(await asyncio.to_thread(species_catalog_resolver.accepted_scientific_names, name))
    return await repo.species_keys([*names, *synonyms], species_ids=species_ids, taxa_id=taxa_id)
