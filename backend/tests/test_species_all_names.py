"""Every recorded name of a species, for recognising a retitled article as the same taxon."""

import sqlite3

from app.services.species_names import SpeciesNameLookup


def _catalogue(path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE species_names (species_id INTEGER, language_tag TEXT, name TEXT)")
    connection.executemany(
        "INSERT INTO species_names VALUES (?, ?, ?)",
        [
            (7, "en", "Eurasian Chaffinch"),
            (7, "en", "Common Chaffinch"),
            (7, "de", "Buchfink"),
            (8, "en", "Brambling"),
        ],
    )
    connection.commit()
    connection.close()


def test_all_names_are_the_species_own_in_every_language_casefolded(tmp_path):
    path = tmp_path / "catalogue.db"
    _catalogue(path)

    lookup = SpeciesNameLookup(path)

    assert lookup.all_names(7) == frozenset({"eurasian chaffinch", "common chaffinch", "buchfink"})
    assert lookup.all_names(9) == frozenset()


def test_a_catalogue_that_cannot_be_read_yields_no_names(tmp_path):
    assert SpeciesNameLookup(tmp_path / "absent.db").all_names(7) == frozenset()
    unreadable = tmp_path / "empty.db"
    sqlite3.connect(unreadable).close()
    assert SpeciesNameLookup(unreadable).all_names(7) == frozenset()
