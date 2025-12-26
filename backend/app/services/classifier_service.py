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
        """Classify an image using this model."""
        if not self.loaded or not self.interpreter:
            log.warning(f"{self.name} model not loaded, cannot classify")
            return []

        # Get expected input size from model (supports different models like 224x224, 300x300)
        input_details = self.input_details[0]
        input_shape = input_details['shape']
        # Shape is typically [1, height, width, 3] for image models
        if len(input_shape) == 4:
            target_height, target_width = input_shape[1], input_shape[2]
        else:
            target_height, target_width = 224, 224  # Fallback

        log.debug(f"{self.name} classify: input image mode={image.mode}, size={image.size}")

        # CRITICAL: Convert to RGB mode first (handles RGBA, grayscale, palette, etc.)
        image = image.convert('RGB')

        # Resize to exact target size (not thumbnail which preserves aspect ratio)
        # Using LANCZOS for high-quality downsampling
        image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)

        # Convert to numpy array - shape will be (height, width, 3)
        input_data = np.array(image, dtype=np.uint8)

        # Add batch dimension - shape becomes (1, height, width, 3)
        input_data = np.expand_dims(input_data, axis=0)

        log.debug(f"{self.name} classify: input_data shape={input_data.shape}, dtype={input_data.dtype}")

        # Handle input type conversion
        if input_details['dtype'] == np.float32:
            # Float models: normalize to [-1, 1] range (MobileNet style)
            input_data = (np.float32(input_data) - 127.5) / 127.5
        elif input_details['dtype'] == np.uint8:
            # Quantized models: use raw uint8 pixel values [0, 255]
            input_data = np.uint8(input_data)

        self.interpreter.set_tensor(input_details['index'], input_data)
        self.interpreter.invoke()

        output_details = self.output_details[0]
        output_data = self.interpreter.get_tensor(output_details['index'])

        log.debug(f"{self.name} classify: output shape={output_data.shape}, dtype={output_data.dtype}")

        # Process output - handle quantized outputs properly
        results = np.squeeze(output_data).astype(np.float32)

        # Dequantize output if needed (check OUTPUT dtype, not input)
        if output_details['dtype'] == np.uint8:
            # Get quantization parameters from output details
            quant_params = output_details.get('quantization_parameters', {})
            scales = quant_params.get('scales', None)
            zero_points = quant_params.get('zero_points', None)

            log.debug(f"{self.name} classify: output quant params scales={scales}, zero_points={zero_points}")

            if scales is not None and len(scales) > 0:
                # Proper dequantization: real_value = (quantized - zero_point) * scale
                scale = scales[0]
                zero_point = zero_points[0] if zero_points is not None and len(zero_points) > 0 else 0
                results = (results - zero_point) * scale
                log.debug(f"{self.name} classify: dequantized with scale={scale}, zero_point={zero_point}")
            else:
                # Fallback: simple normalization to [0, 1]
                results = results / 255.0
                log.debug(f"{self.name} classify: fallback normalization (div 255)")

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

        top_results = [(c['label'], round(c['score'], 3)) for c in classifications[:3]]
        log.info(f"{self.name} classify: top results: {top_results}")

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
