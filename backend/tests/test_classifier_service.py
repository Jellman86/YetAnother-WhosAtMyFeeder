import pytest
import numpy as np
import sys
import types
from unittest.mock import MagicMock, patch, mock_open
from unittest.mock import AsyncMock
from PIL import Image

# Mock model_manager before it's imported by anything
mock_mm = MagicMock()
mock_mm.model_manager = MagicMock()
mock_mm.model_manager.get_active_model_paths.return_value = ("model.tflite", "labels.txt", 224)
mock_mm.model_manager.active_model_id = "default"
mock_mm.REMOTE_REGISTRY = []
_original_model_manager_module = sys.modules.get("app.services.model_manager")
sys.modules["app.services.model_manager"] = mock_mm

from app.services.classifier_service import (  # noqa: E402
    ClassifierService,
    ModelInstance,
    _detect_acceleration_capabilities,
    _extract_openvino_unsupported_ops,
    _normalize_inference_provider,
    _probe_openvino_gpu_plugin_error_safe,
    _reconcile_ort_active_provider,
    _resolve_inference_selection,
    _summarize_openvino_load_error,
)
from app.services import classifier_service as classifier_service_module  # noqa: E402
from app.config import settings  # noqa: E402

# Restore the original module so this test file doesn't leak a mock into other tests.
if _original_model_manager_module is not None:
    sys.modules["app.services.model_manager"] = _original_model_manager_module
else:
    sys.modules.pop("app.services.model_manager", None)

@pytest.fixture
def mock_tflite():
    with patch("app.services.classifier_service.tflite") as mock:
        yield mock

@pytest.fixture
def mock_os_path_exists():
    with patch("os.path.exists") as mock:
        mock.return_value = True
        yield mock

def test_model_instance_load(mock_tflite, mock_os_path_exists):
    # Mock labels file content
    m = mock_open(read_data="Bird A\nBird B\n")
    with patch("builtins.open", m):
        model = ModelInstance("test", "model.tflite", "labels.txt")
        success = model.load()
        
    assert success is True
    assert model.loaded is True
    assert len(model.labels) == 2
    assert model.labels[0] == "Bird A"
    mock_tflite.Interpreter.assert_called_with(model_path="model.tflite")

def test_model_instance_classify(mock_tflite, mock_os_path_exists):
    # Mock labels and interpreter
    m = mock_open(read_data="Bird A\nBird B\n")
    with patch("builtins.open", m):
        model = ModelInstance("test", "model.tflite", "labels.txt")
        model.load()
    
    # Mock interpreter behavior
    interpreter = mock_tflite.Interpreter.return_value
    interpreter.get_input_details.return_value = [{'shape': [1, 224, 224, 3], 'dtype': np.float32, 'index': 0}]
    interpreter.get_output_details.return_value = [{'dtype': np.float32, 'index': 0}]
    
    # Mock output tensor (probabilities)
    # [Bird A score, Bird B score]
    mock_output = np.array([[0.8, 0.2]], dtype=np.float32)
    interpreter.get_tensor.return_value = mock_output
    
    # Test image
    img = Image.new('RGB', (100, 100))
    results = model.classify(img)
    
    assert len(results) > 0
    assert results[0]['label'] == "Bird A"
    assert results[0]['score'] == pytest.approx(0.8)

@pytest.mark.asyncio
async def test_classifier_service_init(mock_tflite, mock_os_path_exists):
    # Define a side effect that sets the loaded attribute to True
    def mock_load(self):
        self.loaded = True
        return True

    # Use autospec=True so 'self' is passed to the side_effect
    with patch("app.services.classifier_service.ModelInstance.load", autospec=True, side_effect=mock_load):
        service = ClassifierService()
        assert "bird" in service._models
        assert service.model_loaded is True

