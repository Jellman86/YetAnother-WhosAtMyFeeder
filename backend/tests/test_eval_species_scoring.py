"""Scoring a model by species identity, and only on the birds it can name.

A regional model names the same bird with its own common name ("Common starling"
for the panel's "European Starling"), and cannot name birds outside its region at
all. The 2026-10-06 evaluation counted both as misses: the European FocalNet
model scored 52.8% overall, 83.0% on the European birds it was built for.
"""

from __future__ import annotations

import pytest

from app.services.eval.species_scoring import AccuracyTally, ModelVocabulary

STARLING = 101
BLUE_JAY = 202
ROBIN = 303

EU_MODEL = ModelVocabulary({0: STARLING, 1: ROBIN})


def test_a_prediction_is_the_species_its_output_index_maps_to():
    assert EU_MODEL.species_for({"index": 0, "label": "Common starling"}) == STARLING


def test_a_prediction_without_a_mapped_index_has_no_identity():
    assert EU_MODEL.species_for({"index": 7, "label": "background"}) is None
    assert EU_MODEL.species_for({"label": "Common starling"}) is None
    assert EU_MODEL.species_for({"index": True, "label": "Common starling"}) is None


def test_same_species_is_decided_by_identity_whatever_the_label_says():
    assert EU_MODEL.same_species({"index": 0, "label": "Common starling"}, STARLING) is True
    assert EU_MODEL.same_species({"index": 1, "label": "European Starling"}, STARLING) is False


def test_same_species_is_undecided_without_both_identities():
    """Undecided falls back to the old name match in the harness."""
    assert EU_MODEL.same_species({"index": 7, "label": "European Starling"}, STARLING) is None
    assert EU_MODEL.same_species({"index": 0, "label": "Common starling"}, None) is None


def test_a_bird_outside_the_vocabulary_cannot_be_named():
    assert EU_MODEL.can_name(STARLING) is True
    assert EU_MODEL.can_name(BLUE_JAY) is False
    assert EU_MODEL.can_name(None) is None


def test_the_tally_scores_known_birds_apart_from_birds_the_model_cannot_name():
    tally = AccuracyTally()
    tally.add([True, False, False], panel="shared_core", can_name=True)
    tally.add([False, True, False], panel="shared_core", can_name=True)
    tally.add([False, False, False], panel="shared_core", can_name=False)
    tally.add([False, False, False], panel="regional", can_name=False)
    tally.add([True], panel="regional", can_name=True)

    summary = tally.summary(vocabulary_known=True)

    assert summary["top1_accuracy"] == pytest.approx(2 / 5)
    assert summary["top3_accuracy"] == pytest.approx(3 / 5)
    assert summary["shared_core_top1"] == pytest.approx(1 / 3, abs=1e-4)
    assert summary["regional_top1"] == pytest.approx(1 / 2)
    assert summary["images_in_vocabulary"] == 3
    assert summary["top1_accuracy_in_vocabulary"] == pytest.approx(2 / 3, abs=1e-4)
    assert summary["top3_accuracy_in_vocabulary"] == pytest.approx(1.0)
    assert summary["shared_core_top1_in_vocabulary"] == pytest.approx(1 / 2)
    assert summary["regional_top1_in_vocabulary"] == pytest.approx(1.0)


def test_a_bird_whose_vocabulary_membership_is_unknown_still_counts():
    """Only a bird proven to be outside the vocabulary is set aside; a miss is never hidden on a guess."""
    tally = AccuracyTally()
    tally.add([False], panel="regional", can_name=None)

    summary = tally.summary(vocabulary_known=True)

    assert summary["images_in_vocabulary"] == 1
    assert summary["top1_accuracy_in_vocabulary"] == 0.0


def test_without_a_known_vocabulary_there_are_no_in_vocabulary_figures():
    tally = AccuracyTally()
    tally.add([True], panel="shared_core", can_name=None)

    summary = tally.summary(vocabulary_known=False)

    assert summary["top1_accuracy"] == 1.0
    assert summary["images_in_vocabulary"] is None
    assert summary["top1_accuracy_in_vocabulary"] is None
    assert summary["shared_core_top1_in_vocabulary"] is None


def test_a_panel_the_model_cannot_name_at_all_has_no_in_vocabulary_score():
    """No score is better than 0%: 0% would say the model failed birds it was never built for."""
    tally = AccuracyTally()
    tally.add([False], panel="shared_core", can_name=False)
    tally.add([True], panel="regional", can_name=True)

    summary = tally.summary(vocabulary_known=True)

    assert summary["shared_core_top1"] == 0.0
    assert summary["shared_core_top1_in_vocabulary"] is None
    assert summary["regional_top1_in_vocabulary"] == 1.0


ROCK_PIGEON = 404
BITTERN = 505

# The European FocalNet mapping: 12 outputs carry no catalogue identity, among them "Feral pigeon" and
# "Great bittern". A missing identity is not proof the model cannot name the bird.
EU_MODEL_WITH_GAPS = ModelVocabulary(
    {0: STARLING, 1: ROBIN},
    unresolved_labels=("Feral pigeon", "Great bittern", "Unknown"),
)


def test_a_bird_an_unresolved_output_may_name_is_not_set_aside():
    assert EU_MODEL_WITH_GAPS.can_name(ROCK_PIGEON, scientific_name="Columba livia", common_name="Rock Pigeon") is None
    assert (
        EU_MODEL_WITH_GAPS.can_name(BITTERN, scientific_name="Botaurus stellaris", common_name="Eurasian Bittern")
        is None
    )


def test_an_abstention_output_does_not_make_every_bird_possible():
    assert EU_MODEL_WITH_GAPS.can_name(BLUE_JAY, scientific_name="Cyanocitta cristata", common_name="Blue Jay") is False


def test_an_unresolved_scientific_output_counts_for_its_genus():
    hierarchy = ModelVocabulary(
        {0: STARLING}, unresolved_labels=("01234_Animalia_Chordata_Aves_Columbiformes_Columbidae_Columba_livia",)
    )
    binomial = ModelVocabulary({0: STARLING}, unresolved_labels=("Columba palumbus",))

    assert hierarchy.can_name(ROCK_PIGEON, scientific_name="Columba livia", common_name="Rock Pigeon") is None
    assert binomial.can_name(ROCK_PIGEON, scientific_name="Columba livia", common_name="Rock Pigeon") is None
    assert binomial.can_name(BLUE_JAY, scientific_name="Cyanocitta cristata", common_name="Blue Jay") is False


def test_a_hyphenated_name_is_matched_on_its_last_word():
    gaps = ModelVocabulary({0: STARLING}, unresolved_labels=("Eurasian collared dove",))

    assert (
        gaps.can_name(ROCK_PIGEON, scientific_name="Streptopelia decaocto", common_name="Eurasian Collared-Dove")
        is None
    )
