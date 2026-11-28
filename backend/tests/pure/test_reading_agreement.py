"""Whether a capture's snapshot reading and its video reading name the same bird (#804)."""

import math

import pytest

from app.services.reading_agreement import (
    READING_AGREEMENTS,
    Reading,
    compare_readings,
    reading_from_model_output,
)

BLUE_TIT = 101
GREAT_TIT = 102
MAGPIE = 103
WOOD_PIGEON = 104

GARDEN_BIRDS = frozenset({BLUE_TIT, GREAT_TIT, MAGPIE, WOOD_PIGEON})


class FakeCatalogue:
    """The two catalogue questions the policy asks, answered from fixed tables."""

    def __init__(self, outputs: dict[str, dict[int, tuple[str, int]]]) -> None:
        # {model_sha256: {output_index: (label the catalogue recorded, species_id)}}
        self._outputs = outputs

    def cached_output_species_id(self, model_sha256: str | None, output_index: int, label: str) -> int | None:
        entry = self._outputs.get(model_sha256 or "", {}).get(output_index)
        if entry is None or entry[0] != label:
            return None
        return entry[1]

    def species_outputs(self, model_sha256: str | None) -> dict[int, int] | None:
        outputs = self._outputs.get(model_sha256 or "")
        if outputs is None:
            return None
        return {index: species_id for index, (_label, species_id) in outputs.items()}


def reading(species_id: int | None, score: float = 0.9, vocabulary: frozenset[int] | None = GARDEN_BIRDS) -> Reading:
    return Reading(species_id=species_id, score=score, vocabulary=vocabulary)


def test_readings_of_the_same_species_agree():
    assert compare_readings(reading(BLUE_TIT, 0.95), reading(BLUE_TIT, 0.81), floor=0.4) == "agree"


def test_readings_of_different_species_above_the_floor_disagree():
    assert compare_readings(reading(WOOD_PIGEON, 0.99), reading(MAGPIE, 0.68), floor=0.4) == "disagree"


def test_a_second_reading_exactly_at_the_floor_counts():
    assert compare_readings(reading(GREAT_TIT, 0.6), reading(BLUE_TIT, 0.4), floor=0.4) == "disagree"


def test_a_second_reading_below_the_floor_never_disagrees():
    assert compare_readings(reading(GREAT_TIT, 0.6), reading(BLUE_TIT, 0.39), floor=0.4) == "cannot_compare"


def test_a_weak_second_reading_of_the_same_species_still_agrees():
    assert compare_readings(reading(GREAT_TIT, 0.6), reading(GREAT_TIT, 0.2), floor=0.4) == "agree"


def test_a_reading_that_names_no_catalogued_bird_cannot_be_compared():
    assert compare_readings(reading(None), reading(BLUE_TIT), floor=0.4) == "cannot_compare"
    assert compare_readings(reading(BLUE_TIT), reading(None), floor=0.4) == "cannot_compare"


def test_a_species_outside_the_second_vocabulary_cannot_be_compared():
    regional = frozenset({BLUE_TIT, MAGPIE})
    first = reading(GREAT_TIT, vocabulary=GARDEN_BIRDS)
    second = reading(BLUE_TIT, vocabulary=regional)

    assert compare_readings(first, second, floor=0.4) == "cannot_compare"


def test_a_species_outside_the_first_vocabulary_cannot_be_compared():
    regional = frozenset({BLUE_TIT, MAGPIE})
    first = reading(BLUE_TIT, vocabulary=regional)
    second = reading(GREAT_TIT, vocabulary=GARDEN_BIRDS)

    assert compare_readings(first, second, floor=0.4) == "cannot_compare"


def test_an_unknown_vocabulary_cannot_prove_a_disagreement():
    assert compare_readings(reading(GREAT_TIT, vocabulary=None), reading(BLUE_TIT), floor=0.4) == "cannot_compare"
    assert compare_readings(reading(GREAT_TIT), reading(BLUE_TIT, vocabulary=None), floor=0.4) == "cannot_compare"