@pytest.mark.asyncio
async def test_classifier_service_classify_async(mock_tflite, mock_os_path_exists):
    with patch("app.services.classifier_service.ModelInstance.load", return_value=True), \
         patch("app.services.classifier_service.ModelInstance.classify") as mock_classify:
        
        mock_classify.return_value = [{"label": "Robin", "score": 0.9}]
        service = ClassifierService()
        
        img = Image.new('RGB', (100, 100))
        results = await service.classify_async(img)
        
        assert results[0]["label"] == "Robin"
        mock_classify.assert_called_once()


@pytest.mark.asyncio
async def test_classifier_service_classify_async_applies_personalization_when_enabled(mock_tflite, mock_os_path_exists):
    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = True
    try:
        with patch("app.services.classifier_service.ModelInstance.load", return_value=True), \
             patch("app.services.classifier_service.ModelInstance.classify") as mock_classify, \
             patch("app.services.classifier_service.personalization_service.rerank", new=AsyncMock()) as mock_rerank:

            mock_classify.return_value = [
                {"label": "Robin", "score": 0.8, "index": 0},
                {"label": "Sparrow", "score": 0.2, "index": 1},
            ]
            mock_rerank.return_value = [
                {"label": "Sparrow", "score": 0.55, "index": 1},
                {"label": "Robin", "score": 0.45, "index": 0},
            ]

            service = ClassifierService()
            img = Image.new("RGB", (100, 100))
            results = await service.classify_async(img, camera_name="front")

            assert results[0]["label"] == "Sparrow"
            mock_rerank.assert_awaited_once()
            kwargs = mock_rerank.await_args.kwargs
            assert kwargs["camera_name"] == "front"
            assert kwargs["model_id"] == service._resolve_active_model_id()
    finally:
        settings.classification.personalized_rerank_enabled = original_toggle


@pytest.mark.asyncio
async def test_classifier_service_classify_async_skips_personalization_when_disabled(mock_tflite, mock_os_path_exists):
    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = False
    try:
        with patch("app.services.classifier_service.ModelInstance.load", return_value=True), \
             patch("app.services.classifier_service.ModelInstance.classify") as mock_classify, \
             patch("app.services.classifier_service.personalization_service.rerank", new=AsyncMock()) as mock_rerank:

            mock_classify.return_value = [{"label": "Robin", "score": 0.9, "index": 0}]
            service = ClassifierService()

            img = Image.new("RGB", (100, 100))
            results = await service.classify_async(img, camera_name="front")

            assert results[0]["label"] == "Robin"
            mock_rerank.assert_not_awaited()
    finally:
        settings.classification.personalized_rerank_enabled = original_toggle


@pytest.mark.asyncio
async def test_classifier_service_uses_separate_executors_for_image_and_video_work(mock_tflite, mock_os_path_exists):
    class _FakeLoop:
        def __init__(self):
            self.executors = []

        async def run_in_executor(self, executor, func, *args):
            self.executors.append(executor)
            return func(*args)

    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = False
    try:
        with patch.object(ClassifierService, "_init_bird_model", return_value=None), \
             patch("app.services.classifier_service.ModelInstance.load", return_value=True), \
             patch.object(ClassifierService, "classify", return_value=[{"label": "Robin", "score": 0.9, "index": 0}]), \
             patch.object(ClassifierService, "classify_video", return_value=[{"label": "Robin", "score": 0.9, "index": 0}]), \
             patch("app.services.classifier_service.asyncio.get_running_loop") as mock_get_loop:

            fake_loop = _FakeLoop()
            mock_get_loop.return_value = fake_loop
            service = ClassifierService()

            img = Image.new("RGB", (100, 100))
            await service.classify_async(img, camera_name="front")
            await service.classify_video_async("/tmp/demo.mp4", max_frames=5, camera_name="front")

            assert fake_loop.executors[0] is service._image_executor
            assert fake_loop.executors[1] is service._video_executor
            assert service._image_executor is not service._video_executor
    finally:
        settings.classification.personalized_rerank_enabled = original_toggle


