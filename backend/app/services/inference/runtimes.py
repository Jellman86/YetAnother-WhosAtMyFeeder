"""Optional inference runtimes, resolved once at import.

Adapters and the classifier read these handles through this module, e.g.
`runtimes.ort`, so a single patch point covers every consumer.
"""

import importlib

# TFLite runtime
try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    try:
        import ai_edge_litert.interpreter as tflite
    except ImportError:
        try:
            import tensorflow.lite as tflite
        except ImportError:
            tflite = None


def tflite_runtime_name() -> str:
    module_name = str(getattr(tflite, "__name__", "") or "")
    if module_name.startswith("ai_edge_litert"):
        return "litert"
    if module_name.startswith("tflite_runtime"):
        return "tflite-runtime"
    return "tensorflow" if tflite is not None else "unavailable"


# ONNX runtime (for high-accuracy models)
try:
    import onnxruntime as ort

    ONNX_AVAILABLE = True
except ImportError:
    ort = None
    ONNX_AVAILABLE = False


def preload_onnxruntime_cuda_runtime_libraries() -> None:
    """Preload packaged CUDA/cuDNN runtime libraries for ONNX Runtime.

    ONNX Runtime supports shipping the CUDA/cuDNN userspace stack via pip.
    In that setup the shared libraries live under Python site-packages rather
    than a standard system library path, so we ask ORT to preload them
    explicitly before probing or creating CUDA sessions.
    """
    if ort is None:
        return
    from app.utils.cuda_runtime import preload_packaged_cuda_libraries

    preload_packaged_cuda_libraries(ort)


def detect_openvino_support() -> dict:
    """Resolve OpenVINO Core import across package versions.

    OpenVINO 2025+ exposes the stable ``openvino.Core`` directly.
    The legacy ``openvino.runtime.Core`` path was deprecated in 2025.x and
    removed in 2026.0. We try the new path first and fall back for pre-2025
    installations.
    """
    attempts: list[str] = []

    for module_name, attr_name, import_path in (
        ("openvino", "Core", "openvino.Core"),
        ("openvino.runtime", "Core", "openvino.runtime.Core"),
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
OPENVINO_SUPPORT = detect_openvino_support()
OpenVINOCore = OPENVINO_SUPPORT["core_class"]
OPENVINO_AVAILABLE = bool(OPENVINO_SUPPORT["available"])