@pytest.mark.parametrize("score", [math.nan, math.inf, -0.1, 1.5])
def test_a_second_reading_without_a_usable_score_cannot_be_compared(score):
    assert compare_readings(reading(GREAT_TIT), reading(BLUE_TIT, score), floor=0.4) == "cannot_compare"


def test_every_outcome_is_one_the_schema_accepts():
    outcomes = {
        compare_readings(reading(BLUE_TIT), reading(BLUE_TIT), floor=0.4),
        compare_readings(reading(BLUE_TIT), reading(MAGPIE), floor=0.4),
        compare_readings(reading(None), reading(MAGPIE), floor=0.4),
    }
    assert outcomes == set(READING_AGREEMENTS)


def test_the_same_species_under_different_label_grammars_agrees():
    catalogue = FakeCatalogue(
        {
            "inat-sha": {7: ("04815_Animalia_Chordata_Aves_Passeriformes_Paridae_Cyanistes_caeruleus", BLUE_TIT)},
            "regional-sha": {3: ("Cyanistes caeruleus (Eurasian Blue Tit)", BLUE_TIT), 4: ("Pica pica", MAGPIE)},
        }
    )
    first = reading_from_model_output(
        catalogue,
        model_sha256="inat-sha",
        output_index=7,
        label="04815_Animalia_Chordata_Aves_Passeriformes_Paridae_Cyanistes_caeruleus",
        score=0.9,
    )
    second = reading_from_model_output(
        catalogue,
        model_sha256="regional-sha",
        output_index=3,
        label="Cyanistes caeruleus (Eurasian Blue Tit)",
        score=0.7,
    )

    assert first.species_id == second.species_id == BLUE_TIT
    assert compare_readings(first, second, floor=0.4) == "agree"


def test_the_same_label_text_from_unidentified_outputs_is_never_an_agreement():
    catalogue = FakeCatalogue({"sha": {1: ("Pica pica", MAGPIE)}})
    unmapped = reading_from_model_output(catalogue, model_sha256="sha", output_index=9, label="Pica pica", score=0.9)
    mapped = reading_from_model_output(catalogue, model_sha256="sha", output_index=1, label="Pica pica", score=0.9)

    assert unmapped.species_id is None
    assert compare_readings(unmapped, mapped, floor=0.4) == "cannot_compare"


def test_a_reading_from_a_model_the_catalogue_does_not_know_has_no_identity_or_vocabulary():
    catalogue = FakeCatalogue({"known": {1: ("Pica pica", MAGPIE)}})

    unknown = reading_from_model_output(catalogue, model_sha256="other", output_index=1, label="Pica pica", score=0.9)

    assert unknown == Reading(species_id=None, score=0.9, vocabulary=None)


def test_a_reading_without_a_model_or_output_has_no_identity():
    catalogue = FakeCatalogue({"sha": {1: ("Pica pica", MAGPIE)}})

    assert reading_from_model_output(catalogue, model_sha256=None, output_index=1, label="Pica pica", score=0.9) == (
        Reading(species_id=None, score=0.9, vocabulary=None)
    )
    assert reading_from_model_output(
        catalogue, model_sha256="sha", output_index=None, label="Pica pica", score=0.9
    ) == (Reading(species_id=None, score=0.9, vocabulary=frozenset({MAGPIE})))


def test_a_readings_vocabulary_is_every_species_its_model_can_name():
    catalogue = FakeCatalogue({"sha": {1: ("Pica pica", MAGPIE), 2: ("Parus major", GREAT_TIT)}})

    result = reading_from_model_output(catalogue, model_sha256="sha", output_index=2, label="Parus major", score=0.8)

    assert result == Reading(species_id=GREAT_TIT, score=0.8, vocabulary=frozenset({MAGPIE, GREAT_TIT}))
