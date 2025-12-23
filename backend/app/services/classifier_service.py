import structlog
import numpy as np
import os
from PIL import Image, ImageOps
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

class ClassifierService:
    def __init__(self):
        self.interpreter = None
        self.labels = []
        self.model_loaded = False
        self.model_error: str | None = None
        self._load_model()

    def get_status(self) -> dict:
        """Return the current status of the classifier."""
        return {
            "loaded": self.model_loaded,
            "error": self.model_error,
            "labels_count": len(self.labels),
            "enabled": self.interpreter is not None,
        }

    def _load_model(self):
        assets_dir = os.path.join(os.path.dirname(__file__), "../assets")
        model_path = os.path.join(assets_dir, settings.classification.model)
        labels_path = os.path.join(assets_dir, "labels.txt")

        # Load labels
        if os.path.exists(labels_path):
            try:
                with open(labels_path, 'r') as f:
                    self.labels = [line.strip() for line in f.readlines() if line.strip()]
                log.info(f"Loaded {len(self.labels)} labels")
            except Exception as e:
                log.error("Failed to load labels", error=str(e))

        if not os.path.exists(model_path):
            self.model_error = f"Model file not found: {model_path}"
            log.warning("Model file not found - classification disabled. Run 'python download_model.py' to download.", path=model_path)
            return

        if tflite is None:
            self.model_error = "TFLite runtime not installed"
            log.error("TFLite runtime not installed, classifier disabled")
            return

        try:
            self.interpreter = tflite.Interpreter(model_path=model_path)
            self.interpreter.allocate_tensors()

            # Get input and output details
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()

            self.model_loaded = True
            self.model_error = None
            log.info("Model loaded successfully")
        except Exception as e:
            self.model_error = f"Failed to load model: {str(e)}"
            log.error("Failed to load model", error=str(e))

    def classify(self, image: Image.Image):
        if not self.interpreter:
            log.warning("Interpreter not loaded, returning empty classification")
            return []

        # Resize and preprocess image matching original logic
        # Resize maintaining aspect ratio
        max_size = (224, 224)
        image.thumbnail(max_size)
        
        # Pad to fill 224x224
        delta_w = max_size[0] - image.size[0]
        delta_h = max_size[1] - image.size[1]
        padding = (delta_w // 2, delta_h // 2, delta_w - (delta_w // 2), delta_h - (delta_h // 2))
        padded_image = ImageOps.expand(image, padding, fill='black')
        
        # Convert to numpy and normalize if needed (checking input details)
        input_data = np.expand_dims(padded_image, axis=0)
        
        # Check input type (uint8 or float32)
        input_details = self.input_details[0]
        if input_details['dtype'] == np.float32:
            input_data = (np.float32(input_data) - 127.5) / 127.5
        elif input_details['dtype'] == np.uint8:
            input_data = np.uint8(input_data)

        self.interpreter.set_tensor(input_details['index'], input_data)
        self.interpreter.invoke()
        
        output_details = self.output_details[0]
        output_data = self.interpreter.get_tensor(output_details['index'])
        
        # Process output (assuming classification output)
        results = np.squeeze(output_data)
        top_k = results.argsort()[-5:][::-1]
        
        classifications = []
        for i in top_k:
            score = float(results[i])
            if input_details['dtype'] == np.uint8:
                 score = score / 255.0 # Normalize if quantized
            
            label = self.labels[i] if i < len(self.labels) else f"Class {i}"

            classifications.append({
                "index": int(i),
                "score": score,
                "label": label
            })
            
        return classifications

