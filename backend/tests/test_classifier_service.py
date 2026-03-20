import pytest
import numpy as np
import sys
import types
import asyncio
import threading
import importlib
from concurrent.futures import ThreadPoolExecutor
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
    BackgroundImageClassificationUnavailableError,
    ClassifierService,
    InvalidInferenceOutputError,
    LiveImageClassificationOverloadedError,
    ModelInstance,
    ONNXModelInstance,
    OpenVINOModelInstance,
    VideoClassificationWorkerError,
    _safe_softmax,
    _detect_acceleration_capabilities,
    _extract_openvino_unsupported_ops,
    _normalize_inference_provider,
    _probe_openvino_gpu_plugin_error_safe,
    _reconcile_ort_active_provider,
    _resolve_inference_selection,
    _summarize_numeric_array,
    _summarize_openvino_load_error,
)
from app.services.classification_admission import ClassificationLeaseExpiredError  # noqa: E402
from app.services import classifier_service as classifier_service_module  # noqa: E402
from app.services.classifier_supervisor import (  # noqa: E402
    ClassifierWorkerCircuitOpenError,
    ClassifierWorkerDeadlineExceededError,
    ClassifierWorkerExitedError,
    ClassifierWorkerHeartbeatTimeoutError,
    ClassifierWorkerStartupTimeoutError,
)
from app.config import settings  # noqa: E402
from app.config_models import ClassificationSettings  # noqa: E402

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


@pytest.fixture(autouse=True)
def force_in_process_mode():
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "in_process"
    try:
        yield
    finally:
        settings.classification.image_execution_mode = original_mode


def _stub_init_bird_model(self):
    self._models["bird"] = MagicMock(loaded=True, error=None, labels=[])


class _FallbackReadyModel:
    def __init__(self, results):
        self.loaded = True
        self.error = None
        self.labels = []
        self._results = list(results)
        self.cleanup_called = False

    def classify(self, _image):
        return list(self._results)

    def cleanup(self):
        self.cleanup_called = True

    def get_status(self):
        return {"loaded": True, "error": None}


