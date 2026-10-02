from types import SimpleNamespace
from unittest.mock import Mock

from app.utils import cuda_runtime as module


def test_windows_packaged_dll_directories_precede_preload_without_repeating_path(tmp_path, monkeypatch):
    cudnn = tmp_path / "nvidia" / "cudnn" / "bin"
    cudnn.mkdir(parents=True)
    (cudnn / "cudnn_graph64_9.dll").touch()
    empty = tmp_path / "nvidia" / "empty" / "bin"
    empty.mkdir(parents=True)
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(
        module.importlib.util,
        "find_spec",
        lambda name: SimpleNamespace(submodule_search_locations=[str(tmp_path / "nvidia")]),
    )
    monkeypatch.setenv("PATH", "existing")
    seen = []
    runtime = SimpleNamespace(preload_dlls=lambda **kw: seen.append((kw, module.os.environ["PATH"])))
    module.preload_packaged_cuda_libraries(runtime)
    module.preload_packaged_cuda_libraries(runtime)
    assert all(path == str(cudnn) + module.os.pathsep + "existing" for _, path in seen)
    assert all(kw == {"directory": ""} for kw, _ in seen)
    assert str(empty) not in module.os.environ["PATH"]


def test_non_windows_preload_does_not_change_search_path(monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setenv("PATH", "existing")
    runtime = SimpleNamespace(preload_dlls=Mock())
    module.preload_packaged_cuda_libraries(runtime)
    assert module.os.environ["PATH"] == "existing"
    runtime.preload_dlls.assert_called_once_with(directory="")


def test_windows_missing_namespace_preserves_system_search_path(monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "win32")
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setenv("PATH", "existing")
    runtime = SimpleNamespace(preload_dlls=Mock())
    module.preload_packaged_cuda_libraries(runtime)
    assert module.os.environ["PATH"] == "existing"
    runtime.preload_dlls.assert_called_once_with(directory="")


def test_classifier_rejects_output_after_internal_cuda_session_fallback():
    import numpy as np
    import pytest
    from app.services.classifier_service import InvalidInferenceOutputError, ONNXModelInstance

    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

    def run(*args):
        providers[:] = ["CPUExecutionProvider"]
        return [np.array([[0.8, 0.2]])]

    session = SimpleNamespace(get_providers=lambda: providers, run=Mock(side_effect=run))
    model = ONNXModelInstance("bird", "unused", "unused", ort_providers=["CUDAExecutionProvider"])
    model.session = session
    with pytest.raises(InvalidInferenceOutputError, match="provider changed"):
        model._run_inference("images", np.zeros((1, 3, 32, 32)))
    with pytest.raises(InvalidInferenceOutputError, match="provider changed"):
        model._run_inference("images", np.zeros((1, 3, 32, 32)))
    assert session.run.call_count == 1


def test_classifier_accepts_reported_cpu_session_when_cuda_failed_during_startup():
    import numpy as np
    from app.services.classifier_service import ONNXModelInstance

    expected = [np.array([[0.8, 0.2]])]
    session = SimpleNamespace(get_providers=lambda: ["CPUExecutionProvider"], run=Mock(return_value=expected))
    model = ONNXModelInstance("bird", "unused", "unused", ort_providers=["CUDAExecutionProvider"])
    model.session = session
    assert model._run_inference("images", np.zeros((1, 3, 32, 32))) is expected
    session.run.assert_called_once()


def test_detector_rejects_output_after_internal_cuda_session_fallback(monkeypatch):
    import numpy as np
    import pytest
    from PIL import Image
    from app.services.bird_crop_service import BirdCropService

    detector = BirdCropService(provider_override="cuda", strict_provider=True)
    session = SimpleNamespace(get_providers=lambda: ["CPUExecutionProvider"], run=lambda *args: [])
    monkeypatch.setattr(detector, "_prepare_detector_input", lambda *args, **kw: (np.zeros((1, 3, 32, 32)), {}))
    with pytest.raises(RuntimeError, match="provider changed"):
        detector.run_detector_outputs({"session": session, "provider": "cuda"}, Image.new("RGB", (32, 32)))


def test_cuda_session_disables_internal_execution_retry():
    session = SimpleNamespace(disable_fallback=Mock())
    module.prevent_internal_cuda_fallback(session)
    session.disable_fallback.assert_called_once_with()


def test_cpu_started_session_errors_identify_the_actual_cpu_provider():
    import numpy as np
    import pytest
    from app.services.classifier_service import InvalidInferenceOutputError, ONNXModelInstance

    model = ONNXModelInstance("bird", "unused", "unused", ort_providers=["CUDAExecutionProvider"])
    model.session = SimpleNamespace(
        get_providers=lambda: ["CPUExecutionProvider"], run=Mock(side_effect=RuntimeError("CPU execution failed"))
    )
    with pytest.raises(InvalidInferenceOutputError) as failure:
        model._run_inference("images", np.zeros((1, 3, 32, 32)))
    assert failure.value.provider == "CPUExecutionProvider"
