import os

import pytest

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
