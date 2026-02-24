import structlog
import numpy as np
import os
import cv2
import asyncio
import ctypes
import importlib
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from typing import Optional

# TFLite runtime
try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    try:
        import tensorflow.lite as tflite
    except ImportError:
        tflite = None

# ONNX runtime (for high-accuracy models)
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ort = None
    ONNX_AVAILABLE = False

def _detect_openvino_support() -> dict:
    """Resolve OpenVINO Core import across package versions.

    OpenVINO 2026+ exposes `openvino.Core`, while older versions commonly use
    `openvino.runtime.Core`.
    """
    attempts: list[str] = []

    for module_name, attr_name, import_path in (
        ("openvino.runtime", "Core", "openvino.runtime.Core"),
        ("openvino", "Core", "openvino.Core"),
    ):
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            attempts.append(f"{import_path}: {type(exc).__name__}: {exc}")
            continue

        core_class = getattr(module, attr_name, None)
        if core_class is None:
            attempts.append(f"{import_path}: missing attribute {attr_name}")
            continue

        version = getattr(module, "__version__", None)
        if not version and module_name != "openvino":
            try:
                top_level = importlib.import_module("openvino")
                version = getattr(top_level, "__version__", None)
            except Exception:
                version = None

        return {
            "available": True,
            "core_class": core_class,
            "version": version,
            "import_path": import_path,
            "import_error": None,
        }

    return {
        "available": False,
        "core_class": None,
        "version": None,
        "import_path": None,
        "import_error": "; ".join(attempts) if attempts else "OpenVINO not installed",
    }


# OpenVINO runtime (optional; single-image Intel acceleration path)
_OPENVINO_SUPPORT = _detect_openvino_support()
OpenVINOCore = _OPENVINO_SUPPORT["core_class"]
OPENVINO_AVAILABLE = bool(_OPENVINO_SUPPORT["available"])

from app.config import settings

log = structlog.get_logger()

SUPPORTED_INFERENCE_PROVIDERS = {"auto", "cpu", "cuda", "intel_gpu", "intel_cpu"}


def _normalize_inference_provider(value: Optional[str]) -> str:
    normalized = (value or "auto").strip().lower()
    return normalized if normalized in SUPPORTED_INFERENCE_PROVIDERS else "auto"


def _detect_acceleration_capabilities() -> dict:
    """Probe optional inference runtimes/providers without raising."""
    dev_dri_entries: list[str] = []
    try:
        if os.path.isdir("/dev/dri"):
            dev_dri_entries = sorted(os.listdir("/dev/dri"))
    except Exception:
        dev_dri_entries = []

    caps = {
        "ort_available": bool(ONNX_AVAILABLE and ort is not None),
        "cuda_provider_installed": False,
        "cuda_hardware_available": False,
        "cuda_available": False,
        "openvino_available": bool(OPENVINO_AVAILABLE and OpenVINOCore is not None),
        "openvino_version": _OPENVINO_SUPPORT.get("version"),
        "openvino_import_path": _OPENVINO_SUPPORT.get("import_path"),
        "openvino_import_error": _OPENVINO_SUPPORT.get("import_error"),
        "openvino_probe_error": None,
        "openvino_gpu_probe_error": None,
        "intel_gpu_available": False,
        "intel_cpu_available": False,
        "openvino_devices": [],
        "dev_dri_present": os.path.isdir("/dev/dri"),
        "dev_dri_entries": dev_dri_entries,
        "process_uid": None,
        "process_gid": None,
        "process_groups": [],
    }
    try:
        caps["process_uid"] = os.getuid()
        caps["process_gid"] = os.getgid()
        caps["process_groups"] = list(os.getgroups())
    except Exception:
        pass

    if caps["ort_available"]:
        try:
            caps["cuda_provider_installed"] = "CUDAExecutionProvider" in (ort.get_available_providers() or [])
            if caps["cuda_provider_installed"]:
                caps["cuda_hardware_available"] = _detect_cuda_hardware_available()
            caps["cuda_available"] = bool(caps["cuda_provider_installed"] and caps["cuda_hardware_available"])
        except Exception as e:
            log.warning("Failed to inspect ONNX Runtime providers", error=str(e))

    if caps["openvino_available"]:
        try:
            ov_core = OpenVINOCore()
            devices = list(getattr(ov_core, "available_devices", []) or [])
            caps["openvino_devices"] = devices
            caps["intel_gpu_available"] = any(d == "GPU" or str(d).startswith("GPU.") for d in devices)
            caps["intel_cpu_available"] = any(d == "CPU" or str(d).startswith("CPU.") for d in devices)
            if caps["openvino_available"] and caps.get("dev_dri_present") and not caps["intel_gpu_available"]:
                caps["openvino_gpu_probe_error"] = _probe_openvino_gpu_plugin_error_safe()
        except Exception as e:
            caps["openvino_available"] = False
            caps["openvino_probe_error"] = f"{type(e).__name__}: {e}"
            log.warning("Failed to inspect OpenVINO devices", error=str(e))

    return caps


