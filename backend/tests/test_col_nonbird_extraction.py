"""Resolving the non-bird model classes against the pinned Catalogue of Life.

The 10,000-class models emit 8,514 non-bird classes, which no bird list
covers. Each label's scientific name is matched against the pinned COL26.7
export. Ambiguity fails closed, exactly as the catalogue design requires: a
name with several accepted candidates, an `ambiguous synonym`, or a
`misapplied` usage stays unresolved and is listed for review, never guessed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_col_nonbird_concepts import ColUsage, resolve_needles  # noqa: E402


def _usage(col_id, status, rank="species", parent_id="P1"):
    return ColUsage(col_id=col_id, parent_id=parent_id, status=status, rank=rank)


class TestResolution:
    def test_a_single_accepted_species_resolves_exactly(self):
        result = resolve_needles(
            {"lumbricus terrestris": ("Lumbricus terrestris", "Animalia", "Clitellata")},
            {"lumbricus terrestris": [_usage("C1", "accepted")]},
            {},
        )

        assert result.resolved[0].scientific_name == "Lumbricus terrestris"
        assert result.resolved[0].col_id == "C1"
        assert result.resolved[0].col_status == "accepted"
        assert result.resolved[0].accepted_col_id == "C1"
        assert not result.unresolved

    def test_a_provisionally_accepted_species_resolves_with_its_status_recorded(self):
        result = resolve_needles(
            {"x y": ("X y", "Plantae", "Magnoliopsida")},
            {"x y": [_usage("C2", "provisionally accepted")]},
            {},
        )

        assert result.resolved[0].col_status == "provisionally accepted"

    def test_two_accepted_candidates_fail_closed(self):
        result = resolve_needles(
            {"cyathus striatus": ("Cyathus striatus", "Fungi", "Agaricomycetes")},
            {"cyathus striatus": [_usage("C3", "accepted"), _usage("C4", "accepted")]},
            {},
        )

        assert not result.resolved
        assert result.unresolved[0].reason == "multiple accepted candidates"

    def test_an_unambiguous_synonym_resolves_to_its_accepted_parent(self):
        result = resolve_needles(
            {"parus caeruleus": ("Parus caeruleus", "Animalia", "Insecta")},
            {"parus caeruleus": [_usage("S1", "synonym", parent_id="A1")]},
            {"A1": ("Cyanistes caeruleus", "accepted", "species")},
        )

        entry = result.resolved[0]
        assert entry.col_status == "synonym"
        assert entry.col_id == "S1"
        assert entry.accepted_col_id == "A1"
        assert entry.accepted_scientific_name == "Cyanistes caeruleus"

    def test_synonyms_pointing_at_different_parents_fail_closed(self):
        result = resolve_needles(
            {"a b": ("A b", "Animalia", "Insecta")},
            {"a b": [_usage("S1", "synonym", parent_id="A1"), _usage("S2", "synonym", parent_id="A2")]},
            {"A1": ("C d", "accepted", "species"), "A2": ("E f", "accepted", "species")},
        )

        assert not result.resolved
        assert result.unresolved[0].reason == "synonym of multiple taxa"

    def test_an_ambiguous_synonym_fails_closed(self):
        result = resolve_needles(
            {"a b": ("A b", "Animalia", "Insecta")},
            {"a b": [_usage("S1", "ambiguous synonym", parent_id="A1")]},
            {"A1": ("C d", "accepted", "species")},
        )

        assert not result.resolved
        assert result.unresolved[0].reason == "only ambiguous or misapplied usages"

    def test_a_synonym_whose_parent_is_not_an_accepted_species_fails_closed(self):
        result = resolve_needles(
            {"a b": ("A b", "Animalia", "Insecta")},
            {"a b": [_usage("S1", "synonym", parent_id="A1")]},
            {"A1": ("C", "accepted", "genus")},
        )

        assert not result.resolved
        assert result.unresolved[0].reason == "synonym parent is not an accepted species"

    def test_a_name_the_release_does_not_carry_stays_unresolved(self):
        result = resolve_needles(
            {"missing entirely": ("Missing entirely", "Fungi", "Agaricomycetes")},
            {},
            {},
        )

        assert not result.resolved
        assert result.unresolved[0].reason == "not in the release"

    def test_an_accepted_match_wins_over_synonym_noise(self):
        """CoL often carries the same text as accepted in one source family and
        synonym in another; the accepted usage is the identity."""
        result = resolve_needles(
            {"a b": ("A b", "Animalia", "Insecta")},
            {"a b": [_usage("S1", "synonym", parent_id="A9"), _usage("C1", "accepted")]},
            {},
        )

        assert result.resolved[0].col_id == "C1"
        assert result.resolved[0].col_status == "accepted"

    def test_output_is_sorted_and_carries_the_label_classification(self):
        result = resolve_needles(
            {
                "zz top": ("Zz top", "Plantae", "Magnoliopsida"),
                "aa first": ("Aa first", "Fungi", "Agaricomycetes"),
            },
            {"zz top": [_usage("C1", "accepted")], "aa first": [_usage("C2", "accepted")]},
            {},
        )

        assert [entry.scientific_name for entry in result.resolved] == ["Aa first", "Zz top"]
        assert result.resolved[0].kingdom == "Fungi"
        assert result.resolved[0].label_class == "Agaricomycetes"
