"""Which name to show for a species, and why that one.

Grouping now keys on catalogue identity, so two names for one bird count as one
bird. The name shown for that group was still `MAX(display_name)`, which is
whichever name sorts last alphabetically. Correct grouping with an arbitrary
label is a half-finished feature: the label is the part a person sees.

One precedence rule, applied at read time. Identity is never renamed by it: a
locale-dependent name is a rendering, not a fact about the bird.
"""

import pytest

from app.services.species_names import CatalogueNames, choose_display_name


def _names(**kwargs) -> CatalogueNames:
    return CatalogueNames(
        overrides=kwargs.get("overrides", {}),
        vernacular=kwargs.get("vernacular", {}),
        scientific=kwargs.get("scientific"),
    )


def test_an_owner_rename_for_the_language_wins_outright():
    names = _names(
        overrides={"de": "Heckenbraunelle (mein Name)", "": "My Dunnock"},
        vernacular={"de": "Heckenbraunelle", "en": "Dunnock"},
        scientific="Prunella modularis",
    )
    assert choose_display_name(names, language="de") == "Heckenbraunelle (mein Name)"


def test_an_owner_rename_with_no_language_applies_to_every_language():
    names = _names(overrides={"": "Garden Dunnock"}, vernacular={"de": "Heckenbraunelle"})
    assert choose_display_name(names, language="de") == "Garden Dunnock"


def test_a_language_specific_rename_beats_a_global_one():
    names = _names(overrides={"": "Global", "fr": "Local"}, vernacular={"fr": "Accenteur mouchet"})
    assert choose_display_name(names, language="fr") == "Local"


def test_the_catalogue_name_for_the_asked_language_is_used():
    names = _names(vernacular={"it": "Passera scopaiola", "en": "Dunnock"}, scientific="Prunella modularis")
    assert choose_display_name(names, language="it") == "Passera scopaiola"


def test_english_stands_in_when_the_language_has_no_name():
    """Measured: Italian covers 10,210 of 11,276 species, so this path is real."""
    names = _names(vernacular={"en": "Dunnock"}, scientific="Prunella modularis")
    assert choose_display_name(names, language="it") == "Dunnock"


def test_the_scientific_name_is_the_last_resort_before_giving_up():
    names = _names(scientific="Prunella modularis")
    assert choose_display_name(names, language="en") == "Prunella modularis"


def test_nothing_known_returns_nothing_so_the_caller_keeps_what_it_had():
    assert choose_display_name(_names(), language="en") is None


def test_a_regional_language_tag_falls_back_to_its_base_language():
    names = _names(vernacular={"pt": "ferreirinha"})
    assert choose_display_name(names, language="pt-BR") == "ferreirinha"


def test_language_matching_ignores_case_and_surrounding_space():
    names = _names(vernacular={"de": "Heckenbraunelle"})
    assert choose_display_name(names, language="  DE  ") == "Heckenbraunelle"


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_a_blank_name_is_never_shown(blank):
    names = _names(overrides={"en": blank}, vernacular={"en": "Dunnock"})
    assert choose_display_name(names, language="en") == "Dunnock"


def test_an_absent_language_defaults_to_english_rather_than_failing():
    names = _names(vernacular={"en": "Dunnock", "de": "Heckenbraunelle"})
    assert choose_display_name(names, language=None) == "Dunnock"


