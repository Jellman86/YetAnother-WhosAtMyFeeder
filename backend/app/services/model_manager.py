import json
import os
import shutil
import aiofiles
import httpx
import structlog
from datetime import datetime
from typing import List, Optional, Dict
from app.models.ai_models import ModelMetadata, InstalledModel, DownloadProgress

log = structlog.get_logger()

# Model Registry
# Supports both TFLite and ONNX runtimes
REMOTE_REGISTRY = [
    {
        "id": "mobilenet_v2_birds",
        "name": "MobileNet V2 (Fast)",
        "description": "Lightweight iNat bird classifier (~960 species). Fast inference, good for real-time detection.",
        "architecture": "MobileNetV2",
        "file_size_mb": 3.4,
        "accuracy_tier": "Medium",
        "inference_speed": "Fast (~30ms)",
        "runtime": "tflite",
        "download_url": "https://raw.githubusercontent.com/google-coral/test_data/master/mobilenet_v2_1.0_224_inat_bird_quant.tflite",
        "labels_url": "https://raw.githubusercontent.com/google-coral/test_data/master/inat_bird_labels.txt",
        "input_size": 224,
        "preprocessing": {
            "padding_color": 128,
            "normalization": "uint8"
        }
    },
    {
        "id": "convnext_large_inat21",
        "name": "ConvNeXt Large (High Accuracy)",
        "description": "State-of-the-art iNat21 classifier. 90%+ accuracy on 10,000 species including birds, mammals, insects. Slower but much more accurate.",
        "architecture": "ConvNeXt-Large-MLP",
        "file_size_mb": 760,
        "accuracy_tier": "Very High (90%+)",
        "inference_speed": "Slow (~500-800ms)",
        "runtime": "onnx",
        "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/convnext_large_inat21.onnx",
        "weights_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/convnext_large_inat21.onnx.data",
        "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/convnext_large_inat21_labels.txt",
        "input_size": 384,
        "preprocessing": {
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
            "normalization": "float32"
        },
        "license": "CC-BY-NC-4.0"
    },
    {
        "id": "eva02_large_inat21",
        "name": "EVA-02 Large (Elite Accuracy)",
        "description": "State-of-the-art iNat21 classifier. 91%+ accuracy on 10,000 species. Requires ~2GB RAM. Slower but extremely precise.",
        "architecture": "EVA-02-Large",
        "file_size_mb": 1200,
        "accuracy_tier": "Elite (91%+)",
        "inference_speed": "Slow (~1s)",
        "runtime": "onnx",
        "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/eva02_large_inat21.onnx", 
        "weights_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/eva02_large_inat21.onnx.data",
        "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/eva02_large_inat21_labels.txt",
        "input_size": 336,
        "preprocessing": {
            "mean": [0.48145466, 0.4578275, 0.40821073],
            "std": [0.26862954, 0.26130258, 0.27577711],
            "normalization": "float32"
        },
        "license": "CC-BY-NC-4.0"
    }
]

# Use /data/models if it exists (standard for container), otherwise use local data dir
if os.path.exists("/data/models"):
    MODELS_DIR = "/data/models"