def _make_three_band_image(width: int = 8, height: int = 4) -> Image.Image:
    image = Image.new("RGB", (width, height))
    for x in range(width):
        if x < width // 4:
            color = (0, 255, 0)
        elif x >= width - (width // 4):
            color = (0, 0, 255)
        else:
            color = (255, 0, 0)
        for y in range(height):
            image.putpixel((x, y), color)
    return image


class _SingleSlotBlockingSupervisor:
    def __init__(self):
        self.calls = []
        self.abort_calls = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self._slot_available = asyncio.Event()
        self._slot_available.set()

    async def classify(self, **kwargs):
        self.calls.append(dict(kwargs))
        await self._slot_available.wait()
        self._slot_available.clear()
        try:
            if len(self.calls) == 1:
                self.started.set()
                await self.release.wait()
                return [{"label": "Robin", "score": 0.97, "index": 0}]
            return [{"label": "Blackbird", "score": 0.91, "index": 0}]
        finally:
            self._slot_available.set()

    async def abort_request(self, *, priority: str, work_id: str, lease_token: int, reason: str):
        self.abort_calls.append(
            {
                "priority": priority,
                "work_id": work_id,
                "lease_token": lease_token,
                "reason": reason,
            }
        )
        self.release.set()

    def get_metrics(self):
        return {
            "live": {
                "workers": 1,
                "restarts": 0,
                "last_exit_reason": None,
                "last_runtime_recovery": None,
                "circuit_open": False,
                "circuit_open_until_monotonic": None,
            },
            "background": {
                "workers": 1,
                "restarts": 0,
                "last_exit_reason": None,
                "last_runtime_recovery": None,
                "circuit_open": False,
                "circuit_open_until_monotonic": None,
            },
            "video": {
                "workers": 1,
                "restarts": 0,
                "last_exit_reason": None,
                "last_runtime_recovery": None,
                "circuit_open": False,
                "circuit_open_until_monotonic": None,
            },
            "late_results_ignored": 0,
        }

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


def test_onnx_model_instance_aggregates_grouped_nabirds_species_scores():
    model = ONNXModelInstance("test", "model.onnx", "labels.txt", input_size=224)
    model.loaded = True
    model.labels = [
        "American Goldfinch (Female/Nonbreeding Male)",
        "American Goldfinch (Male)",
        "House Sparrow (Female/Juvenile)",
    ]
    model.label_grouping = {"strategy": "strip_trailing_parenthetical"}
    model._preprocess = MagicMock(return_value=np.zeros((1, 3, 224, 224), dtype=np.float32))

    mock_session = MagicMock()
    mock_session.get_inputs.return_value = [types.SimpleNamespace(name="input")]
    mock_session.run.return_value = [
        np.array([[np.log(0.4), np.log(0.35), np.log(0.25)]], dtype=np.float32)
    ]
    model.session = mock_session

    results = model.classify(Image.new("RGB", (32, 32), color="white"), top_k=5)

    assert [item["label"] for item in results] == ["American Goldfinch", "House Sparrow"]
    assert results[0]["score"] == pytest.approx(0.75, rel=1e-3)
    assert results[1]["score"] == pytest.approx(0.25, rel=1e-3)


def test_onnx_preprocess_letterbox_respects_configured_padding_color():
    model = ONNXModelInstance(
        "test",
        "model.onnx",
        "labels.txt",
        preprocessing={
            "resize_mode": "letterbox",
            "padding_color": [64, 64, 64],
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
        },
        input_size=4,
    )

    image = Image.new("RGB", (8, 4), color=(255, 0, 0))
    arr = model._preprocess(image)[0].transpose(1, 2, 0)

    assert arr[0, 0, 0] == pytest.approx(64.0 / 255.0, abs=1e-3)
    assert arr[2, 2, 0] == pytest.approx(1.0, abs=1e-3)


def test_onnx_preprocess_ignores_invalid_non_rgb_color_space():
    model = ONNXModelInstance(
        "test",
        "model.onnx",
        "labels.txt",
        preprocessing={
            "color_space": "RGBA",
            "resize_mode": "direct_resize",
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
        },
        input_size=4,
    )

    arr = model._preprocess(Image.new("RGB", (4, 4), color=(255, 0, 0)))

    assert arr.shape == (1, 3, 4, 4)


@pytest.mark.parametrize(
    "factory",
    [
        lambda preprocessing: ONNXModelInstance(
            "test",
            "model.onnx",
            "labels.txt",
            preprocessing=preprocessing,
            input_size=4,
        ),
        lambda preprocessing: OpenVINOModelInstance(
            "test",
            "model.onnx",
            "labels.txt",
            preprocessing=preprocessing,
            input_size=4,
            device_name="CPU",
            startup_self_test_enabled=False,
        ),
    ],
)
def test_model_preprocess_center_crop_removes_outer_edge_bands(factory):
    model = factory(
        {
            "resize_mode": "center_crop",
            "crop_pct": 1.0,
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
        }
    )

    arr = model._preprocess(_make_three_band_image())[0].transpose(1, 2, 0)

    assert float(arr[:, 0, 0].mean()) > 0.8
    assert float(arr[:, 0, 1].mean()) < 0.2
    assert float(arr[:, 0, 2].mean()) < 0.2
    assert float(arr[:, -1, 0].mean()) > 0.8
    assert float(arr[:, -1, 1].mean()) < 0.2
    assert float(arr[:, -1, 2].mean()) < 0.2


@pytest.mark.parametrize(
    "factory",
    [
        lambda preprocessing: ONNXModelInstance(
            "test",
            "model.onnx",
            "labels.txt",
            preprocessing=preprocessing,
            input_size=4,
        ),
        lambda preprocessing: OpenVINOModelInstance(
            "test",
            "model.onnx",
            "labels.txt",
            preprocessing=preprocessing,
            input_size=4,
            device_name="CPU",
            startup_self_test_enabled=False,
        ),
    ],
)
def test_model_preprocess_direct_resize_preserves_full_frame_edges(factory):
    model = factory(
        {
            "resize_mode": "direct_resize",
            "mean": [0.0, 0.0, 0.0],
            "std": [1.0, 1.0, 1.0],
        }
    )

    arr = model._preprocess(_make_three_band_image())[0].transpose(1, 2, 0)

    assert float(arr[:, 0, 1].mean()) > 0.8
    assert float(arr[:, 0, 0].mean()) < 0.2
    assert float(arr[:, -1, 2].mean()) > 0.8
    assert float(arr[:, -1, 0].mean()) < 0.2


def test_safe_softmax_sanitizes_non_finite_logits():
    probs = _safe_softmax(np.array([1.0, np.nan, 3.0], dtype=np.float32), context="test")

    assert probs.shape == (3,)
    assert np.isfinite(probs).all()
    assert probs[1] == pytest.approx(0.0)
    assert float(np.sum(probs)) == pytest.approx(1.0)


def test_safe_softmax_non_strict_mode_coerces_all_non_finite_logits(monkeypatch):
    original_value = settings.classification.strict_non_finite_output
    settings.classification.strict_non_finite_output = False

    try:
        probs = _safe_softmax(np.array([np.nan, np.inf, -np.inf], dtype=np.float32), context="test")
    finally:
        settings.classification.strict_non_finite_output = original_value

    assert probs.shape == (3,)
    assert np.isfinite(probs).all()
    assert float(np.sum(probs)) == pytest.approx(1.0)


def test_classifier_supervisor_config_defaults():
    config = ClassificationSettings()

    assert config.image_execution_mode == "in_process"
    assert config.live_worker_count == 2
    assert config.background_worker_count == 1
    assert config.worker_heartbeat_timeout_seconds == pytest.approx(5.0)
    assert config.worker_hard_deadline_seconds == pytest.approx(60.0)
    assert config.background_worker_hard_deadline_seconds == pytest.approx(120.0)
    assert config.strict_non_finite_output is True
    assert config.worker_restart_window_seconds == pytest.approx(60.0)
    assert config.worker_restart_threshold == 3
    assert config.worker_breaker_cooldown_seconds == pytest.approx(60.0)
    assert config.live_event_stale_drop_seconds == pytest.approx(30.0)
    assert config.live_event_coalescing_enabled is True


@pytest.mark.asyncio
async def test_classifier_service_skips_main_bird_model_init_in_subprocess_mode():
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "subprocess"

    try:
        with patch.object(
            ClassifierService,
            "_init_bird_model",
            side_effect=AssertionError("main process should not eagerly load bird model"),
        ):
            service = ClassifierService(supervisor=MagicMock())
            assert "bird" not in service._models
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode


@pytest.mark.asyncio
async def test_classifier_service_caches_acceleration_probe_results():
    caps = {
        "ort_available": False,
        "cuda_provider_installed": False,
        "cuda_hardware_available": False,
        "cuda_available": False,
        "openvino_available": True,
        "openvino_version": "2026.1",
        "openvino_import_path": "openvino.Core",
        "openvino_import_error": None,
        "openvino_probe_error": None,
        "openvino_gpu_probe_error": None,
        "intel_gpu_available": True,
        "intel_cpu_available": True,
        "openvino_devices": ["GPU", "CPU"],
        "dev_dri_present": True,
        "dev_dri_entries": ["renderD128"],
        "process_uid": 1000,
        "process_gid": 1000,
        "process_groups": [44],
    }

    with patch.object(ClassifierService, "_init_bird_model", return_value=None), \
         patch.object(classifier_service_module, "_detect_acceleration_capabilities", return_value=dict(caps)) as mock_detect:
        service = ClassifierService()
        service.get_status()
        service.get_status()

        assert mock_detect.call_count == 1

        service._accel_caps_last_refreshed_monotonic = (
            (service._accel_caps_last_refreshed_monotonic or 0.0) - service._accel_caps_ttl_seconds - 1.0
        )
        service.get_status()

        assert mock_detect.call_count == 2
        await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_routes_live_requests_through_supervisor(mock_tflite, mock_os_path_exists):
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "subprocess"

    class _FakeSupervisor:
        def __init__(self):
            self.calls = []

        async def classify(self, **kwargs):
            self.calls.append(kwargs)
            return [{"label": "Robin", "score": 0.97}]

        def get_metrics(self):
            return {
                "live": {"workers": 2, "restarts": 0, "last_exit_reason": None},
                "background": {"workers": 1, "restarts": 0, "last_exit_reason": None},
                "late_results_ignored": 0,
            }

    supervisor = _FakeSupervisor()

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
            service = ClassifierService(supervisor=supervisor)
            with patch.object(ClassifierService, "classify", side_effect=AssertionError("should use supervisor")):
                img = Image.new("RGB", (32, 32), color="red")
                results = await service.classify_async_live(img, camera_name="front", model_id="default")

            assert results[0]["label"] == "Robin"
            assert supervisor.calls[0]["priority"] == "live"
            assert supervisor.calls[0]["camera_name"] == "front"
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode


@pytest.mark.asyncio
async def test_classifier_service_routes_background_requests_through_supervisor(mock_tflite, mock_os_path_exists):
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "subprocess"

    class _FakeSupervisor:
        def __init__(self):
            self.calls = []

        async def classify(self, **kwargs):
            self.calls.append(kwargs)
            return [{"label": "Blackbird", "score": 0.83}]

        def get_metrics(self):
            return {
                "live": {"workers": 2, "restarts": 0, "last_exit_reason": None},
                "background": {"workers": 1, "restarts": 0, "last_exit_reason": None},
                "late_results_ignored": 0,
            }

    supervisor = _FakeSupervisor()

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
            service = ClassifierService(supervisor=supervisor)
            with patch.object(ClassifierService, "classify", side_effect=AssertionError("should use supervisor")):
                img = Image.new("RGB", (32, 32), color="blue")
                results = await service.classify_async_background(img, camera_name="garden", model_id="default")

            assert results[0]["label"] == "Blackbird"
            assert supervisor.calls[0]["priority"] == "background"
            assert supervisor.calls[0]["camera_name"] == "garden"
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode


@pytest.mark.asyncio
async def test_classifier_service_subprocess_live_queue_saturation_raises_fast(
    mock_tflite, mock_os_path_exists, monkeypatch
):
    original_mode = settings.classification.image_execution_mode
    original_toggle = settings.classification.personalized_rerank_enabled
    original_live_workers = settings.classification.live_worker_count
    settings.classification.image_execution_mode = "subprocess"
    settings.classification.personalized_rerank_enabled = False
    settings.classification.live_worker_count = 1
    monkeypatch.setattr(
        classifier_service_module,
        "CLASSIFIER_LIVE_IMAGE_ADMISSION_TIMEOUT_SECONDS",
        0.01,
        raising=False,
    )

    supervisor = _SingleSlotBlockingSupervisor()

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
            service = ClassifierService(supervisor=supervisor)
            img = Image.new("RGB", (32, 32), color="red")
            first_task = asyncio.create_task(service.classify_async_live(img, camera_name="front"))
            await asyncio.wait_for(supervisor.started.wait(), timeout=1.0)

            with pytest.raises(LiveImageClassificationOverloadedError, match="classify_snapshot_overloaded"):
                await asyncio.wait_for(service.classify_async_live(img, camera_name="front"), timeout=0.2)

            supervisor.release.set()
            assert (await first_task)[0]["label"] == "Robin"
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode
        settings.classification.personalized_rerank_enabled = original_toggle
        settings.classification.live_worker_count = original_live_workers


@pytest.mark.asyncio
async def test_classifier_service_subprocess_status_tracks_live_in_flight_requests(
    mock_tflite, mock_os_path_exists
):
    original_mode = settings.classification.image_execution_mode
    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.image_execution_mode = "subprocess"
    settings.classification.personalized_rerank_enabled = False
    supervisor = _SingleSlotBlockingSupervisor()

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
            service = ClassifierService(supervisor=supervisor)
            img = Image.new("RGB", (32, 32), color="green")
            task = asyncio.create_task(service.classify_async_live(img, camera_name="front"))
            await asyncio.wait_for(supervisor.started.wait(), timeout=1.0)

            assert service.get_status()["live_image_in_flight"] == 1

            supervisor.release.set()
            assert (await task)[0]["label"] == "Robin"
            assert service.get_status()["live_image_in_flight"] == 0
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode
        settings.classification.personalized_rerank_enabled = original_toggle


@pytest.mark.asyncio
async def test_classifier_service_subprocess_live_reclaims_stale_capacity_for_next_request(
    mock_tflite, mock_os_path_exists, monkeypatch
):
    original_mode = settings.classification.image_execution_mode
    original_toggle = settings.classification.personalized_rerank_enabled
    original_live_workers = settings.classification.live_worker_count
    settings.classification.image_execution_mode = "subprocess"
    settings.classification.personalized_rerank_enabled = False
    settings.classification.live_worker_count = 1
    monkeypatch.setattr(
        classifier_service_module,
        "CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS",
        0.01,
        raising=False,
    )

    supervisor = _SingleSlotBlockingSupervisor()

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
            service = ClassifierService(supervisor=supervisor)
            img = Image.new("RGB", (32, 32), color="yellow")
            first_task = asyncio.create_task(service.classify_async_live(img, camera_name="front"))
            await asyncio.wait_for(supervisor.started.wait(), timeout=1.0)

            with pytest.raises(ClassificationLeaseExpiredError):
                await asyncio.wait_for(first_task, timeout=0.2)

            results = await asyncio.wait_for(service.classify_async_live(img, camera_name="front"), timeout=0.2)

            assert results[0]["label"] == "Blackbird"
            assert supervisor.abort_calls
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode
        settings.classification.personalized_rerank_enabled = original_toggle
        settings.classification.live_worker_count = original_live_workers


@pytest.mark.asyncio
async def test_classifier_service_routes_video_requests_through_supervisor(mock_tflite, mock_os_path_exists):
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "subprocess"

    class _FakeSupervisor:
        def __init__(self):
            self.calls = []

        async def classify_video(self, **kwargs):
            self.calls.append(kwargs)
            callback = kwargs.get("progress_callback")
            if callback is not None:
                await callback(1, 3, 0.7, "Robin", None, 0, 3, "bird")
            return [{"label": "Robin", "score": 0.95, "index": 0}]

        def get_metrics(self):
            return {
                "live": {"workers": 2, "restarts": 0, "last_exit_reason": None, "last_runtime_recovery": None},
                "background": {"workers": 1, "restarts": 0, "last_exit_reason": None, "last_runtime_recovery": None},
                "video": {"workers": 1, "restarts": 0, "last_exit_reason": None, "last_runtime_recovery": None},
                "late_results_ignored": 0,
            }

    seen_progress: list[tuple[int, int, str]] = []

    async def _progress(*args):
        seen_progress.append((args[0], args[1], args[3]))

    supervisor = _FakeSupervisor()

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model), \
             patch.object(ClassifierService, "classify_video", side_effect=AssertionError("should use supervisor")):
            service = ClassifierService(supervisor=supervisor)
            results = await service.classify_video_async(
                "/tmp/demo.mp4",
                max_frames=3,
                progress_callback=_progress,
                camera_name="front",
                model_id="default",
            )

            assert results[0]["label"] == "Robin"
            assert supervisor.calls[0]["video_path"] == "/tmp/demo.mp4"
            assert seen_progress == [(1, 3, "Robin")]
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode


@pytest.mark.asyncio
async def test_classifier_service_uses_extended_video_deadline_for_supervisor_workers(mock_tflite, mock_os_path_exists):
    original_mode = settings.classification.image_execution_mode
    original_worker_deadline = settings.classification.worker_hard_deadline_seconds
    original_background_worker_deadline = settings.classification.background_worker_hard_deadline_seconds
    original_video_timeout = settings.classification.video_classification_timeout_seconds
    settings.classification.image_execution_mode = "subprocess"
    settings.classification.worker_hard_deadline_seconds = 35.0
    settings.classification.background_worker_hard_deadline_seconds = 120.0
    settings.classification.video_classification_timeout_seconds = 180

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model), \
             patch("app.services.classifier_service.ClassifierSupervisor") as mock_supervisor:
            service = ClassifierService()

            kwargs = mock_supervisor.call_args.kwargs
            assert kwargs["hard_deadline_seconds"] == 35.0
            assert kwargs["background_hard_deadline_seconds"] == 120.0
            assert kwargs["video_hard_deadline_seconds"] > 180.0
            assert kwargs["video_hard_deadline_seconds"] > kwargs["hard_deadline_seconds"]
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode
        settings.classification.worker_hard_deadline_seconds = original_worker_deadline
        settings.classification.background_worker_hard_deadline_seconds = original_background_worker_deadline
        settings.classification.video_classification_timeout_seconds = original_video_timeout


