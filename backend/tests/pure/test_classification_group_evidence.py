"""Presence evidence uses every output before top-k or species grouping."""

import numpy as np
import pytest

from app.services.inference.outputs import build_classification_results, resolve_model_labels
from app.services.model_output_groups import BoundOutputGroups
from app.services.species_catalog_resolver import species_catalog_resolver


MODEL = "a" * 64
MAPPING = "b" * 64
LABELS = ["bird one", "bird two", "fixture", "unresolved"]


@pytest.fixture
def bound_groups(monkeypatch):
    groups = BoundOutputGroups(MODEL, MAPPING, ("bird", "bird", "nonbird", "unknown"))
    monkeypatch.setattr(
        species_catalog_resolver,
        "cached_output_groups",
        lambda model, labels: groups if model == MODEL and labels == LABELS else None,
    )
    return groups


def test_group_mass_uses_all_outputs_before_species_aggregation_and_top_k(bound_groups):
    results = build_classification_results(
        np.array([0.2, 0.3, 0.4, 0.1]),
        LABELS,
        top_k=1,
        grouped_labels=["bird", "bird", "fixture", "unresolved"],
        model_sha256=MODEL,
    )
    assert len(results) == 1
    assert results[0]["label"] == "bird"
    proof = results[0]["taxonomic_evidence"]
    assert proof == {
        "model_sha256": MODEL,
        "mapping_sha256": MAPPING,
        "output_width": 4,
        "bird_outputs": 2,
        "nonbird_outputs": 1,
        "bird_mass": pytest.approx(0.5),
        "nonbird_mass": pytest.approx(0.4),
        "unknown_mass": pytest.approx(0.1),
        "top_group": "nonbird",
    }


@pytest.mark.parametrize("model,labels", [(None, LABELS), ("c" * 64, LABELS), (MODEL, list(reversed(LABELS)))])
def test_unbound_classification_keeps_ordinary_results_without_presence_evidence(bound_groups, model, labels):
    results = build_classification_results(np.array([0.2, 0.3, 0.4, 0.1]), labels, top_k=2, model_sha256=model)
    assert len(results) == 2
    assert all("taxonomic_evidence" not in result for result in results)


@pytest.mark.parametrize("probs", [[float("nan"), 0, 0, 1], [-0.1, 0.2, 0.4, 0.5], [0.2, 0.3, 0.4, 0.2], [0.5, 0.5]])
def test_invalid_or_wrong_width_probability_vector_has_no_presence_evidence(bound_groups, probs):
    results = build_classification_results(np.array(probs), LABELS, top_k=1, model_sha256=MODEL)
    assert all("taxonomic_evidence" not in result for result in results)


def test_bird_only_mapping_is_not_presence_evidence(monkeypatch):
    groups = BoundOutputGroups(MODEL, MAPPING, ("bird",) * 4)
    monkeypatch.setattr(species_catalog_resolver, "cached_output_groups", lambda *args: groups)
    results = build_classification_results(np.array([0.2, 0.3, 0.4, 0.1]), LABELS, top_k=1, model_sha256=MODEL)
    assert "taxonomic_evidence" not in results[0]


def test_unavailable_group_snapshot_never_changes_valid_species_labels(monkeypatch):
    from app.services import catalogue_labels

    monkeypatch.setattr(catalogue_labels, "catalogue_labels_for_model", lambda model: LABELS)

    def unavailable():
        raise ValueError("group snapshot unavailable")

    monkeypatch.setattr(species_catalog_resolver, "ensure_loaded", unavailable)
    labels, grouped, source = resolve_model_labels("/absent-labels", {}, model_sha256=MODEL)
    assert (labels, grouped, source) == (LABELS, [], "catalogue")
