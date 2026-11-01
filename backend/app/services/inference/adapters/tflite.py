"""TFLite adapter: the bundled MobileNet path and any `.tflite` bird model."""

import os
import threading
from typing import Any, Optional

import numpy as np
import structlog
from PIL import Image

from app.config import settings
from app.services.inference import runtimes
from app.services.inference.errors import InvalidInferenceOutputError
from app.services.inference.outputs import (
    build_classification_results,
    check_catalogue_output_width,
    normalize_probability_vector,
    resolve_grouped_labels,
    resolve_model_labels,
    safe_softmax,
)
from app.services.inference.preprocessing import resize_with_preprocessing, resolve_interpolation
from app.services.native_crash_quarantine import artifact_digest

log = structlog.get_logger()


class ModelInstance:
    """Represents a loaded TFLite model with its labels."""

    def __init__(
        self,
        name: str,
        model_path: str,
        labels_path: str,
        preprocessing: Optional[dict] = None,
        label_grouping: Optional[dict] = None,
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
        self.interpreter = None
        self.labels: list[str] = []
        self.grouped_labels: list[str] = []
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

            self.labels, self.grouped_labels, label_source = resolve_model_labels(
                self.labels_path,
                self.label_grouping,
                model_sha256=self.model_sha256,
                context=self.name,
            )
            self._label_source = label_source
            if self.labels:
                log.info(f"Loaded {len(self.labels)} labels for {self.name}", label_source=label_source)

            if not os.path.exists(self.model_path):
                self.error = f"Model file not found: {self.model_path}"
                log.warning(f"{self.name} model not found", path=self.model_path)
                return False

            if runtimes.tflite is None:
                self.error = "TFLite runtime not installed"
                log.error("TFLite runtime not installed")
                return False

            try:
                self.interpreter = runtimes.tflite.Interpreter(model_path=self.model_path)
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
        processed = resize_with_preprocessing(
            image,
            max(int(target_width), int(target_height)),
            preprocessing=self.preprocessing,
            default_resize_mode="letterbox",
            default_padding_color=int(self.preprocessing.get("padding_color", 0) or 0),
        )
        if processed.size != (target_width, target_height):
            processed = processed.resize((target_width, target_height), resolve_interpolation(self.preprocessing))
        return np.array(processed, dtype=np.float32)

    def _run_inference(self, image: Image.Image) -> np.ndarray:
        """Internal method to run inference and return probability vector.

        Args:
            image: PIL Image to classify

        Returns:
            Normalized probability vector as numpy array
        """
        # Get expected input size from model
        input_details = self.input_details[0]
        input_shape = input_details["shape"]

        # Shape is typically [1, height, width, 3] for image models
        if len(input_shape) == 4:
            target_height, target_width = input_shape[1], input_shape[2]
        else:
            target_height, target_width = 300, 300  # Default fallback

        # Preprocess image
        input_data = self._preprocess_image(image, target_width, target_height)

        # Normalize based on model input type
        raw_input_dtype = input_details.get("dtype")
        input_dtype = (
            raw_input_dtype
            if isinstance(raw_input_dtype, np.dtype)
            else np.dtype(raw_input_dtype)
            if isinstance(raw_input_dtype, type) and issubclass(raw_input_dtype, np.generic)
            else None
        )
        if input_dtype == np.dtype(np.float32):
            spec_mean = self.preprocessing.get("mean")
            spec_std = self.preprocessing.get("std")
            if spec_mean is not None or spec_std is not None:
                # Use per-channel mean/std provided in the model spec (ImageNet-style)
                mean = np.array(spec_mean if spec_mean is not None else [0.485, 0.456, 0.406], dtype=np.float32)
                std = np.array(spec_std if spec_std is not None else [0.229, 0.224, 0.225], dtype=np.float32)
                input_data = (input_data / 255.0 - mean) / std
            else:
                # Legacy MobileNet-style: maps [0, 255] to [-1, 1] via (x / 127.5) - 1
                input_data = (input_data - 127.5) / 127.5
        elif input_dtype is not None and np.issubdtype(input_dtype, np.integer):
            normalization = str(self.preprocessing.get("normalization") or "uint8").strip().lower()
            real_input = input_data
            if normalization not in {"uint8", "none"}:
                spec_mean = self.preprocessing.get("mean")
                spec_std = self.preprocessing.get("std")
                if spec_mean is not None or spec_std is not None:
                    mean = np.array(
                        spec_mean if spec_mean is not None else [0.485, 0.456, 0.406],
                        dtype=np.float32,
                    )
                    std = np.array(
                        spec_std if spec_std is not None else [0.229, 0.224, 0.225],
                        dtype=np.float32,
                    )
                    real_input = (real_input / 255.0 - mean) / std
                elif normalization in {"float32_0_1", "0_1"}:
                    real_input = real_input / 255.0
                else:
                    real_input = (real_input - 127.5) / 127.5

            quant_params = input_details.get("quantization_parameters", {})
            scales = np.asarray(quant_params.get("scales", []), dtype=np.float32)
            zero_points = np.asarray(quant_params.get("zero_points", []), dtype=np.float32)
            if normalization in {"uint8", "none"} and input_dtype == np.dtype(np.uint8):
                # A uint8 model reads the RGB bytes as its quantized input; its scale and zero point
                # describe what they mean, not a conversion still to apply. Quantizing them again
                # (scale 1/128, zero point 128 on the bundled MobileNet) saturated the image to white.
                input_data = np.clip(real_input, 0, 255).astype(np.uint8)
            elif scales.size > 0 and float(scales[0]) > 0:
                zero_point = float(zero_points[0]) if zero_points.size > 0 else 0.0
                quantized = np.rint(real_input / float(scales[0]) + zero_point)
                limits = np.iinfo(input_dtype)
                input_data = np.clip(quantized, limits.min, limits.max).astype(input_dtype)
            elif input_dtype == np.dtype(np.uint8):
                # Compatibility for older uint8 models that omit quantization
                # metadata and directly consume raw RGB bytes.
                input_data = np.clip(real_input, 0, 255).astype(np.uint8)
            else:
                raise InvalidInferenceOutputError(
                    backend="tflite",
                    provider="tflite",
                    detail=f"{self.name} int8 input is missing valid quantization metadata",
                )

        # Add batch dimension
        input_data = np.expand_dims(input_data, axis=0)

        # Run inference protected by lock
        with self._lock:
            self.interpreter.set_tensor(input_details["index"], input_data)
            self.interpreter.invoke()

            # Get output
            output_details = self.output_details[0]
            output_data = self.interpreter.get_tensor(output_details["index"])

        results = np.squeeze(output_data).astype(np.float32)

        # Dequantize if needed
        raw_output_dtype = output_details.get("dtype")
        output_dtype = (
            raw_output_dtype
            if isinstance(raw_output_dtype, np.dtype)
            else np.dtype(raw_output_dtype)
            if isinstance(raw_output_dtype, type) and issubclass(raw_output_dtype, np.generic)
            else None
        )
        if output_dtype is not None and np.issubdtype(output_dtype, np.integer):
            quant_params = output_details.get("quantization_parameters", {})
            scales = np.asarray(quant_params.get("scales", []), dtype=np.float32)
            zero_points = np.asarray(quant_params.get("zero_points", []), dtype=np.float32)

            if scales.size == results.size and results.ndim == 1:
                zero_values = zero_points if zero_points.size == results.size else np.zeros_like(scales)
                results = (results - zero_values) * scales
            elif scales.size > 0 and float(scales[0]) > 0:
                zero_point = float(zero_points[0]) if zero_points.size > 0 else 0.0
                results = (results - zero_point) * float(scales[0])
            elif output_dtype == np.dtype(np.uint8):
                results = results / 255.0
            else:
                raise InvalidInferenceOutputError(
                    backend="tflite",
                    provider="tflite",
                    detail=f"{self.name} int8 output is missing valid quantization metadata",
                )

        check_catalogue_output_width(self.labels, results.size, getattr(self, "_label_source", "none"))
        # Softmax if needed (logits vs probabilities)
        finite_results = results[np.isfinite(results)]
        if finite_results.size == 0:
            log.warning("TFLite inference produced no finite outputs", model=self.name)
            raise InvalidInferenceOutputError(
                backend="tflite",
                provider="tflite",
                detail=f"{self.name} inference produced no finite outputs",
            )

        output_min = float(finite_results.min())
        output_max = float(finite_results.max())
        is_probability = output_min >= 0 and output_max <= 1.0

        if is_probability:
            results = normalize_probability_vector(results, context=f"{self.name}:tflite")
        else:
            results = safe_softmax(results, context=f"{self.name}:tflite")

        return results

    def classify(self, image: Image.Image, input_context: Any | None = None) -> list[dict]:
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

        max_results = settings.classification.max_classification_results
        grouped_labels = resolve_grouped_labels(
            self.labels,
            label_grouping=self.label_grouping,
            existing_grouped_labels=self.grouped_labels,
        )
        return build_classification_results(
            results,
            self.labels,
            top_k=max_results,
            grouped_labels=grouped_labels,
        )

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
            "grouped_labels_count": len(set(self.grouped_labels)) if self.grouped_labels else None,
            "enabled": self.interpreter is not None,
            "model_path": self.model_path,
            "runtime": "tflite",
        }