@pytest.mark.asyncio
async def test_classifier_service_can_propagate_supervisor_video_failure_reason(mock_tflite, mock_os_path_exists):
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "subprocess"

    class _FakeSupervisor:
        async def classify_video(self, **_kwargs):
            raise ClassifierWorkerDeadlineExceededError("worker hard deadline exceeded")

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
            service = ClassifierService(supervisor=_FakeSupervisor())
            with pytest.raises(VideoClassificationWorkerError, match="video_worker_deadline_exceeded") as excinfo:
                await service.classify_video_async(
                    "/tmp/demo.mp4",
                    max_frames=3,
                    camera_name="front",
                    propagate_worker_failure=True,
                )

            assert excinfo.value.reason_code == "video_worker_deadline_exceeded"
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode


@pytest.mark.asyncio
async def test_classifier_service_maps_supervisor_circuit_open_to_live_overload(mock_tflite, mock_os_path_exists):
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "subprocess"

    class _FakeSupervisor:
        async def classify(self, **_kwargs):
            raise ClassifierWorkerCircuitOpenError("live circuit open")

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
            service = ClassifierService(supervisor=_FakeSupervisor())
            img = Image.new("RGB", (16, 16), color="green")
            with pytest.raises(LiveImageClassificationOverloadedError, match="classify_snapshot_circuit_open"):
                await service.classify_async_live(img, camera_name="front")
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode


@pytest.mark.asyncio
async def test_classifier_service_maps_supervisor_heartbeat_timeout_to_live_lease_expiry(mock_tflite, mock_os_path_exists):
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "subprocess"

    class _FakeSupervisor:
        async def classify(self, **_kwargs):
            raise ClassifierWorkerHeartbeatTimeoutError("worker heartbeat timed out")

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
            service = ClassifierService(supervisor=_FakeSupervisor())
            img = Image.new("RGB", (16, 16), color="yellow")
            with pytest.raises(ClassificationLeaseExpiredError):
                await service.classify_async_live(img, camera_name="front")
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode


@pytest.mark.asyncio
async def test_classifier_service_maps_supervisor_startup_timeout_to_live_overload(mock_tflite, mock_os_path_exists):
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "subprocess"

    class _FakeSupervisor:
        async def classify(self, **_kwargs):
            raise ClassifierWorkerStartupTimeoutError("worker startup timed out")

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
            service = ClassifierService(supervisor=_FakeSupervisor())
            img = Image.new("RGB", (16, 16), color="orange")
            with pytest.raises(LiveImageClassificationOverloadedError, match="classify_snapshot_worker_unavailable"):
                await service.classify_async_live(img, camera_name="front")
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode


@pytest.mark.asyncio
async def test_classifier_service_maps_supervisor_startup_timeout_to_empty_background_results(mock_tflite, mock_os_path_exists):
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "subprocess"

    class _FakeSupervisor:
        async def classify(self, **_kwargs):
            raise ClassifierWorkerStartupTimeoutError("worker startup timed out")

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
            service = ClassifierService(supervisor=_FakeSupervisor())
            img = Image.new("RGB", (16, 16), color="purple")
            with pytest.raises(BackgroundImageClassificationUnavailableError, match="background_image_worker_startup_timeout"):
                await service.classify_async_background(img, camera_name="garden")
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode


@pytest.mark.asyncio
async def test_classifier_service_maps_supervisor_exit_during_send_to_background_unavailable(mock_tflite, mock_os_path_exists):
    original_mode = settings.classification.image_execution_mode
    settings.classification.image_execution_mode = "subprocess"

    class _FakeSupervisor:
        async def classify(self, **_kwargs):
            raise ClassifierWorkerExitedError("worker send failed: ConnectionResetError")

    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
            service = ClassifierService(supervisor=_FakeSupervisor())
            img = Image.new("RGB", (16, 16), color="purple")
            with pytest.raises(BackgroundImageClassificationUnavailableError, match="background_image_worker_unavailable"):
                await service.classify_async_background(img, camera_name="garden")
            await service.shutdown()
    finally:
        settings.classification.image_execution_mode = original_mode

@pytest.mark.asyncio
async def test_classifier_service_init(mock_tflite, mock_os_path_exists):
    with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
        service = ClassifierService()
        assert "bird" in service._models
        assert service.model_loaded is True
        await service.shutdown()


@pytest.mark.asyncio
async def test_classify_video_normalizes_birder_taxonomy_labels(mock_tflite, mock_os_path_exists):
    class _FakeBirdModel:
        loaded = True
        labels = [
            "04853_Animalia_Chordata_Mammalia_Carnivora_Felidae_Panthera_tigris",
            "00004_Animalia_Arthropoda_Arachnida_Araneae_Agelenidae_Eratigena_duellica",
        ]

    class _FakeCapture:
        def __init__(self, _path):
            self._index = 0

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == classifier_service_module.cv2.CAP_PROP_FRAME_COUNT:
                return 3
            if prop == classifier_service_module.cv2.CAP_PROP_FPS:
                return 30
            return 0

        def set(self, *_args):
            return True

        def read(self):
            if self._index >= 3:
                return False, None
            self._index += 1
            return True, np.zeros((16, 16, 3), dtype=np.uint8)

        def release(self):
            return None

    fake_model = _FakeBirdModel()
    seen_progress_labels = []

    with patch.object(ClassifierService, "_init_bird_model", return_value=None), \
         patch("app.services.classifier_service.cv2.VideoCapture", _FakeCapture), \
         patch("app.services.classifier_service.cv2.cvtColor", side_effect=lambda frame, _code: frame), \
         patch.object(ClassifierService, "_classify_raw_with_runtime_recovery", return_value=(np.array([0.91, 0.09]), fake_model)):
        service = ClassifierService()
        service._models["bird"] = fake_model

        def _progress_callback(**kwargs):
            seen_progress_labels.append(kwargs.get("top_label"))

        results = service.classify_video("/tmp/demo.mp4", max_frames=3, progress_callback=_progress_callback)

    assert results[0]["label"] == "Panthera tigris"
    assert seen_progress_labels
    assert all(label == "Panthera tigris" for label in seen_progress_labels if label)
    await service.shutdown()


