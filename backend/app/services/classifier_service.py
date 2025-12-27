import structlog
import numpy as np
import os
from PIL import Image, ImageOps
from typing import Optional
try:
    # Try importing typical TFLite runtimes
    import tflite_runtime.interpreter as tflite
except ImportError:
    try:
        import tensorflow.lite as tflite
    except ImportError:
        tflite = None

from app.config import settings

log = structlog.get_logger()

# Global singleton instance
_classifier_instance: Optional['ClassifierService'] = None


def get_classifier() -> 'ClassifierService':
    """Get the shared classifier service instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = ClassifierService()
    return _classifier_instance


class ModelInstance:
    """Represents a loaded TFLite model with its labels."""

    def __init__(self, name: str, model_path: str, labels_path: str):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.interpreter = None
        self.labels: list[str] = []
        self.loaded = False
        self.error: Optional[str] = None
        self.input_details = None
        self.output_details = None

    def load(self) -> bool:
        """Load the model and labels. Returns True if successful."""
        if self.loaded:
            return True

        # Load labels first
        if os.path.exists(self.labels_path):
            try:
                with open(self.labels_path, 'r') as f:
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

    def classify(self, image: Image.Image) -> list[dict]:
        """Classify an image using this model.

        Preprocessing for EfficientNet-Lite4:
        - Input: 300x300 (or model-specified size) RGB float32
        - Normalization: (pixel - 127) / 128 → range [-1, 1]
        - Output: Apply softmax to convert logits to probabilities
        """
        if not self.loaded or not self.interpreter:
            log.warning(f"{self.name} model not loaded, cannot classify")
            return []

        # Get expected input size from model
        input_details = self.input_details[0]
        input_shape = input_details['shape']

        # Shape is typically [1, height, width, 3] for image models
        if len(input_shape) == 4:
            target_height, target_width = input_shape[1], input_shape[2]
        else:
            target_height, target_width = 300, 300  # EfficientNet-Lite4 default

        log.info(f"{self.name} classify: input image mode={image.mode}, size={image.size}, "
                 f"target={target_width}x{target_height}, model_dtype={input_details['dtype']}")

        # Step 1: Convert to RGB (handles RGBA, grayscale, palette, etc.)
        image = image.convert('RGB')

        # Step 2: Resize to exact target size using high-quality resampling
        image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)

        # Step 3: Convert to numpy array (uint8, range 0-255)
        input_data = np.array(image, dtype=np.float32)

        # Step 4: Normalize based on model input type
        if input_details['dtype'] == np.float32:
            # EfficientNet-Lite normalization: (pixel - 127) / 128 → range [-1, 1]
            input_data = (input_data - 127.0) / 128.0
            log.debug(f"{self.name}: Normalized to [-1,1], range=[{input_data.min():.2f}, {input_data.max():.2f}]")
        elif input_details['dtype'] == np.uint8:
            # Quantized models: keep as uint8
            input_data = np.array(image, dtype=np.uint8)

        # Step 5: Add batch dimension - shape becomes (1, height, width, 3)
        input_data = np.expand_dims(input_data, axis=0)

        log.debug(f"{self.name}: input_data shape={input_data.shape}, dtype={input_data.dtype}")

        # Run inference
        self.interpreter.set_tensor(input_details['index'], input_data)
        self.interpreter.invoke()

        # Get output
        output_details = self.output_details[0]
        output_data = self.interpreter.get_tensor(output_details['index'])

        log.debug(f"{self.name}: output shape={output_data.shape}, dtype={output_data.dtype}")

        # Process output
        results = np.squeeze(output_data).astype(np.float32)

        # Dequantize if output is uint8
        if output_details['dtype'] == np.uint8:
            quant_params = output_details.get('quantization_parameters', {})
            scales = quant_params.get('scales', None)
            zero_points = quant_params.get('zero_points', None)

            if scales is not None and len(scales) > 0:
                scale = scales[0]
                zero_point = zero_points[0] if zero_points is not None and len(zero_points) > 0 else 0
                results = (results - zero_point) * scale
                log.debug(f"{self.name}: dequantized with scale={scale}, zero_point={zero_point}")
            else:
                results = results / 255.0

        # Check if output is already probabilities vs logits
        # Probabilities: all values >= 0, max <= 1.0, sum close to 1.0
        # Logits: can have negative values, or values > 2-3, sum is arbitrary
        output_sum = float(results.sum())
        output_min = float(results.min())
        output_max = float(results.max())
        log.info(f"{self.name}: Raw output stats - min={output_min:.6f}, max={output_max:.6f}, sum={output_sum:.6f}")

        # Detect if output looks like probabilities (post-softmax)
        # - All values are non-negative
        # - Max value is reasonable for a probability (< 1.5 to allow for quantization error)
        # - Sum is somewhat close to 1.0 (0.8 to 1.2 to allow for quantization error)
        is_probability = output_min >= 0 and output_max < 1.5 and 0.8 < output_sum < 1.2

        if is_probability:
            # Already probabilities, just normalize to ensure they sum to 1.0
            # This handles quantization error without applying softmax
            if abs(output_sum - 1.0) > 0.001:
                log.info(f"{self.name}: Normalizing probabilities (sum={output_sum:.4f})")
                results = results / output_sum
            else:
                log.info(f"{self.name}: Output is probabilities (sum={output_sum:.4f}), no adjustment needed")
        else:
            # Logits - apply softmax to convert to probabilities
            log.info(f"{self.name}: Applying softmax to logits (sum was {output_sum:.4f})")
            exp_results = np.exp(results - np.max(results))
            results = exp_results / np.sum(exp_results)
            log.info(f"{self.name}: After softmax - max={float(results.max()):.6f}")

        # Get top-5 predictions
        top_k = results.argsort()[-5:][::-1]

        classifications = []
        for i in top_k:
            score = float(results[i])
            label = self.labels[i] if i < len(self.labels) else f"Class {i}"
            classifications.append({
                "index": int(i),
                "score": score,
                "label": label
            })

        top_results = [(c['label'], f"{c['score']*100:.1f}%") for c in classifications[:3]]
        log.info(f"{self.name} classify results: {top_results}")

        return classifications

    def get_status(self) -> dict:
        """Return the current status of this model."""
        return {
            "loaded": self.loaded,
            "error": self.error,
            "labels_count": len(self.labels),
            "enabled": self.interpreter is not None,
            "model_path": self.model_path,
        }


class ClassifierService:
    """Service for managing multiple classification models."""

    def __init__(self):
        self._models: dict[str, ModelInstance] = {}
        self._init_bird_model()

    def _get_model_paths(self, model_file: str, labels_file: str) -> tuple[str, str]:
        """Get full paths for model and labels files."""
        persistent_dir = "/data/models"
        fallback_dir = os.path.join(os.path.dirname(__file__), "../assets")

        # Check persistent location first
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
        model_path, labels_path = self._get_model_paths(
            settings.classification.model,
            "labels.txt"
        )

        bird_model = ModelInstance("bird", model_path, labels_path)
        bird_model.load()  # Load immediately for bird model
        self._models["bird"] = bird_model

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

    # Legacy properties for backwards compatibility
    @property
    def interpreter(self):
        return self._models.get("bird", ModelInstance("", "", "")).interpreter

    @property
    def labels(self) -> list[str]:
        return self._models.get("bird", ModelInstance("", "", "")).labels

    @property
    def model_loaded(self) -> bool:
        return self._models.get("bird", ModelInstance("", "", "")).loaded

    @property
    def model_error(self) -> Optional[str]:
        return self._models.get("bird", ModelInstance("", "", "")).error

    def get_status(self) -> dict:
        """Return the current status of the bird classifier (legacy)."""
        bird = self._models.get("bird")
        if bird:
            return bird.get_status()
        return {
            "loaded": False,
            "error": "Bird model not initialized",
            "labels_count": 0,
            "enabled": False,
        }

    def get_wildlife_status(self) -> dict:
        """Return the current status of the wildlife classifier."""
        wildlife = self._models.get("wildlife")
        if wildlife:
            return wildlife.get_status()

        # Check if model file exists without loading
        model_path, labels_path = self._get_model_paths(
            settings.classification.wildlife_model,
            settings.classification.wildlife_labels
        )

        model_exists = os.path.exists(model_path)
        labels_exist = os.path.exists(labels_path)

        # Count labels if file exists
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
        """Classify an image using the bird model (legacy method)."""
        bird = self._models.get("bird")
        if bird:
            return bird.classify(image)
        return []

    def classify_wildlife(self, image: Image.Image) -> list[dict]:
        """Classify an image using the wildlife model."""
        wildlife = self._get_wildlife_model()
        return wildlife.classify(image)

    def get_wildlife_labels(self) -> list[str]:
        """Get the list of wildlife labels."""
        wildlife = self._get_wildlife_model()
        return wildlife.labels