else:
    # Fallback to local project directory
    MODELS_DIR = os.path.join(os.path.dirname(__file__), "../../data/models")
    os.makedirs(MODELS_DIR, exist_ok=True)

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
                    onnx_path = os.path.join(model_dir, "model.onnx")
                    labels_path = os.path.join(model_dir, "labels.txt")
                    
                    if os.path.exists(tflite_path) or os.path.exists(onnx_path):
                        metadata = available_map.get(item)
                        installed.append(InstalledModel(
                            id=item,
                            path=tflite_path if os.path.exists(tflite_path) else onnx_path,
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
        """Download a model from the registry (supports TFLite and ONNX)."""
        model_meta = next((m for m in REMOTE_REGISTRY if m['id'] == model_id), None)
        if not model_meta:
            log.error("Model ID not found in registry", model_id=model_id)
            return False

        # Check if download URLs are configured
        if model_meta.get('download_url') == 'pending':
            log.error("Model download URL not configured yet", model_id=model_id)
            # Report error to UI immediately
            progress = DownloadProgress(
                model_id=model_id,
                status="error",
                progress=0.0,
                error="Model download URL not configured yet"
            )
            self.active_downloads[model_id] = (progress, datetime.now())
            return False

        # Determine file extension based on runtime
        runtime = model_meta.get('runtime', 'tflite')
        model_ext = '.onnx' if runtime == 'onnx' else '.tflite'
        model_filename = f"model{model_ext}"

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
            # Use longer timeout for large ONNX models
            timeout = httpx.Timeout(30.0, read=300.0) if runtime == 'onnx' else httpx.Timeout(30.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                # 1. Download model file
                log.info("Downloading model", url=model_meta['download_url'], runtime=runtime)
                async with client.stream("GET", model_meta['download_url'], follow_redirects=True) as response:
                    response.raise_for_status()
                    total_header = response.headers.get("content-length")
                    total = int(total_header) if total_header else 0
                    downloaded = 0
                    async with aiofiles.open(os.path.join(target_dir, model_filename), 'wb') as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                progress.progress = (downloaded / total) * 90  # Model is 90% of total job
                                self.active_downloads[model_id] = (progress, datetime.now())

                # 2. Download Weights (Optional, for large ONNX models)
                if runtime == 'onnx' and model_meta.get('weights_url'):
                    weights_filename = f"{model_filename}.data"
                    log.info("Downloading model weights", url=model_meta['weights_url'])
                    async with client.stream("GET", model_meta['weights_url'], follow_redirects=True) as response:
                        response.raise_for_status()
                        total_header = response.headers.get("content-length")
                        total = int(total_header) if total_header else 0
                        downloaded = 0
                        async with aiofiles.open(os.path.join(target_dir, weights_filename), 'wb') as f:
                            async for chunk in response.aiter_bytes():
                                await f.write(chunk)
                                downloaded += len(chunk)
                                if total > 0:
                                    # Weights are usually the bulk of the download
                                    progress.progress = 10 + (downloaded / total) * 80 
                                    self.active_downloads[model_id] = (progress, datetime.now())

                # 3. Download Labels
                log.info("Downloading labels", url=model_meta['labels_url'])
                resp = await client.get(model_meta['labels_url'], follow_redirects=True)
                resp.raise_for_status()
                async with aiofiles.open(os.path.join(target_dir, "labels.txt"), 'wb') as f:
                    await f.write(resp.content)

                progress.progress = 100.0
                progress.status = "completed"
                self.active_downloads[model_id] = (progress, datetime.now())

            log.info("Model downloaded successfully", model_id=model_id, runtime=runtime)
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
        # 1. Check if it's a directory-based model in persistent storage
        target_dir = os.path.join(MODELS_DIR, model_id)
        if os.path.exists(target_dir) and os.path.isdir(target_dir):
            self._save_active_model_id(model_id)
            return True

        # 2. Special case for mobilenet_v2_birds (default model)
        if model_id == "mobilenet_v2_birds":
            # Check legacy flat files in MODELS_DIR
            if os.path.exists(os.path.join(MODELS_DIR, "model.tflite")):
                self._save_active_model_id(model_id)
                return True
            
            # Check bundled assets
            assets_dir = os.path.join(os.path.dirname(__file__), "../assets")
            if os.path.exists(os.path.join(assets_dir, "model.tflite")):
                self._save_active_model_id(model_id)
                return True

        log.warning("Activation failed: model not found", model_id=model_id)
        return False

    def get_active_model_paths(self) -> tuple[str, str, int]:
        """Get the paths and input size for the currently active model."""
        model_id = self.active_model_id
        target_dir = os.path.join(MODELS_DIR, model_id)

        meta = next((m for m in REMOTE_REGISTRY if m['id'] == model_id), None)
        input_size = meta['input_size'] if meta else 224
        runtime = meta.get('runtime', 'tflite') if meta else 'tflite'

        # Determine model file extension
        model_ext = '.onnx' if runtime == 'onnx' else '.tflite'
        model_filename = f"model{model_ext}"

        if not os.path.exists(target_dir):
            # Fallback to default TFLite model
            return "model.tflite", "labels.txt", 224

        model_path = os.path.join(target_dir, model_filename)
        labels_path = os.path.join(target_dir, "labels.txt")

        return model_path, labels_path, input_size

model_manager = ModelManager()