@pytest.mark.asyncio
async def test_classify_video_returns_empty_for_degenerate_uniform_confidence(mock_tflite, mock_os_path_exists):
    class _FakeBirdModel:
        loaded = True
        labels = [f"Class {i}" for i in range(5)]

    fake_model = _FakeBirdModel()
    fake_probs = np.full(5, 0.2, dtype=np.float32)
    fake_frame = np.zeros((32, 32, 3), dtype=np.uint8)

    with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model):
        service = ClassifierService()
        service._models["bird"] = fake_model
        service._active_inference_provider = "intel_gpu"
        service._inference_backend = "openvino"

        with patch.object(service, "_classify_raw_with_runtime_recovery", return_value=(fake_probs, fake_model)), \
             patch("cv2.VideoCapture") as mock_capture:
            capture = mock_capture.return_value
            capture.isOpened.return_value = True
            capture.get.side_effect = lambda prop: 20 if prop == 7 else 10  # 7 is cv2.CAP_PROP_FRAME_COUNT
            capture.set.return_value = True
            capture.read.return_value = (True, fake_frame)
            results = service.classify_video("/tmp/fake.mp4", max_frames=5)

        assert results == []
        await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_classify_async(mock_tflite, mock_os_path_exists):
    with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model), \
         patch.object(ClassifierService, "classify") as mock_classify:
        
        mock_classify.return_value = [{"label": "Robin", "score": 0.9}]
        service = ClassifierService()
        
        img = Image.new('RGB', (100, 100))
        results = await service.classify_async(img)
        
        assert results[0]["label"] == "Robin"
        mock_classify.assert_called_once()
        await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_recovers_from_invalid_openvino_gpu_output(mock_tflite, mock_os_path_exists):
    class _BrokenOpenVINOModel:
        loaded = True
        error = None
        labels = []

        def __init__(self):
            self.cleanup_called = False

        def classify(self, _image):
            raise InvalidInferenceOutputError(
                backend="openvino",
                provider="intel_gpu",
                detail="bird inference produced no finite probabilities",
                diagnostics={
                    "output_summary": {
                        "nan_count": 10000,
                        "finite_count": 0,
                    },
                    "compile_properties": {
                        "INFERENCE_PRECISION_HINT": "f32",
                        "NUM_STREAMS": "1",
                    },
                },
            )

        def cleanup(self):
            self.cleanup_called = True

        def get_status(self):
            return {"loaded": True, "error": None}

    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()
        broken = _BrokenOpenVINOModel()
        recovered = _FallbackReadyModel([{"label": "Unknown Bird", "score": 0.12, "index": 0}])
        service._models["bird"] = broken
        service._inference_backend = "openvino"
        service._active_inference_provider = "intel_gpu"
        service._accel_caps = {
            "openvino_available": True,
            "intel_cpu_available": True,
            "ort_available": True,
        }

        with patch.object(
            service,
            "_load_runtime_fallback_bird_model",
            return_value=(
                recovered,
                "openvino",
                "intel_cpu",
                "Runtime fallback after invalid openvino/intel_gpu output: invalid logits; using openvino/intel_cpu",
            ),
        ) as mock_load, patch.object(
            service,
            "_attempt_gpu_retry_after_invalid_output",
            return_value=False,
        ):
            results = service.classify(Image.new("RGB", (32, 32), color="white"))

        assert results == [{"label": "Unknown Bird", "score": 0.12, "index": 0}]
        assert service._models["bird"] is recovered
        assert service._inference_backend == "openvino"
        assert service._active_inference_provider == "intel_cpu"
        assert service._runtime_invalid_output_failures == 1
        assert service._runtime_fallback_recoveries == 1
        assert service._last_runtime_recovery["status"] == "recovered"
        assert service._last_runtime_recovery["diagnostics"]["output_summary"]["nan_count"] == 10000
        assert service._last_runtime_recovery["diagnostics"]["compile_properties"]["INFERENCE_PRECISION_HINT"] == "f32"
        assert broken.cleanup_called is True
        assert "openvino/intel_cpu" in (service._inference_fallback_reason or "")
        mock_load.assert_called_once()
        await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_retries_gpu_once_before_cpu_fallback(mock_tflite, mock_os_path_exists):
    class _BrokenOpenVINOModel:
        loaded = True
        error = None
        labels = []

        def __init__(self):
            self.cleanup_called = False

        def classify(self, _image):
            raise InvalidInferenceOutputError(
                backend="openvino",
                provider="GPU",
                detail="bird inference produced no finite probabilities",
            )

        def cleanup(self):
            self.cleanup_called = True

        def get_status(self):
            return {"loaded": True, "error": None}

    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()
        broken = _BrokenOpenVINOModel()
        recovered_gpu = _FallbackReadyModel([{"label": "Robin", "score": 0.77, "index": 0}])
        service._models["bird"] = broken
        service._inference_backend = "openvino"
        service._active_inference_provider = "intel_gpu"
        service._accel_caps = {
            "openvino_available": True,
            "intel_gpu_available": True,
            "intel_cpu_available": True,
            "ort_available": True,
        }

        with patch.object(
            service,
            "_build_bird_model_for_backend",
            return_value=recovered_gpu,
        ) as mock_build, patch.object(
            service,
            "_load_runtime_fallback_bird_model",
        ) as mock_fallback, patch.object(
            service,
            "_resolve_active_bird_model_spec",
            return_value={
                "model_path": "/tmp/model.onnx",
                "labels_path": "/tmp/labels.txt",
                "input_size": 384,
                "preprocessing": None,
                "runtime": "onnx",
            },
        ):
            results = service.classify(Image.new("RGB", (32, 32), color="white"))

        assert results == [{"label": "Robin", "score": 0.77, "index": 0}]
        assert service._models["bird"] is recovered_gpu
        assert service._inference_backend == "openvino"
        assert service._active_inference_provider == "intel_gpu"
        assert service._runtime_gpu_retries == 1
        assert service._runtime_fallback_recoveries == 0
        mock_build.assert_called()
        mock_fallback.assert_not_called()
        await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_auto_restores_gpu_after_cpu_fallback_cooldown(mock_tflite, mock_os_path_exists):
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()
        cpu_model = _FallbackReadyModel([{"label": "CPU Bird", "score": 0.2, "index": 0}])
        gpu_model = _FallbackReadyModel([{"label": "GPU Bird", "score": 0.9, "index": 0}])
        service._models["bird"] = cpu_model
        service._inference_backend = "openvino"
        service._active_inference_provider = "intel_cpu"
        service._gpu_restore_not_before_monotonic = 0.0
        service._accel_caps = {
            "openvino_available": True,
            "intel_gpu_available": True,
            "intel_cpu_available": True,
            "ort_available": True,
        }

        original_provider = settings.classification.inference_provider
        settings.classification.inference_provider = "auto"
        try:
            with patch.object(
                service,
                "_build_bird_model_for_backend",
                return_value=gpu_model,
            ) as mock_build, patch.object(
                service,
                "_resolve_active_bird_model_spec",
                return_value={
                    "model_path": "/tmp/model.onnx",
                    "labels_path": "/tmp/labels.txt",
                    "input_size": 384,
                    "preprocessing": None,
                    "runtime": "onnx",
                },
            ):
                results = service.classify(Image.new("RGB", (32, 32), color="white"))
        finally:
            settings.classification.inference_provider = original_provider

        assert results == [{"label": "GPU Bird", "score": 0.9, "index": 0}]
        assert service._models["bird"] is gpu_model
        assert service._inference_backend == "openvino"
        assert service._active_inference_provider == "intel_gpu"
        assert service._runtime_gpu_restore_attempts == 1
        assert service._runtime_gpu_restore_successes == 1
        mock_build.assert_called()
        await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_auto_restore_gpu_skips_artifacts_that_disallow_intel_gpu(
    mock_tflite, mock_os_path_exists
):
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()
        cpu_model = _FallbackReadyModel([{"label": "CPU Bird", "score": 0.2, "index": 0}])
        service._models["bird"] = cpu_model
        service._inference_backend = "openvino"
        service._active_inference_provider = "intel_cpu"
        service._gpu_restore_not_before_monotonic = 0.0
        service._accel_caps = {
            "openvino_available": True,
            "intel_gpu_available": True,
            "intel_cpu_available": True,
            "ort_available": True,
        }

        original_provider = settings.classification.inference_provider
        settings.classification.inference_provider = "auto"
        try:
            with patch.object(
                service,
                "_build_bird_model_for_backend",
            ) as mock_build, patch.object(
                service,
                "_resolve_active_bird_model_spec",
                return_value={
                    "model_path": "/tmp/model.onnx",
                    "labels_path": "/tmp/labels.txt",
                    "input_size": 224,
                    "preprocessing": None,
                    "runtime": "onnx",
                    "supported_inference_providers": ["cpu", "intel_cpu"],
                },
            ):
                results = service.classify(Image.new("RGB", (32, 32), color="white"))
        finally:
            settings.classification.inference_provider = original_provider

        assert results == [{"label": "CPU Bird", "score": 0.2, "index": 0}]
        assert service._models["bird"] is cpu_model
        assert service._active_inference_provider == "intel_cpu"
        assert service._runtime_gpu_restore_attempts == 0
        mock_build.assert_not_called()
        await service.shutdown()


def test_build_bird_model_for_backend_rejects_unsupported_provider():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    spec = {
        "model_path": "/tmp/model.onnx",
        "labels_path": "/tmp/labels.txt",
        "input_size": 224,
        "preprocessing": {},
        "label_grouping": {},
        "supported_inference_providers": ["cpu", "intel_cpu"],
    }

    try:
        assert service._build_bird_model_for_backend(spec, backend="openvino", provider="intel_gpu") is None
        assert service._build_bird_model_for_backend(spec, backend="onnxruntime", provider="cuda") is None
    finally:
        asyncio.run(service.shutdown())


@pytest.mark.asyncio
async def test_classifier_service_recovers_raw_classification_from_invalid_openvino_gpu_output(
    mock_tflite, mock_os_path_exists
):
    class _BrokenOpenVINOModel:
        loaded = True
        error = None
        labels = []

        def __init__(self):
            self.cleanup_called = False

        def classify_raw(self, _image):
            raise InvalidInferenceOutputError(
                backend="openvino",
                provider="intel_gpu",
                detail="bird inference produced no finite probabilities",
            )

        def cleanup(self):
            self.cleanup_called = True

        def get_status(self):
            return {"loaded": True, "error": None}

    class _RecoveredRawModel(_FallbackReadyModel):
        def classify_raw(self, _image):
            return np.array([0.8, 0.2], dtype=np.float32)

    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()
        broken = _BrokenOpenVINOModel()
        recovered = _RecoveredRawModel([])
        recovered.labels = ["Robin", "Sparrow"]
        service._models["bird"] = broken
        service._inference_backend = "openvino"
        service._active_inference_provider = "intel_gpu"

        with patch.object(
            service,
            "_load_runtime_fallback_bird_model",
            return_value=(
                recovered,
                "openvino",
                "intel_cpu",
                "Runtime fallback after invalid openvino/intel_gpu output: invalid logits; using openvino/intel_cpu",
            ),
        ):
            scores, active_model = service._classify_raw_with_runtime_recovery(Image.new("RGB", (32, 32), color="white"))

        assert np.allclose(scores, np.array([0.8, 0.2], dtype=np.float32))
        assert active_model is recovered
        assert service._models["bird"] is recovered
        assert broken.cleanup_called is True
        await service.shutdown()


def test_openvino_model_classify_raw_raises_invalid_output_on_runtime_exception():
    model = OpenVINOModelInstance(
        "bird",
        "/tmp/model.onnx",
        "/tmp/labels.txt",
        device_name="GPU",
    )
    model.loaded = True
    model.compiled_model = object()
    model.input_name = "input"
    model.labels = ["Robin", "Sparrow"]

    with patch.object(
        model,
        "_infer_logits",
        side_effect=RuntimeError("clFlush failed: CL_OUT_OF_RESOURCES"),
    ):
        with pytest.raises(InvalidInferenceOutputError) as exc:
            model.classify_raw(Image.new("RGB", (32, 32), color="white"))

    assert exc.value.backend == "openvino"
    assert exc.value.provider == "GPU"
    assert "CL_OUT_OF_RESOURCES" in exc.value.detail


def test_openvino_model_classify_raises_invalid_output_on_runtime_exception():
    model = OpenVINOModelInstance(
        "bird",
        "/tmp/model.onnx",
        "/tmp/labels.txt",
        device_name="GPU",
    )
    model.loaded = True
    model.compiled_model = object()
    model.input_name = "input"
    model.labels = ["Robin", "Sparrow"]

    with patch.object(
        model,
        "_infer_logits",
        side_effect=RuntimeError("clFlush failed: CL_OUT_OF_RESOURCES"),
    ):
        with pytest.raises(InvalidInferenceOutputError) as exc:
            model.classify(Image.new("RGB", (32, 32), color="white"))

    assert exc.value.backend == "openvino"
    assert exc.value.provider == "GPU"
    assert "CL_OUT_OF_RESOURCES" in exc.value.detail


def test_openvino_model_load_fails_when_gpu_startup_self_test_is_non_finite(mock_os_path_exists):
    fake_core = MagicMock()
    fake_core.read_model.return_value = object()
    fake_core.compile_model.return_value = MagicMock()

    with patch("app.services.classifier_service.OPENVINO_AVAILABLE", True), \
         patch("app.services.classifier_service.OpenVINOCore", return_value=fake_core), \
         patch("builtins.open", mock_open(read_data="Bird A\nBird B\n")), \
         patch.object(
             OpenVINOModelInstance,
             "_run_gpu_startup_self_test",
             side_effect=InvalidInferenceOutputError(
                 backend="openvino",
                 provider="GPU",
                 detail="bird inference produced no finite probabilities during startup self-test",
                 diagnostics={"output_summary": {"nan_count": 10000, "finite_count": 0}},
             ),
         ):
        model = OpenVINOModelInstance(
            "bird",
            "/tmp/model.onnx",
            "/tmp/labels.txt",
            device_name="GPU",
        )

        loaded = model.load()

    assert loaded is False
    assert model.loaded is False
    assert model.compiled_model is None
    assert "startup self-test" in (model.error or "")


