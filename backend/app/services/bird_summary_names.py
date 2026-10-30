"""Names for the species counted in a capture, as the visit's own name is shown.

A counted bird stores the classifier's label, usually a scientific name. Rows that list the
species in a capture need the reader's common name beside it, so each label is resolved
through the catalogue once per page. An unresolved label keeps no names and the row falls
back to the label itself.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Optional

from app.services.species_catalog_resolver import SpeciesCatalogResolver, species_catalog_resolver
from app.services.species_names import SpeciesIdentityNames, SpeciesNameLookup, species_name_lookup, vernacular_case


def summary_labels(summaries: Mapping[str, dict]) -> list[str]:
    """Every distinct species label across the summaries, once, in a stable order."""
    labels: dict[str, str] = {}
    for summary in summaries.values():
        for entry in summary.get("species", []):
            label = str(entry.get("species") or "").strip()
            if label:
                labels.setdefault(label.casefold(), label)
    return sorted(labels.values(), key=str.casefold)


def resolve_label_names(
    labels: Iterable[str],
    language: Optional[str],
    *,
    resolver: SpeciesCatalogResolver = species_catalog_resolver,
    lookup: SpeciesNameLookup = species_name_lookup,
) -> dict[str, SpeciesIdentityNames]:
    """Catalogue names keyed by casefolded label. Synchronous: run it off the event loop."""
    identities: dict[str, int] = {}
    for label in labels:
        species_id, _status = resolver.resolve_scientific_name(label)
        if species_id is not None:
            identities[label.casefold()] = species_id
    names = lookup.resolve(identities.values(), language=language)
    resolved: dict[str, SpeciesIdentityNames] = {}
    for key, species_id in identities.items():
        found = names.get(species_id)
        if found:
            display = vernacular_case(found.display) if found.display else None
            resolved[key] = SpeciesIdentityNames(display=display, scientific=found.scientific)
    return resolved


def name_summaries(summaries: Mapping[str, dict], names: Mapping[str, SpeciesIdentityNames]) -> dict[str, dict]:
    """Copies of the summaries with each species' common and scientific name beside its label."""
    named: dict[str, dict] = {}
    for event, summary in summaries.items():
        species = []
        for entry in summary.get("species", []):
            found = names.get(str(entry.get("species") or "").strip().casefold())
            species.append(
                {
                    **entry,
                    "common_name": found.display if found else None,
                    "scientific_name": found.scientific if found else None,
                }
            )
        named[event] = {**summary, "species": species}
    return named
