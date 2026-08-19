"""The Phase 0 model-artifact inventory.

The catalogue design requires an inventory covering 100% of supported artifact
checksums, with the label grammar declared per artifact rather than guessed from
the file's shape: a NABirds plumage label like `Lesser Goldfinch
(Female/juvenile)` is indistinguishable by shape from the Coral
`Scientific (Common)` pair, and reading it as one put a common name into the
taxon map as a scientific name.
"""

from pathlib import Path

from app.services.model_manager import REMOTE_REGISTRY, RETIRED_CLASSIFIER_MODEL_IDS
from app.services.model_registry_inventory import RegistryArtifact, registry_artifacts
from app.services.model_taxon_map import LABEL_FORMATS

EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "reviews" / "2026-08-19-species-catalogue-phase0-inventory.md"


def _registry_checksums() -> set[str]:
    """Every concrete artifact checksum, walked independently of the inventory."""
    found: set[str] = set()
    for spec in REMOTE_REGISTRY:
        if str(spec.get("sha256") or "").strip():
            found.add(spec["sha256"])
        for variant in (spec.get("region_variants") or {}).values():
            if str(variant.get("sha256") or "").strip():
                found.add(variant["sha256"])
    return found


def test_every_concrete_artifact_appears_exactly_once():
    artifacts = registry_artifacts()

    assert {a.sha256 for a in artifacts} == _registry_checksums()
    assert len({a.artifact_id for a in artifacts}) == len(artifacts)


def test_every_artifact_declares_a_known_label_format():
    for artifact in registry_artifacts():
        assert artifact.label_format in LABEL_FORMATS, artifact.artifact_id


def test_classifiers_and_crop_detectors_are_told_apart():
    artifacts = registry_artifacts()

    detectors = {a.artifact_id for a in artifacts if a.artifact_kind == "crop_detector"}
    assert detectors == {"bird_crop_detector", "bird_crop_detector_accurate_yolox_tiny"}
    for artifact in artifacts:
        expected = "detector_classes" if artifact.artifact_kind == "crop_detector" else None
        if expected:
            assert artifact.label_format == expected, artifact.artifact_id
        else:
            assert artifact.label_format != "detector_classes", artifact.artifact_id


def test_region_variants_are_inventoried_as_their_own_artifacts():
    by_id = {a.artifact_id: a for a in registry_artifacts()}

    assert by_id["small_birds/eu"].sha256 != by_id["small_birds/na"].sha256
    assert by_id["small_birds/eu"].region == "eu"
    # The family parent has no artifact of its own; only its regions do.
    assert "small_birds" not in by_id


def test_retired_models_are_not_inventoried():
    inventoried = {a.model_id for a in registry_artifacts()}

    assert not (inventoried & RETIRED_CLASSIFIER_MODEL_IDS)


def test_the_declared_formats_match_the_published_label_files():
    """Formats verified against the real files on 2026-08-19 (see the evidence doc)."""
    by_id = {a.artifact_id: a.label_format for a in registry_artifacts()}

    assert by_id["rope_vit_b14_inat21"] == "scientific_hierarchy"
    assert by_id["convnext_large_inat21"] == "scientific_binomial"
    assert by_id["eva02_large_inat21"] == "scientific_binomial"
    assert by_id["mobilenet_v2_birds"] == "scientific_paired_common"
    assert by_id["flexivit_il_all"] == "common_name"
    assert by_id["eu_medium_focalnet_b"] == "common_name"
    assert by_id["small_birds/eu"] == "common_name"
    assert by_id["small_birds/na"] == "common_name"
    assert by_id["medium_birds/eu"] == "common_name"
    assert by_id["medium_birds/na"] == "common_name"


def test_the_committed_evidence_covers_every_artifact_checksum():
    """The freeze is only evidence if the committed inventory stays current.

    Adding or replacing a registry artifact without regenerating
    `docs/reviews/2026-08-19-species-catalogue-phase0-inventory.md` fails here,
    which is the Phase 0 gate: the inventory must cover 100% of supported
    artifact checksums.
    """
    text = EVIDENCE.read_text(encoding="utf-8")

    for artifact in registry_artifacts():
        assert artifact.sha256 in text, f"{artifact.artifact_id} missing from the inventory evidence"
        if artifact.labels_sha256:
            assert artifact.labels_sha256 in text, f"{artifact.artifact_id} labels missing from the inventory"


def test_artifact_rows_carry_the_fields_the_catalogue_schema_will_key_on():
    artifact = next(a for a in registry_artifacts() if a.artifact_id == "rope_vit_b14_inat21")

    assert isinstance(artifact, RegistryArtifact)
    assert artifact.runtime == "onnx"
    assert artifact.taxonomy_scope == "wildlife_wide"
    assert len(artifact.sha256) == 64
    assert artifact.labels_sha256 and len(artifact.labels_sha256) == 64