def test_openvino_model_load_skips_gpu_startup_self_test_when_disabled(mock_os_path_exists):
    fake_core = MagicMock()
    fake_core.read_model.return_value = object()
    fake_compiled_model = MagicMock()
    fake_compiled_model.inputs = [MagicMock(get_any_name=MagicMock(return_value="input"))]
    fake_core.compile_model.return_value = fake_compiled_model

    with patch("app.services.classifier_service.OPENVINO_AVAILABLE", True), \
         patch("app.services.classifier_service.OpenVINOCore", return_value=fake_core), \
         patch("builtins.open", mock_open(read_data="Bird A\nBird B\n")), \
         patch.object(OpenVINOModelInstance, "_run_gpu_startup_self_test") as mock_self_test:
        model = OpenVINOModelInstance(
            "bird",
            "/tmp/model.onnx",
            "/tmp/labels.txt",
            device_name="GPU",
            startup_self_test_enabled=False,
        )

        loaded = model.load()

    assert loaded is True
    assert model.loaded is True
    mock_self_test.assert_not_called()


def test_summarize_numeric_array_marks_all_nan_output_kind():
    summary = _summarize_numeric_array(
        np.full((1, 10000), np.nan, dtype=np.float32),
        name="output_logits",
    )

    assert summary["shape"] == [1, 10000]
    assert summary["nan_count"] == 10000
    assert summary["finite_count"] == 0
    assert summary["invalid_output_kind"] == "all_nan"


def test_summarize_numeric_array_marks_empty_output_kind():
    summary = _summarize_numeric_array(
        np.array([], dtype=np.float32),
        name="output_logits",
    )

    assert summary["shape"] == [0]
    assert summary["element_count"] == 0
    assert summary["invalid_output_kind"] == "empty"


def test_extract_model_artifact_metadata_reports_hashes_and_onnx_metadata(tmp_path):
    model_path = tmp_path / "model.onnx"
    weights_path = tmp_path / "model.onnx.data"
    model_path.write_bytes(b"onnx-model")
    weights_path.write_bytes(b"weights-data")

    class _FakeOpset:
        def __init__(self, domain, version):
            self.domain = domain
            self.version = version

    fake_model = types.SimpleNamespace(
        producer_name="pytorch",
        producer_version="2.9.1",
        opset_import=[_FakeOpset("", 18)],
        graph=types.SimpleNamespace(
            input=[],
            output=[],
        ),
    )
    fake_onnx = types.SimpleNamespace(load=lambda *_args, **_kwargs: fake_model)
    original_import_module = importlib.import_module

    with patch("importlib.import_module", side_effect=lambda name: fake_onnx if name == "onnx" else original_import_module(name)):
        metadata = classifier_service_module._extract_model_artifact_metadata(str(model_path))

    assert metadata["model_sha256"]
    assert metadata["weights_sha256"]
    assert metadata["producer_name"] == "pytorch"
    assert metadata["producer_version"] == "2.9.1"
    assert metadata["opset"] == [{"domain": "ai.onnx", "version": 18}]


def test_openvino_model_load_applies_optional_gpu_debug_properties(mock_os_path_exists, monkeypatch):
    fake_core = MagicMock()
    fake_core.read_model.return_value = object()
    fake_core.compile_model.return_value = MagicMock()
    monkeypatch.setenv("OPENVINO_GPU_EXECUTION_MODE_HINT", "ACCURACY")
    monkeypatch.setenv("OPENVINO_GPU_ACTIVATIONS_SCALE_FACTOR", "8.0")

    with patch("app.services.classifier_service.OPENVINO_AVAILABLE", True), \
         patch("app.services.classifier_service.OpenVINOCore", return_value=fake_core), \
         patch("builtins.open", mock_open(read_data="Bird A\nBird B\n")), \
         patch.object(OpenVINOModelInstance, "_run_gpu_startup_self_test", return_value=None):
        model = OpenVINOModelInstance(
            "bird",
            "/tmp/model.onnx",
            "/tmp/labels.txt",
            device_name="GPU",
        )

        loaded = model.load()

    assert loaded is True
    _, _, kwargs = fake_core.compile_model.mock_calls[0]
    assert kwargs["config"]["EXECUTION_MODE_HINT"] == "ACCURACY"
    assert kwargs["config"]["ACTIVATIONS_SCALE_FACTOR"] == "8.0"


@pytest.mark.asyncio
async def test_classifier_service_falls_back_when_gpu_startup_self_test_fails(mock_os_path_exists):
    class _FakeOpenVINOModel:
        def __init__(self, *args, **kwargs):
            self.loaded = False
            self.error = "Failed OpenVINO model startup self-test: produced no finite probabilities"

        def load(self):
            return False

    class _FakeONNXModel:
        def __init__(self, *args, **kwargs):
            self.loaded = True
            self.error = None
            self.labels = []
            self.session = None

        def load(self):
            return True

        def get_status(self):
            return {"loaded": True, "error": None}

    caps = {
        "ort_available": True,
        "cuda_provider_installed": False,
        "cuda_hardware_available": False,
        "cuda_available": False,
        "openvino_available": True,
        "openvino_version": "2025.4.1",
        "openvino_import_path": "openvino.runtime.Core",
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
        "process_groups": [44, 107],
    }

    original_provider = settings.classification.inference_provider
    settings.classification.inference_provider = "auto"
    try:
        with patch("app.services.classifier_service._detect_acceleration_capabilities", return_value=caps), \
             patch.object(
                 ClassifierService,
                 "_resolve_active_bird_model_spec",
                 return_value={
                     "model_path": "/tmp/model.onnx",
                     "labels_path": "/tmp/labels.txt",
                     "input_size": 384,
                     "preprocessing": None,
                     "runtime": "onnx",
                 },
             ), \
             patch("app.services.classifier_service.OpenVINOModelInstance", _FakeOpenVINOModel), \
             patch("app.services.classifier_service.ONNXModelInstance", _FakeONNXModel):
            service = ClassifierService()
    finally:
        settings.classification.inference_provider = original_provider

    assert service._inference_backend == "onnxruntime"
    assert service._active_inference_provider == "cpu"
    assert "startup self-test" in (service._openvino_model_compile_error or "")
    await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_uses_tflite_asset_paths_when_onnx_fallback_reaches_tflite(
    mock_tflite, mock_os_path_exists
):
    with patch.object(
        classifier_service_module,
        "_detect_acceleration_capabilities",
        return_value={
            "openvino_available": False,
            "ort_available": True,
            "intel_cpu_available": False,
            "intel_gpu_available": False,
        },
    ), patch.object(
        classifier_service_module,
        "_resolve_inference_selection",
        return_value={
            "backend": "onnxruntime",
            "active_provider": "cpu",
            "ort_providers": ["CPUExecutionProvider"],
            "fallback_reason": None,
        },
    ), patch.object(
        ClassifierService,
        "_resolve_active_bird_model_spec",
        return_value={
            "model_path": "/tmp/active/model.onnx",
            "labels_path": "/tmp/active/labels.txt",
            "input_size": 384,
            "preprocessing": {"mean": [0.5, 0.5, 0.5], "std": [0.5, 0.5, 0.5]},
            "runtime": "onnx",
        },
    ), patch.object(
        ClassifierService,
        "_get_model_paths",
        return_value=("/tmp/fallback/model.tflite", "/tmp/fallback/labels.txt"),
    ), patch(
        "app.services.classifier_service.ONNXModelInstance"
    ) as mock_onnx_model, patch(
        "app.services.classifier_service.ModelInstance"
    ) as mock_tflite_model:
        mock_onnx_model.return_value.load.return_value = False
        mock_tflite_model.return_value.load.return_value = True
        mock_tflite_model.return_value.loaded = True
        mock_tflite_model.return_value.error = None

        service = ClassifierService()

        mock_tflite_model.assert_called_with(
            "bird",
            "/tmp/fallback/model.tflite",
            "/tmp/fallback/labels.txt",
            preprocessing={"mean": [0.5, 0.5, 0.5], "std": [0.5, 0.5, 0.5]},
            label_grouping=None,
        )
        assert service._inference_backend == "tflite"
        assert service._active_inference_provider == "tflite"
        await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_health_reports_error_when_invalid_output_recovery_fails(mock_tflite, mock_os_path_exists):
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()
        service._models["bird"] = _FallbackReadyModel([{"label": "Robin", "score": 0.9, "index": 0}])
        service._last_runtime_recovery = {
            "status": "failed",
            "failed_backend": "openvino",
            "failed_provider": "intel_gpu",
            "detail": "bird inference produced no finite probabilities",
            "at": 123.0,
        }

        health = service.check_health()

        assert health["status"] == "error"
        assert health["runtime_recovery"]["last_recovery"]["status"] == "failed"
        await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_classify_async_applies_personalization_when_enabled(mock_tflite, mock_os_path_exists):
    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = True
    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model), \
             patch.object(ClassifierService, "classify") as mock_classify, \
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
            await service.shutdown()
    finally:
        settings.classification.personalized_rerank_enabled = original_toggle


@pytest.mark.asyncio
async def test_classifier_service_classify_async_skips_personalization_when_disabled(mock_tflite, mock_os_path_exists):
    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = False
    try:
        with patch.object(ClassifierService, "_init_bird_model", new=_stub_init_bird_model), \
             patch.object(ClassifierService, "classify") as mock_classify, \
             patch("app.services.classifier_service.personalization_service.rerank", new=AsyncMock()) as mock_rerank:

            mock_classify.return_value = [{"label": "Robin", "score": 0.9, "index": 0}]
            service = ClassifierService()

            img = Image.new("RGB", (100, 100))
            results = await service.classify_async(img, camera_name="front")

            assert results[0]["label"] == "Robin"
            mock_rerank.assert_not_awaited()
            await service.shutdown()
    finally:
        settings.classification.personalized_rerank_enabled = original_toggle


@pytest.mark.asyncio
async def test_classifier_service_classify_async_returns_empty_when_image_queue_saturated(
    mock_tflite, mock_os_path_exists, monkeypatch
):
    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = False
    started = threading.Event()
    release = threading.Event()

    def _blocking_classify(*_args, **_kwargs):
        started.set()
        release.wait(timeout=1.0)
        return [{"label": "Robin", "score": 0.9, "index": 0}]

    try:
        with patch.object(ClassifierService, "_init_bird_model", return_value=None), \
             patch.object(ClassifierService, "classify", side_effect=_blocking_classify):
            monkeypatch.setattr(
                classifier_service_module,
                "CLASSIFIER_IMAGE_MAX_CONCURRENT",
                1,
                raising=False,
            )
            service = ClassifierService()
            monkeypatch.setattr(
                classifier_service_module,
                "CLASSIFIER_IMAGE_ADMISSION_TIMEOUT_SECONDS",
                0.01,
                raising=False,
            )
            service._classification_admission._background_capacity = 1

            img = Image.new("RGB", (100, 100))
            first_task = asyncio.create_task(service.classify_async(img, camera_name="front"))
            await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=1.0)
            results = await service.classify_async(img, camera_name="front")

            assert results == []
            release.set()
            await first_task
            await service.shutdown()
    finally:
        settings.classification.personalized_rerank_enabled = original_toggle


