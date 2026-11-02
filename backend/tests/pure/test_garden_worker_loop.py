"""A warm Garden worker serves only the model binding it loaded first."""

import pytest

from app.services.garden_worker_loop import BoundModel


def binding(request: dict) -> tuple[str, str]:
    return (request["model"], request["provider"])


def test_the_model_loads_once_for_its_binding_and_serves_every_later_request():
    loads = []
    model = BoundModel(lambda request: loads.append(request) or f"model-{len(loads)}", binding)
    first = {"model": "a.onnx", "provider": "cpu", "image": "one.jpg"}
    assert model.get(first) == "model-1"
    assert model.get({"model": "a.onnx", "provider": "cpu", "image": "two.jpg"}) == "model-1"
    assert loads == [first]


@pytest.mark.parametrize("change", [{"model": "b.onnx"}, {"provider": "intel_npu"}])
def test_a_request_for_another_binding_is_refused_not_served_by_the_loaded_model(change):
    model = BoundModel(lambda request: object(), binding)
    model.get({"model": "a.onnx", "provider": "cpu"})
    with pytest.raises(ValueError, match="another model binding"):
        model.get({"model": "a.onnx", "provider": "cpu"} | change)


def test_a_failed_load_binds_nothing():
    attempts = []

    def load(request):
        attempts.append(request["provider"])
        if len(attempts) == 1:
            raise RuntimeError("device unavailable")
        return "loaded"

    model = BoundModel(load, binding)
    with pytest.raises(RuntimeError):
        model.get({"model": "a.onnx", "provider": "intel_npu"})
    assert model.get({"model": "a.onnx", "provider": "cpu"}) == "loaded"
