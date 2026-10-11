import importlib.util
import json
from pathlib import Path

import pytest


path = Path(__file__).parents[1] / "scripts" / "prepare_garden_model_bundle.py"
spec = importlib.util.spec_from_file_location("garden_bundle", path)
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


def test_taxonomy_keeps_model_output_order_and_rejects_duplicate_ids(tmp_path):
    source = tmp_path / "taxonomy.txt"
    source.write_text("second;mammalia;carnivora;canidae;vulpes;vulpes;red fox\nfirst;aves;;;;;bird\n")
    assert [row["id"] for row in bundle.load_taxonomy(source)] == ["second", "first"]
    source.write_text("duplicate;;;;;;blank\nduplicate;;;;;;animal\n")
    with pytest.raises(ValueError, match="unique"):
        bundle.load_taxonomy(source)


def test_source_metadata_cannot_escape_extracted_release(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        bundle.source_file(tmp_path, "../private.txt")


def test_bundle_binds_ordered_taxonomy_to_exact_models_and_requires_matching_variants(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    for name in ("4.0.3a.onnx", "4.0.3b.onnx", "mdv6-compact-640.onnx", "mdv6-compact-1280.onnx"):
        (models / name).write_bytes(name.encode())
    labels = "".join(f"id-{i};mammalia;;;;;animal-{i}\n" for i in range(2498))
    for variant in ("4.0.3a", "4.0.3b"):
        root = tmp_path / variant
        root.mkdir()
        (root / "info.json").write_text(
            json.dumps(
                {
                    "version": variant,
                    "type": "always_crop" if variant.endswith("a") else "full_image",
                    "classifier_labels": "labels.txt",
                    "taxonomy": "labels.txt",
                    "geofence": "geofence.json",
                }
            )
        )
        (root / "labels.txt").write_text(labels)
        (root / "geofence.json").write_text("{}")
    result = bundle.prepare(tmp_path, models, ["GBR"])
    assert len(result["outputs"]) == 2498
    assert result["model_sha256"]["4.0.3a"] == bundle.checksum(models / "4.0.3a.onnx")
    assert result["outputs"][1]["id"] == "id-1"
    (tmp_path / "4.0.3b/geofence.json").write_text('{"changed": {}}')
    with pytest.raises(ValueError, match="agree"):
        bundle.prepare(tmp_path, models, ["GBR"])