@pytest.mark.asyncio
async def test_classifier_service_classify_async_live_raises_when_live_queue_saturated(
    mock_tflite, mock_os_path_exists, monkeypatch
):
    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = False
    started = threading.Event()
    release = threading.Event()

    def _blocking_classify(*_args, **_kwargs):
        started.set()
        release.wait(timeout=1.0)
        return [{"label": "Robin", "score": 0.9, "index": 0}]

    try:
        with patch.object(ClassifierService, "_init_bird_model", return_value=None), \
             patch.object(ClassifierService, "classify", side_effect=_blocking_classify):
            monkeypatch.setattr(
                classifier_service_module,
                "CLASSIFIER_IMAGE_MAX_CONCURRENT",
                1,
                raising=False,
            )
            service = ClassifierService()
            monkeypatch.setattr(
                classifier_service_module,
                "CLASSIFIER_LIVE_IMAGE_ADMISSION_TIMEOUT_SECONDS",
                0.01,
                raising=False,
            )
            service._classification_admission._live_capacity = 1

            img = Image.new("RGB", (100, 100))
            first_task = asyncio.create_task(service.classify_async_live(img, camera_name="front"))
            await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=1.0)
            with pytest.raises(LiveImageClassificationOverloadedError, match="classify_snapshot_overloaded"):
                await service.classify_async_live(img, camera_name="front")

            release.set()
            assert (await first_task)[0]["label"] == "Robin"
            await service.shutdown()
    finally:
        settings.classification.personalized_rerank_enabled = original_toggle


@pytest.mark.asyncio
async def test_classifier_service_classify_async_live_keeps_capacity_reserved_until_worker_finishes(
    mock_tflite, mock_os_path_exists
):
    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = False
    started = threading.Event()
    release = threading.Event()

    def _blocking_classify(*_args, **_kwargs):
        started.set()
        release.wait(timeout=1.0)
        return [{"label": "Robin", "score": 0.9, "index": 0}]

    try:
        with patch.object(ClassifierService, "_init_bird_model", return_value=None), \
             patch("app.services.classifier_service.ModelInstance.load", return_value=True), \
             patch.object(ClassifierService, "classify", side_effect=_blocking_classify):
            service = ClassifierService()
            img = Image.new("RGB", (100, 100))

            task = asyncio.create_task(service.classify_async_live(img, camera_name="front"))
            await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=1.0)

            assert service.get_status()["live_image_in_flight"] == 1

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            assert service.get_status()["live_image_in_flight"] == 1

            release.set()
            await asyncio.sleep(0.05)

            assert service.get_status()["live_image_in_flight"] == 0
            await service.shutdown()
    finally:
        settings.classification.personalized_rerank_enabled = original_toggle


@pytest.mark.asyncio
async def test_classifier_service_classify_async_live_isolated_from_non_live_executor(
    mock_tflite, mock_os_path_exists
):
    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = False
    shared_started = threading.Event()
    shared_release = threading.Event()
    live_started = threading.Event()

    def _blocking_non_live(*_args, **_kwargs):
        shared_started.set()
        shared_release.wait(timeout=1.0)
        return [{"label": "Robin", "score": 0.9, "index": 0}]

    def _fast_live(*_args, **_kwargs):
        live_started.set()
        return [{"label": "Robin", "score": 0.91, "index": 0}]

    try:
        with patch.object(ClassifierService, "_init_bird_model", return_value=None), \
             patch("app.services.classifier_service.ModelInstance.load", return_value=True):
            service = ClassifierService()
            service._image_executor.shutdown(wait=False, cancel_futures=True)
            service._image_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="test_shared_image_worker")
            service._executor = service._image_executor

            img = Image.new("RGB", (100, 100))

            with patch.object(service, "classify", side_effect=_blocking_non_live):
                shared_task = asyncio.create_task(service.classify_async(img, camera_name="front"))
                await asyncio.wait_for(asyncio.to_thread(shared_started.wait), timeout=1.0)

            with patch.object(service, "classify", side_effect=_fast_live):
                live_results = await asyncio.wait_for(
                    service.classify_async_live(img, camera_name="front"),
                    timeout=0.2,
                )

            assert live_started.is_set()
            assert live_results[0]["label"] == "Robin"

            shared_release.set()
            await asyncio.wait_for(shared_task, timeout=1.0)
            await service.shutdown()
    finally:
        settings.classification.personalized_rerank_enabled = original_toggle


@pytest.mark.asyncio
async def test_classifier_service_classify_async_live_reclaims_stale_capacity_for_next_request(
    mock_tflite, mock_os_path_exists, monkeypatch
):
    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = False
    started = threading.Event()
    release = threading.Event()

    def _blocking_classify(*_args, **_kwargs):
        started.set()
        release.wait(timeout=1.0)
        return [{"label": "Robin", "score": 0.9, "index": 0}]

    try:
        with patch.object(ClassifierService, "_init_bird_model", return_value=None), \
             patch("app.services.classifier_service.ModelInstance.load", return_value=True), \
             patch.object(ClassifierService, "classify", side_effect=_blocking_classify):
            monkeypatch.setattr(
                classifier_service_module,
                "CLASSIFIER_IMAGE_MAX_CONCURRENT",
                1,
                raising=False,
            )
            monkeypatch.setattr(
                classifier_service_module,
                "CLASSIFIER_LIVE_IMAGE_LEASE_TIMEOUT_SECONDS",
                0.01,
                raising=False,
            )
            service = ClassifierService()
            service._classification_admission._live_capacity = 1
            img = Image.new("RGB", (100, 100))

            first_task = asyncio.create_task(service.classify_async_live(img, camera_name="front"))
            await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=1.0)

            with pytest.raises(ClassificationLeaseExpiredError):
                await first_task

            release.set()
            await asyncio.sleep(0.05)

            with patch.object(ClassifierService, "classify", return_value=[{"label": "Robin", "score": 0.92, "index": 0}]):
                results = await service.classify_async_live(img, camera_name="front")

            assert results[0]["label"] == "Robin"
            await service.shutdown()
    finally:
        settings.classification.personalized_rerank_enabled = original_toggle


@pytest.mark.asyncio
async def test_classifier_service_uses_separate_executors_for_image_and_video_work(mock_tflite, mock_os_path_exists):
    class _FakeLoop:
        def __init__(self, real_loop):
            self.executors = []
            self._real_loop = real_loop

        async def run_in_executor(self, executor, func, *args):
            self.executors.append(executor)
            return func(*args)

        def create_task(self, coro):
            return self._real_loop.create_task(coro)

        def create_future(self):
            return self._real_loop.create_future()

    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = False
    try:
        real_loop = asyncio.get_running_loop()
        with patch.object(ClassifierService, "_init_bird_model", return_value=None), \
             patch("app.services.classifier_service.ModelInstance.load", return_value=True), \
             patch.object(ClassifierService, "classify", return_value=[{"label": "Robin", "score": 0.9, "index": 0}]), \
             patch.object(ClassifierService, "classify_video", return_value=[{"label": "Robin", "score": 0.9, "index": 0}]), \
             patch("app.services.classifier_service.asyncio.get_running_loop") as mock_get_loop:

            fake_loop = _FakeLoop(real_loop)
            mock_get_loop.return_value = fake_loop
            service = ClassifierService()

            img = Image.new("RGB", (100, 100))
            await service.classify_async(img, camera_name="front")
            await service.classify_async_background(img, camera_name="front")
            await service.classify_video_async("/tmp/demo.mp4", max_frames=5, camera_name="front")

            assert fake_loop.executors[0] is service._image_executor
            assert fake_loop.executors[1] is service._background_image_executor
            assert fake_loop.executors[2] is service._video_executor
            assert service._image_executor is not service._video_executor
            assert service._background_image_executor is not service._video_executor
            assert service._background_image_executor is not service._image_executor
            await service.shutdown()
    finally:
        settings.classification.personalized_rerank_enabled = original_toggle


@pytest.mark.asyncio
async def test_classifier_service_accepts_input_context_and_normalizes_is_cropped(mock_tflite, mock_os_path_exists):
    class _InputContextAwareBirdModel:
        def __init__(self):
            self.loaded = True
            self.error = None
            self.labels = ["Robin"]
            self.seen_input_contexts = []

        def classify(self, image, input_context=None):
            self.seen_input_contexts.append(input_context)
            return [{"label": "Robin", "score": 0.91, "index": 0}]

    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()
        bird_model = _InputContextAwareBirdModel()
        service._models["bird"] = bird_model
        image = Image.new("RGB", (32, 32))

        sync_results = service.classify(image, input_context={"is_cropped": True})
        async_results = await service.classify_async(image, input_context={"is_cropped": "not-a-bool"})

        assert sync_results[0]["label"] == "Robin"
        assert async_results[0]["label"] == "Robin"
        assert bird_model.seen_input_contexts[0].is_cropped is True
        assert bird_model.seen_input_contexts[1].is_cropped is False
        await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_forwards_input_context_through_subprocess_supervisor(mock_tflite, mock_os_path_exists):
    class _FakeSupervisor:
        def __init__(self):
            self.calls = []

        async def classify(self, **kwargs):
            self.calls.append(kwargs)
            return [{"label": "Robin", "score": 0.93, "index": 0}]

    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService(supervisor=_FakeSupervisor())
        image = Image.new("RGB", (32, 32))

        results = await service._run_supervised_inference(
            "background",
            image,
            "front",
            "bird-model",
            {"is_cropped": True},
        )

        assert results[0]["label"] == "Robin"
        assert service._classifier_supervisor.calls[0]["input_context"]["is_cropped"] is True
        await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_classify_wildlife_async_forwards_input_context(mock_tflite, mock_os_path_exists):
    class _WildlifeModel:
        def __init__(self):
            self.loaded = True
            self.calls = []

        def classify(self, image, input_context=None):
            self.calls.append(input_context)
            return [{"label": "Sparrow", "score": 0.88, "index": 0}]

    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()
        wildlife = _WildlifeModel()
        service._models["wildlife"] = wildlife
        image = Image.new("RGB", (32, 32))

        results = await service.classify_wildlife_async(image, input_context={"is_cropped": True})

        assert results[0]["label"] == "Sparrow"
        assert wildlife.calls[0].is_cropped is True
        await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_video_progress_callback_failure_does_not_drop_results(mock_tflite, mock_os_path_exists):
    original_toggle = settings.classification.personalized_rerank_enabled
    settings.classification.personalized_rerank_enabled = False

    class _LoadedBirdModel:
        loaded = True
        labels = ["Robin", "Blackbird"]

    class _FakeCapture:
        def __init__(self, _path):
            self._index = 0

        def isOpened(self):
            return True

        def get(self, prop):
            if prop == classifier_service_module.cv2.CAP_PROP_FRAME_COUNT:
                return 3
            if prop == classifier_service_module.cv2.CAP_PROP_FPS:
                return 30
            return 0

        def set(self, *_args):
            return True

        def read(self):
            if self._index >= 3:
                return False, None
            self._index += 1
            return True, np.zeros((16, 16, 3), dtype=np.uint8)

        def release(self):
            return None

    try:
        with patch.object(ClassifierService, "_init_bird_model", return_value=None), \
             patch("app.services.classifier_service.cv2.VideoCapture", _FakeCapture), \
             patch("app.services.classifier_service.cv2.cvtColor", side_effect=lambda frame, _code: frame), \
             patch.object(ClassifierService, "_classify_raw_with_runtime_recovery", return_value=(np.array([0.91, 0.09]), _LoadedBirdModel())):
            service = ClassifierService()
            service._models["bird"] = _LoadedBirdModel()

            def _broken_progress(**_kwargs):
                raise TimeoutError("simulated slow progress delivery")

            results = service.classify_video("/tmp/demo.mp4", max_frames=3, progress_callback=_broken_progress)

            assert results
            assert results[0]["label"] == "Robin"
            await service.shutdown()
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


