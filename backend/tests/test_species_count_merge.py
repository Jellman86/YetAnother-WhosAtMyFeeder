"""One bird must never arrive as two summary rows.

Observed live: the canonical key prefers catalogue identity, and rows written
between ingest and the next identity backfill lack species_id while their
neighbours carry it - the same Dunnock then grouped as two rows, and the
dashboard's keyed species list crashed on the duplicate, taking the lower
half of the page with it.
"""

from datetime import datetime

from app.repositories.detection_repository import merge_species_count_rows


def _row(species, count, taxa_id=None, at="2026-08-31 09:00:00", event="e1", **extra):
    return {
        "species": species,
        "count": count,
        "latest_event": event,
        "latest_detection_time": datetime.fromisoformat(at),
        "scientific_name": extra.get("scientific_name"),
        "common_name": extra.get("common_name"),
        "taxa_id": taxa_id,
    }


def test_same_taxon_under_two_identity_keys_becomes_one_row():
    rows = [
        _row("Dunnock", 5, taxa_id=13988, at="2026-08-31 08:50:00", event="older"),
        _row("Dunnock", 2, taxa_id=13988, at="2026-08-31 09:19:00", event="newer"),
    ]
    merged = merge_species_count_rows(rows)
    assert len(merged) == 1
    assert merged[0]["count"] == 7
    assert merged[0]["latest_event"] == "newer"


def test_same_name_without_taxon_still_merges_and_adopts_the_taxon():
    rows = [
        _row("Dunnock", 3, taxa_id=13988, scientific_name="Prunella modularis"),
        _row("Dunnock", 1, taxa_id=None),
    ]
    merged = merge_species_count_rows(rows)
    assert len(merged) == 1
    assert merged[0]["taxa_id"] == 13988
    assert merged[0]["scientific_name"] == "Prunella modularis"
    assert merged[0]["count"] == 4


def test_distinct_species_stay_distinct_and_sorted_by_count():
    rows = [
        _row("Dunnock", 2, taxa_id=13988),
        _row("Jungle Babbler", 6, taxa_id=1289423),
    ]
    merged = merge_species_count_rows(rows)
    assert [entry["species"] for entry in merged] == ["Jungle Babbler", "Dunnock"]