def _probe_openvino_gpu_plugin_error_safe() -> Optional[str]:
    """Probe OpenVINO GPU plugin in a subprocess so plugin crashes cannot kill the backend."""
    script = (
        "import sys\n"
        "try:\n"
        "    from openvino import Core\n"
        "except Exception:\n"
        "    from openvino.runtime import Core\n"
        "core = Core()\n"
        "try:\n"
        "    core.get_property('GPU', 'FULL_DEVICE_NAME')\n"
        "    print('OK')\n"
        "except Exception as e:\n"
        "    print(f'{type(e).__name__}: {e}')\n"
        "    sys.exit(2)\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return "TimeoutExpired: OpenVINO GPU plugin probe timed out"
    except Exception as e:
        return f"{type(e).__name__}: {e}"

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode == 0:
        return None
    if stdout:
        return stdout
    if stderr:
        return stderr
    return f"OpenVINO GPU plugin probe failed with exit code {proc.returncode}"


def _detect_cuda_hardware_available() -> bool:
    """Detect whether an NVIDIA CUDA device is actually accessible in this runtime.

    ORT can report CUDAExecutionProvider when the wheel supports CUDA even if no NVIDIA
    GPU is passed through. Probe the CUDA driver API directly to avoid false positives.
    """
    for library_name in ("libcuda.so.1", "libcuda.so", "nvcuda.dll"):
        try:
            cuda = ctypes.CDLL(library_name)
        except OSError:
            continue

        try:
            cu_init = cuda.cuInit
            cu_init.argtypes = [ctypes.c_uint]
            cu_init.restype = ctypes.c_int

            cu_device_get_count = cuda.cuDeviceGetCount
            cu_device_get_count.argtypes = [ctypes.POINTER(ctypes.c_int)]
            cu_device_get_count.restype = ctypes.c_int

            if cu_init(0) != 0:
                return False

            count = ctypes.c_int(0)
            if cu_device_get_count(ctypes.byref(count)) != 0:
                return False

            return count.value > 0
        except Exception as e:
            log.warning("CUDA driver probe failed", library=library_name, error=str(e))
            return False

    return False


def _resolve_inference_selection(requested_provider: Optional[str], caps: dict) -> dict:
    """Resolve desired inference provider to a concrete backend/device with fallback."""
    requested = _normalize_inference_provider(requested_provider)

    def _ort_cpu(reason: Optional[str] = None) -> dict:
        if caps.get("ort_available"):
            return {
                "requested_provider": requested,
                "active_provider": "cpu",
                "backend": "onnxruntime",
                "ort_providers": ["CPUExecutionProvider"],
                "openvino_device": None,
                "fallback_reason": reason,
            }
        if caps.get("openvino_available") and caps.get("intel_cpu_available"):
            fallback_reason = reason or "ONNX Runtime unavailable; using OpenVINO CPU"
            return {
                "requested_provider": requested,
                "active_provider": "intel_cpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "CPU",
                "fallback_reason": fallback_reason,
            }
        return {
            "requested_provider": requested,
            "active_provider": "unavailable",
            "backend": "unavailable",
            "ort_providers": [],
            "openvino_device": None,
            "fallback_reason": reason or "No ONNX-capable runtime available (onnxruntime/OpenVINO)",
        }

    if requested == "cpu":
        return _ort_cpu()

    if requested == "cuda":
        if caps.get("ort_available") and caps.get("cuda_available"):
            return {
                "requested_provider": requested,
                "active_provider": "cuda",
                "backend": "onnxruntime",
                "ort_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
                "openvino_device": None,
                "fallback_reason": None,
            }
        return _ort_cpu("CUDA requested but CUDAExecutionProvider is not available")

    if requested == "intel_cpu":
        if caps.get("openvino_available") and caps.get("intel_cpu_available"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_cpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "CPU",
                "fallback_reason": None,
            }
        return _ort_cpu("OpenVINO CPU requested but OpenVINO CPU device is not available")

    if requested == "intel_gpu":
        if caps.get("openvino_available") and caps.get("intel_gpu_available"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_gpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "GPU",
                "fallback_reason": None,
            }
        if caps.get("openvino_available") and caps.get("intel_cpu_available"):
            return {
                "requested_provider": requested,
                "active_provider": "intel_cpu",
                "backend": "openvino",
                "ort_providers": [],
                "openvino_device": "CPU",
                "fallback_reason": "Intel GPU requested but not available; falling back to OpenVINO CPU",
            }
        return _ort_cpu("Intel GPU requested but OpenVINO GPU is not available")

    # auto: prefer Intel GPU, then CUDA, then CPU
    if caps.get("openvino_available") and caps.get("intel_gpu_available"):
        return {
            "requested_provider": requested,
            "active_provider": "intel_gpu",
            "backend": "openvino",
            "ort_providers": [],
            "openvino_device": "GPU",
            "fallback_reason": None,
        }
    if caps.get("ort_available") and caps.get("cuda_available"):
        return {
            "requested_provider": requested,
            "active_provider": "cuda",
            "backend": "onnxruntime",
            "ort_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            "openvino_device": None,
            "fallback_reason": None,
        }
    return _ort_cpu()


def _reconcile_ort_active_provider(
    requested_active_provider: str,
    session_providers: list[str] | None,
) -> tuple[str, Optional[str]]:
    """Reconcile planned ORT provider with the session's actual enabled providers.

    ONNX Runtime can initialize a session with CPU only even when CUDA was requested,
    depending on runtime/library availability. Keep YA-WAMF status/fallback reporting honest.
    """
    actual = requested_active_provider
    providers = list(session_providers or [])

    if requested_active_provider == "cuda" and "CUDAExecutionProvider" not in providers:
        if "CPUExecutionProvider" in providers:
            return (
                "cpu",
                "CUDA requested but ONNX Runtime session initialized without CUDAExecutionProvider; using CPUExecutionProvider",
            )
        return (
            "cpu",
            "CUDA requested but ONNX Runtime session initialized without CUDAExecutionProvider",
        )

    return actual, None

# Global singleton instance
_classifier_instance: Optional['ClassifierService'] = None
_classifier_lock = threading.Lock()


def get_classifier() -> 'ClassifierService':
    """Get the shared classifier service instance (thread-safe)."""
    global _classifier_instance
    if _classifier_instance is None:
        with _classifier_lock:
            # Double-check pattern to avoid race condition
            if _classifier_instance is None:
                _classifier_instance = ClassifierService()
    return _classifier_instance


class ModelInstance:
    """Represents a loaded TFLite model with its labels."""

    def __init__(self, name: str, model_path: str, labels_path: str, preprocessing: Optional[dict] = None):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.preprocessing = preprocessing or {}
        self.interpreter = None
        self.labels: list[str] = []
        self.loaded = False
        self.error: Optional[str] = None
        self.input_details = None
        self.output_details = None
        self._lock = threading.Lock()

    def load(self) -> bool:
        """Load the model and labels. Returns True if successful."""
        with self._lock:
            if self.loaded:
                return True

            # Load labels first
            if os.path.exists(self.labels_path):
                try:
                    with open(self.labels_path, 'r', encoding='utf-8', errors='replace') as f:
                        self.labels = [line.strip() for line in f.readlines() if line.strip()]
                    log.info(f"Loaded {len(self.labels)} labels for {self.name}")
                except Exception as e:
                    log.error(f"Failed to load labels for {self.name}", error=str(e))

            if not os.path.exists(self.model_path):
                self.error = f"Model file not found: {self.model_path}"
                log.warning(f"{self.name} model not found", path=self.model_path)
                return False

            if tflite is None:
                self.error = "TFLite runtime not installed"
                log.error("TFLite runtime not installed")
                return False

            try:
                self.interpreter = tflite.Interpreter(model_path=self.model_path)
                self.interpreter.allocate_tensors()
                self.input_details = self.interpreter.get_input_details()
                self.output_details = self.interpreter.get_output_details()
                self.loaded = True
                self.error = None
                log.info(f"{self.name} model loaded successfully")
                return True
            except Exception as e:
                self.error = f"Failed to load model: {str(e)}"
                log.error(f"Failed to load {self.name} model", error=str(e))
                return False

    def _preprocess_image(self, image: Image.Image, target_width: int, target_height: int) -> np.ndarray:
        """
        Preprocess image: resize with padding (letterbox) to maintain aspect ratio,
        then normalize.
        """
        # Convert to RGB
        image = image.convert('RGB')
        
        # Calculate scale to fit within target dims while maintaining aspect ratio
        iw, ih = image.size
        w, h = target_width, target_height
        scale = min(w / iw, h / ih)
        nw = int(iw * scale)
        nh = int(ih * scale)

        # Resize image
        image = image.resize((nw, nh), Image.Resampling.BICUBIC)

        # Padding color (128 for iNat models, 0 for generic)
        pad_color = self.preprocessing.get("padding_color", 0)
        if isinstance(pad_color, int):
            fill_color = (pad_color, pad_color, pad_color)
        else:
            fill_color = tuple(pad_color)

        # Create new image with padding
        new_image = Image.new('RGB', (w, h), fill_color)
        
        # Paste resized image in center
        new_image.paste(image, ((w - nw) // 2, (h - nh) // 2))

        # Convert to numpy array
        input_data = np.array(new_image, dtype=np.float32)
        
        return input_data

    def _run_inference(self, image: Image.Image) -> np.ndarray:
        """Internal method to run inference and return probability vector.

        Args:
            image: PIL Image to classify

        Returns:
            Normalized probability vector as numpy array
        """
        # Get expected input size from model
        input_details = self.input_details[0]
        input_shape = input_details['shape']

        # Shape is typically [1, height, width, 3] for image models
        if len(input_shape) == 4:
            target_height, target_width = input_shape[1], input_shape[2]
        else:
            target_height, target_width = 300, 300  # Default fallback

        # Preprocess image
        input_data = self._preprocess_image(image, target_width, target_height)

        # Normalize based on model input type
        if input_details['dtype'] == np.float32:
            input_data = (input_data - 127.0) / 128.0
        elif input_details['dtype'] == np.uint8:
            input_data = input_data.astype(np.uint8)

        # Add batch dimension
        input_data = np.expand_dims(input_data, axis=0)

        # Run inference protected by lock
        with self._lock:
            self.interpreter.set_tensor(input_details['index'], input_data)
            self.interpreter.invoke()

            # Get output
            output_details = self.output_details[0]
            output_data = self.interpreter.get_tensor(output_details['index'])

        results = np.squeeze(output_data).astype(np.float32)

        # Dequantize if needed
        if output_details['dtype'] == np.uint8:
            quant_params = output_details.get('quantization_parameters', {})
            scales = quant_params.get('scales', None)
            zero_points = quant_params.get('zero_points', None)

            if scales is not None and len(scales) > 0:
                scale = scales[0]
                zero_point = zero_points[0] if zero_points is not None and len(zero_points) > 0 else 0
                results = (results - zero_point) * scale
            else:
                results = results / 255.0

        # Softmax if needed (logits vs probabilities)
        output_min = float(results.min())
        output_max = float(results.max())
        is_probability = output_min >= 0 and output_max <= 1.0

        if is_probability:
            output_sum = float(results.sum())
            if output_sum > 0:
                results = results / output_sum
        else:
            exp_results = np.exp(results - np.max(results))
            results = exp_results / np.sum(exp_results)

        return results

    def classify(self, image: Image.Image) -> list[dict]:
        """Classify an image using this model.

        Args:
            image: PIL Image to classify

        Returns:
            List of top 5 classifications with score and label
        """
        if not self.loaded or not self.interpreter:
            log.warning(f"{self.name} model not loaded, cannot classify")
            return []

        # Run inference and get probability vector
        results = self._run_inference(image)

        # Convert to classification list
        classifications = []
        for i, score in enumerate(results):
            label = self.labels[i] if i < len(self.labels) else f"Class {i}"
            classifications.append({
                "index": int(i),
                "score": float(score),
                "label": label
            })

        classifications.sort(key=lambda x: x['score'], reverse=True)
        max_results = settings.classification.max_classification_results
        return classifications[:max_results]

    def classify_raw(self, image: Image.Image) -> np.ndarray:
        """Classify and return the raw probability vector (for ensemble).

        Args:
            image: PIL Image to classify

        Returns:
            Normalized probability vector as numpy array
        """
        if not self.loaded or not self.interpreter:
            return np.array([])

        return self._run_inference(image)

    def cleanup(self):
        """Clean up model resources."""
        with self._lock:
            if self.interpreter is not None:
                # TFLite interpreters don't have explicit cleanup,
                # but we can dereference it to allow garbage collection
                self.interpreter = None
            self.loaded = False
            log.info(f"{self.name} model resources cleaned up")

    def get_status(self) -> dict:
        """Return the current status of this model."""
        return {
            "loaded": self.loaded,
            "error": self.error,
            "labels_count": len(self.labels),
            "enabled": self.interpreter is not None,
            "model_path": self.model_path,
            "runtime": "tflite",
        }


class ONNXModelInstance:
    """Represents a loaded ONNX model with its labels (for high-accuracy models)."""

    def __init__(
        self,
        name: str,
        model_path: str,
        labels_path: str,
        preprocessing: Optional[dict] = None,
        input_size: int = 384,
        ort_providers: Optional[list[str]] = None,
    ):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.preprocessing = preprocessing or {}
        self.input_size = input_size
        self.ort_providers = list(ort_providers or ["CPUExecutionProvider"])
        self.session = None
        self.labels: list[str] = []
        self.loaded = False
        self.error: Optional[str] = None
        self._lock = threading.Lock()

        # ImageNet normalization defaults (used by timm models)
        self.mean = np.array(self.preprocessing.get("mean", [0.485, 0.456, 0.406]))
        self.std = np.array(self.preprocessing.get("std", [0.229, 0.224, 0.225]))

    def load(self) -> bool:
        """Load the ONNX model and labels. Returns True if successful."""
        if self.loaded:
            return True

        if not ONNX_AVAILABLE:
            self.error = "ONNX Runtime not installed"
            log.error("ONNX Runtime not installed")
            return False

        # Load labels first
        if os.path.exists(self.labels_path):
            try:
                with open(self.labels_path, 'r', encoding='utf-8', errors='replace') as f:
                    self.labels = [line.strip() for line in f.readlines() if line.strip()]
                log.info(f"Loaded {len(self.labels)} labels for ONNX model {self.name}")
            except Exception as e:
                log.error(f"Failed to load labels for {self.name}", error=str(e))

        if not os.path.exists(self.model_path):
            self.error = f"ONNX model file not found: {self.model_path}"
            log.warning(f"{self.name} ONNX model not found", path=self.model_path)
            return False

        try:
            # Configure ONNX Runtime session with CPU optimizations
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = 4  # Use multiple threads

            # Use providers resolved by ClassifierService (already validated/fallback-aware)
            providers = list(self.ort_providers or ["CPUExecutionProvider"])
            self.session = ort.InferenceSession(self.model_path, sess_options, providers=providers)
            self.loaded = True
            self.error = None
            log.info(f"{self.name} ONNX model loaded successfully", input_size=self.input_size, providers=providers)
            return True
        except Exception as e:
            self.error = f"Failed to load ONNX model: {str(e)}"
            log.error(f"Failed to load {self.name} ONNX model", error=str(e))
            return False

    def _resize_with_padding(self, image: Image.Image, target_size: int) -> Image.Image:
        """Resize image with padding to maintain aspect ratio."""
        iw, ih = image.size
        scale = min(target_size / iw, target_size / ih)
        nw = int(iw * scale)
        nh = int(ih * scale)

        image = image.resize((nw, nh), Image.Resampling.BICUBIC)

        # Create new image with gray padding (ImageNet standard)
        new_image = Image.new('RGB', (target_size, target_size), (128, 128, 128))
        new_image.paste(image, ((target_size - nw) // 2, (target_size - nh) // 2))

        return new_image

    def _preprocess(self, image: Image.Image) -> np.ndarray:
        """Preprocess image for ONNX inference."""
        image = image.convert('RGB')
        image = self._resize_with_padding(image, self.input_size)

        # Convert to numpy and normalize (ImageNet style for timm models)
        arr = np.array(image).astype(np.float32) / 255.0
        arr = (arr - self.mean) / self.std
        arr = arr.transpose(2, 0, 1)  # HWC -> CHW (ONNX expects NCHW)
        return arr[np.newaxis, ...].astype(np.float32)  # Add batch dimension

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """Apply softmax to convert logits to probabilities."""
        exp_x = np.exp(x - np.max(x))
        return exp_x / np.sum(exp_x)

    def classify(self, image: Image.Image, top_k: int = 5) -> list[dict]:
        """Classify an image using this ONNX model."""
        if not self.loaded or not self.session:
            log.warning(f"{self.name} ONNX model not loaded, cannot classify")
            return []

        try:
            input_tensor = self._preprocess(image)

            # Get input name from model
            input_name = self.session.get_inputs()[0].name

            # Run inference
            with self._lock:
                outputs = self.session.run(None, {input_name: input_tensor})
            logits = outputs[0][0]

            # Apply softmax to get probabilities
            probs = self._softmax(logits)

            # Get top-k results
            top_indices = np.argsort(probs)[::-1][:top_k]

            classifications = []
            for i in top_indices:
                label = self.labels[i] if i < len(self.labels) else f"Class {i}"
                classifications.append({
                    "index": int(i),
                    "score": float(probs[i]),
                    "label": label
                })

            return classifications

        except Exception as e:
            log.error(f"ONNX inference failed for {self.name}", error=str(e))
            return []

    def classify_raw(self, image: Image.Image) -> np.ndarray:
        """Classify and return the raw probability vector (for ensemble)."""
        if not self.loaded or not self.session:
            return np.array([])

        try:
            input_tensor = self._preprocess(image)
            input_name = self.session.get_inputs()[0].name
            with self._lock:
                outputs = self.session.run(None, {input_name: input_tensor})
            logits = outputs[0][0]
            return self._softmax(logits)
        except Exception as e:
            log.error("ONNX raw classification failed", error=str(e))
            return np.array([])

    def cleanup(self):
        """Clean up ONNX model resources."""
        if self.session is not None:
            # ONNX sessions don't have explicit cleanup,
            # but we can dereference to allow garbage collection
            self.session = None
        self.loaded = False
        log.info(f"{self.name} ONNX model resources cleaned up")

    def get_status(self) -> dict:
        """Return the current status of this model."""
        return {
            "loaded": self.loaded,
            "error": self.error,
            "labels_count": len(self.labels),
            "enabled": self.session is not None,
            "model_path": self.model_path,
            "runtime": "onnx",
            "input_size": self.input_size,
        }


class OpenVINOModelInstance:
    """Represents a loaded ONNX model compiled with OpenVINO (Intel CPU/GPU)."""

    def __init__(
        self,
        name: str,
        model_path: str,
        labels_path: str,
        preprocessing: Optional[dict] = None,
        input_size: int = 384,
        device_name: str = "CPU",
    ):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.preprocessing = preprocessing or {}
        self.input_size = input_size
        self.device_name = device_name
        self.core = None
        self.compiled_model = None
        self.input_name: Optional[str] = None
        self.labels: list[str] = []
        self.loaded = False
        self.error: Optional[str] = None
        self._lock = threading.Lock()

        self.mean = np.array(self.preprocessing.get("mean", [0.485, 0.456, 0.406]))
        self.std = np.array(self.preprocessing.get("std", [0.229, 0.224, 0.225]))

    def load(self) -> bool:
        if self.loaded:
            return True

        if not OPENVINO_AVAILABLE or OpenVINOCore is None:
            self.error = "OpenVINO runtime not installed"
            log.error("OpenVINO runtime not installed")
            return False

        if os.path.exists(self.labels_path):
            try:
                with open(self.labels_path, 'r', encoding='utf-8', errors='replace') as f:
                    self.labels = [line.strip() for line in f.readlines() if line.strip()]
                log.info(f"Loaded {len(self.labels)} labels for OpenVINO model {self.name}")
            except Exception as e:
                log.error(f"Failed to load labels for {self.name}", error=str(e))

        if not os.path.exists(self.model_path):
            self.error = f"ONNX model file not found: {self.model_path}"
            log.warning(f"{self.name} OpenVINO model not found", path=self.model_path)
            return False

        try:
            self.core = OpenVINOCore()
            model = self.core.read_model(self.model_path)
            self.compiled_model = self.core.compile_model(model, self.device_name)
            self.input_name = self.compiled_model.inputs[0].get_any_name()
            self.loaded = True
            self.error = None
            log.info("OpenVINO model loaded successfully", model=self.name, device=self.device_name, input_size=self.input_size)
            return True
        except Exception as e:
            self.error = f"Failed to load OpenVINO model: {str(e)}"
            log.error(f"Failed to load {self.name} OpenVINO model", error=str(e), device=self.device_name)
            return False

    def _resize_with_padding(self, image: Image.Image, target_size: int) -> Image.Image:
        iw, ih = image.size
        scale = min(target_size / iw, target_size / ih)
        nw = int(iw * scale)
        nh = int(ih * scale)
        image = image.resize((nw, nh), Image.Resampling.BICUBIC)
        new_image = Image.new('RGB', (target_size, target_size), (128, 128, 128))
        new_image.paste(image, ((target_size - nw) // 2, (target_size - nh) // 2))
        return new_image

    def _preprocess(self, image: Image.Image) -> np.ndarray:
        image = image.convert('RGB')
        image = self._resize_with_padding(image, self.input_size)
        arr = np.array(image).astype(np.float32) / 255.0
        arr = (arr - self.mean) / self.std
        arr = arr.transpose(2, 0, 1)  # NCHW
        return arr[np.newaxis, ...].astype(np.float32)

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        exp_x = np.exp(x - np.max(x))
        return exp_x / np.sum(exp_x)

    def _infer_logits(self, image: Image.Image) -> np.ndarray:
        if not self.loaded or self.compiled_model is None or self.input_name is None:
            return np.array([])

        input_tensor = self._preprocess(image)
        with self._lock:
            infer_request = self.compiled_model.create_infer_request()
            outputs = infer_request.infer({self.input_name: input_tensor})
        raw = next(iter(outputs.values()))
        return np.asarray(raw)[0]

    def classify(self, image: Image.Image, top_k: int = 5) -> list[dict]:
        if not self.loaded or self.compiled_model is None:
            log.warning(f"{self.name} OpenVINO model not loaded, cannot classify")
            return []
        try:
            logits = self._infer_logits(image)
            if logits.size == 0:
                return []
            probs = self._softmax(logits)
            top_indices = np.argsort(probs)[::-1][:top_k]
            return [
                {
                    "index": int(i),
                    "score": float(probs[i]),
                    "label": self.labels[i] if i < len(self.labels) else f"Class {i}",
                }
                for i in top_indices
            ]
        except Exception as e:
            log.error(f"OpenVINO inference failed for {self.name}", error=str(e), device=self.device_name)
            return []

    def classify_raw(self, image: Image.Image) -> np.ndarray:
        if not self.loaded or self.compiled_model is None:
            return np.array([])
        try:
            logits = self._infer_logits(image)
            if logits.size == 0:
                return np.array([])
            return self._softmax(logits)
        except Exception as e:
            log.error("OpenVINO raw classification failed", error=str(e), device=self.device_name)
            return np.array([])

    def cleanup(self):
        self.compiled_model = None
        self.core = None
        self.loaded = False
        log.info(f"{self.name} OpenVINO model resources cleaned up", device=self.device_name)

    def get_status(self) -> dict:
        return {
            "loaded": self.loaded,
            "error": self.error,
            "labels_count": len(self.labels),
            "enabled": self.compiled_model is not None,
            "model_path": self.model_path,
            "runtime": "openvino",
            "input_size": self.input_size,
            "device": self.device_name,
        }


class ClassifierService:
    """Service for managing multiple classification models (TFLite and ONNX)."""

    # Union type for model instances
    ModelType = ModelInstance | ONNXModelInstance | OpenVINOModelInstance

    def __init__(self):
        self._models: dict[str, ClassifierService.ModelType] = {}
        self._models_lock = threading.Lock()
        # Dedicated executor for ML tasks to avoid blocking default executor
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ml_worker")
        self._selected_inference_provider = _normalize_inference_provider(
            getattr(settings.classification, "inference_provider", "auto")
        )
        self._active_inference_provider = "tflite"
        self._inference_backend = "tflite"
        self._inference_fallback_reason: Optional[str] = None
        self._accel_caps = _detect_acceleration_capabilities()
        self._init_bird_model()

    def _get_model_paths(self, model_file: str, labels_file: str) -> tuple[str, str]:
        """Get full paths for model and labels files."""
        persistent_dir = "/data/models"
        fallback_dir = os.path.join(os.path.dirname(__file__), "../assets")

        if os.path.exists(os.path.join(persistent_dir, model_file)):
            assets_dir = persistent_dir
            log.info("Using persistent model directory", path=persistent_dir)
        else:
            assets_dir = fallback_dir
            log.info("Using fallback model directory", path=fallback_dir)

        model_path = os.path.join(assets_dir, model_file)
        labels_path = os.path.join(assets_dir, labels_file)

        return model_path, labels_path

    def _init_bird_model(self):
        """Initialize the bird classification model (loaded at startup)."""
        from app.services.model_manager import model_manager, REMOTE_REGISTRY

        model_path, labels_path, input_size = model_manager.get_active_model_paths()

        # Fetch metadata from model_manager registry
        active_model_id = model_manager.active_model_id
        model_meta = next((m for m in REMOTE_REGISTRY if m['id'] == active_model_id), None)
        preprocessing = model_meta.get('preprocessing') if model_meta else None
        runtime = model_meta.get('runtime', 'tflite') if model_meta else 'tflite'

        if not os.path.exists(model_path):
            model_path, labels_path = self._get_model_paths(
                settings.classification.model,
                "labels.txt"
            )

        log.info("Initializing bird model",
                 path=model_path,
                 input_size=input_size,
                 runtime=runtime,
                 preprocessing=preprocessing)

        self._selected_inference_provider = _normalize_inference_provider(
            getattr(settings.classification, "inference_provider", "auto")
        )
        self._accel_caps = _detect_acceleration_capabilities()
        self._inference_fallback_reason = None
        self._inference_backend = "tflite"
        self._active_inference_provider = "tflite"

        if not self._accel_caps.get("openvino_available"):
            if self._accel_caps.get("openvino_import_error"):
                log.warning(
                    "OpenVINO unavailable (import)",
                    error=self._accel_caps.get("openvino_import_error"),
                    version=self._accel_caps.get("openvino_version"),
                )
            elif self._accel_caps.get("openvino_probe_error"):
                log.warning(
                    "OpenVINO unavailable (probe)",
                    error=self._accel_caps.get("openvino_probe_error"),
                    dev_dri_present=self._accel_caps.get("dev_dri_present"),
                    dev_dri_entries=self._accel_caps.get("dev_dri_entries"),
                    process_groups=self._accel_caps.get("process_groups"),
                )
            elif self._accel_caps.get("openvino_gpu_probe_error"):
                log.warning(
                    "OpenVINO GPU plugin unavailable",
                    error=self._accel_caps.get("openvino_gpu_probe_error"),
                    dev_dri_present=self._accel_caps.get("dev_dri_present"),
                    dev_dri_entries=self._accel_caps.get("dev_dri_entries"),
                    process_groups=self._accel_caps.get("process_groups"),
                )

        # Create appropriate model instance based on runtime
        if runtime == 'onnx':
            selection = _resolve_inference_selection(self._selected_inference_provider, self._accel_caps)
            self._inference_fallback_reason = selection.get("fallback_reason")
            self._active_inference_provider = selection.get("active_provider", "unavailable")
            self._inference_backend = selection.get("backend", "unavailable")

            if selection["backend"] == "openvino":
                bird_model = OpenVINOModelInstance(
                    "bird",
                    model_path,
                    labels_path,
                    preprocessing=preprocessing,
                    input_size=input_size,
                    device_name=selection["openvino_device"] or "CPU",
                )
                if bird_model.load():
                    session_providers = []
                    if getattr(bird_model, "session", None):
                        try:
                            session_providers = list(bird_model.session.get_providers() or [])
                        except Exception:
                            session_providers = []
                    reconciled_provider, session_fallback_reason = _reconcile_ort_active_provider(
                        self._active_inference_provider,
                        session_providers,
                    )
                    if session_fallback_reason:
                        prev_reason = self._inference_fallback_reason
                        self._active_inference_provider = reconciled_provider
                        self._inference_fallback_reason = (
                            f"{prev_reason}; {session_fallback_reason}" if prev_reason else session_fallback_reason
                        )
                        log.warning(
                            "ONNX Runtime session provider mismatch; applying runtime fallback status",
                            requested=self._selected_inference_provider,
                            planned_active=selection.get("active_provider"),
                            actual_active=self._active_inference_provider,
                            session_providers=session_providers,
                            reason=session_fallback_reason,
                        )
                    self._models["bird"] = bird_model
                    if self._inference_fallback_reason:
                        log.warning(
                            "Inference provider fallback applied",
                            requested=self._selected_inference_provider,
                            active=self._active_inference_provider,
                            backend=self._inference_backend,
                            reason=self._inference_fallback_reason,
                        )
                    return
                # Device/plugin can still fail even if detection said "available" (e.g. /dev/dri permissions)
                if self._accel_caps.get("ort_available"):
                    log.warning(
                        "OpenVINO model load failed; retrying with ONNX Runtime CPU fallback",
                        requested=self._selected_inference_provider,
                        device=selection.get("openvino_device"),
                        error=bird_model.error,
                    )
                    self._inference_backend = "onnxruntime"
                    self._active_inference_provider = "cpu"
                    prev_reason = self._inference_fallback_reason
                    self._inference_fallback_reason = (
                        f"{prev_reason}; OpenVINO load failed" if prev_reason else "OpenVINO load failed; using ONNX Runtime CPU"
                    )
                    fallback_model = ONNXModelInstance(
                        "bird",
                        model_path,
                        labels_path,
                        preprocessing=preprocessing,
                        input_size=input_size,
                        ort_providers=["CPUExecutionProvider"],
                    )
                    fallback_model.load()
                    self._models["bird"] = fallback_model
                    return
                log.warning("OpenVINO model load failed and no ORT fallback available; falling back to TFLite", error=bird_model.error)
                runtime = 'tflite'

            if selection["backend"] == "onnxruntime":
                bird_model = ONNXModelInstance(
                    "bird",
                    model_path,
                    labels_path,
                    preprocessing=preprocessing,
                    input_size=input_size,
                    ort_providers=selection.get("ort_providers") or ["CPUExecutionProvider"],
                )
                if bird_model.load():
                    self._models["bird"] = bird_model
                    if self._inference_fallback_reason:
                        log.warning(
                            "Inference provider fallback applied",
                            requested=self._selected_inference_provider,
                            active=self._active_inference_provider,
                            backend=self._inference_backend,
                            reason=self._inference_fallback_reason,
                        )
                    return
                if self._accel_caps.get("openvino_available") and self._accel_caps.get("intel_cpu_available"):
                    log.warning("ONNX Runtime model load failed; retrying with OpenVINO CPU fallback", error=bird_model.error)
                    self._inference_backend = "openvino"
                    self._active_inference_provider = "intel_cpu"
                    prev_reason = self._inference_fallback_reason
                    self._inference_fallback_reason = (
                        f"{prev_reason}; ONNX Runtime load failed" if prev_reason else "ONNX Runtime load failed; using OpenVINO CPU"
                    )
                    fallback_model = OpenVINOModelInstance(
                        "bird",
                        model_path,
                        labels_path,
                        preprocessing=preprocessing,
                        input_size=input_size,
                        device_name="CPU",
                    )
                    fallback_model.load()
                    self._models["bird"] = fallback_model
                    return
                log.warning("ONNX Runtime model load failed; falling back to TFLite", error=bird_model.error)
                runtime = 'tflite'

            log.error(
                "ONNX model requested but no ONNX-capable runtime is available; falling back to TFLite",
                requested_provider=self._selected_inference_provider,
                reason=self._inference_fallback_reason,
            )
            runtime = 'tflite'

        # Default: TFLite model
        bird_model = ModelInstance("bird", model_path, labels_path, preprocessing=preprocessing)
        bird_model.load()
        self._models["bird"] = bird_model
        self._inference_backend = "tflite"
        self._active_inference_provider = "tflite"

    def reload_bird_model(self):
        """Reload the bird model (e.g., after switching models)."""
        with self._models_lock:
            if "bird" in self._models:
                # Cleanup old model resources before replacing
                old_model = self._models.pop("bird")
                if hasattr(old_model, 'cleanup'):
                    old_model.cleanup()
                del old_model
            self._init_bird_model()
        log.info("Reloaded bird model")

    def _get_wildlife_model(self) -> ModelInstance:
        """Get or lazily load the wildlife model."""
        if "wildlife" not in self._models:
            model_path, labels_path = self._get_model_paths(
                settings.classification.wildlife_model,
                settings.classification.wildlife_labels
            )
            self._models["wildlife"] = ModelInstance("wildlife", model_path, labels_path)

        model = self._models["wildlife"]
        if not model.loaded:
            model.load()

        return model

    def check_health(self) -> dict:
        """Detailed health check for the classification service."""
        bird = self._models.get("bird")
        
        # Determine which TFLite runtime is actually in use
        tflite_type = "none"
        if tflite:
            if "tflite_runtime" in str(tflite):
                tflite_type = "tflite-runtime"
            else:
                tflite_type = "tensorflow-full"

        return {
            "status": "ok" if (bird and bird.loaded) else "error",
            "runtimes": {
                "tflite": {
                    "installed": tflite is not None,
                    "type": tflite_type
                },
                "onnx": {
                    "installed": ONNX_AVAILABLE,
                    "available": ort is not None
                },
                "openvino": {
                    "installed": OPENVINO_AVAILABLE,
                    "available": OpenVINOCore is not None
                }
            },
            "models": {
                name: {
                    "loaded": model.loaded,
                    "runtime": "onnx" if isinstance(model, ONNXModelInstance) else ("openvino" if isinstance(model, OpenVINOModelInstance) else "tflite"),
                    "error": model.error
                } for name, model in self._models.items()
            }
        }

    # Legacy properties
    @property
    def interpreter(self):
        bird = self._models.get("bird")
        return getattr(bird, "interpreter", None)

    @property
    def labels(self) -> list[str]:
        bird = self._models.get("bird")
        return bird.labels if bird else []

    @property
    def model_loaded(self) -> bool:
        bird = self._models.get("bird")
        return bool(getattr(bird, "loaded", False))

    @property
    def model_error(self) -> Optional[str]:
        bird = self._models.get("bird")
        return getattr(bird, "error", None)

    def get_status(self) -> dict:
        bird = self._models.get("bird")
        self._accel_caps = _detect_acceleration_capabilities()

        status = {
            "runtime": "tflite-runtime" if "tflite_runtime" in str(tflite) else "tensorflow",
            "runtime_installed": tflite is not None,
            "onnx_available": ONNX_AVAILABLE,
            "openvino_available": bool(self._accel_caps.get("openvino_available")),
            "openvino_version": self._accel_caps.get("openvino_version"),
            "openvino_import_path": self._accel_caps.get("openvino_import_path"),
            "openvino_import_error": self._accel_caps.get("openvino_import_error"),
            "openvino_probe_error": self._accel_caps.get("openvino_probe_error"),
            "openvino_gpu_probe_error": self._accel_caps.get("openvino_gpu_probe_error"),
            "openvino_devices": self._accel_caps.get("openvino_devices") or [],
            "cuda_provider_installed": bool(self._accel_caps.get("cuda_provider_installed")),
            "cuda_hardware_available": bool(self._accel_caps.get("cuda_hardware_available")),
            "cuda_available": bool(self._accel_caps.get("cuda_available")),
            "intel_gpu_available": bool(self._accel_caps.get("intel_gpu_available")),
            "intel_cpu_available": bool(self._accel_caps.get("intel_cpu_available")),
            "dev_dri_present": bool(self._accel_caps.get("dev_dri_present")),
            "dev_dri_entries": self._accel_caps.get("dev_dri_entries") or [],
            "process_uid": self._accel_caps.get("process_uid"),
            "process_gid": self._accel_caps.get("process_gid"),
            "process_groups": self._accel_caps.get("process_groups") or [],
            "selected_provider": _normalize_inference_provider(getattr(settings.classification, "inference_provider", "auto")),
            "active_provider": self._active_inference_provider,
            "inference_backend": self._inference_backend,
            "fallback_reason": self._inference_fallback_reason,
            "available_providers": [
                p for p in ["cpu", "cuda", "intel_cpu", "intel_gpu"]
                if p == "cpu"
                or (p == "cuda" and self._accel_caps.get("cuda_available"))
                or (p == "intel_cpu" and self._accel_caps.get("intel_cpu_available"))
                or (p == "intel_gpu" and self._accel_caps.get("intel_gpu_available"))
            ],
            # legacy compatibility (can be removed later)
            "cuda_enabled": _normalize_inference_provider(getattr(settings.classification, "inference_provider", "auto")) == "cuda",
            "models": {}
        }
        
        for name, model in self._models.items():
            model_status = model.get_status()
            if name == "bird" and isinstance(model, ONNXModelInstance) and model.session:
                model_status["active_providers"] = model.session.get_providers()
            status["models"][name] = model_status
            
        if bird:
            # For backward compatibility
            status.update(bird.get_status())
            
        return status

    def get_wildlife_status(self) -> dict:
        wildlife = self._models.get("wildlife")
        if wildlife:
            return wildlife.get_status()

        model_path, labels_path = self._get_model_paths(
            settings.classification.wildlife_model,
            settings.classification.wildlife_labels
        )
        model_exists = os.path.exists(model_path)
        labels_exist = os.path.exists(labels_path)
        labels_count = 0
        if labels_exist:
            try:
                with open(labels_path, 'r') as f:
                    labels_count = sum(1 for line in f if line.strip())
            except Exception:
                pass

        return {
            "loaded": False,
            "error": None if model_exists else f"Model not found: {model_path}",
            "labels_count": labels_count,
            "enabled": model_exists,
            "model_path": model_path,
        }

    def classify(self, image: Image.Image) -> list[dict]:
        """Classify an image using the bird model."""
        bird = self._models.get("bird")
        if bird:
            return bird.classify(image)
        return []

    async def classify_async(self, image: Image.Image) -> list[dict]:
        """Async wrapper for classify to prevent blocking the event loop."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self.classify, image)

    def classify_wildlife(self, image: Image.Image) -> list[dict]:
        """Classify an image using the wildlife model."""
        wildlife = self._get_wildlife_model()
        return wildlife.classify(image)

    async def classify_wildlife_async(self, image: Image.Image) -> list[dict]:
        """Async wrapper for wildlife classification."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self.classify_wildlife, image)

    def get_wildlife_labels(self) -> list[str]:
        wildlife = self._get_wildlife_model()
        return wildlife.labels

    def reload_wildlife_model(self):
        if "wildlife" in self._models:
            old_model = self._models.pop("wildlife")
            if hasattr(old_model, 'cleanup'):
                old_model.cleanup()
            del old_model
            log.info("Cleared cached wildlife model instance")
        try:
            self._get_wildlife_model()
            log.info("Reloaded wildlife model")
        except Exception as e:
            log.error("Failed to reload wildlife model", error=str(e))

    def classify_video(self, video_path: str, stride: int = 5, max_frames: Optional[int] = None, progress_callback=None) -> list[dict]:
        """
        Classify a video clip using Temporal Ensemble (Soft Voting) with Normal Distribution sampling.

        Args:
            video_path: Path to the video file.
            stride: Legacy parameter, no longer used for sampling but kept for API compatibility.
            max_frames: Maximum number of frames to process.
            progress_callback: Optional callback function.

        Returns:
            List of classifications with aggregated scores.
        """
        if max_frames is None:
            max_frames = settings.classification.video_classification_frames

        bird_model = self._models.get("bird")
        if not bird_model or not bird_model.loaded:
            log.error("Bird model not loaded for video classification")
            return []

        cap = None
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                log.error(f"Could not open video file: {video_path}")
                return []

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)

            if total_frames <= 0:
                log.warning("Video has no frames", path=video_path)
                return []

            log.info("Analyzing video", frames=total_frames, fps=fps, max_samples=max_frames)

            # --- Normal Distribution Sampling ---
            # We want to sample frames mostly from the middle where the bird is likely most active/visible
            # mu = center of video, sigma = 1/4 of video length to cover ~95% of duration
            mu = total_frames / 2
            sigma = total_frames / 4

            # Use a local RNG for deterministic sampling
            rng = np.random.RandomState(42)

            # Generate more samples than needed then unique/sort to get high-quality distribution
            raw_indices = rng.normal(mu, sigma, max_frames * 2)
            frame_indices = np.clip(raw_indices, 0, total_frames - 1).astype(int)
            frame_indices = np.unique(np.sort(frame_indices))

            # If we have too many after unique, take max_frames spread out
            if len(frame_indices) > max_frames:
                # Sub-sample to exactly max_frames
                idx = np.round(np.linspace(0, len(frame_indices) - 1, max_frames)).astype(int)
                frame_indices = frame_indices[idx]
            # ------------------------------------

            all_scores = []

            from app.services.model_manager import model_manager, REMOTE_REGISTRY

            active_model_id = model_manager.active_model_id
            model_meta = next((m for m in REMOTE_REGISTRY if m["id"] == active_model_id), None)
            model_name = model_meta["name"] if model_meta else None
            if not model_name and hasattr(bird_model, "model_path"):
                model_name = os.path.basename(bird_model.model_path)
            if not model_name:
                model_name = "bird"

            for idx in frame_indices:
                # Seek to frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret:
                    continue

                # Convert BGR (OpenCV) to RGB (PIL)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)

                # Get raw probability vector
                scores = bird_model.classify_raw(image)

                if len(scores) > 0:
                    all_scores.append(scores)

                    # Call progress callback if provided
                    if progress_callback:
                        # Get top prediction for this frame
                        top_idx = int(np.argmax(scores))
                        top_score = float(scores[top_idx])
                        top_label = bird_model.labels[top_idx] if top_idx < len(bird_model.labels) else f"Class {top_idx}"
                        frame_thumb = None
                        try:
                            from io import BytesIO
                            import base64
                            thumb = image.copy()
                            thumb.thumbnail((96, 72))
                            buf = BytesIO()
                            thumb.save(buf, format="JPEG", quality=60)
                            frame_thumb = base64.b64encode(buf.getvalue()).decode("ascii")
                        except Exception as e:
                            log.debug("Failed to encode frame thumbnail", error=str(e))

                        progress_callback(
                            current_frame=len(all_scores),
                            total_frames=len(frame_indices),
                            frame_score=top_score,
                            top_label=top_label,
                            frame_thumb=frame_thumb,
                            frame_index=int(idx) + 1,
                            clip_total=int(total_frames),
                            model_name=model_name
                        )

            if not all_scores:
                log.warning("No frames processed from video")
                return []

            # Top-K Average (Representative Score Logic)
            # This focuses on the 'best looks' the model got at the bird.
            processed_count = len(all_scores)
            scores_matrix = np.vstack(all_scores)

            # Use top 5 frames (or all if fewer than 5)
            k = min(processed_count, 5)

            # For each class, sort and take the average of the top K scores
            top_k_per_class = np.sort(scores_matrix, axis=0)[-k:]
            representative_scores = np.mean(top_k_per_class, axis=0)

            # Create standard classification list from representative scores
            top_indices = representative_scores.argsort()[-5:][::-1]

            classifications = []
            for i in top_indices:
                score = float(representative_scores[i])
                label = bird_model.labels[i] if i < len(bird_model.labels) else f"Class {i}"
                classifications.append({
                    "index": int(i),
                    "score": score,
                    "label": label
                })

            log.info(f"Video classification complete (Top-K). Analyzed {processed_count} frames.",
                     top_result=classifications[0]['label'] if classifications else None,
                     top_score=round(classifications[0]['score'], 3))

            return classifications

        except Exception as e:
            log.error("Error during video classification", error=str(e))
            return []
        finally:
            # Always release video capture to prevent memory leaks
            if cap is not None:
                cap.release()

    async def classify_video_async(self, video_path: str, stride: int = 5, max_frames: Optional[int] = None, progress_callback=None) -> list[dict]:
        """Async wrapper for video classification."""
        if max_frames is None:
            max_frames = settings.classification.video_classification_frames

        loop = asyncio.get_running_loop()

        # Wrap the callback to make it thread-safe
        if progress_callback:
            def sync_callback(
                current_frame,
                total_frames,
                frame_score,
                top_label,
                frame_thumb=None,
                frame_index=None,
                clip_total=None,
                model_name=None
            ):
                try:
                    # Schedule the async callback in the event loop from the executor thread
                    future = asyncio.run_coroutine_threadsafe(
                        progress_callback(
                            current_frame,
                            total_frames,
                            frame_score,
                            top_label,
                            frame_thumb,
                            frame_index,
                            clip_total,
                            model_name
                        ),
                        loop
                    )
                    # Wait for completion and catch any exceptions
                    # Use a short timeout to avoid blocking the video processing
                    try:
                        future.result(timeout=1.0)
                    except TimeoutError:
                        log.warning("Progress callback timed out after 1s",
                                   frame=current_frame,
                                   total=total_frames)
                    except Exception as e:
                        log.error("Progress callback failed",
                                 error=str(e),
                                 frame=current_frame,
                                 total=total_frames)
                except Exception as e:
                    # Catch any exception in scheduling itself
                    log.error("Failed to schedule progress callback", error=str(e))
            return await loop.run_in_executor(self._executor, self.classify_video, video_path, stride, max_frames, sync_callback)
        else:
            return await loop.run_in_executor(self._executor, self.classify_video, video_path, stride, max_frames, None)
