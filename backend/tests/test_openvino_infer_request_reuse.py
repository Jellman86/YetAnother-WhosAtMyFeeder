"""One OpenVINO InferRequest per model, not one per inference.

Creating a request per call churns runtime allocations on every single
classification — device buffers the allocator never returns to the OS — and
was a prime suspect for resident memory growing eightfold in a day (#314).
A reused request rewrites its output buffer on the next inference, so the
result handed to callers must be a copy, never a view of the buffer.
"""

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from app.services.bird_crop_service import _OpenVINODetectorSession
from app.services.classifier_service import OpenVINOModelInstance


def _fake_compiled(output_key: str, output_array: np.ndarray) -> MagicMock:
    compiled = MagicMock()
    compiled.outputs = [output_key]
    request = MagicMock()
    request.infer.return_value = {output_key: output_array}
    compiled.create_infer_request.return_value = request
    return compiled


def _classifier_instance(output_array: np.ndarray) -> OpenVINOModelInstance:
    instance = OpenVINOModelInstance.__new__(OpenVINOModelInstance)
    instance.name = "test"
    instance._lock = threading.Lock()
    instance.input_name = "images"
    instance.compiled_model = _fake_compiled("logits", output_array)
    instance._infer_request = None
    instance._preprocess = lambda image: np.zeros((1, 3, 2, 2), dtype=np.float32)
    return instance


def test_one_infer_request_serves_every_classification():
    instance = _classifier_instance(np.zeros((1, 3), dtype=np.float32))

    instance._infer_output_tensor(object())
    instance._infer_output_tensor(object())

    assert instance.compiled_model.create_infer_request.call_count == 1


def test_classification_output_is_a_copy_not_a_view_of_the_request_buffer():
    buffer = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
    instance = _classifier_instance(buffer)

    result = instance._infer_output_tensor(object())
    buffer[:] = 99.0  # the next inference rewrites the request's buffer

    assert not np.shares_memory(result, buffer)
    assert result[0][0] == 1.0


def test_one_infer_request_serves_every_detector_run():
    buffer = np.array([[0.5]], dtype=np.float32)
    session = _OpenVINODetectorSession.__new__(_OpenVINODetectorSession)
    session._lock = threading.Lock()
    session._compiled = _fake_compiled("det", buffer)
    session._input = SimpleNamespace(name="images")
    session._output_ports = ["det"]
    session._request = None

    feeds = {"images": np.zeros((1, 3, 2, 2), dtype=np.float32)}
    first = session.run(None, feeds)
    session.run(None, feeds)

    assert session._compiled.create_infer_request.call_count == 1
    buffer[:] = 99.0
    assert not np.shares_memory(first[0], buffer)
