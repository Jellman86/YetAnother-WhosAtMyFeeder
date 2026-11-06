"""The runtime adapters live behind one contract and one runtime seam.

`ClassifierService` stays the import-compatible facade: the adapters it builds are the
same classes the adapter package exports, and every consumer reads an optional runtime
through `app.services.inference.runtimes`, so one patch there reaches them all.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image

from app.services import classifier_service
from app.services.inference import runtimes
from app.services.inference.adapters import InferenceAdapter
from app.services.inference.adapters.onnx import ONNXModelInstance
from app.services.inference.adapters.openvino import OpenVINOModelInstance
from app.services.inference.adapters.tflite import ModelInstance
from app.services.inference.errors import InvalidInferenceOutputError
from app.services.model_output_groups import BoundOutputGroups
from app.services.species_catalog_resolver import species_catalog_resolver


@pytest.mark.parametrize("adapter_class", [ModelInstance, ONNXModelInstance, OpenVINOModelInstance])
def test_every_runtime_adapter_satisfies_the_facade_contract(adapter_class, tmp_path):
    adapter = adapter_class("bird", str(tmp_path / "absent-model"), str(tmp_path / "absent-labels.txt"))

    assert isinstance(adapter, InferenceAdapter)
    assert adapter.loaded is False
    assert adapter.loaded_artifact_sha256 is None


def test_the_facade_builds_the_adapter_package_classes():
    assert classifier_service.ModelInstance is ModelInstance
    assert classifier_service.ONNXModelInstance is ONNXModelInstance
    assert classifier_service.OpenVINOModelInstance is OpenVINOModelInstance
    assert classifier_service.InvalidInferenceOutputError is InvalidInferenceOutputError
    assert classifier_service.ClassifierService.ModelType is InferenceAdapter


def test_one_runtime_patch_reaches_the_adapter_and_the_capability_probe(monkeypatch, tmp_path):
    monkeypatch.setattr(runtimes, "ONNX_AVAILABLE", False)
    monkeypatch.setattr(runtimes, "ort", None)
    monkeypatch.setattr(runtimes, "OPENVINO_AVAILABLE", False)
    monkeypatch.setattr(runtimes, "OpenVINOCore", None)
    model_path = tmp_path / "model.onnx"
    model_path.write_bytes(b"weights")

    onnx = ONNXModelInstance("bird", str(model_path), str(tmp_path / "labels.txt"))
    openvino = OpenVINOModelInstance("bird", str(model_path), str(tmp_path / "labels.txt"))

    assert onnx.load() is False
    assert onnx.error == "ONNX Runtime not installed"
    assert openvino.load() is False
    assert openvino.error == "OpenVINO runtime not installed"
    capabilities = classifier_service._detect_acceleration_capabilities()
    assert capabilities["ort_available"] is False
    assert capabilities["openvino_available"] is False


def test_a_missing_tflite_runtime_is_reported_not_raised(monkeypatch, tmp_path):
    monkeypatch.setattr(runtimes, "tflite", None)
    model_path = tmp_path / "model.tflite"
    model_path.write_bytes(b"weights")

    model = ModelInstance("bird", str(model_path), str(tmp_path / "labels.txt"))

    assert model.load() is False
    assert model.error == "TFLite runtime not installed"
    assert runtimes.tflite_runtime_name() == "unavailable"


def test_the_onnx_adapter_attributes_execution_failures_to_its_active_provider(tmp_path):
    model = ONNXModelInstance(
        "bird", str(tmp_path / "model.onnx"), str(tmp_path / "labels.txt"), ort_providers=["CUDAExecutionProvider"]
    )
    model.session = MagicMock()
    model.session.get_providers.return_value = ["CPUExecutionProvider"]
    model.session.run.side_effect = RuntimeError("device lost")
    model.loaded = True

    with pytest.raises(InvalidInferenceOutputError) as raised:
        model.classify_raw(Image.new("RGB", (32, 32)))

    assert raised.value.backend == "onnxruntime"
    assert raised.value.provider == "CPUExecutionProvider"
    assert "device lost" in raised.value.detail


def test_the_openvino_adapter_refuses_non_finite_output(tmp_path):
    model = OpenVINOModelInstance("bird", str(tmp_path / "model.onnx"), str(tmp_path / "labels.txt"), input_size=8)
    model.loaded = True
    model.compiled_model = MagicMock()
    model.input_name = "input"
    model._infer_output_tensor = lambda image, input_tensor=None: np.full((1, 3), np.nan, dtype=np.float32)

    with pytest.raises(InvalidInferenceOutputError) as raised:
        model.classify_raw(Image.new("RGB", (8, 8)))

    assert raised.value.backend == "openvino"
    assert raised.value.diagnostics["output_summary"]["invalid_output_kind"] == "all_nan"


@pytest.mark.parametrize("adapter_class", [ModelInstance, ONNXModelInstance, OpenVINOModelInstance])
@pytest.mark.parametrize("have_actual_digest", [True, False])
def test_native_adapters_bind_group_evidence_to_actual_loaded_weights(
    adapter_class, have_actual_digest, monkeypatch, tmp_path
):
    model_file = tmp_path / "model"
    model_file.write_bytes(b"actual weights")
    adapter = adapter_class("bird", str(model_file), str(tmp_path / "labels"), model_sha256="f" * 64)
    digest = adapter.loaded_artifact_sha256
    if not have_actual_digest:
        adapter.loaded_artifact_sha256 = None
    adapter.loaded = True
    adapter.labels = ["bird", "fixture", "unknown"]
    groups = BoundOutputGroups(digest, "b" * 64, ("bird", "nonbird", "unknown"))
    monkeypatch.setattr(
        species_catalog_resolver, "cached_output_groups", lambda sha, labels: groups if sha == digest else None
    )
    probs = np.array([0.55, 0.35, 0.1], dtype=np.float32)
    if adapter_class is not ModelInstance:
        monkeypatch.setattr(adapter, "_preprocess", lambda image: np.zeros((1, 3, 8, 8)))
    if adapter_class is ModelInstance:
        adapter.interpreter = MagicMock()
        monkeypatch.setattr(adapter, "_run_inference", lambda image: probs)
    elif adapter_class is ONNXModelInstance:
        adapter.session = MagicMock()
        monkeypatch.setattr(adapter, "_run_inference", lambda *args: [])
        monkeypatch.setattr(adapter, "_probabilities_from_outputs", lambda outputs: probs)
    else:
        adapter.compiled_model = MagicMock()
        monkeypatch.setattr(adapter, "_infer_logits", lambda *args, **kwargs: np.log(probs))
    results = adapter.classify(Image.new("RGB", (8, 8)))
    assert results[0]["label"] == "bird"
    if have_actual_digest:
        assert results[0]["taxonomic_evidence"]["model_sha256"] == digest
        assert results[0]["taxonomic_evidence"]["bird_mass"] == pytest.approx(0.55)
    else:
        assert "taxonomic_evidence" not in results[0]
