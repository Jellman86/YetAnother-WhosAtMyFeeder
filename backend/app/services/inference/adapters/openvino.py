"""OpenVINO adapter: an ONNX model compiled for an Intel CPU, GPU or NPU."""

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
from app.services.openvino_cache import resolve_openvino_cache_dir

log = structlog.get_logger()


def openvino_gpu_startup_self_test_enabled() -> bool:
    return os.getenv("OPENVINO_GPU_STARTUP_SELF_TEST", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def openvino_gpu_optional_compile_properties() -> dict[str, str]:
    properties: dict[str, str] = {}
    execution_mode = os.getenv("OPENVINO_GPU_EXECUTION_MODE_HINT", "").strip()
    activations_scale = os.getenv("OPENVINO_GPU_ACTIVATIONS_SCALE_FACTOR", "").strip()
    if execution_mode:
        properties["EXECUTION_MODE_HINT"] = execution_mode
    if activations_scale:
        properties["ACTIVATIONS_SCALE_FACTOR"] = activations_scale
    return properties


class OpenVINOModelInstance:
    """Represents a loaded ONNX model compiled with OpenVINO (Intel CPU/GPU)."""

    def __init__(
        self,
        name: str,
        model_path: str,
        labels_path: str,
        preprocessing: Optional[dict] = None,
        label_grouping: Optional[dict] = None,
        input_size: int = 384,
        device_name: str = "CPU",
        startup_self_test_enabled: bool | None = None,
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
        self.device_name = device_name
        self._startup_self_test_enabled = (
            openvino_gpu_startup_self_test_enabled()
            if startup_self_test_enabled is None
            else bool(startup_self_test_enabled)
        )
        self.core = None
        self.compiled_model = None
        self._infer_request = None
        self.input_name: Optional[str] = None
        self.labels: list[str] = []
        self.grouped_labels: list[str] = []
        self.loaded = False
        self.error: Optional[str] = None
        self._lock = threading.Lock()
        self._last_startup_self_test_diagnostics: dict[str, Any] | None = None
        self._last_startup_self_test_error: str | None = None
        self._startup_self_test_ran = False

        self.mean = np.array(self.preprocessing.get("mean", [0.485, 0.456, 0.406]))
        self.std = np.array(self.preprocessing.get("std", [0.229, 0.224, 0.225]))

    def _collect_runtime_diagnostics(
        self,
        *,
        input_tensor: np.ndarray | None = None,
        logits: np.ndarray | None = None,
    ) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {
            "device_name": str(self.device_name),
            "model_path": self.model_path,
        }
        compiled_properties: dict[str, Any] = {}
        if self.compiled_model is not None:
            for name in ("INFERENCE_PRECISION_HINT", "NUM_STREAMS", "PERFORMANCE_HINT", "EXECUTION_DEVICES"):
                try:
                    value = self.compiled_model.get_property(name)
                    if isinstance(value, np.ndarray):
                        compiled_properties[name] = value.tolist()
                    elif isinstance(value, tuple):
                        compiled_properties[name] = list(value)
                    else:
                        compiled_properties[name] = str(value)
                except Exception as exc:
                    compiled_properties[name] = f"ERROR: {exc}"
        diagnostics["compile_properties"] = compiled_properties
        if input_tensor is not None:
            diagnostics["input_summary"] = summarize_numeric_array(input_tensor, name="input_tensor")
        if logits is not None:
            diagnostics["output_summary"] = summarize_numeric_array(logits, name="output_logits")
        return diagnostics

    def _build_startup_self_test_image(self) -> Image.Image:
        size = max(8, int(self.input_size))
        x = np.linspace(0, 255, size, dtype=np.uint8)
        y = np.linspace(255, 0, size, dtype=np.uint8)
        red = np.tile(x, (size, 1))
        green = np.tile(y[:, None], (1, size))
        blue = np.full((size, size), 127, dtype=np.uint8)
        return Image.fromarray(np.stack((red, green, blue), axis=2), mode="RGB")

    def _run_gpu_startup_self_test(self) -> None:
        if not self._startup_self_test_enabled:
            return
        self._startup_self_test_ran = True
        image = self._build_startup_self_test_image()
        input_tensor = self._preprocess(image)
        logits = self._infer_output_tensor(image, input_tensor=input_tensor)
        self._last_startup_self_test_diagnostics = self._collect_runtime_diagnostics(
            input_tensor=input_tensor,
            logits=logits,
        )
        self._last_startup_self_test_error = None
        if logits.size == 0 or not np.isfinite(logits).any():
            raise InvalidInferenceOutputError(
                backend="openvino",
                provider=self.device_name,
                detail=f"{self.name} inference produced no finite probabilities during startup self-test",
                diagnostics=dict(self._last_startup_self_test_diagnostics),
            )
        # Also detect near-uniform/degenerate output: if the logit range is
        # extremely small (<0.5), the softmax will be nearly uniform regardless
        # of the input — a sign that GPU inference is silently broken.
        finite_logits = logits[np.isfinite(logits)]
        if finite_logits.size > 1:
            logit_range = float(finite_logits.max() - finite_logits.min())
            if logit_range < 0.5:
                raise InvalidInferenceOutputError(
                    backend="openvino",
                    provider=self.device_name,
                    detail=(
                        f"{self.name} inference produced near-uniform logits (range={logit_range:.4f}) "
                        "during startup self-test — GPU may be silently producing degenerate output"
                    ),
                    diagnostics=dict(self._last_startup_self_test_diagnostics),
                )

    def load(self) -> bool:
        if self.loaded:
            return True

        if not runtimes.OPENVINO_AVAILABLE or runtimes.OpenVINOCore is None:
            self.error = "OpenVINO runtime not installed"
            log.error("OpenVINO runtime not installed")
            return False

        self.labels, self.grouped_labels, label_source = resolve_model_labels(
            self.labels_path,
            self.label_grouping,
            model_sha256=self.model_sha256,
            context=self.name,
        )
        self._label_source = label_source
        if self.labels:
            log.info(f"Loaded {len(self.labels)} labels for OpenVINO model {self.name}", label_source=label_source)

        if not os.path.exists(self.model_path):
            self.error = f"ONNX model file not found: {self.model_path}"
            log.warning(f"{self.name} OpenVINO model not found", path=self.model_path)
            return False

        try:
            self.core = runtimes.OpenVINOCore()

            # Enable caching so GPU model compilation isn't repeated from scratch
            # on every worker process startup, avoiding readiness timeouts.
            cache_dir = resolve_openvino_cache_dir()
            os.makedirs(cache_dir, exist_ok=True)
            self.core.set_property({"CACHE_DIR": cache_dir})

            model = self.core.read_model(self.model_path)

            # Intel GPUs default to f16 inference precision. Un-quantized ONNX models
            # often have intermediate activations >65504, which overflow f16, resulting
            # in non-finite logits (NaN/inf) and crashing the strict softmax pipeline.
            config = {"PERFORMANCE_HINT": "LATENCY", "NUM_STREAMS": "1"}
            _is_gpu = self.device_name == "GPU" or str(self.device_name).startswith("GPU.")
            _is_npu = self.device_name == "NPU" or str(self.device_name).startswith("NPU.")
            if _is_gpu or _is_npu:
                # Both the iGPU and NPU need a static batch dimension (the NPU compiler
                # *requires* it; on the iGPU it avoids the clWaitForEvents -14 crash), so
                # the dynamic-batch reshape below applies to both accelerators.
                if _is_gpu:
                    # Intel GPU defaults to f16; un-quantized ONNX activations >65504
                    # overflow f16 → non-finite logits, so force f32 on the GPU only.
                    config["INFERENCE_PRECISION_HINT"] = "f32"
                    config.update(openvino_gpu_optional_compile_properties())
                # NPU: only f16/i8 are valid for INFERENCE_PRECISION_HINT (f32 is rejected
                # at compile — "Wrong value f32 ... Supported values: f16, i8"), so leave
                # the NPU at its default precision. Validated to give finite, CPU-matching
                # output (rope_vit_b14: top-5 identical to CPU).
                try:
                    partial = model.inputs[0].get_partial_shape()
                    if partial.rank.is_static and partial[0].is_dynamic:
                        static_shape = [1] + [partial[d].get_length() for d in range(1, partial.rank.get_length())]
                        model.reshape(static_shape)
                except Exception:
                    pass  # Non-fatal; proceed with original dynamic shape

            self.compiled_model = self.core.compile_model(model, self.device_name, config=config)
            self._infer_request = None
            self.input_name = self.compiled_model.inputs[0].get_any_name()
            if self._startup_self_test_enabled and (_is_gpu or _is_npu):
                # Reused for the NPU as well — validates the compiled model isn't
                # producing degenerate / non-finite logits on this accelerator.
                self._run_gpu_startup_self_test()
            self.loaded = True
            self.error = None
            log.info(
                "OpenVINO model loaded successfully",
                model=self.name,
                device=self.device_name,
                input_size=self.input_size,
            )
            return True
        except InvalidInferenceOutputError as exc:
            self.error = f"Failed OpenVINO model startup self-test: {exc.detail}"
            self._last_startup_self_test_error = self.error
            log.warning(
                "OpenVINO model failed startup self-test",
                model=self.name,
                device=self.device_name,
                detail=exc.detail,
                diagnostics=exc.diagnostics,
            )
            self.compiled_model = None
            self._infer_request = None
            self.core = None
            self.loaded = False
            return False
        except Exception as e:
            self.error = f"Failed to load OpenVINO model: {str(e)}"
            log.error(f"Failed to load {self.name} OpenVINO model", error=str(e), device=self.device_name)
            return False

    def current_compile_properties(self) -> dict[str, Any]:
        return self._collect_runtime_diagnostics().get("compile_properties") or {}

    def startup_self_test_status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self._startup_self_test_enabled),
            "ran": bool(self._startup_self_test_ran),
            "error": self._last_startup_self_test_error,
            "diagnostics": dict(self._last_startup_self_test_diagnostics or {}),
        }

    def probe(self, image: Image.Image) -> dict[str, Any]:
        input_tensor = self._preprocess(image)
        report: dict[str, Any] = {
            "status": "ok",
            "device": str(self.device_name),
            "compile_properties": self.current_compile_properties(),
            "input_summary": summarize_numeric_array(input_tensor, name="input_tensor"),
        }
        try:
            logits = self._infer_output_tensor(image, input_tensor=input_tensor)
            report["output_summary"] = summarize_numeric_array(logits, name="output_logits")
            if logits.size == 0 or not np.isfinite(logits).any():
                report["status"] = "invalid_output"
            return report
        except Exception as exc:
            report["status"] = "runtime_error"
            report["error"] = summarize_runtime_exception(exc, max_len=600)
            return report

    def _preprocess(self, image: Image.Image) -> np.ndarray:
        processed = resize_with_preprocessing(
            image,
            self.input_size,
            preprocessing=self.preprocessing,
            default_resize_mode="letterbox",
            default_padding_color=128,
        )
        arr = np.array(processed).astype(np.float32) / 255.0
        if classifier_wants_bgr(self.preprocessing):
            arr = arr[:, :, ::-1]
        arr = (arr - self.mean) / self.std
        arr = arr.transpose(2, 0, 1)  # NCHW
        return arr[np.newaxis, ...].astype(np.float32)

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        check_catalogue_output_width(self.labels, np.asarray(x).size, getattr(self, "_label_source", "none"))
        return safe_softmax(x, context=f"{self.name}:openvino")

    def _infer_output_tensor(
        self,
        image: Image.Image,
        *,
        input_tensor: np.ndarray | None = None,
    ) -> np.ndarray:
        if self.compiled_model is None or self.input_name is None:
            return np.array([])

        if input_tensor is None:
            input_tensor = self._preprocess(image)
        # _preprocess emits NCHW [1,3,H,W]. Some exported models (e.g. MobileNet)
        # expect NHWC [1,H,W,3]; feed whatever the compiled model declares.
        try:
            dims = self.compiled_model.inputs[0].get_partial_shape()
            if dims.rank.is_static and dims.rank.get_length() == 4:
                last = dims[3]
                second = dims[1]
                if last.is_static and last.get_length() == 3 and not (second.is_static and second.get_length() == 3):
                    input_tensor = np.ascontiguousarray(np.transpose(input_tensor, (0, 2, 3, 1)))
        except Exception:
            pass
        with self._lock:
            # One request serves every inference: a request per call churns
            # runtime allocations on every classification (#314).
            if self._infer_request is None:
                self._infer_request = self.compiled_model.create_infer_request()
            outputs = self._infer_request.infer(
                {self.input_name: input_tensor, **classifier_auxiliary_inputs(self.preprocessing)}
            )
            try:
                raw = outputs[self.compiled_model.outputs[0]]
            except Exception:
                raw = next(iter(outputs.values()))
            # The reused request rewrites this buffer on its next inference, so
            # the caller must own a copy.
            return np.array(raw)

    def _infer_logits(
        self,
        image: Image.Image,
        *,
        input_tensor: np.ndarray | None = None,
    ) -> np.ndarray:
        raw = self._infer_output_tensor(image, input_tensor=input_tensor)
        if raw.ndim > 0 and raw.shape[0] == 1:
            return raw[0]
        return raw

    def classify(self, image: Image.Image, top_k: int = 5, input_context: Any | None = None) -> list[dict]:
        if not self.loaded or self.compiled_model is None:
            log.warning(f"{self.name} OpenVINO model not loaded, cannot classify")
            return []
        try:
            input_tensor = self._preprocess(image)
            logits = self._infer_logits(image, input_tensor=input_tensor)
            if logits.size == 0:
                return []
            probs = self._softmax(logits)
            if probs.size == 0:
                raise InvalidInferenceOutputError(
                    backend="openvino",
                    provider=self.device_name,
                    detail=f"{self.name} inference produced no finite probabilities",
                    diagnostics=self._collect_runtime_diagnostics(
                        input_tensor=input_tensor,
                        logits=logits,
                    ),
                )
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
        except InvalidInferenceOutputError:
            raise
        except Exception as e:
            log.error(f"OpenVINO inference failed for {self.name}", error=str(e), device=self.device_name)
            raise InvalidInferenceOutputError(
                backend="openvino",
                provider=str(self.device_name),
                detail=f"{self.name} runtime exception: {summarize_runtime_exception(e)}",
            ) from e

    def classify_raw(self, image: Image.Image) -> np.ndarray:
        if not self.loaded or self.compiled_model is None:
            return np.array([])
        try:
            input_tensor = self._preprocess(image)
            logits = self._infer_logits(image, input_tensor=input_tensor)
            if logits.size == 0:
                return np.array([])
            probs = self._softmax(logits)
            if probs.size == 0:
                raise InvalidInferenceOutputError(
                    backend="openvino",
                    provider=self.device_name,
                    detail=f"{self.name} inference produced no finite probabilities",
                    diagnostics=self._collect_runtime_diagnostics(
                        input_tensor=input_tensor,
                        logits=logits,
                    ),
                )
            return probs
        except InvalidInferenceOutputError:
            raise
        except Exception as e:
            log.error("OpenVINO raw classification failed", error=str(e), device=self.device_name)
            raise InvalidInferenceOutputError(
                backend="openvino",
                provider=str(self.device_name),
                detail=f"{self.name} runtime exception: {summarize_runtime_exception(e)}",
            ) from e

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
            "grouped_labels_count": len(set(self.grouped_labels)) if self.grouped_labels else None,
            "enabled": self.compiled_model is not None,
            "model_path": self.model_path,
            "runtime": "openvino",
            "input_size": self.input_size,
            "device": self.device_name,
            "compile_properties": self.current_compile_properties(),
            "startup_self_test": self.startup_self_test_status(),
        }
