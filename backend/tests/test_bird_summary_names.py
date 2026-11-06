"""A capture's counted species are named as the visit itself is, not by their stored label."""

import sqlite3

import pytest

from app.services.bird_summary_names import name_summaries, resolve_label_names, summary_labels
from app.services.species_catalog_migrations import upgrade_catalog
from app.services.species_catalog_resolver import SpeciesCatalogResolver
from app.services.species_names import SpeciesIdentityNames, SpeciesNameLookup


def _summary(*species: tuple[str, int]) -> dict:
    return {
        "counted": sum(count for _, count in species),
        "unknown": 0,
        "excluded": 0,
        "species": [{"species": name, "count": count} for name, count in species],
        "hint_only": False,
    }


def test_each_counted_species_carries_its_catalogue_names_and_keeps_its_label():
    summaries = {"event": _summary(("Prunella modularis", 2), ("Rattus norvegicus", 1))}
    named = name_summaries(
        summaries,
        {"prunella modularis": SpeciesIdentityNames(display="Dunnock", scientific="Prunella modularis")},
    )
    assert named["event"]["species"] == [
        {
            "species": "Prunella modularis",
            "count": 2,
            "common_name": "Dunnock",
            "scientific_name": "Prunella modularis",
        },
        {"species": "Rattus norvegicus", "count": 1, "common_name": None, "scientific_name": None},
    ]
    assert summaries["event"]["species"][0] == {"species": "Prunella modularis", "count": 2}


def test_labels_are_collected_once_across_captures():
    summaries = {"a": _summary(("Parus major", 1)), "b": _summary(("parus major", 2), ("Erithacus rubecula", 1))}
    assert summary_labels(summaries) == ["Erithacus rubecula", "Parus major"]


@pytest.fixture
def catalogue(tmp_path):
    path = tmp_path / "catalog.db"
    upgrade_catalog(path)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO species(species_id,rank,status) VALUES (77,'species','accepted')")
        db.execute(
            "INSERT INTO species_concepts(species_id,provider,provider_taxon_id,source_release,scientific_name) "
            "VALUES (77,'google-speciesnet','rat','4.0.3','Rattus norvegicus')"
        )
        db.executemany(
            "INSERT INTO species_names(species_id,language_tag,name,name_kind,preferred,provider,source_release) "
            "VALUES (77,?,?,'vernacular',0,'google-speciesnet','4.0.3')",
            [("en", "brown rat"), ("de", "Wanderratte")],
        )
    return path


def test_labels_resolve_through_the_catalogue_in_the_reader_language(catalogue):
    resolver, lookup = SpeciesCatalogResolver(catalogue), SpeciesNameLookup(catalogue)
    english = resolve_label_names(["Rattus norvegicus", "Not a species"], "en", resolver=resolver, lookup=lookup)
    german = resolve_label_names(["Rattus norvegicus"], "de", resolver=resolver, lookup=lookup)
    assert english == {"rattus norvegicus": SpeciesIdentityNames(display="Brown Rat", scientific="Rattus norvegicus")}
    assert german["rattus norvegicus"].display == "Wanderratte"