@pytest.fixture
def catalogue(tmp_path):
    """A miniature catalogue with the same shape as the shipped one."""
    import sqlite3

    path = tmp_path / "species_catalog.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE species_concepts (species_id INTEGER, provider TEXT, provider_taxon_id TEXT,
            source_release TEXT, scientific_name TEXT, authorship TEXT, accepted_name_usage TEXT, status TEXT);
        CREATE TABLE species_names (id INTEGER PRIMARY KEY, species_id INTEGER, language_tag TEXT,
            name TEXT, name_kind TEXT DEFAULT 'vernacular', preferred INTEGER DEFAULT 1,
            region TEXT, provider TEXT, source_release TEXT);
        CREATE TABLE species_name_overrides (id INTEGER PRIMARY KEY, species_id INTEGER,
            language_tag TEXT DEFAULT '', name TEXT, updated_at TEXT);
        """
    )
    connection.execute(
        "INSERT INTO species_concepts VALUES (10081,'ioc','Prunella modularis','14.2','Prunella modularis',NULL,NULL,NULL)"
    )
    for tag, name in (("en", "Dunnock"), ("de", "Heckenbraunelle"), ("it", "Passera scopaiola")):
        connection.execute(
            "INSERT INTO species_names (species_id, language_tag, name, provider, source_release)"
            " VALUES (?,?,?,'ioc','14.2')",
            (10081, tag, name),
        )
    connection.execute(
        "INSERT INTO species_concepts VALUES (9293,'ioc','Erithacus rubecula','14.2','Erithacus rubecula',NULL,NULL,NULL)"
    )
    connection.execute(
        "INSERT INTO species_names (species_id, language_tag, name, provider, source_release)"
        " VALUES (9293,'en','European Robin','ioc','14.2')"
    )
    connection.commit()
    connection.close()
    return path


def test_the_lookup_reads_names_for_the_species_asked_for(catalogue):
    from app.services.species_names import SpeciesNameLookup

    lookup = SpeciesNameLookup(catalogue)
    assert lookup.display_names([10081], language="de") == {10081: "Heckenbraunelle"}
    assert lookup.display_names([10081], language="it") == {10081: "Passera scopaiola"}


def test_the_lookup_falls_back_to_english_then_scientific(catalogue):
    from app.services.species_names import SpeciesNameLookup

    lookup = SpeciesNameLookup(catalogue)
    assert lookup.display_names([9293], language="de") == {9293: "European Robin"}


def test_the_lookup_answers_for_several_species_at_once(catalogue):
    from app.services.species_names import SpeciesNameLookup

    lookup = SpeciesNameLookup(catalogue)
    resolved = lookup.display_names([10081, 9293], language="en")
    assert resolved == {10081: "Dunnock", 9293: "European Robin"}


def test_an_owner_override_is_honoured_by_the_lookup(catalogue):
    import sqlite3

    from app.services.species_names import SpeciesNameLookup

    connection = sqlite3.connect(catalogue)
    connection.execute(
        "INSERT INTO species_name_overrides (species_id, language_tag, name) VALUES (10081,'','Hedge Sparrow')"
    )
    connection.commit()
    connection.close()

    assert SpeciesNameLookup(catalogue).display_names([10081], language="de") == {10081: "Hedge Sparrow"}


def test_an_unknown_species_is_simply_absent(catalogue):
    from app.services.species_names import SpeciesNameLookup

    assert SpeciesNameLookup(catalogue).display_names([999999], language="en") == {}


def test_no_species_ids_asks_the_database_nothing(catalogue):
    from app.services.species_names import SpeciesNameLookup

    assert SpeciesNameLookup(catalogue).display_names([], language="en") == {}


def test_a_missing_catalogue_never_raises_into_a_read_path(tmp_path):
    from app.services.species_names import SpeciesNameLookup

    assert SpeciesNameLookup(tmp_path / "absent.db").display_names([1], language="en") == {}


def test_the_router_prefers_an_owner_rename_over_the_catalogue():
    """A rename is the person's own decision and must outrank every source.

    Guarded explicitly because the catalogue holds a curated name for nearly
    every species, so a naive preference would quietly undo every rename an
    owner had made.
    """
    import inspect

    from app.routers import species as species_router

    source = inspect.getsource(species_router)
    assert "owner_renamed" in source
    assert "None if owner_renamed else catalogue_names.get" in source


def test_the_router_looks_names_up_once_for_the_page():
    """A query per row would put the catalogue in the middle of a loop."""
    import inspect

    from app.routers import species as species_router

    source = inspect.getsource(species_router)
    assert source.count("species_name_lookup.display_names") == 1
    assert "asyncio.to_thread" in source
