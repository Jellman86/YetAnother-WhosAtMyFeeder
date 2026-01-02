import structlog
import numpy as np
import os
import cv2
import tempfile
import asyncio
from PIL import Image, ImageOps
from typing import Optional, List, Dict
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

        # Create new image with gray padding (common for EfficientNet, or black for others)
        # Using black (0) for generic approach as it works well with MobileNet too
        new_image = Image.new('RGB', (w, h), (0, 0, 0))
        
        # Paste resized image in center
        new_image.paste(image, ((w - nw) // 2, (h - nh) // 2))

        # Convert to numpy array
        input_data = np.array(new_image, dtype=np.float32)
        
        return input_data

    def classify(self, image: Image.Image) -> list[dict]:
        """Classify an image using this model."""
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
            target_height, target_width = 300, 300  # Default fallback

        log.debug(f"{self.name} classify: target={target_width}x{target_height}, dtype={input_details['dtype']}")

        # Preprocess
        input_data = self._preprocess_image(image, target_width, target_height)

        # Normalize based on model input type
        if input_details['dtype'] == np.float32:
            input_data = (input_data - 127.0) / 128.0
        elif input_details['dtype'] == np.uint8:
            input_data = input_data.astype(np.uint8)

        # Add batch dimension
        input_data = np.expand_dims(input_data, axis=0)

        # Run inference
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

        # Get all predictions for aggregation
        classifications = []
        for i, score in enumerate(results):
            label = self.labels[i] if i < len(self.labels) else f"Class {i}"
            classifications.append({
                "index": int(i),
                "score": float(score),
                "label": label
            })
        
        # Sort for logging but return all for ensemble logic if needed
        # Actually, returning top-k is usually enough, but for ensemble we might want full vector.
        # For simplicity and compat with existing API, let's return sorted top-k.
        # But wait, for video ensemble we want to sum scores. 
        # Ideally we return the full result vector or a large top-k.
        
        # Let's return sorted top-10 for standard usage, but sorted list.
        # For video aggregation we might call this differently?
        # Actually, let's just return sorted top-5 as usual for external consumers.
        # Internal aggregation will need raw scores. 
        # Refactoring to return raw scores is risky for existing consumers.
        
        # Let's just return the sorted list as usual.
        classifications.sort(key=lambda x: x['score'], reverse=True)
        return classifications[:5]

    def classify_raw(self, image: Image.Image) -> np.ndarray:
        """Classify and return the raw probability vector (for ensemble)."""
        if not self.loaded or not self.interpreter:
            return np.array([])

        # Reuse logic from classify, but return raw results array
        # Duplication is minor here to avoid breaking `classify` API
        input_details = self.input_details[0]
        input_shape = input_details['shape']
        if len(input_shape) == 4:
            target_height, target_width = input_shape[1], input_shape[2]
        else:
            target_height, target_width = 300, 300

        input_data = self._preprocess_image(image, target_width, target_height)
        
        if input_details['dtype'] == np.float32:
            input_data = (input_data - 127.0) / 128.0
        elif input_details['dtype'] == np.uint8:
            input_data = input_data.astype(np.uint8)
            
        input_data = np.expand_dims(input_data, axis=0)
        self.interpreter.set_tensor(input_details['index'], input_data)
        self.interpreter.invoke()
        
        output_details = self.output_details[0]
        output_data = self.interpreter.get_tensor(output_details['index'])
        results = np.squeeze(output_data).astype(np.float32)

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
        from app.services.model_manager import model_manager
        model_path, labels_path, input_size = model_manager.get_active_model_paths()
        
        if not os.path.exists(model_path):
             model_path, labels_path = self._get_model_paths(
                settings.classification.model,
                "labels.txt"
             )

        log.info("Initializing bird model", path=model_path, input_size=input_size)
        bird_model = ModelInstance("bird", model_path, labels_path)
        bird_model.load()
        self._models["bird"] = bird_model

    def reload_bird_model(self):
        """Reload the bird model (e.g., after switching models)."""
        if "bird" in self._models:
            del self._models["bird"]
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

    # Legacy properties
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
        return await loop.run_in_executor(None, self.classify, image)

    def classify_wildlife(self, image: Image.Image) -> list[dict]:
        """Classify an image using the wildlife model."""
        wildlife = self._get_wildlife_model()
        return wildlife.classify(image)

    async def classify_wildlife_async(self, image: Image.Image) -> list[dict]:
        """Async wrapper for wildlife classification."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.classify_wildlife, image)

    def get_wildlife_labels(self) -> list[str]:
        wildlife = self._get_wildlife_model()
        return wildlife.labels

    def reload_wildlife_model(self):
        if "wildlife" in self._models:
            del self._models["wildlife"]
            log.info("Cleared cached wildlife model instance")
        try:
            self._get_wildlife_model()
            log.info("Reloaded wildlife model")
        except Exception as e:
            log.error("Failed to reload wildlife model", error=str(e))

    def classify_video(self, video_path: str, stride: int = 5, max_frames: int = 15) -> list[dict]:
        """
        Classify a video clip using Temporal Ensemble (Soft Voting).
        
        Args:
            video_path: Path to the video file.
            stride: Process every Nth frame.
            max_frames: Maximum number of frames to process to limit latency.
            
        Returns:
            List of classifications with aggregated scores.
        """
        bird_model = self._models.get("bird")
        if not bird_model or not bird_model.loaded:
            log.error("Bird model not loaded for video classification")
            return []

        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                log.error(f"Could not open video file: {video_path}")
                return []

            frame_count = 0
            processed_count = 0
            cumulative_scores = None # Will be initialized on first valid frame

            while processed_count < max_frames:
                ret, frame = cap.read()
                if not ret:
                    break

                # Process every 'stride' frames
                if frame_count % stride == 0:
                    # Convert BGR (OpenCV) to RGB (PIL)
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image = Image.fromarray(frame_rgb)
                    
                    # Get raw probability vector
                    scores = bird_model.classify_raw(image)
                    
                    if len(scores) > 0:
                        if cumulative_scores is None:
                            cumulative_scores = scores
                        else:
                            # Accumulate scores (Soft Voting)
                            # Ensure dimensions match (they should if model doesn't change)
                            if len(scores) == len(cumulative_scores):
                                cumulative_scores += scores
                        
                        processed_count += 1

                frame_count += 1

            cap.release()

            if cumulative_scores is None:
                log.warning("No frames processed from video")
                return []

            # Normalize aggregated scores
            if processed_count > 0:
                cumulative_scores = cumulative_scores / processed_count

            # Create standard classification list from aggregated scores
            top_k = cumulative_scores.argsort()[-5:][::-1]
            
            classifications = []
            for i in top_k:
                score = float(cumulative_scores[i])
                label = bird_model.labels[i] if i < len(bird_model.labels) else f"Class {i}"
                classifications.append({
                    "index": int(i),
                    "score": score,
                    "label": label
                })
            
            log.info(f"Video classification complete. Processed {processed_count} frames.", 
                     top_result=classifications[0]['label'] if classifications else None)
            
            return classifications

        except Exception as e:
            log.error("Error during video classification", error=str(e))
            return []

    async def classify_video_async(self, video_path: str, stride: int = 5, max_frames: int = 15) -> list[dict]:
        """Async wrapper for video classification."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.classify_video, video_path, stride, max_frames)