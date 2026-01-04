import structlog
import numpy as np
import os
import cv2
import asyncio
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
        # Optional: Add custom mean/std logic from self.preprocessing if needed
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

        # Get all predictions for aggregation
        classifications = []
        for i, score in enumerate(results):
            label = self.labels[i] if i < len(self.labels) else f"Class {i}"
            classifications.append({
                "index": int(i),
                "score": float(score),
                "label": label
            })
        
        classifications.sort(key=lambda x: x['score'], reverse=True)
        return classifications[:5]

    def classify_raw(self, image: Image.Image) -> np.ndarray:
        """Classify and return the raw probability vector (for ensemble)."""
        if not self.loaded or not self.interpreter:
            return np.array([])

        # Reuse logic from classify, but return raw results array
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
        
        with self._lock:
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
            "runtime": "tflite",
        }


class ONNXModelInstance:
    """Represents a loaded ONNX model with its labels (for high-accuracy models)."""

    def __init__(self, name: str, model_path: str, labels_path: str, preprocessing: Optional[dict] = None, input_size: int = 384):
        self.name = name
        self.model_path = model_path
        self.labels_path = labels_path
        self.preprocessing = preprocessing or {}
        self.input_size = input_size
        self.session = None
        self.labels: list[str] = []
        self.loaded = False
        self.error: Optional[str] = None

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

            self.session = ort.InferenceSession(
                self.model_path,
                sess_options,
                providers=['CPUExecutionProvider']
            )
            self.loaded = True
            self.error = None
            log.info(f"{self.name} ONNX model loaded successfully", input_size=self.input_size)
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
            outputs = self.session.run(None, {input_name: input_tensor})
            logits = outputs[0][0]
            return self._softmax(logits)
        except Exception as e:
            log.error("ONNX raw classification failed", error=str(e))
            return np.array([])

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


class ClassifierService:
    """Service for managing multiple classification models (TFLite and ONNX)."""

    # Union type for model instances
    ModelType = ModelInstance | ONNXModelInstance

    def __init__(self):
        self._models: dict[str, ModelInstance | ONNXModelInstance] = {}
        # Dedicated executor for ML tasks to avoid blocking default executor
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ml_worker")
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

        # Create appropriate model instance based on runtime
        if runtime == 'onnx':
            if not ONNX_AVAILABLE:
                log.error("ONNX model requested but onnxruntime not installed, falling back to TFLite")
                runtime = 'tflite'
            else:
                bird_model = ONNXModelInstance(
                    "bird",
                    model_path,
                    labels_path,
                    preprocessing=preprocessing,
                    input_size=input_size
                )
                bird_model.load()
                self._models["bird"] = bird_model
                return

        # Default: TFLite model
        bird_model = ModelInstance("bird", model_path, labels_path, preprocessing=preprocessing)
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
                }
            },
            "models": {
                name: {
                    "loaded": model.loaded,
                    "runtime": "onnx" if isinstance(model, ONNXModelInstance) else "tflite",
                    "error": model.error
                } for name, model in self._models.items()
            }
        }

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
        status = {
            "runtime": "tflite-runtime" if "tflite_runtime" in str(tflite) else "tensorflow",
            "runtime_installed": tflite is not None,
            "models": {}
        }
        
        for name, model in self._models.items():
            status["models"][name] = model.get_status()
            
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
            del self._models["wildlife"]
            log.info("Cleared cached wildlife model instance")
        try:
            self._get_wildlife_model()
            log.info("Reloaded wildlife model")
        except Exception as e:
            log.error("Failed to reload wildlife model", error=str(e))

    def classify_video(self, video_path: str, stride: int = 5, max_frames: int = 15, progress_callback=None) -> list[dict]:
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
        bird_model = self._models.get("bird")
        if not bird_model or not bird_model.loaded:
            log.error("Bird model not loaded for video classification")
            return []

        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                log.error(f"Could not open video file: {video_path}")
                return []

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            if total_frames <= 0:
                log.warning("Video has no frames", path=video_path)
                cap.release()
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

                        progress_callback(
                            current_frame=len(all_scores),
                            total_frames=len(frame_indices),
                            frame_score=top_score,
                            top_label=top_label
                        )

            cap.release()

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

    async def classify_video_async(self, video_path: str, stride: int = 5, max_frames: int = 15, progress_callback=None) -> list[dict]:
        """Async wrapper for video classification."""
        loop = asyncio.get_running_loop()

        # Wrap the callback to make it thread-safe
        if progress_callback:
            def sync_callback(current_frame, total_frames, frame_score, top_label):
                # Schedule the async callback in the event loop from the executor thread
                asyncio.run_coroutine_threadsafe(
                    progress_callback(current_frame, total_frames, frame_score, top_label),
                    loop
                )
            return await loop.run_in_executor(self._executor, self.classify_video, video_path, stride, max_frames, sync_callback)
        else:
            return await loop.run_in_executor(self._executor, self.classify_video, video_path, stride, max_frames, None)
