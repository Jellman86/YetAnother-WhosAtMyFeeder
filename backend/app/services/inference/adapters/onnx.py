"""ONNX Runtime adapter for CPU and CUDA execution providers."""

import os
import threading
from typing import Any, Optional

import numpy as np
import structlog
from PIL import Image

from app.services.inference import runtimes
from app.services.inference.diagnostics import summarize_numeric_array, summarize_runtime_exception
from app.services.inference.errors import InvalidInferenceOutputError
from app.services.inference.outputs import (
    build_classification_results,
    check_catalogue_output_width,
    resolve_grouped_labels,
    resolve_model_labels,
    safe_softmax,
)
from app.services.inference.preprocessing import (
    classifier_auxiliary_inputs,
    classifier_wants_bgr,
    resize_with_preprocessing,
)
from app.services.native_crash_quarantine import artifact_digest

log = structlog.get_logger()


class ONNXModelInstance:
    """Represents a loaded ONNX model with its labels (for high-accuracy models)."""

    def __init__(
        self,
        name: str,
        model_path: str,
        labels_path: str,
        preprocessing: Optional[dict] = None,
        label_grouping: Optional[dict] = None,
        input_size: int = 384,
        ort_providers: Optional[list[str]] = None,
        model_sha256: Optional[str] = None,
    ):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.preprocessing = preprocessing or {}
        self.label_grouping = dict(label_grouping or {})
        # The weights this instance loads, bound now: results carry it as their
        # provenance, and a reinstall can replace the file under a running instance.
        # Every backend and fallback is built here, including one loading other weights.
        self.loaded_artifact_sha256 = artifact_digest(model_path)
        # Fallbacks may load different weights from the selected registry model.
        # Reuse their bound digest so labels follow those actual output indices.
        self.model_sha256 = self.loaded_artifact_sha256 or model_sha256
        self.input_size = input_size
        self.ort_providers = list(ort_providers or ["CPUExecutionProvider"])
        self.session = None
        self._session_primary_provider: str | None = None
        self.labels: list[str] = []
        self.grouped_labels: list[str] = []
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

        if not runtimes.ONNX_AVAILABLE:
            self.error = "ONNX Runtime not installed"
            log.error("ONNX Runtime not installed")
            return False

        self.labels, self.grouped_labels, label_source = resolve_model_labels(
            self.labels_path,
            self.label_grouping,
            model_sha256=self.model_sha256,
            context=self.name,
        )
        self._label_source = label_source
        if self.labels:
            log.info(f"Loaded {len(self.labels)} labels for ONNX model {self.name}", label_source=label_source)

        if not os.path.exists(self.model_path):
            self.error = f"ONNX model file not found: {self.model_path}"
            log.warning(f"{self.name} ONNX model not found", path=self.model_path)
            return False

        try:
            # Configure ONNX Runtime session with CPU optimizations
            sess_options = runtimes.ort.SessionOptions()
            sess_options.graph_optimization_level = runtimes.ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = 4  # Use multiple threads

            # Use providers resolved by ClassifierService (already validated/fallback-aware)
            providers = list(self.ort_providers or ["CPUExecutionProvider"])
            if "CUDAExecutionProvider" in providers:
                runtimes.preload_onnxruntime_cuda_runtime_libraries()
            self.session = runtimes.ort.InferenceSession(self.model_path, sess_options, providers=providers)
            self._session_primary_provider = self._active_primary_provider()
            if self._session_primary_provider == "CUDAExecutionProvider":
                from app.utils.cuda_runtime import prevent_internal_cuda_fallback

                prevent_internal_cuda_fallback(self.session)
            self.loaded = True
            self.error = None
            log.info(f"{self.name} ONNX model loaded successfully", input_size=self.input_size, providers=providers)
            return True
        except Exception as e:
            self.error = f"Failed to load ONNX model: {str(e)}"
            log.error(f"Failed to load {self.name} ONNX model", error=str(e))
            return False

    def _preprocess(self, image: Image.Image) -> np.ndarray:
        """Preprocess image for ONNX inference."""
        processed = resize_with_preprocessing(
            image,
            self.input_size,
            preprocessing=self.preprocessing,
            default_resize_mode="letterbox",
            default_padding_color=128,
        )
        if self.preprocessing.get("normalization") == "uint8":
            # Quantized/SSD-style models expect raw uint8 NHWC input
            return np.array(processed, dtype=np.uint8)[np.newaxis, ...]
        arr = np.array(processed).astype(np.float32) / 255.0
        if classifier_wants_bgr(self.preprocessing):
            arr = arr[:, :, ::-1]
        arr = (arr - self.mean) / self.std
        arr = arr.transpose(2, 0, 1)  # HWC -> CHW (ONNX expects NCHW)
        return arr[np.newaxis, ...].astype(np.float32)  # Add batch dimension

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """Apply softmax to convert logits to probabilities."""
        check_catalogue_output_width(self.labels, np.asarray(x).size, getattr(self, "_label_source", "none"))
        return safe_softmax(x, context=f"{self.name}:onnx")

    def _active_primary_provider(self) -> str | None:
        get_providers = getattr(self.session, "get_providers", None)
        providers = list(get_providers() or []) if callable(get_providers) else []
        return providers[0] if providers else None

    def _run_inference(self, input_name: str, input_tensor: np.ndarray) -> list[Any]:
        """Run the provider and expose execution failures to recovery policy."""
        try:
            with self._lock:
                if self._session_primary_provider is None:
                    self._session_primary_provider = self._active_primary_provider()
                enforce_cuda = self._session_primary_provider == "CUDAExecutionProvider"
                if enforce_cuda:
                    from app.utils.cuda_runtime import verify_cuda_session_provider

                    verify_cuda_session_provider(self.session)
                outputs = self.session.run(
                    None, {input_name: input_tensor, **classifier_auxiliary_inputs(self.preprocessing)}
                )
                if enforce_cuda:
                    verify_cuda_session_provider(self.session)
                return outputs
        except Exception as exc:
            log.error(f"ONNX inference failed for {self.name}", error=str(exc))
            raise InvalidInferenceOutputError(
                backend="onnxruntime",
                provider=self._session_primary_provider or (self.ort_providers[0] if self.ort_providers else "cpu"),
                detail=f"{self.name} inference execution failed: {exc}",
                diagnostics={"exception_type": type(exc).__name__},
            ) from exc

    def _probabilities_from_outputs(self, outputs: list[Any]) -> np.ndarray:
        """Validate provider output shape before converting logits to probabilities."""
        try:
            logits = np.asarray(outputs[0])[0]
            probs = self._softmax(logits)
        except InvalidInferenceOutputError:
            raise
        except Exception as exc:
            raise InvalidInferenceOutputError(
                backend="onnxruntime",
                provider=self._session_primary_provider or (self.ort_providers[0] if self.ort_providers else "cpu"),
                detail=f"{self.name} returned an invalid output structure: {exc}",
                diagnostics={"exception_type": type(exc).__name__},
            ) from exc
        if probs.size == 0:
            raise InvalidInferenceOutputError(
                backend="onnxruntime",
                provider=self._session_primary_provider or (self.ort_providers[0] if self.ort_providers else "cpu"),
                detail=f"{self.name} inference produced no finite probabilities",
            )
        return probs

    def classify(self, image: Image.Image, top_k: int = 5, input_context: Any | None = None) -> list[dict]:
        """Classify an image using this ONNX model."""
        if not self.loaded or not self.session:
            log.warning(f"{self.name} ONNX model not loaded, cannot classify")
            return []

        input_tensor = self._preprocess(image)
        input_name = self.session.get_inputs()[0].name
        outputs = self._run_inference(input_name, input_tensor)
        probs = self._probabilities_from_outputs(outputs)

        grouped_labels = resolve_grouped_labels(
            self.labels,
            label_grouping=self.label_grouping,
            existing_grouped_labels=self.grouped_labels,
        )
        return build_classification_results(
            probs,
            self.labels,
            top_k=top_k,
            grouped_labels=grouped_labels,
        )

    def classify_raw(self, image: Image.Image) -> np.ndarray:
        """Classify and return the raw probability vector (for ensemble)."""
        if not self.loaded or not self.session:
            return np.array([])

        input_tensor = self._preprocess(image)
        input_name = self.session.get_inputs()[0].name
        outputs = self._run_inference(input_name, input_tensor)
        return self._probabilities_from_outputs(outputs)

    def probe(self, image: Image.Image) -> dict[str, Any]:
        provider = self.ort_providers[0] if self.ort_providers else "CPUExecutionProvider"
        input_tensor = self._preprocess(image)
        report: dict[str, Any] = {
            "status": "ok",
            "provider": str(provider),
            "active_providers": [],
            "input_summary": summarize_numeric_array(input_tensor, name="input_tensor"),
        }
        if not self.loaded or not self.session:
            report["status"] = "compile_failed"
            report["error"] = self.error or "ONNX Runtime model is not loaded"
            return report

        try:
            try:
                report["active_providers"] = list(self.session.get_providers() or [])
            except Exception:
                report["active_providers"] = []
            input_name = self.session.get_inputs()[0].name
            outputs = self._run_inference(input_name, input_tensor)
            report["active_providers"] = list(self.session.get_providers() or [])
            logits = np.asarray(outputs[0])
            if logits.ndim > 0 and logits.shape[0] == 1:
                logits = logits[0]
            report["output_summary"] = summarize_numeric_array(logits, name="output_logits")
            if logits.size == 0 or not np.isfinite(logits).any():
                report["status"] = "invalid_output"
            return report
        except Exception as exc:
            report["status"] = "runtime_error"
            report["error"] = summarize_runtime_exception(exc, max_len=600)
            try:
                report["active_providers"] = list(self.session.get_providers() or [])
            except Exception:
                report["active_providers"] = []
            return report

    def cleanup(self):
        """Clean up ONNX model resources."""
        if self.session is not None:
            # ONNX sessions don't have explicit cleanup,
            # but we can dereference to allow garbage collection
            self.session = None
        self._session_primary_provider = None
        self.loaded = False
        log.info(f"{self.name} ONNX model resources cleaned up")

    def get_status(self) -> dict:
        """Return the current status of this model."""
        return {
            "loaded": self.loaded,
            "error": self.error,
            "labels_count": len(self.labels),
            "grouped_labels_count": len(set(self.grouped_labels)) if self.grouped_labels else None,
            "enabled": self.session is not None,
            "model_path": self.model_path,
            "runtime": "onnx",
            "input_size": self.input_size,
        }
