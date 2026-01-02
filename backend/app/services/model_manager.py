import json
import os
import shutil
import aiofiles
import httpx
import structlog
from typing import List, Optional, Dict
from app.config import settings
from app.models.ai_models import ModelMetadata, InstalledModel

log = structlog.get_logger()

# Hardcoded registry for now - in production this would fetch from a GitHub raw JSON
REMOTE_REGISTRY = [
    {
        "id": "mobilenet_v2_birds",
        "name": "MobileNet V2 (Standard)",
        "description": "The default lightweight model. Good balance of speed and accuracy for Raspberry Pi 3/4.",
        "architecture": "MobileNetV2",
        "file_size_mb": 3.4,
        "accuracy_tier": "Medium",
        "inference_speed": "Fast",
        "download_url": "https://raw.githubusercontent.com/google-coral/test_data/master/tf2_mobilenet_v2_1.0_224_ptq.tflite", # Placeholder/Example URL
        "labels_url": "https://raw.githubusercontent.com/google-coral/test_data/master/inat_bird_labels.txt", # Placeholder
        "input_size": 224
    },
    {
        "id": "efficientnet_lite4_birds",
        "name": "EfficientNet-Lite4 (High Res)",
        "description": "High accuracy model. Recommended for Pi 5, N100, or Desktop. Slower inference but better detail recognition.",
        "architecture": "EfficientNet-Lite4",
        "file_size_mb": 12.8,
        "accuracy_tier": "High",
        "inference_speed": "Slow",
        "download_url": "https://raw.githubusercontent.com/tensorflow/tflite-support/master/tensorflow_lite_support/metadata/python/tests/testdata/image_classifier/efficientnet_lite0.tflite", # Placeholder - using lite0 for test
        "labels_url": "https://storage.googleapis.com/download.tensorflow.org/data/ImageNetLabels.txt", # Placeholder
        "input_size": 300
    }
]

MODELS_DIR = "/data/models"

class ModelManager:
    def __init__(self):
        # Ensure models directory exists
        os.makedirs(MODELS_DIR, exist_ok=True)
        self.active_model_id = self._load_active_model_id()

    def _load_active_model_id(self) -> str:
        """Load the active model ID from a local config file."""
        config_path = os.path.join(MODELS_DIR, "active_model.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                    return data.get("active_model_id", "mobilenet_v2_birds")
            except Exception:
                return "mobilenet_v2_birds"
        return "mobilenet_v2_birds"

    def _save_active_model_id(self, model_id: str):
        """Save the active model ID."""
        config_path = os.path.join(MODELS_DIR, "active_model.json")
        with open(config_path, 'w') as f:
            json.dump({"active_model_id": model_id}, f)
        self.active_model_id = model_id

    async def list_available_models(self) -> List[ModelMetadata]:
        """Fetch list of available models from remote registry."""
        # In a real scenario, this would await httpx.get(REGISTRY_URL)
        return [ModelMetadata(**m) for m in REMOTE_REGISTRY]

    async def list_installed_models(self) -> List[InstalledModel]:
        """List models currently present in the models directory."""
        installed = []
        available = await self.list_available_models()
        available_map = {m.id: m for m in available}

        # Scan directory
        if os.path.exists(MODELS_DIR):
            for item in os.listdir(MODELS_DIR):
                model_dir = os.path.join(MODELS_DIR, item)
                if os.path.isdir(model_dir):
                    # Check for model file and labels
                    tflite_path = os.path.join(model_dir, "model.tflite")
                    labels_path = os.path.join(model_dir, "labels.txt")
                    
                    if os.path.exists(tflite_path):
                        metadata = available_map.get(item)
                        installed.append(InstalledModel(
                            id=item,
                            path=tflite_path,
                            labels_path=labels_path,
                            is_active=(item == self.active_model_id),
                            metadata=metadata
                        ))
        
        # Add default legacy model if it exists in the old location?
        # For now, we assume migration or new downloads.
        return installed

    async def download_model(self, model_id: str) -> bool:
        """Download a model from the registry."""
        model_meta = next((m for m in REMOTE_REGISTRY if m['id'] == model_id), None)
        if not model_meta:
            log.error("Model ID not found in registry", model_id=model_id)
            return False

        target_dir = os.path.join(MODELS_DIR, model_id)
        os.makedirs(target_dir, exist_ok=True)
        
        try:
            async with httpx.AsyncClient() as client:
                # Download TFLite
                log.info("Downloading model", url=model_meta['download_url'])
                resp = await client.get(model_meta['download_url'], follow_redirects=True)
                resp.raise_for_status()
                async with aiofiles.open(os.path.join(target_dir, "model.tflite"), 'wb') as f:
                    await f.write(resp.content)

                # Download Labels
                log.info("Downloading labels", url=model_meta['labels_url'])
                resp = await client.get(model_meta['labels_url'], follow_redirects=True)
                resp.raise_for_status()
                async with aiofiles.open(os.path.join(target_dir, "labels.txt"), 'wb') as f:
                    await f.write(resp.content)

            log.info("Model downloaded successfully", model_id=model_id)
            return True
        except Exception as e:
            log.error("Failed to download model", model_id=model_id, error=str(e))
            # Cleanup
            shutil.rmtree(target_dir, ignore_errors=True)
            return False

    async def activate_model(self, model_id: str) -> bool:
        """Set a model as active."""
        target_dir = os.path.join(MODELS_DIR, model_id)
        if not os.path.exists(target_dir):
             return False
        
        self._save_active_model_id(model_id)
        
        # Notify ClassifierService to reload (we'll implement this link in the router or service)
        return True

    def get_active_model_paths(self) -> tuple[str, str, int]:
        """Get the paths and input size for the currently active model."""
        model_id = self.active_model_id
        target_dir = os.path.join(MODELS_DIR, model_id)
        
        # Find metadata to get input size
        meta = next((m for m in REMOTE_REGISTRY if m['id'] == model_id), None)
        input_size = meta['input_size'] if meta else 224

        # Fallback to default/legacy if active not found
        if not os.path.exists(target_dir):
            # Fallback logic here? Or return defaults
            return "model.tflite", "labels.txt", 224
            
        return os.path.join(target_dir, "model.tflite"), os.path.join(target_dir, "labels.txt"), input_size

model_manager = ModelManager()
