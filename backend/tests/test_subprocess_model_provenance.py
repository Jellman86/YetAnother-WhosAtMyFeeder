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


def test_each_result_carries_the_checksum_of_the_model_that_produced_it(tmp_path, monkeypatch):
    """Provenance is bound at inference time, in the process that ran the model, so a model switch while
    the event is still being saved cannot pair one model's output index with another model's identity."""
    from PIL import Image

    from app.services import classifier_service as module

    weights = tmp_path / "rope.onnx"
    weights.write_bytes(b"rope weights")
    service = ClassifierService()
    service._models["bird"] = type("Bird", (), {"model_path": str(weights), "loaded": True})()
    monkeypatch.setattr(service, "_maybe_restore_gpu_provider", lambda: None)
    monkeypatch.setattr(service, "_resolve_bird_classification_image", lambda image, input_context: (image, {}))
    monkeypatch.setattr(
        module,
        "_invoke_model_classify",
        lambda bird, image, input_context=None: [{"index": 3, "label": "Dunnock", "score": 0.9}],
    )

    results = service.classify(Image.new("RGB", (8, 8)))

    assert results[0]["model_sha256"] == hashlib.sha256(b"rope weights").hexdigest()


@pytest.mark.asyncio
async def test_detection_provenance_comes_from_the_result_not_the_currently_loaded_model(monkeypatch):
    from app.services import detection_service as module
    from app.services.species_catalog_resolver import ShadowResolution

    resolved_with: list[str] = []

    class SwitchedClassifier:
        def active_model_sha256(self):
            return "b" * 64  # the model loaded after the switch

    def shadow_resolve(sha, index, name, event):
        resolved_with.append(sha)
        return ShadowResolution(verdict="agree", species_id=5, model_artifact_id=3, model_output_index=index)

    monkeypatch.setattr(module, "get_classifier", lambda: SwitchedClassifier())
    monkeypatch.setattr(module.species_catalog_resolver, "shadow_resolve", shadow_resolve)

    result = await module._catalog_shadow_resolution(
        {"index": 7, "label": "Dunnock", "model_sha256": "a" * 64}, "Prunella modularis", "evt"
    )

    assert resolved_with == ["a" * 64]
    assert result.model_output_index == 7


@pytest.mark.asyncio
async def test_a_result_that_does_not_say_which_model_produced_it_records_no_provenance(monkeypatch):
    from app.services import detection_service as module

    class LoadedClassifier:
        def active_model_sha256(self):
            return "b" * 64

    attempts: list[tuple] = []

    def shadow_resolve(*args):
        attempts.append(args)
        raise AssertionError("an unattributed result must not be resolved against whatever model is loaded now")

    monkeypatch.setattr(module, "get_classifier", lambda: LoadedClassifier())
    monkeypatch.setattr(module.species_catalog_resolver, "shadow_resolve", shadow_resolve)

    result = await module._catalog_shadow_resolution({"index": 7, "label": "Dunnock"}, "Prunella modularis", "evt")

    assert attempts == []
    assert result.verdict == "unavailable"
    assert result.model_artifact_id is None


def test_the_unknown_bird_catchall_keeps_the_producing_models_checksum():
    from app.services.detection_service import DetectionService

    catchall = DetectionService._build_unknown_catchall(
        {"index": 7, "label": "Dunnock", "score": 0.2, "model_sha256": "a" * 64}, source="low_confidence_catchall"
    )

    assert catchall["model_sha256"] == "a" * 64
