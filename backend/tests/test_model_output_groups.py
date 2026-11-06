"""Coarse bird membership must survive missing species identity and retain provenance."""

import hashlib
import json
from pathlib import Path

import pytest


HIERARCHY_SHA = "a" * 64
BINOMIAL_SHA = "b" * 64


def label_file(labels, grammar):
    digest = hashlib.sha256(("\n".join(labels) + "\n").encode()).hexdigest()
    return digest, {
        "label_format": grammar,
        "output_width": len(labels),
        "outputs": [
            {"index": i, "kind": "species", "label": label, "unresolved": "no catalogue identity"}
            for i, label in enumerate(labels)
        ],
    }


def package():
    hierarchy = [
        "00000_Animalia_Chordata_Aves_Passeriformes_Muscicapidae_Erithacus_rubecula",
        "00001_Animalia_Chordata_Mammalia_Rodentia_Sciuridae_Sciurus_carolinensis",
        "00002_Plantae_Tracheophyta_Magnoliopsida_Lamiales_Lamiaceae_Salvia_microphylla",
        "00003_Fungi_Basidiomycota_Agaricomycetes_Agaricales_Agaricaceae_Agaricus_campestris",
    ]
    hs, h = label_file(hierarchy, "scientific_hierarchy")
    # The other model has deliberately DIFFERENT output ordering.
    bs, b = label_file(
        ["Sciurus carolinensis", "Salvia microphylla", "Erithacus rubecula", "Unresolved species"],
        "scientific_binomial",
    )
    return {
        "schema_version": 1,
        "label_files": {hs: h, bs: b},
        "artifacts": [
            {"artifact_id": "hierarchy", "model_sha256": HIERARCHY_SHA, "labels_sha256": hs, "runtime": "onnx"},
            {"artifact_id": "binomial", "model_sha256": BINOMIAL_SHA, "labels_sha256": bs, "runtime": "onnx"},
        ],
    }


def compile_groups(value):
    from app.services.model_output_groups import compile_output_groups

    return compile_output_groups(value)


def test_unresolved_species_identity_still_has_verified_nonbird_group():
    groups = compile_groups(package())
    assert groups[HIERARCHY_SHA][0] == "bird"
    assert groups[HIERARCHY_SHA][1] == "nonbird"
    assert groups[HIERARCHY_SHA][2] == "nonbird"
    assert groups[HIERARCHY_SHA][3] == "nonbird"


def test_binomial_bridge_matches_names_without_assuming_index_alignment():
    groups = compile_groups(package())
    assert groups[BINOMIAL_SHA] == {0: "nonbird", 1: "nonbird", 2: "bird", 3: "unknown"}


def test_conflicting_class_evidence_never_becomes_last_writer_wins():
    value = package()
    sha, other = label_file(
        ["00000_Animalia_Chordata_Aves_Passeriformes_Sciuridae_Sciurus_carolinensis"], "scientific_hierarchy"
    )
    value["label_files"][sha] = other
    value["artifacts"].append(
        {"artifact_id": "conflict", "model_sha256": "c" * 64, "labels_sha256": sha, "runtime": "onnx"}
    )
    result = compile_groups(value)
    assert result[HIERARCHY_SHA][1] == "unknown"
    assert result[BINOMIAL_SHA][0] == "unknown"


@pytest.mark.parametrize("mutation", ["checksum", "duplicate", "order", "width", "boolean", "unknown_artifact_source"])
def test_unverified_or_incomplete_label_rows_are_rejected(mutation):
    value = package()
    key = next(iter(value["label_files"]))
    entry = value["label_files"][key]
    if mutation == "checksum":
        entry["outputs"][0]["label"] = "changed"
    elif mutation == "duplicate":
        entry["outputs"][1]["index"] = 0
    elif mutation == "order":
        entry["outputs"].reverse()
    elif mutation == "width":
        entry["output_width"] += 1
    elif mutation == "boolean":
        entry["outputs"][0]["index"] = False
    else:
        value["artifacts"][0]["labels_sha256"] = "d" * 64
    with pytest.raises(ValueError):
        compile_groups(value)


def test_ioc_provider_proves_bird_membership_for_a_common_name_output():
    value = package()
    sha, entry = label_file(["European Robin"], "common_name")
    entry["outputs"][0].update(provider="ioc-world-bird-list", taxon="Erithacus rubecula")
    value["label_files"][sha] = entry
    value["artifacts"].append(
        {"artifact_id": "common", "model_sha256": "e" * 64, "labels_sha256": sha, "runtime": "onnx"}
    )
    assert compile_groups(value)["e" * 64][0] == "bird"


def test_unknown_common_name_does_not_gain_a_group_from_arbitrary_result_text():
    value = package()
    sha, entry = label_file(["squirrel"], "common_name")
    value["label_files"][sha] = entry
    value["artifacts"].append(
        {"artifact_id": "custom", "model_sha256": "e" * 64, "labels_sha256": sha, "runtime": "onnx"}
    )
    assert compile_groups(value)["e" * 64][0] == "unknown"


def test_real_bundled_squirrel_is_nonbird_even_without_a_canonical_species():
    value = json.loads((Path(__file__).parents[1] / "app/assets/model_output_mappings.json").read_text())
    artifact = next(row for row in value["artifacts"] if row["artifact_id"] == "dinov2_b14_inat21_metadata_336")
    row = value["label_files"][artifact["labels_sha256"]]["outputs"][4844]
    assert row["label"] == "Sciurus carolinensis" and "unresolved" in row
    assert compile_groups(value)[artifact["model_sha256"]][4844] == "nonbird"


@pytest.mark.parametrize("kind", ["background", "unknown"])
def test_declared_abstention_output_does_not_gain_a_group_from_species_text(kind):
    value = package()
    entry = next(iter(value["label_files"].values()))
    entry["outputs"][1]["kind"] = kind
    assert compile_groups(value)[HIERARCHY_SHA][1] == "unknown"
