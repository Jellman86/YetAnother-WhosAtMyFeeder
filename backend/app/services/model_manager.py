import json
import os
import shutil
import aiofiles
import httpx
import structlog
from typing import List, Optional, Dict
from app.config import settings
from app.models.ai_models import ModelMetadata, InstalledModel, DownloadProgress

log = structlog.get_logger()

# Real TFLite models
REMOTE_REGISTRY = [
    {
        "id": "mobilenet_v2_birds",
        "name": "MobileNet V2 (Standard)",
        "description": "Default lightweight bird classifier. Balanced for speed on edge devices.",
        "architecture": "MobileNetV2",
        "file_size_mb": 3.4,
        "accuracy_tier": "Medium",
        "inference_speed": "Fast",
        "download_url": "https://raw.githubusercontent.com/google-coral/test_data/master/tf2_mobilenet_v2_1.0_224_ptq.tflite",
        "labels_url": "https://raw.githubusercontent.com/google-coral/test_data/master/inat_bird_labels.txt",
        "input_size": 224
    },
    {
        "id": "efficientnet_lite4_birds",
        "name": "EfficientNet-Lite4 (High Res)",
        "description": "High precision bird classifier. Best for detailed recognition on powerful hardware.",
        "architecture": "EfficientNet-Lite4",
        "file_size_mb": 13.0,
        "accuracy_tier": "High",
        "inference_speed": "Slow",
        "download_url": "https://raw.githubusercontent.com/tensorflow/tflite-support/master/tensorflow_lite_support/metadata/python/tests/testdata/image_classifier/efficientnet_lite4.tflite",
        "labels_url": "https://storage.googleapis.com/download.tensorflow.org/data/ImageNetLabels.txt",
        "input_size": 300
    }
]

MODELS_DIR = "/data/models"

class ModelManager:
    def __init__(self):
        # Ensure models directory exists
        os.makedirs(MODELS_DIR, exist_ok=True)
        self.active_model_id = self._load_active_model_id()
        self.active_downloads: Dict[str, DownloadProgress] = {}

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
        return installed

    def get_download_status(self, model_id: str) -> Optional[DownloadProgress]:
        return self.active_downloads.get(model_id)

    async def download_model(self, model_id: str) -> bool:
        """Download a model from the registry."""
        model_meta = next((m for m in REMOTE_REGISTRY if m['id'] == model_id), None)
        if not model_meta:
            log.error("Model ID not found in registry", model_id=model_id)
            return False

        # Initialize progress
        self.active_downloads[model_id] = DownloadProgress(
            model_id=model_id,
            status="downloading",
            progress=0.0
        )

        target_dir = os.path.join(MODELS_DIR, model_id)
        os.makedirs(target_dir, exist_ok=True)
        
        try:
            async with httpx.AsyncClient() as client:
                # 1. Download TFLite
                log.info("Downloading model", url=model_meta['download_url'])
                async with client.stream("GET", model_meta['download_url'], follow_redirects=True) as response:
                    response.raise_for_status()
                    total = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    async with aiofiles.open(os.path.join(target_dir, "model.tflite"), 'wb') as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                self.active_downloads[model_id].progress = (downloaded / total) * 90 # Model is 90% of total job

                # 2. Download Labels
                log.info("Downloading labels", url=model_meta['labels_url'])
                resp = await client.get(model_meta['labels_url'], follow_redirects=True)
                resp.raise_for_status()
                async with aiofiles.open(os.path.join(target_dir, "labels.txt"), 'wb') as f:
                    await f.write(resp.content)
                
                self.active_downloads[model_id].progress = 100.0
                self.active_downloads[model_id].status = "completed"

            log.info("Model downloaded successfully", model_id=model_id)
            return True
        except Exception as e:
            log.error("Failed to download model", model_id=model_id, error=str(e))
            if model_id in self.active_downloads:
                self.active_downloads[model_id].status = "error"
                self.active_downloads[model_id].error = str(e)
            shutil.rmtree(target_dir, ignore_errors=True)
            return False

    async def activate_model(self, model_id: str) -> bool:
        """Set a model as active."""
        target_dir = os.path.join(MODELS_DIR, model_id)
        if not os.path.exists(target_dir):
             return False
        
        self._save_active_model_id(model_id)
        return True

    def get_active_model_paths(self) -> tuple[str, str, int]:
        """Get the paths and input size for the currently active model."""
        model_id = self.active_model_id
        target_dir = os.path.join(MODELS_DIR, model_id)
        
        meta = next((m for m in REMOTE_REGISTRY if m['id'] == model_id), None)
        input_size = meta['input_size'] if meta else 224

        if not os.path.exists(target_dir):
            return "model.tflite", "labels.txt", 224
            
        return os.path.join(target_dir, "model.tflite"), os.path.join(target_dir, "labels.txt"), input_size

model_manager = ModelManager()