def test_resolve_inference_selection_auto_skips_intel_gpu_when_model_disallows_it():
    caps = {
        "ort_available": True,
        "cuda_available": False,
        "openvino_available": True,
        "intel_gpu_available": True,
        "intel_cpu_available": True,
    }

    sel = _resolve_inference_selection("auto", caps, supported_providers=["cpu", "intel_cpu"])

    assert sel["active_provider"] == "intel_cpu"
    assert sel["backend"] == "openvino"
    assert sel["openvino_device"] == "CPU"
    assert "does not support Intel GPU" in (sel["fallback_reason"] or "")


@pytest.mark.asyncio
async def test_classifier_service_respects_artifact_provider_constraints(mock_os_path_exists):
    original_provider = settings.classification.inference_provider
    settings.classification.inference_provider = "auto"

    class _FakeOpenVINOModel:
        created_devices = []

        def __init__(self, *_args, device_name="CPU", **_kwargs):
            self.device_name = device_name
            self.loaded = False
            self.error = None
            self.labels = []
            _FakeOpenVINOModel.created_devices.append(device_name)

        def load(self):
            self.loaded = True
            return True

        def cleanup(self):
            return None

        def current_compile_properties(self):
            return {}

        def startup_self_test_status(self):
            return {"enabled": False, "ran": False, "error": None, "diagnostics": {}}

        def get_status(self):
            return {"loaded": self.loaded, "error": self.error}

    try:
        with patch.object(
            classifier_service_module,
            "_detect_acceleration_capabilities",
            return_value={
                "openvino_available": True,
                "ort_available": True,
                "intel_cpu_available": True,
                "intel_gpu_available": True,
                "cuda_available": False,
            },
        ), patch.object(
            ClassifierService,
            "_resolve_active_bird_model_spec",
            return_value={
                "model_path": "/tmp/active/model.onnx",
                "labels_path": "/tmp/active/labels.txt",
                "input_size": 224,
                "preprocessing": {},
                "runtime": "onnx",
                "supported_inference_providers": ["cpu", "intel_cpu"],
            },
        ), patch("app.services.classifier_service.OpenVINOModelInstance", _FakeOpenVINOModel):
            service = ClassifierService()
    finally:
        settings.classification.inference_provider = original_provider

    assert service._inference_backend == "openvino"
    assert service._active_inference_provider == "intel_cpu"
    assert _FakeOpenVINOModel.created_devices == ["CPU"]
    assert "does not support Intel GPU" in (service._inference_fallback_reason or "")
    await service.shutdown()


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


@pytest.mark.asyncio
async def test_classifier_status_exposes_openvino_runtime_diagnostics_block():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    service._image_execution_mode = "in_process"
    service._active_inference_provider = "intel_gpu"
    service._inference_backend = "openvino"
    service._last_runtime_recovery = {
        "status": "recovered",
        "failed_backend": "openvino",
        "failed_provider": "GPU",
        "recovered_backend": "openvino",
        "recovered_provider": "intel_cpu",
        "detail": "non-finite logits",
        "at": 123.0,
        "diagnostics": {
            "compile_properties": {
                "INFERENCE_PRECISION_HINT": "f32",
                "NUM_STREAMS": "1",
            },
            "output_summary": {
                "nan_count": 10000,
                "finite_count": 0,
            },
        },
    }
    service._models["bird"] = MagicMock()
    service._models["bird"].get_status.return_value = {
        "loaded": True,
        "runtime": "openvino",
        "device": "GPU",
        "model_path": "/models/bird.onnx",
        "input_size": 384,
    }
    service._resolve_active_bird_model_spec = MagicMock(return_value={
        "model_path": "/models/bird.onnx",
        "labels_path": "/models/labels.txt",
        "input_size": 384,
        "preprocessing": {"mean": [0.1, 0.2, 0.3], "std": [0.4, 0.5, 0.6]},
        "runtime": "onnx",
    })
    service._bird_model_artifact_metadata = {
        "model_sha256": "abc123",
        "weights_sha256": "def456",
        "producer_name": "pytorch",
        "producer_version": "2.9.1",
        "opset": [{"domain": "ai.onnx", "version": 18}],
    }
    service._bird_model_compatibility = {
        "devices": {
            "GPU": {
                "artifact_trust_state": "untrusted",
                "last_probe_status": "invalid_output",
            }
        }
    }

    status = service.get_status()

    assert status["openvino_runtime"]["selected_provider"] == "auto"
    assert status["openvino_runtime"]["active_provider"] == "intel_gpu"
    assert status["openvino_runtime"]["inference_backend"] == "openvino"
    assert status["openvino_runtime"]["gpu_settings"]["startup_self_test_enabled"] is True
    assert status["openvino_runtime"]["model"]["model_path"] == "/models/bird.onnx"
    assert status["openvino_runtime"]["model"]["input_size"] == 384
    assert status["openvino_runtime"]["model"]["preprocessing"]["mean"] == [0.1, 0.2, 0.3]
    assert status["openvino_runtime"]["model"]["model_sha256"] == "abc123"
    assert status["openvino_runtime"]["model"]["weights_sha256"] == "def456"
    assert status["openvino_runtime"]["model"]["producer_name"] == "pytorch"
    assert status["openvino_runtime"]["model"]["producer_version"] == "2.9.1"
    assert status["openvino_runtime"]["model"]["opset"] == [{"domain": "ai.onnx", "version": 18}]
    assert status["openvino_runtime"]["compatibility"]["devices"]["GPU"]["artifact_trust_state"] == "untrusted"
    assert status["openvino_runtime"]["compatibility"]["devices"]["GPU"]["last_probe_status"] == "invalid_output"
    assert status["openvino_runtime"]["last_runtime_recovery"]["diagnostics"]["compile_properties"]["INFERENCE_PRECISION_HINT"] == "f32"
    assert status["openvino_runtime"]["last_runtime_recovery"]["diagnostics"]["output_summary"]["nan_count"] == 10000
    await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_status_disables_gpu_startup_self_test_in_worker_process_mode():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService(worker_process_mode=True)

    status = service.get_status()

    assert status["openvino_runtime"]["gpu_settings"]["startup_self_test_enabled"] is False
    await service.shutdown()


@pytest.mark.asyncio
async def test_probe_bird_runtime_updates_compatibility_state_from_probe_result():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    service._resolve_active_bird_model_spec = MagicMock(return_value={
        "model_path": "/models/bird.onnx",
        "labels_path": "/models/labels.txt",
        "input_size": 384,
        "preprocessing": {"mean": [0.1, 0.2, 0.3], "std": [0.4, 0.5, 0.6]},
        "runtime": "onnx",
    })

    fake_model = MagicMock()
    fake_model.load.return_value = True
    fake_model.error = None
    fake_model.current_compile_properties.return_value = {"INFERENCE_PRECISION_HINT": "f32"}
    fake_model.startup_self_test_status.return_value = {"enabled": True, "ran": True, "error": None, "diagnostics": {}}
    fake_model.probe.return_value = {
        "status": "invalid_output",
        "output_summary": {
            "shape": [1, 10000],
            "nan_count": 10000,
            "finite_count": 0,
            "invalid_output_kind": "all_nan",
        },
    }

    with patch("app.services.classifier_service.OpenVINOModelInstance", return_value=fake_model):
        report = service.probe_bird_runtime(device="GPU", synthetic_image=True)

    assert report["status"] == "invalid_output"
    assert report["output_summary"]["invalid_output_kind"] == "all_nan"
    assert service._bird_model_compatibility["devices"]["GPU"]["artifact_trust_state"] == "untrusted"
    assert service._bird_model_compatibility["devices"]["GPU"]["last_probe_status"] == "invalid_output"
    await service.shutdown()


@pytest.mark.asyncio
async def test_cpu_probe_does_not_overwrite_gpu_compatibility_state():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    service._bird_model_compatibility = {
        "devices": {
            "GPU": {
                "artifact_trust_state": "untrusted",
                "last_probe_status": "invalid_output",
            }
        }
    }
    service._update_bird_model_compatibility(device="CPU", status="ok")

    assert service._bird_model_compatibility["devices"]["GPU"]["artifact_trust_state"] == "untrusted"
    assert service._bird_model_compatibility["devices"]["CPU"]["artifact_trust_state"] == "trusted"
    await service.shutdown()