def test_normalize_inference_provider_defaults_to_auto_for_invalid_value():
    assert _normalize_inference_provider(None) == "auto"
    assert _normalize_inference_provider("") == "auto"
    assert _normalize_inference_provider("not-real") == "auto"


def test_resolve_inference_selection_auto_prefers_intel_gpu_then_cuda():
    caps = {
        "ort_available": True,
        "cuda_available": True,
        "openvino_available": True,
        "intel_gpu_available": True,
        "intel_cpu_available": True,
    }
    sel = _resolve_inference_selection("auto", caps)
    assert sel["active_provider"] == "intel_gpu"
    assert sel["backend"] == "openvino"
    assert sel["openvino_device"] == "GPU"
    assert sel["fallback_reason"] is None


def test_resolve_inference_selection_cuda_falls_back_to_cpu_when_unavailable():
    caps = {
        "ort_available": True,
        "cuda_available": False,
        "openvino_available": False,
        "intel_gpu_available": False,
        "intel_cpu_available": False,
    }
    sel = _resolve_inference_selection("cuda", caps)
    assert sel["active_provider"] == "cpu"
    assert sel["backend"] == "onnxruntime"
    assert sel["ort_providers"] == ["CPUExecutionProvider"]
    assert sel["fallback_reason"] is not None


def test_resolve_inference_selection_intel_gpu_falls_back_to_intel_cpu_when_possible():
    caps = {
        "ort_available": True,
        "cuda_available": False,
        "openvino_available": True,
        "intel_gpu_available": False,
        "intel_cpu_available": True,
    }
    sel = _resolve_inference_selection("intel_gpu", caps)
    assert sel["active_provider"] == "intel_cpu"
    assert sel["backend"] == "openvino"
    assert sel["openvino_device"] == "CPU"
    assert sel["fallback_reason"] is not None


def test_detect_acceleration_capabilities_does_not_report_cuda_available_without_nvidia_device():
    with patch("app.services.classifier_service.ONNX_AVAILABLE", True), \
         patch("app.services.classifier_service.ort") as mock_ort, \
         patch("app.services.classifier_service._detect_cuda_hardware_available", return_value=False):
        mock_ort.get_available_providers.return_value = ["CUDAExecutionProvider", "CPUExecutionProvider"]

        caps = _detect_acceleration_capabilities()

    assert caps["ort_available"] is True
    assert caps["cuda_provider_installed"] is True
    assert caps["cuda_available"] is False


def test_openvino_import_supports_top_level_core_when_runtime_module_missing():
    fake_openvino = types.SimpleNamespace(Core=object, __version__="2026.0.0")

    def fake_import_module(name: str):
        if name == "openvino.runtime":
            raise ModuleNotFoundError("No module named 'openvino.runtime'")
        if name == "openvino":
            return fake_openvino
        raise AssertionError(f"unexpected import: {name}")

    with patch("importlib.import_module", side_effect=fake_import_module):
        support = classifier_service_module._detect_openvino_support()

    assert support["available"] is True
    assert support["core_class"] is object
    assert support["version"] == "2026.0.0"
    assert support["import_path"] == "openvino.Core"


def test_reconcile_ort_active_provider_downgrades_cuda_when_session_is_cpu_only():
    active, reason = _reconcile_ort_active_provider(
        requested_active_provider="cuda",
        session_providers=["CPUExecutionProvider"],
    )
    assert active == "cpu"
    assert reason is not None
    assert "without CUDAExecutionProvider" in reason


def test_probe_openvino_gpu_plugin_error_safe_reports_nonzero_subprocess_exit():
    completed = types.SimpleNamespace(returncode=139, stdout="", stderr="")
    with patch("app.services.classifier_service.subprocess.run", return_value=completed):
        err = _probe_openvino_gpu_plugin_error_safe()
    assert err is not None
    assert "exit code 139" in err


