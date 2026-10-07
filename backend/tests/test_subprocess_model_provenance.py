"""In subprocess mode the parent must still know which weights its workers run.

Detections are tied to the model that produced them through the species catalogue,
keyed on the model's checksum (`ClassifierService.active_model_sha256`). Only
`_init_bird_model` recorded that checksum, and a subprocess-mode parent never runs
it: workers load the model, the parent does not. Subprocess is the default, so on
the reference install 663 of 663 detections had no model provenance, catalogue
shadow resolution never ran, and the model evaluation could not score by species.
"""

from __future__ import annotations

import hashlib

import pytest

from app.services.classifier_service import ClassifierService


def _subprocess_parent(monkeypatch, model_path) -> ClassifierService:
    service = ClassifierService()
    service._image_execution_mode = "subprocess"
    service._worker_process_mode = False
    service._classifier_supervisor = None
    service._video_supervisor = None
    monkeypatch.setattr(service, "_resolve_active_bird_model_spec", lambda: {"model_path": str(model_path())})
    return service


@pytest.mark.asyncio
async def test_a_subprocess_parent_records_the_checksum_of_the_model_its_workers_load(tmp_path, monkeypatch):
    weights = tmp_path / "model.onnx"
    weights.write_bytes(b"focalnet weights")
    loads: list[str] = []
    service = _subprocess_parent(monkeypatch, lambda: weights)
    monkeypatch.setattr(service, "_init_bird_model", lambda: loads.append("loaded"))

    await service.reload_bird_model()

    assert service.active_model_sha256() == hashlib.sha256(b"focalnet weights").hexdigest()
    assert loads == [], "the parent must still not load the model itself"


@pytest.mark.asyncio
async def test_switching_models_in_subprocess_mode_moves_the_checksum_with_it(tmp_path, monkeypatch):
    first = tmp_path / "first.onnx"
    second = tmp_path / "second.onnx"
    first.write_bytes(b"rope weights")
    second.write_bytes(b"eva weights")
    current = {"path": first}
    service = _subprocess_parent(monkeypatch, lambda: current["path"])

    await service.reload_bird_model()
    current["path"] = second
    await service.reload_bird_model()

    assert service.active_model_sha256() == hashlib.sha256(b"eva weights").hexdigest()


@pytest.mark.asyncio
async def test_a_missing_model_file_leaves_no_checksum_rather_than_a_stale_one(tmp_path, monkeypatch):
    weights = tmp_path / "model.onnx"
    weights.write_bytes(b"rope weights")
    current = {"path": weights}
    service = _subprocess_parent(monkeypatch, lambda: current["path"])
    await service.reload_bird_model()

    current["path"] = tmp_path / "gone.onnx"
    await service.reload_bird_model()

    assert service.active_model_sha256() is None


def test_a_subprocess_parent_knows_the_checksum_from_startup(tmp_path, monkeypatch):
    from app.config import settings

    weights = tmp_path / "model.onnx"
    weights.write_bytes(b"startup weights")
    monkeypatch.setattr(settings.classification, "image_execution_mode", "subprocess")
    monkeypatch.setattr(ClassifierService, "_resolve_active_bird_model_spec", lambda self: {"model_path": str(weights)})

    service = ClassifierService()

    assert service._image_execution_mode == "subprocess"
    assert service.active_model_sha256() == hashlib.sha256(b"startup weights").hexdigest()