def test_openvino_infer_output_tensor_uses_compiled_output_handle_and_preserves_nan_shape(mock_os_path_exists):
    infer_request = MagicMock()
    infer_request.infer.return_value = {"wrong": np.array([], dtype=np.float64)}
    compiled_model = MagicMock()
    compiled_model.outputs = ["output0"]
    compiled_model.create_infer_request.return_value = infer_request
    infer_request.infer.return_value = {"output0": np.full((1, 10000), np.nan, dtype=np.float32)}

    model = OpenVINOModelInstance(
        "bird",
        "/tmp/model.onnx",
        "/tmp/labels.txt",
        device_name="GPU",
    )
    model.loaded = True
    model.compiled_model = compiled_model
    model.input_name = "input"

    logits = model._infer_output_tensor(Image.new("RGB", (32, 32), color="white"))

    assert logits.shape == (1, 10000)
    assert np.isnan(logits).all()


def test_openvino_infer_output_tensor_can_run_during_startup_self_test_before_loaded_flag(mock_os_path_exists):
    infer_request = MagicMock()
    compiled_model = MagicMock()
    compiled_model.outputs = ["output0"]
    compiled_model.create_infer_request.return_value = infer_request
    infer_request.infer.return_value = {"output0": np.full((1, 10000), np.nan, dtype=np.float32)}

    model = OpenVINOModelInstance(
        "bird",
        "/tmp/model.onnx",
        "/tmp/labels.txt",
        device_name="GPU",
    )
    model.loaded = False
    model.compiled_model = compiled_model
    model.input_name = "input"

    logits = model._infer_output_tensor(Image.new("RGB", (32, 32), color="white"))

    assert logits.shape == (1, 10000)
    assert np.isnan(logits).all()


def test_openvino_gpu_startup_self_test_preserves_all_nan_output_diagnostics(mock_os_path_exists):
    model = OpenVINOModelInstance(
        "bird",
        "/tmp/model.onnx",
        "/tmp/labels.txt",
        device_name="GPU",
    )
    model.loaded = True
    model.compiled_model = MagicMock()
    model.input_name = "input"

    with patch.object(model, "_infer_output_tensor", return_value=np.full((1, 10000), np.nan, dtype=np.float32)):
        with pytest.raises(InvalidInferenceOutputError) as exc:
            model._run_gpu_startup_self_test()

    summary = exc.value.diagnostics["output_summary"]
    assert summary["shape"] == [1, 10000]
    assert summary["nan_count"] == 10000
    assert summary["invalid_output_kind"] == "all_nan"


@pytest.mark.asyncio
async def test_classifier_check_health_exposes_live_image_pressure():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    service._live_image_admission_timeouts = 4
    service._classification_admission.get_metrics = MagicMock(return_value={  # type: ignore[method-assign]
        "live": {
            "capacity": 2,
            "queued": 0,
            "running": 1,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "rejected": 0,
            "oldest_running_age_seconds": 1.0,
        },
        "background": {
            "capacity": 1,
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "rejected": 0,
            "oldest_running_age_seconds": None,
        },
        "late_completions_ignored": 0,
        "recent_outcomes": [],
        "background_throttled": False,
        "closed": False,
    })
    health = service.check_health()

    assert health["live_image"]["max_concurrent"] >= 1
    assert health["live_image"]["in_flight"] == 1
    assert health["live_image"]["admission_timeouts"] == 4
    await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_check_health_keeps_transient_live_saturation_out_of_degraded_status():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    service._classification_admission.get_metrics = MagicMock(return_value={  # type: ignore[method-assign]
        "live": {
            "capacity": 2,
            "queued": 1,
            "running": 2,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "rejected": 0,
            "oldest_running_age_seconds": 1.0,
        },
        "background": {
            "capacity": 1,
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "rejected": 0,
            "oldest_running_age_seconds": None,
        },
        "late_completions_ignored": 0,
        "recent_outcomes": [],
        "background_throttled": True,
        "closed": False,
    })

    health = service.check_health()

    assert health["live_image"]["pressure_level"] == "high"
    assert health["live_image"]["status"] == "ok"
    await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_get_admission_status_is_lightweight_and_exposes_throttle_state():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    service._classification_admission.get_metrics = MagicMock(return_value={  # type: ignore[method-assign]
        "live": {
            "capacity": 2,
            "queued": 0,
            "running": 1,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "rejected": 0,
            "oldest_running_age_seconds": 0.5,
        },
        "background": {
            "capacity": 1,
            "queued": 3,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "rejected": 0,
            "oldest_running_age_seconds": None,
        },
        "late_completions_ignored": 0,
        "recent_outcomes": [],
        "background_throttled": True,
        "closed": False,
    })

    with patch("app.services.classifier_service._detect_acceleration_capabilities", side_effect=AssertionError("should not probe runtimes")):
        status = service.get_admission_status()

    assert status["background_throttled"] is True
    assert status["background"]["queued"] == 3
    await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_check_health_exposes_supervisor_pool_state():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    service._classifier_supervisor = MagicMock()
    service._classifier_supervisor.get_metrics.return_value = {
        "live": {
            "workers": 2,
            "restarts": 3,
            "last_exit_reason": "heartbeat_timeout",
            "circuit_open": True,
            "circuit_open_until_monotonic": 123.0,
        },
        "background": {
            "workers": 1,
            "restarts": 0,
            "last_exit_reason": None,
            "circuit_open": False,
            "circuit_open_until_monotonic": None,
        },
        "late_results_ignored": 4,
    }
    service._image_execution_mode = "subprocess"

    health = service.check_health()
    status = service.get_admission_status()

    assert health["execution_mode"] == "subprocess"
    assert health["worker_pools"]["live"]["workers"] == 2
    assert health["worker_pools"]["live"]["circuit_open"] is True
    assert health["live_image"]["status"] == "degraded"
    assert health["live_image"]["recovery_reason"] == "worker_circuit_open"
    assert status["worker_pools"]["live"]["restarts"] == 3
    assert status["late_results_ignored"] == 4
    await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_check_health_uses_worker_runtime_state_in_subprocess_mode():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    service._classifier_supervisor = MagicMock()
    service._classifier_supervisor.get_metrics.return_value = {
        "live": {
            "workers": 2,
            "restarts": 1,
            "last_exit_reason": None,
            "last_runtime_recovery": {
                "status": "recovered",
                "failed_backend": "openvino",
                "failed_provider": "GPU",
                "recovered_backend": "openvino",
                "recovered_provider": "intel_cpu",
                "detail": "invalid probabilities",
                "at": 123.0,
            },
            "circuit_open": False,
            "circuit_open_until_monotonic": None,
        },
        "background": {
            "workers": 1,
            "restarts": 0,
            "last_exit_reason": None,
            "last_runtime_recovery": None,
            "circuit_open": False,
            "circuit_open_until_monotonic": None,
        },
        "late_results_ignored": 0,
    }
    service._image_execution_mode = "subprocess"
    service._classification_admission.get_metrics = MagicMock(return_value={
        "live": {
            "capacity": 2,
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "rejected": 0,
            "oldest_running_age_seconds": None,
        },
        "background": {
            "capacity": 1,
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "rejected": 0,
            "oldest_running_age_seconds": None,
        },
        "late_completions_ignored": 0,
        "recent_outcomes": [],
        "background_throttled": False,
        "closed": False,
    })

    health = service.check_health()
    status = service.get_status()

    assert health["status"] == "ok"
    assert health["runtime_recovery"]["last_recovery"]["failed_provider"] == "GPU"
    assert status["last_runtime_recovery"]["recovered_provider"] == "intel_cpu"
    await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_status_uses_video_worker_runtime_truth_in_subprocess_mode():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    service._classifier_supervisor = MagicMock()
    service._classifier_supervisor.get_metrics.return_value = {
        "live": {
            "workers": 0,
            "restarts": 0,
            "last_exit_reason": None,
            "last_runtime_recovery": None,
            "circuit_open": False,
            "circuit_open_until_monotonic": None,
        },
        "background": {
            "workers": 0,
            "restarts": 0,
            "last_exit_reason": None,
            "last_runtime_recovery": None,
            "circuit_open": False,
            "circuit_open_until_monotonic": None,
        },
        "video": {
            "workers": 2,
            "restarts": 0,
            "last_exit_reason": None,
            "last_runtime_recovery": {
                "status": "recovered",
                "failed_backend": "openvino",
                "failed_provider": "GPU",
                "recovered_backend": "openvino",
                "recovered_provider": "intel_cpu",
                "detail": "bird inference produced no finite probabilities",
                "at": 456.0,
            },
            "circuit_open": False,
            "circuit_open_until_monotonic": None,
        },
        "late_results_ignored": 0,
    }
    service._image_execution_mode = "subprocess"
    service._active_inference_provider = "tflite"
    service._inference_backend = "tflite"

    status = service.get_status()

    assert status["selected_provider"] == "auto"
    assert status["active_provider"] == "intel_cpu"
    assert status["inference_backend"] == "openvino"
    assert status["last_runtime_recovery"]["recovered_provider"] == "intel_cpu"
    await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_check_health_is_ok_before_lazy_subprocess_workers_start():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    service._classifier_supervisor = MagicMock()
    service._classifier_supervisor.get_metrics.return_value = {
        "live": {
            "workers": 0,
            "restarts": 0,
            "last_exit_reason": None,
            "last_runtime_recovery": None,
            "circuit_open": False,
            "circuit_open_until_monotonic": None,
        },
        "background": {
            "workers": 0,
            "restarts": 0,
            "last_exit_reason": None,
            "last_runtime_recovery": None,
            "circuit_open": False,
            "circuit_open_until_monotonic": None,
        },
        "video": {
            "workers": 0,
            "restarts": 0,
            "last_exit_reason": None,
            "last_runtime_recovery": None,
            "circuit_open": False,
            "circuit_open_until_monotonic": None,
        },
        "late_results_ignored": 0,
    }
    service._image_execution_mode = "subprocess"
    service._classification_admission.get_metrics = MagicMock(return_value={
        "live": {
            "capacity": 2,
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "rejected": 0,
            "oldest_running_age_seconds": None,
        },
        "background": {
            "capacity": 1,
            "queued": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "abandoned": 0,
            "rejected": 0,
            "oldest_running_age_seconds": None,
        },
        "late_completions_ignored": 0,
        "recent_outcomes": [],
        "background_throttled": False,
        "closed": False,
    })

    health = service.check_health()

    assert health["status"] == "ok"
    await service.shutdown()


@pytest.mark.asyncio
async def test_classifier_service_shutdown_closes_all_executors():
    with patch.object(ClassifierService, "_init_bird_model", return_value=None):
        service = ClassifierService()

    await service.shutdown()

    assert service._image_executor._shutdown is True
    assert service._live_image_executor._shutdown is True
    assert service._background_image_executor._shutdown is True
    assert service._video_executor._shutdown is True