def test_detect_acceleration_capabilities_uses_safe_openvino_device_probe():
    with patch("app.services.classifier_service.ONNX_AVAILABLE", False), \
         patch("app.services.classifier_service.OPENVINO_AVAILABLE", True), \
         patch("app.services.classifier_service.OpenVINOCore", side_effect=AssertionError("must not instantiate OpenVINO Core in-process")), \
         patch(
             "app.services.classifier_service._probe_openvino_devices_safe",
             return_value={
                 "ok": True,
                 "devices": ["CPU", "GPU"],
                 "error": None,
                 "gpu_probe_error": None,
             },
         ):
        caps = _detect_acceleration_capabilities()

    assert caps["openvino_available"] is True
    assert caps["openvino_devices"] == ["CPU", "GPU"]
    assert caps["intel_cpu_available"] is True
    assert caps["intel_gpu_available"] is True


def test_summarize_openvino_load_error_includes_unsupported_ops():
    err = (
        "Failed to load OpenVINO model: Exception from src/inference/src/cpp/core.cpp:93:\n"
        "OpenVINO does not support the following ONNX operations: "
        "SequenceEmpty, ConcatFromSequence, SequenceInsert"
    )
    msg = _summarize_openvino_load_error(err, "GPU")
    assert "unsupported ONNX ops" in msg
    assert "SequenceEmpty" in msg
    assert "ConcatFromSequence" in msg
    assert "SequenceInsert" in msg
    assert "using ONNX Runtime CPU" in msg


def test_extract_openvino_unsupported_ops_parses_list():
    err = (
        "Exception from src/inference/src/cpp/core.cpp:93:\n"
        "OpenVINO does not support the following ONNX operations: "
        "SequenceEmpty, ConcatFromSequence, SequenceInsert"
    )
    ops = _extract_openvino_unsupported_ops(err)
    assert ops == ["SequenceEmpty", "ConcatFromSequence", "SequenceInsert"]


def test_summarize_openvino_load_error_truncates_long_error_text():
    err = "Failed to load OpenVINO model: " + ("x" * 1000)
    msg = _summarize_openvino_load_error(err, "CPU")
    assert "OpenVINO CPU could not compile this model on this host" in msg
    assert "using ONNX Runtime CPU" in msg
    assert len(msg) < 420


def test_classifier_status_exposes_openvino_model_compile_diagnostics():
    caps = {
        "ort_available": True,
        "cuda_provider_installed": False,
        "cuda_hardware_available": False,
        "cuda_available": False,
        "openvino_available": True,
        "openvino_version": "2026.0.0",
        "openvino_import_path": "openvino.Core",
        "openvino_import_error": None,
        "openvino_probe_error": None,
        "openvino_gpu_probe_error": None,
        "intel_gpu_available": True,
        "intel_cpu_available": True,
        "openvino_devices": ["CPU", "GPU"],
        "dev_dri_present": True,
        "dev_dri_entries": ["card0", "renderD128"],
        "process_uid": 1000,
        "process_gid": 1000,
        "process_groups": [44, 992],
    }

    with patch.object(ClassifierService, "_init_bird_model", return_value=None), \
         patch("app.services.classifier_service._detect_acceleration_capabilities", return_value=caps):
        service = ClassifierService()

    service._openvino_model_compile_ok = False
    service._openvino_model_compile_device = "GPU"
    service._openvino_model_compile_error = "unsupported ONNX ops: SequenceEmpty"
    service._openvino_model_compile_unsupported_ops = ["SequenceEmpty"]
    status = service.get_status()

    assert status["openvino_model_compile_ok"] is False
    assert status["openvino_model_compile_device"] == "GPU"
    assert "SequenceEmpty" in (status["openvino_model_compile_error"] or "")
    assert status["openvino_model_compile_unsupported_ops"] == ["SequenceEmpty"]
