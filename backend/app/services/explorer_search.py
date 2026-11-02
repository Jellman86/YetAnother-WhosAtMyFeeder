"""The Explorer's search: what was seen here, by any of its names, and one record by its id.

Matching is pure and runs on names the species catalogue already holds, so a keystroke never
reaches iNaturalist. Only taxa with something seen beneath them in the reader's window are
offered; the counts that decide that come from the repositories, under the reader's rules.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal

from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.repositories.garden_repository import GardenRepository
from app.services.taxonomy_tree import SEARCHABLE_RANKS, NamedTaxon, taxonomy_tree

#: Frigate names an event by its start time and a short random suffix: 1793624285.74056-6j3htl.
_FRIGATE_EVENT_ID = re.compile(r"^\d{9,11}\.\d{1,8}-[a-z0-9]{4,16}$")
#: A Garden capture is a UUID written as 32 hex digits.
_GARDEN_CAPTURE_ID = re.compile(r"^[a-f0-9]{32}$")
_SEPARATORS = re.compile(r"[\s\-_.,;:'’()/]+")

RecordKind = Literal["detection", "garden"]


def normalize_search_text(value: str) -> str:
    """Case, accents and separators set aside, so "Mésange-charbonnière" is typed as "mesange charbonniere"."""
    decomposed = unicodedata.normalize("NFKD", value)
    bare = "".join(character for character in decomposed if not unicodedata.combining(character))
    return " ".join(_SEPARATORS.sub(" ", bare.casefold()).split())


def record_id_kind(query: str) -> RecordKind | None:
    """Which record an id names, judged by its shape alone; None for ordinary text."""
    text = query.strip()
    if _GARDEN_CAPTURE_ID.match(text):
        return "garden"
    if _FRIGATE_EVENT_ID.match(text):
        return "detection"
    return None


def _match_strength(query: str, name: str) -> int | None:
    """0 for the whole name, 1 for its start, 2 for the start of a later word, 3 anywhere; None for no match."""
    normalized = normalize_search_text(name)
    if normalized == query:
        return 0
    if normalized.startswith(query):
        return 1
    if f" {query}" in f" {normalized}":
        return 2
    if query in normalized:
        return 3
    return None


@dataclass(frozen=True)
class TaxonHit:
    taxon: NamedTaxon
    bird_species: int
    bird_detections: int
    garden_species: int
    garden_captures: int


def rank_taxon_hits(
    query: str,
    taxa: Iterable[NamedTaxon],
    birds: Mapping[int, tuple[int, int]],
    garden: Mapping[int, tuple[int, int]],
) -> list[TaxonHit]:
    """Taxa whose names match, closest match first, then the most seen, then by name."""
    needle = normalize_search_text(query)
    if not needle:
        return []
    scored: list[tuple[int, int, str, TaxonHit]] = []
    for taxon in taxa:
        strengths = [strength for name in taxon.names if (strength := _match_strength(needle, name)) is not None]
        if not strengths:
            continue
        bird_species, bird_detections = birds.get(taxon.taxon_id, (0, 0))
        garden_species, garden_captures = garden.get(taxon.taxon_id, (0, 0))
        if bird_species + garden_species == 0:
            continue
        hit = TaxonHit(taxon, bird_species, bird_detections, garden_species, garden_captures)
        label = (taxon.name or taxon.scientific_name).casefold()
        scored.append((min(strengths), -(bird_detections + garden_captures), label, hit))
    scored.sort(key=lambda entry: entry[:3])
    return [hit for *_, hit in scored]


def _rolled(counts: Mapping[int, int]) -> dict[int, tuple[int, int]]:
    return taxonomy_tree.seen_by_taxon(counts) if counts else {}


def _search_taxa(
    query: str, language: str, bird_counts: Mapping[int, int], garden_counts: Mapping[int, int]
) -> list[TaxonHit]:
    seen = {species_id for species_id, count in (*bird_counts.items(), *garden_counts.items()) if count > 0}
    if not seen:
        return []
    taxa = taxonomy_tree.seen_taxa(seen, language=language, ranks=SEARCHABLE_RANKS)
    return rank_taxon_hits(query, taxa, _rolled(bird_counts), _rolled(garden_counts))


async def search_seen_taxa(
    query: str, *, language: str, bird_counts: Mapping[int, int], garden_counts: Mapping[int, int]
) -> list[TaxonHit]:
    """Species, genera, families and orders seen here whose names match, read from the catalogue off the loop."""
    return await asyncio.to_thread(_search_taxa, query, language, bird_counts, garden_counts)


async def bird_taxon_members(taxon_id: int) -> set[int]:
    """The species with a bird detection here that are the taxon or sit beneath it."""
    async with get_db() as db:
        seen = await DetectionRepository(db).seen_species_ids()
    return await asyncio.to_thread(taxonomy_tree.members_beneath, taxon_id, seen)


async def garden_taxon_members(taxon_id: int) -> set[int]:
    """The species a Garden capture was named as that are the taxon or sit beneath it."""
    async with get_db() as db:
        seen = await GardenRepository(db).seen_species_ids()
    return await asyncio.to_thread(taxonomy_tree.members_beneath, taxon_id, seen)
