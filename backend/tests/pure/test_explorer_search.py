"""Search matching and record-id recognition need no history, catalogue or network."""

import pytest

from app.services.explorer_search import normalize_search_text, rank_taxon_hits, record_id_kind
from app.services.taxonomy_tree import NamedTaxon


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("  Mésange  CHARBONNIÈRE ", "mesange charbonniere"),
        ("Great-tit", "great tit"),
        ("Straße", "strasse"),
        ("  白頭翁 ", "白頭翁"),
    ],
)
def test_search_text_ignores_case_accents_and_separators(text: str, expected: str) -> None:
    assert normalize_search_text(text) == expected


@pytest.mark.parametrize(
    ("query", "kind"),
    [
        ("1793624285.74056-6j3htl", "detection"),
        ("a" * 32, "garden"),
        (" 1793624285.74056-6j3htl ", "detection"),
        ("Great Tit", None),
        ("../1793624285.74056-6j3htl", None),
        ("1793624285.74056-6j3htl/clip", None),
        ("1793624285.74056-", None),
        ("a" * 33, None),
    ],
)
def test_record_ids_are_recognized_only_in_their_complete_shape(query: str, kind: str | None) -> None:
    assert record_id_kind(query) == kind


def taxon(taxon_id: int, name: str) -> NamedTaxon:
    return NamedTaxon(taxon_id, "species", name, name, (name,))


def test_closer_name_matches_rank_ahead_of_more_frequent_visitors() -> None:
    taxa = [taxon(1, "Tit"), taxon(2, "Titmouse"), taxon(3, "Great Tit"), taxon(4, "Antithesis")]
    counts = {1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (1, 4)}
    assert [hit.taxon.taxon_id for hit in rank_taxon_hits("tit", taxa, counts, {})] == [1, 2, 3, 4]


def test_equally_close_matches_rank_by_bird_and_garden_counts_then_name() -> None:
    taxa = [taxon(1, "Great Tit"), taxon(2, "Coal Tit"), taxon(3, "Blue Tit")]
    birds = {1: (1, 1), 2: (1, 2)}
    garden = {3: (1, 2)}
    assert [hit.taxon.taxon_id for hit in rank_taxon_hits("tit", taxa, birds, garden)] == [3, 2, 1]


def test_unseen_taxa_and_empty_queries_produce_no_matches() -> None:
    taxa = [taxon(1, "Great Tit")]
    assert rank_taxon_hits("tit", taxa, {}, {}) == []
    assert rank_taxon_hits(" ", taxa, {1: (1, 3)}, {}) == []
