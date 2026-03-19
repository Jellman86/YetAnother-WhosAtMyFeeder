import os
import json

import pytest

from app.config import settings
from app.services.model_manager import ModelManager


def test_swap_model_dirs_rolls_back_on_rename_failure(tmp_path, monkeypatch):
    manager = ModelManager()

    target_dir = tmp_path / "convnext_large_inat21"
    staged_dir = tmp_path / "convnext_large_inat21.download"
    target_dir.mkdir(parents=True, exist_ok=True)
    staged_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "labels.txt").write_text("old-labels\n", encoding="utf-8")
    (staged_dir / "labels.txt").write_text("new-labels\n", encoding="utf-8")

    real_rename = os.rename
    staged_to_target_seen = {"value": False}

    def flaky_rename(src, dst):
        if os.path.abspath(src) == os.path.abspath(str(staged_dir)) and os.path.abspath(dst) == os.path.abspath(str(target_dir)):
            staged_to_target_seen["value"] = True
            raise OSError("injected rename failure")
        return real_rename(src, dst)

    monkeypatch.setattr(os, "rename", flaky_rename)

    with pytest.raises(OSError):
        manager._swap_model_dirs(str(staged_dir), str(target_dir))

    assert staged_to_target_seen["value"] is True
    assert (target_dir / "labels.txt").read_text(encoding="utf-8") == "old-labels\n"


def test_validate_download_payload_requires_labels(tmp_path):
    manager = ModelManager()
    staged_dir = tmp_path / "mobilenet_v2_birds.download"
    staged_dir.mkdir(parents=True, exist_ok=True)
    (staged_dir / "model.tflite").write_bytes(b"fake-model")

    meta = {
        "id": "mobilenet_v2_birds",
        "runtime": "tflite",
        "labels_url": "https://example.invalid/labels.txt",
        "download_url": "https://example.invalid/model.tflite",
    }

    with pytest.raises(RuntimeError, match="labels.txt"):
        manager._validate_download_payload(meta, str(staged_dir), "model.tflite")


def test_validate_download_payload_requires_onnx_weights_when_configured(tmp_path):
    manager = ModelManager()
    staged_dir = tmp_path / "convnext_large_inat21.download"
    staged_dir.mkdir(parents=True, exist_ok=True)
    (staged_dir / "model.onnx").write_bytes(b"fake-onnx")
    (staged_dir / "labels.txt").write_text("label\n", encoding="utf-8")

    meta = {
        "id": "convnext_large_inat21",
        "runtime": "onnx",
        "labels_url": "https://example.invalid/labels.txt",
        "download_url": "https://example.invalid/model.onnx",
        "weights_url": "https://example.invalid/model.onnx.data",
    }

    with pytest.raises(RuntimeError, match="model.onnx.data"):
        manager._validate_download_payload(meta, str(staged_dir), "model.onnx")


def test_load_active_model_id_respects_selection(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.model_manager.MODELS_DIR", str(tmp_path))
    config_path = tmp_path / "active_model.json"
    config_path.write_text(json.dumps({"active_model_id": "eva02_large_inat21"}), encoding="utf-8")

    manager = ModelManager()
    assert manager.active_model_id == "eva02_large_inat21"


def test_get_active_model_spec_resolves_family_variant_paths_and_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.model_manager.MODELS_DIR", str(tmp_path))

    family_dir = tmp_path / "small_birds"
    na_dir = family_dir / "na"
    eu_dir = family_dir / "eu"
    na_dir.mkdir(parents=True, exist_ok=True)
    eu_dir.mkdir(parents=True, exist_ok=True)
    (na_dir / "model.onnx").write_bytes(b"na")
    (na_dir / "labels.txt").write_text("na-label\n", encoding="utf-8")
    (eu_dir / "model.onnx").write_bytes(b"eu")
    (eu_dir / "labels.txt").write_text("eu-label\n", encoding="utf-8")

    manager = ModelManager()
    manager.active_model_id = "small_birds"

    original_country = settings.location.country
    original_override = settings.classification.bird_model_region_override
    settings.location.country = "US"
    settings.classification.bird_model_region_override = "auto"
    try:
        na_spec = manager.get_active_model_spec()
        assert na_spec["resolved_region"] == "na"
        assert na_spec["model_path"] == str(na_dir / "model.onnx")
        assert na_spec["labels_path"] == str(na_dir / "labels.txt")
        assert na_spec["input_size"] == 224
        assert na_spec["label_grouping"]["strategy"] == "strip_trailing_parenthetical"
        assert na_spec["supported_inference_providers"] == ["cpu", "intel_cpu"]

        eu_spec = manager.get_active_model_spec(override="eu")
        assert eu_spec["resolved_region"] == "eu"
        assert eu_spec["model_path"] == str(eu_dir / "model.onnx")
        assert eu_spec["labels_path"] == str(eu_dir / "labels.txt")
        assert eu_spec["input_size"] == 384
        assert "intel_gpu" in eu_spec["supported_inference_providers"]
    finally:
        settings.location.country = original_country
        settings.classification.bird_model_region_override = original_override


@pytest.mark.asyncio
async def test_list_installed_models_includes_downloaded_family(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.model_manager.MODELS_DIR", str(tmp_path))

    family_dir = tmp_path / "small_birds" / "na"
    family_dir.mkdir(parents=True, exist_ok=True)
    (family_dir / "model.onnx").write_bytes(b"na")
    (family_dir / "labels.txt").write_text("na-label\n", encoding="utf-8")

    manager = ModelManager()
    manager.active_model_id = "small_birds"

    installed = await manager.list_installed_models()
    by_id = {model.id: model for model in installed}

    assert "small_birds" in by_id
    assert by_id["small_birds"].path == str(family_dir / "model.onnx")
    assert by_id["small_birds"].labels_path == str(family_dir / "labels.txt")
    assert by_id["small_birds"].is_active is True


@pytest.mark.asyncio
async def test_list_available_models_returns_models_sorted_by_sort_order(monkeypatch):
    from app.services import model_manager as model_manager_module

    monkeypatch.setattr(
        model_manager_module,
        "REMOTE_REGISTRY",
        list(reversed(model_manager_module.REMOTE_REGISTRY)),
    )

    models = await ModelManager().list_available_models()

    assert [model.id for model in models] == [
        "mobilenet_v2_birds",
        "small_birds",
        "hieradet_small_inat21",
        "medium_birds",
        "rope_vit_b14_inat21",
        "convnext_large_inat21",
        "eva02_large_inat21",
    ]
    assert [model.sort_order for model in models] == [10, 14, 15, 17, 18, 20, 30]


def test_build_download_progress_is_monotonic_across_onnx_phases():
    manager = ModelManager()

    model_progress = manager._build_download_progress('model', downloaded=100, total=100)
    weights_progress = manager._build_download_progress('weights', downloaded=0, total=100)
    labels_progress = manager._build_download_progress('labels', downloaded=1, total=1)

    assert model_progress == 80.0
    assert weights_progress == 80.0
    assert labels_progress == 99.0


def test_small_slot_registry_entry_requires_external_data_weights_url():
    from app.services import model_manager as model_manager_module

    model_meta = next(model for model in model_manager_module.REMOTE_REGISTRY if model["id"] == "hieradet_small_inat21")

    assert model_meta["runtime"] == "onnx"
    assert model_meta["weights_url"].endswith("hieradet_small_inat21.onnx.data")
