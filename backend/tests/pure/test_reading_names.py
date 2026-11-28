"""A record's two readings are named the way every other bird is: by the catalogue, in the reader's language (#804)."""

from app.services.bird_summary_names import reading_lookup_label, reading_names
from app.services.species_names import SpeciesIdentityNames

MAGPIE = SpeciesIdentityNames(display="Elster", scientific="Pica pica", species_id=7)


def test_a_reading_the_catalogue_knows_takes_the_readers_names():
    named = reading_names("Pica pica", 0.68, {"pica pica": MAGPIE})

    assert named == {"label": "Pica pica", "scientific_name": "Pica pica", "common_name": "Elster", "score": 0.68}


def test_labels_in_other_grammars_are_looked_up_by_their_scientific_name():
    assert reading_lookup_label("Pica pica (Eurasian Magpie)") == "Pica pica"
    assert reading_lookup_label("05000_Animalia_Chordata_Aves_Passeriformes_Corvidae_Pica_pica") == "Pica pica"
    assert reading_lookup_label("  Pica pica ") == "Pica pica"
    assert reading_names("Pica pica (Eurasian Magpie)", 0.7, {"pica pica": MAGPIE})["common_name"] == "Elster"


def test_a_reading_the_catalogue_cannot_name_keeps_its_stored_names_or_its_label():
    assert reading_names(
        "Corvus corone", 0.98, {}, stored_scientific="Corvus corone", stored_common="Carrion Crow"
    ) == {
        "label": "Corvus corone",
        "scientific_name": "Corvus corone",
        "common_name": "Carrion Crow",
        "score": 0.98,
    }
    assert reading_names("Garden blackbird", 0.5, {}) == {
        "label": "Garden blackbird",
        "scientific_name": None,
        "common_name": None,
        "score": 0.5,
    }


def test_a_stored_scientific_name_is_the_lookup_when_given():
    named = reading_names("Unusual label", 0.9, {"pica pica": MAGPIE}, lookup="Pica pica")

    assert named["common_name"] == "Elster"
    assert named["label"] == "Unusual label"
