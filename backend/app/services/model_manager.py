import json
import os
import shutil
import aiofiles
import httpx
import structlog
from datetime import datetime
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
        "download_url": "https://storage.googleapis.com/download.tensorflow.org/models/tflite/mobilenet_v2_1.0_224_quant_and_labels.zip", # We will need to unzip this one, or just use the direct tflite if available. Let's use a direct link for now to simplify.
        # Actually, let's use the Coral model which is standard
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
        "download_url": "https://raw.githubusercontent.com/tensorflow/tflite-support/master/tensorflow_lite_support/metadata/python/tests/testdata/image_classifier/efficientnet_lite0.tflite", # Fallback to lite0 for test stability if lite4 is gone, but let's try a better source.
        # Using a reliable mirror or the official one if found. 
        # Ideally: https://storage.googleapis.com/cloud-tpu-checkpoints/efficientnet/lite/efficientnet-lite4-int8.tflite
        "download_url": "https://storage.googleapis.com/cloud-tpu-checkpoints/efficientnet/lite/efficientnet-lite4-int8.tflite",
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
        self.active_downloads: Dict[str, tuple[DownloadProgress, datetime]] = {}

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
        """List models currently present in the models directory or bundled assets."""
        installed = []
        available = await self.list_available_models()
        available_map = {m.id: m for m in available}
        
        # Paths to check
        paths_to_check = [MODELS_DIR]
        
        # Add bundled assets path
        # backend/app/services/model_manager.py -> backend/app/assets
        assets_dir = os.path.join(os.path.dirname(__file__), "../assets")
        if os.path.exists(assets_dir):
            paths_to_check.append(assets_dir)

        seen_ids = set()

        # Helper to check a directory for models
        def check_dir(base_dir, is_bundled=False):
            if not os.path.exists(base_dir):
                return

            # Check for directory-based models (e.g. /data/models/mobilenet_v2_birds/)
            for item in os.listdir(base_dir):
                if item in seen_ids:
                    continue
                    
                model_dir = os.path.join(base_dir, item)
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
                        seen_ids.add(item)
            
            # Check for flat-file models (legacy/bundled structure: /assets/model.tflite)
            # We map "model.tflite" in root of assets to the default ID "mobilenet_v2_birds"
            default_id = "mobilenet_v2_birds"
            if default_id not in seen_ids:
                flat_model = os.path.join(base_dir, "model.tflite")
                flat_labels = os.path.join(base_dir, "labels.txt")
                
                if os.path.exists(flat_model):
                    metadata = available_map.get(default_id)
                    installed.append(InstalledModel(
                        id=default_id,
                        path=flat_model,
                        labels_path=flat_labels,
                        is_active=(default_id == self.active_model_id),
                        metadata=metadata
                    ))
                    seen_ids.add(default_id)

        # Check persistent storage first (overrides bundled)
        check_dir(MODELS_DIR)
        
        # Check bundled assets
        check_dir(assets_dir, is_bundled=True)
        
        return installed

    def _cleanup_downloads(self):
        """Remove completed or error downloads older than 10 minutes."""
        now = datetime.now()
        to_remove = []
        for model_id, (_, timestamp) in self.active_downloads.items():
            if (now - timestamp).total_seconds() > 600: # 10 minutes
                to_remove.append(model_id)
        
        for model_id in to_remove:
            del self.active_downloads[model_id]

    def get_download_status(self, model_id: str) -> Optional[DownloadProgress]:
        self._cleanup_downloads()
        status_tuple = self.active_downloads.get(model_id)
        return status_tuple[0] if status_tuple else None

    async def download_model(self, model_id: str) -> bool:
        """Download a model from the registry."""
        model_meta = next((m for m in REMOTE_REGISTRY if m['id'] == model_id), None)
        if not model_meta:
            log.error("Model ID not found in registry", model_id=model_id)
            return False

        # Initialize progress
        progress = DownloadProgress(
            model_id=model_id,
            status="downloading",
            progress=0.0
        )
        self.active_downloads[model_id] = (progress, datetime.now())

        target_dir = os.path.join(MODELS_DIR, model_id)
        os.makedirs(target_dir, exist_ok=True)
        
        try:
            async with httpx.AsyncClient() as client:
                # 1. Download TFLite
                log.info("Downloading model", url=model_meta['download_url'])
                async with client.stream("GET", model_meta['download_url'], follow_redirects=True) as response:
                    response.raise_for_status()
                    total_header = response.headers.get("content-length")
                    total = int(total_header) if total_header else 0
                    downloaded = 0
                    async with aiofiles.open(os.path.join(target_dir, "model.tflite"), 'wb') as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                progress.progress = (downloaded / total) * 90 # Model is 90% of total job
                                self.active_downloads[model_id] = (progress, datetime.now())

                # 2. Download Labels
                log.info("Downloading labels", url=model_meta['labels_url'])
                resp = await client.get(model_meta['labels_url'], follow_redirects=True)
                resp.raise_for_status()
                async with aiofiles.open(os.path.join(target_dir, "labels.txt"), 'wb') as f:
                    await f.write(resp.content)
                
                progress.progress = 100.0
                progress.status = "completed"
                self.active_downloads[model_id] = (progress, datetime.now())

            log.info("Model downloaded successfully", model_id=model_id)
            return True
        except Exception as e:
            log.error("Failed to download model", model_id=model_id, error=str(e))
            if model_id in self.active_downloads:
                progress.status = "error"
                progress.error = str(e)
                self.active_downloads[model_id] = (progress, datetime.now())
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
