import json
import os
import shutil
import aiofiles
import httpx
import structlog
from datetime import datetime, UTC
from typing import Any, List, Optional, Dict
from app.models.ai_models import CropGeneratorConfig, ModelMetadata, InstalledModel, DownloadProgress
from app.config import settings
from app.config_models import normalize_crop_model_override, normalize_crop_source_override
from app.services.bird_model_region_resolver import resolve_bird_model_region

log = structlog.get_logger()

# Model Registry
# Supports both TFLite and ONNX runtimes
REMOTE_REGISTRY = [
    {
        "id": "bird_crop_detector",
        "name": "Bird Crop Detector",
        "description": "Shared bird-localization detector used by crop-enabled classifier models.",
        "architecture": "SSD-MobileNet V1 INT8",
        "artifact_kind": "crop_detector",
        "file_size_mb": 12.4,
        "accuracy_tier": "System",
        "inference_speed": "Fast",
        "runtime": "onnx",
        "supported_inference_providers": ["cpu"],
        "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/bird_crop_detector_ssd_mobilenet_v1_12_int8.onnx",
        "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/bird_crop_detector_labels.txt",
        "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/bird_crop_detector_model_config.json",
        "input_size": 320,
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "letterbox",
            "interpolation": "bilinear",
            "normalization": "uint8"
        },
        "tier": "dependency",
        "taxonomy_scope": "system",
        "recommended_for": "Required dependency for crop-enabled bird classification.",
        "estimated_ram_mb": 256,
        "advanced_only": True,
        "sort_order": 5,
        "status": "stable",
        "notes": "Install this once to enable crop-assisted classification for models that opt into bird cropping."
    },
    {
        "id": "mobilenet_v2_birds",
        "name": "MobileNet V2 (Fast)",
        "description": "Lightweight iNat bird classifier (~960 species). Fast inference, good for real-time detection.",
        "architecture": "MobileNetV2",
        "file_size_mb": 3.4,
        "accuracy_tier": "Medium",
        "inference_speed": "Fast (~30ms)",
        "runtime": "tflite",
        "supported_inference_providers": ["cpu"],
        "download_url": "https://raw.githubusercontent.com/google-coral/test_data/master/mobilenet_v2_1.0_224_inat_bird_quant.tflite",
        "labels_url": "https://raw.githubusercontent.com/google-coral/test_data/master/inat_bird_labels.txt",
        "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/mobilenet_v2_birds_model_config.json",
        "input_size": 224,
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "letterbox",
            "interpolation": "bicubic",
            "padding_color": 0,
            "normalization": "uint8"
        },
        "tier": "cpu_only",
        "taxonomy_scope": "birds_only",
        "recommended_threshold": 0.70,
        "recommended_for": "Default bird-only inference on CPU and low-RAM devices.",
        "estimated_ram_mb": 128,
        "advanced_only": False,
        "sort_order": 10,
        "status": "stable",
        "notes": "Fastest option for the default bird classifier."
    },
    {
        "id": "small_birds",
        "name": "Small Birds",
        "description": "Regional birds-only small-tier family with automatic location-based selection.",
        "architecture": "Regional Birds Family",
        "file_size_mb": 0,
        "accuracy_tier": "High",
        "inference_speed": "Medium",
        "runtime": "onnx",
        "supported_inference_providers": ["cpu", "intel_cpu", "intel_gpu"],
        "download_url": "pending",
        "labels_url": "pending",
        "input_size": 224,
        "tier": "small",
        "taxonomy_scope": "birds_only",
        "recommended_threshold": 0.65,
        "recommended_for": "Regional birds-only small model with auto region selection.",
        "estimated_ram_mb": 768,
        "advanced_only": False,
        "sort_order": 14,
        "status": "planned",
        "family_id": "small_birds",
        "default_region": "na",
        "region_variants": {
            "eu": {
                "region_scope": "eu",
                "name": "Small Birds",
                "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/small_birds_eu_mobilenet_v4_l_candidate.onnx",
                "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/small_birds_eu_mobilenet_v4_l_candidate_labels.txt",
                "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/small_birds_eu_mobilenet_v4_l_candidate_model_config.json",
                "file_size_mb": 122.7,
                "input_size": 384,
                "preprocessing": {
                    "color_space": "RGB",
                    "resize_mode": "center_crop",
                    "interpolation": "bicubic",
                    "crop_pct": 1.0,
                    "mean": [0.5248, 0.5372, 0.5086],
                    "std": [0.2135, 0.2103, 0.2622],
                    "normalization": "float32",
                },
                "crop_generator": {
                    "enabled": False,
                },
            },
            "na": {
                "region_scope": "na",
                "name": "Small Birds",
                "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/n2b8_efficientnet_b0_nabirds.onnx",
                "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/n2b8_class_labels.txt",
                "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/small_birds_na_efficientnet_b0_candidate_model_config.json",
                "file_size_mb": 18.0,
                "input_size": 224,
                "preprocessing": {
                    "color_space": "RGB",
                    "resize_mode": "center_crop",
                    "interpolation": "bicubic",
                    "crop_pct": 0.875,
                    "mean": [0.485, 0.456, 0.406],
                    "std": [0.229, 0.224, 0.225],
                    "normalization": "float32",
                },
                "supported_inference_providers": ["cpu", "intel_cpu"],
                "label_grouping": {
                    "strategy": "strip_trailing_parenthetical",
                },
                "crop_generator": {
                    "enabled": True,
                    "source_preference": "high_quality",
                    "input_context": {
                        "is_cropped": True,
                    },
                },
            },
        },
        "notes": "Regional birds-only family. Assets pending validation and release upload."
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
        "supported_inference_providers": ["cpu", "cuda", "intel_cpu", "intel_gpu"],
        "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/convnext_large_inat21.onnx",
        "weights_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/convnext_large_inat21.onnx.data",
        "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/convnext_large_inat21_labels.txt",
        "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/convnext_large_inat21_model_config.json",
        "input_size": 384,
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "center_crop",
            "interpolation": "bicubic",
            "crop_pct": 0.95,
            "mean": [0.48145466, 0.4578275, 0.40821073],
            "std": [0.26862954, 0.26130258, 0.27577711],
            "normalization": "float32"
        },
        "license": "CC-BY-NC-4.0",
        "tier": "large",
        "taxonomy_scope": "wildlife_wide",
        "recommended_threshold": 0.45,
        "recommended_for": "General-purpose wildlife classification with strong accuracy across birds, mammals, and insects.",
        "estimated_ram_mb": 2048,
        "advanced_only": False,
        "sort_order": 20,
        "status": "stable",
        "notes": "Higher-accuracy broad model. Uses a 10,000-class label space; lower confidence scores are normal — recommended threshold is 0.45."
    },
    {
        "id": "hieradet_small_inat21",
        "name": "ViT Small (Balanced)",
        "description": "Compact iNat21 classifier tuned for broad wildlife coverage with a smaller ONNX footprint than the medium and large models.",
        "architecture": "ViT Reg4 M16 RMS Avg (I-JEPA)",
        "file_size_mb": 167,
        "accuracy_tier": "High (83%+)",
        "inference_speed": "Medium (~150-300ms)",
        "runtime": "onnx",
        "supported_inference_providers": ["cpu", "cuda", "intel_cpu", "intel_gpu"],
        "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/hieradet_small_inat21.onnx",
        "weights_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/hieradet_small_inat21.onnx.data",
        "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/hieradet_small_inat21_labels.txt",
        "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/hieradet_small_inat21_model_config.json",
        "input_size": 256,
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "center_crop",
            "interpolation": "bicubic",
            "crop_pct": 1.0,
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
            "normalization": "float32"
        },
        "license": "Apache-2.0",
        "tier": "small",
        "taxonomy_scope": "wildlife_wide",
        "recommended_threshold": 0.45,
        "recommended_for": "Broad wildlife classification on CPU or Intel GPU when you want a lighter recommendation before stepping up to RoPE or ConvNeXt.",
        "estimated_ram_mb": 1024,
        "advanced_only": True,
        "sort_order": 15,
        "status": "experimental",
        "notes": "ONNX Runtime CPU, OpenVINO CPU, and Intel GPU validated locally; CUDA unverified and best-effort only in this environment. Candidate remains experimental until broader runtime coverage is confirmed. Uses a 10,000-class label space; recommended threshold is 0.45."
    },
    {
        "id": "hieradet_dino_small_inat21",
        "name": "HieraDeT DINOv2 Small (Wildlife)",
        "description": "Compact iNat21 wildlife classifier using HieraDeT architecture pretrained with DINOv2. 10,000 species at 256px — lighter than the large models with strong broad-wildlife coverage.",
        "architecture": "HieraDeT-D-Small + DINOv2",
        "file_size_mb": 159,
        "accuracy_tier": "High (84%+)",
        "inference_speed": "Medium (~120-250ms)",
        "runtime": "onnx",
        "supported_inference_providers": ["cpu", "cuda", "intel_cpu", "intel_gpu"],
        "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/hieradet_dino_small_inat21.onnx",
        "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/hieradet_dino_small_inat21_labels.txt",
        "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/hieradet_dino_small_inat21_model_config.json",
        "input_size": 256,
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "center_crop",
            "interpolation": "bicubic",
            "crop_pct": 1.0,
            "mean": [0.5191, 0.5306, 0.4877],
            "std": [0.2316, 0.2304, 0.2588],
            "normalization": "float32"
        },
        "license": "Apache-2.0",
        "tier": "small",
        "taxonomy_scope": "wildlife_wide",
        "recommended_threshold": 0.45,
        "recommended_for": "Broad wildlife classification — lighter alternative to RoPE ViT for CPU-constrained systems.",
        "estimated_ram_mb": 768,
        "advanced_only": True,
        "sort_order": 16,
        "status": "experimental",
        "notes": "Exported from Birder pretrained weights (hieradet_d_small_dino-v2-inat21-256px). Uses a 10,000-class label space; recommended threshold is 0.45."
    },
    {
        "id": "eu_medium_focalnet_b",
        "name": "FocalNet-B EU Medium (Birds Only)",
        "description": "EU-focused birds-only FocalNet-B model from the Birder project. Covers 707 European species at 384px resolution with excellent regional accuracy.",
        "architecture": "FocalNet-B LRF Intermediate",
        "file_size_mb": 338,
        "accuracy_tier": "Very High (87%+)",
        "inference_speed": "Medium-Slow (~300-500ms)",
        "runtime": "onnx",
        "supported_inference_providers": ["cpu", "cuda", "intel_cpu", "intel_gpu"],
        "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/eu_medium_focalnet_b.onnx",
        "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/eu_medium_focalnet_b_labels.txt",
        "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/eu_medium_focalnet_b_model_config.json",
        "input_size": 384,
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "center_crop",
            "interpolation": "bicubic",
            "crop_pct": 1.0,
            "mean": [0.5, 0.5, 0.5],
            "std": [0.5, 0.5, 0.5],
            "normalization": "float32"
        },
        "license": "Apache-2.0",
        "tier": "medium",
        "taxonomy_scope": "birds_only",
        "recommended_threshold": 0.65,
        "recommended_for": "European feeder setups wanting a birds-only model with strong regional accuracy.",
        "estimated_ram_mb": 1024,
        "advanced_only": True,
        "sort_order": 19,
        "status": "experimental",
        "notes": "Exported from Birder pretrained weights (focalnet_b_lrf_intermediate-eu-common). 707 European species, 384px input."
    },
    {
        "id": "flexivit_il_all",
        "name": "FlexiViT Global Birds (Birds Only)",
        "description": "Global birds-only FlexiViT model pretrained with DINOv2 on iNaturalist. 550 worldwide species at 240px — compact and fast, good for global/unspecified regions.",
        "architecture": "FlexiViT-Reg1-S16-RMS + DINOv2",
        "file_size_mb": 84,
        "accuracy_tier": "High",
        "inference_speed": "Fast (~80-150ms)",
        "runtime": "onnx",
        "supported_inference_providers": ["cpu", "cuda", "intel_cpu", "intel_gpu"],
        "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/flexivit_il_all.onnx",
        "weights_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/flexivit_il_all.onnx.data",
        "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/flexivit_il_all_labels.txt",
        "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/flexivit_il_all_model_config.json",
        "input_size": 240,
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "center_crop",
            "interpolation": "bicubic",
            "crop_pct": 1.0,
            "mean": [0.5, 0.5, 0.5],
            "std": [0.5, 0.5, 0.5],
            "normalization": "float32"
        },
        "license": "Apache-2.0",
        "tier": "small",
        "taxonomy_scope": "birds_only",
        "recommended_threshold": 0.60,
        "recommended_for": "Global feeder setups or regions without a dedicated regional model. Compact and fast.",
        "estimated_ram_mb": 512,
        "advanced_only": True,
        "sort_order": 13,
        "status": "experimental",
        "notes": "Exported from Birder pretrained weights (flexivit_reg1_s16_rms_ls_dino-v2-il-all). 550 global bird species, uses ONNX external data file."
    },
    {
        "id": "medium_birds",
        "name": "Medium Birds",
        "description": "Regional birds-only medium-tier family with automatic location-based selection.",
        "architecture": "Regional Birds Family",
        "file_size_mb": 0,
        "accuracy_tier": "Very High",
        "inference_speed": "Medium-Slow",
        "runtime": "onnx",
        "supported_inference_providers": ["cpu", "intel_cpu", "intel_gpu"],
        "download_url": "pending",
        "labels_url": "pending",
        "input_size": 224,
        "tier": "medium",
        "taxonomy_scope": "birds_only",
        "recommended_threshold": 0.65,
        "recommended_for": "Regional birds-only medium model with auto region selection.",
        "estimated_ram_mb": 1536,
        "advanced_only": False,
        "sort_order": 17,
        "status": "planned",
        "family_id": "medium_birds",
        "default_region": "na",
        "region_variants": {
            "eu": {
                "region_scope": "eu",
                "name": "Medium Birds",
                "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/medium_birds_eu_convnext_v2_tiny_256_candidate.onnx",
                "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/medium_birds_eu_convnext_v2_tiny_256_candidate_labels.txt",
                "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/medium_birds_eu_convnext_v2_tiny_256_candidate_model_config.json",
                "file_size_mb": 108.5,
                "input_size": 256,
                "preprocessing": {
                    "color_space": "RGB",
                    "resize_mode": "center_crop",
                    "interpolation": "bicubic",
                    "crop_pct": 1.0,
                    "mean": [0.5191, 0.5306, 0.4877],
                    "std": [0.2316, 0.2304, 0.2588],
                    "normalization": "float32",
                },
                "crop_generator": {
                    "enabled": False,
                },
            },
            "na": {
                "region_scope": "na",
                "name": "Medium Birds",
                "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/medium_birds_na_binocular_candidate.onnx",
                "weights_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/medium_birds_na_binocular_candidate.onnx.data",
                "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/medium_birds_na_binocular_candidate_labels.txt",
                "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/medium_birds_na_binocular_candidate_model_config.json",
                "file_size_mb": 333.0,
                "input_size": 224,
                "preprocessing": {
                    "color_space": "RGB",
                    "resize_mode": "center_crop",
                    "interpolation": "bicubic",
                    "crop_pct": 0.875,
                    "mean": [0.485, 0.456, 0.406],
                    "std": [0.229, 0.224, 0.225],
                    "normalization": "float32",
                },
                "supported_inference_providers": ["cpu", "intel_cpu"],
                "label_grouping": {
                    "strategy": "strip_trailing_parenthetical",
                },
                "crop_generator": {
                    "enabled": True,
                    "source_preference": "high_quality",
                    "input_context": {
                        "is_cropped": True,
                    },
                },
            },
        },
        "notes": "Regional birds-only family. Assets pending validation and release upload."
    },
    {
        "id": "rope_vit_b14_inat21",
        "name": "RoPE ViT-B14 (Medium Accuracy)",
        "description": "Mid-tier iNat21 classifier intended to bridge the gap between the small wildlife model and ConvNeXt large.",
        "architecture": "RoPE-ViT-B14-CAPI",
        "file_size_mb": 375,
        "accuracy_tier": "Very High (89%+)",
        "inference_speed": "Medium-Slow (~220-400ms)",
        "runtime": "onnx",
        "supported_inference_providers": ["cpu", "cuda", "intel_cpu", "intel_gpu"],
        "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/rope_vit_b14_inat21.onnx",
        "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/rope_vit_b14_inat21_labels.txt",
        "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/rope_vit_b14_inat21_model_config.json",
        "input_size": 224,
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "center_crop",
            "interpolation": "bicubic",
            "crop_pct": 1.0,
            "mean": [0.5248, 0.5372, 0.5086],
            "std": [0.2135, 0.2103, 0.2622],
            "normalization": "float32"
        },
        "license": "Apache-2.0",
        "tier": "medium",
        "taxonomy_scope": "wildlife_wide",
        "recommended_threshold": 0.45,
        "recommended_for": "Broader wildlife coverage with stronger accuracy than the small model while staying lighter than ConvNeXt large.",
        "estimated_ram_mb": 1536,
        "advanced_only": True,
        "sort_order": 18,
        "status": "experimental",
        "notes": "CPU and OpenVINO CPU validated locally; CUDA unverified in this environment. Candidate remains experimental until broader runtime coverage is confirmed. Uses a 10,000-class label space; recommended threshold is 0.45."
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
        "supported_inference_providers": ["cpu", "cuda", "intel_cpu", "intel_gpu"],
        "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/eva02_large_inat21.onnx", 
        "weights_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/eva02_large_inat21.onnx.data",
        "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/eva02_large_inat21_labels.txt",
        "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/eva02_large_inat21_model_config.json",
        "input_size": 336,
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "center_crop",
            "interpolation": "bicubic",
            "crop_pct": 1.0,
            "mean": [0.48145466, 0.4578275, 0.40821073],
            "std": [0.26862954, 0.26130258, 0.27577711],
            "normalization": "float32"
        },
        "license": "CC-BY-NC-4.0",
        "tier": "advanced",
        "taxonomy_scope": "wildlife_wide",
        "recommended_threshold": 0.45,
        "recommended_for": "Highest-accuracy wildlife classification for advanced users with more compute and RAM.",
        "estimated_ram_mb": 3072,
        "advanced_only": True,
        "sort_order": 30,
        "status": "stable",
        "notes": "Elite accuracy model. Uses a 10,000-class label space; recommended threshold is 0.45."
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
                    model_id = data.get("active_model_id", "mobilenet_v2_birds")
                    return str(model_id or "mobilenet_v2_birds").strip() or "mobilenet_v2_birds"
            except Exception:
                return "mobilenet_v2_birds"
        return "mobilenet_v2_birds"

    def _save_active_model_id(self, model_id: str):
        """Save the active model ID."""
        config_path = os.path.join(MODELS_DIR, "active_model.json")
        with open(config_path, 'w') as f:
            json.dump(
                {
                    "active_model_id": model_id,
                },
                f,
            )
        self.active_model_id = model_id

    def _get_registry_model_meta(self, model_id: str) -> Optional[dict[str, Any]]:
        return next((m for m in REMOTE_REGISTRY if m["id"] == model_id), None)

    def get_crop_detector_meta(self) -> Optional[dict[str, Any]]:
        return self._get_registry_model_meta("bird_crop_detector")

    def get_crop_detector_spec(self) -> dict[str, Any]:
        meta = dict(self.get_crop_detector_meta() or {})
        model_dir = os.path.join(MODELS_DIR, "bird_crop_detector")
        model_path = os.path.join(model_dir, "model.onnx")
        labels_path = os.path.join(model_dir, "labels.txt")
        config_path = os.path.join(model_dir, "model_config.json")
        installed = os.path.exists(model_path)
        healthy = installed and os.path.exists(config_path)
        return {
            "model_id": "bird_crop_detector",
            "artifact_kind": str(meta.get("artifact_kind") or "crop_detector"),
            "installed": installed,
            "healthy": healthy,
            "enabled_for_runtime": healthy,
            "reason": "ready" if healthy else ("config_missing" if installed else "not_installed"),
            "model_path": model_path,
            "labels_path": labels_path,
            "model_config_path": config_path,
            "metadata": meta,
        }

    def _is_family_model(self, model_meta: Optional[dict[str, Any]]) -> bool:
        return bool((model_meta or {}).get("region_variants"))

    def _resolve_region_inputs(
        self,
        *,
        country: Optional[str] = None,
        override: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        resolved_country = settings.location.country if country is None else country
        resolved_override = (
            settings.classification.bird_model_region_override
            if override is None
            else override
        )
        return resolved_country, resolved_override

    def _model_filename_for_runtime(self, runtime: str) -> str:
        model_ext = ".onnx" if runtime == "onnx" else ".tflite"
        return f"model{model_ext}"

    def _normalize_crop_generator_block(self, raw_value: Any) -> dict[str, Any]:
        try:
            config = CropGeneratorConfig.model_validate(raw_value or {})
        except Exception:
            config = CropGeneratorConfig()
        return config.model_dump(exclude_none=True)

    def _get_crop_model_overrides(self) -> dict[str, str]:
        raw = getattr(settings.classification, "crop_model_overrides", {}) or {}
        if not isinstance(raw, dict):
            return {}
        normalized: dict[str, str] = {}
        for raw_key, raw_value in raw.items():
            key = str(raw_key or "").strip()
            if not key:
                continue
            normalized[key] = normalize_crop_model_override(raw_value)
        return normalized

    def _get_crop_source_overrides(self) -> dict[str, str]:
        raw = getattr(settings.classification, "crop_source_overrides", {}) or {}
        if not isinstance(raw, dict):
            return {}
        normalized: dict[str, str] = {}
        for raw_key, raw_value in raw.items():
            key = str(raw_key or "").strip()
            if not key:
                continue
            normalized[key] = normalize_crop_source_override(raw_value)
        return normalized

    def _apply_crop_overrides(self, spec: dict[str, Any]) -> dict[str, Any]:
        merged = dict(spec)
        crop_generator = self._normalize_crop_generator_block(merged.get("crop_generator"))

        model_id = str(merged.get("model_id") or merged.get("id") or "").strip()
        family_id = str(merged.get("family_id") or model_id or "").strip()
        resolved_region = str(merged.get("resolved_region") or merged.get("region_scope") or "").strip()
        variant_id = f"{family_id}.{resolved_region}" if family_id and resolved_region else ""

        model_overrides = self._get_crop_model_overrides()
        source_overrides = self._get_crop_source_overrides()

        family_crop_override = model_overrides.get(family_id) or model_overrides.get(model_id) or "default"
        variant_crop_override = model_overrides.get(variant_id, "default") if variant_id else "default"
        effective_crop_override = (
            variant_crop_override
            if variant_crop_override != "default"
            else family_crop_override
        )
        if effective_crop_override == "on":
            crop_generator["enabled"] = True
        elif effective_crop_override == "off":
            crop_generator["enabled"] = False

        family_source_override = source_overrides.get(family_id) or source_overrides.get(model_id) or "default"
        variant_source_override = source_overrides.get(variant_id, "default") if variant_id else "default"
        effective_source_override = (
            variant_source_override
            if variant_source_override != "default"
            else family_source_override
        )
        if effective_source_override != "default":
            crop_generator["source_preference"] = effective_source_override

        merged["crop_generator"] = self._normalize_crop_generator_block(crop_generator)
        return merged

    def _merge_family_variant_meta(
        self,
        model_meta: dict[str, Any],
        *,
        region: str,
    ) -> dict[str, Any]:
        variant = dict((model_meta.get("region_variants") or {}).get(region) or {})
        merged = dict(model_meta)
        merged.update(variant)
        merged["resolved_region"] = region
        merged["family_id"] = model_meta.get("family_id") or model_meta.get("id")
        merged["runtime"] = variant.get("runtime", model_meta.get("runtime", "tflite"))
        merged["file_size_mb"] = float(variant.get("file_size_mb", model_meta.get("file_size_mb", 0.0)) or 0.0)
        merged["input_size"] = int(variant.get("input_size", model_meta.get("input_size", 224)) or 224)
        merged["preprocessing"] = dict(variant.get("preprocessing") or model_meta.get("preprocessing") or {})
        merged["label_grouping"] = dict(variant.get("label_grouping") or model_meta.get("label_grouping") or {})
        merged["supported_inference_providers"] = list(
            variant.get("supported_inference_providers")
            or model_meta.get("supported_inference_providers")
            or []
        )
        if "crop_generator" in variant:
            merged["crop_generator"] = self._normalize_crop_generator_block(variant.get("crop_generator"))
        else:
            merged["crop_generator"] = self._normalize_crop_generator_block(model_meta.get("crop_generator"))
        merged["download_url"] = variant.get("download_url", model_meta.get("download_url"))
        merged["weights_url"] = variant.get("weights_url", model_meta.get("weights_url"))
        merged["labels_url"] = variant.get("labels_url", model_meta.get("labels_url"))
        merged["model_config_url"] = variant.get("model_config_url", model_meta.get("model_config_url"))
        return merged

    def _build_model_config_payload(self, model_meta: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model_id": str(model_meta.get("id") or model_meta.get("family_id") or ""),
            "runtime": str(model_meta.get("runtime") or "tflite"),
            "input_size": int(model_meta.get("input_size", 224) or 224),
            "preprocessing": dict(model_meta.get("preprocessing") or {}),
            "label_grouping": dict(model_meta.get("label_grouping") or {}),
            "supported_inference_providers": list(model_meta.get("supported_inference_providers") or []),
            "crop_generator": self._normalize_crop_generator_block(model_meta.get("crop_generator")),
        }
        region_scope = str(model_meta.get("region_scope") or "").strip()
        if region_scope:
            payload["region_scope"] = region_scope
        return payload

    def _write_model_config_payload(self, staged_dir: str, payload: dict[str, Any]) -> None:
        config_path = os.path.join(staged_dir, "model_config.json")
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")

    def _load_installed_model_config(self, model_dir: str) -> dict[str, Any]:
        config_path = os.path.join(model_dir, "model_config.json")
        if not os.path.exists(config_path):
            return {}
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            log.warning("Failed to load installed model config", model_dir=model_dir, error=str(exc))
            return {}

    def _apply_installed_model_config(
        self,
        spec: dict[str, Any],
        *,
        model_dir: str,
    ) -> dict[str, Any]:
        config = self._load_installed_model_config(model_dir)
        if not config:
            return spec

        merged = dict(spec)
        merged["model_config_path"] = os.path.join(model_dir, "model_config.json")
        runtime = config.get("runtime")
        if isinstance(runtime, str) and runtime.strip():
            merged["runtime"] = runtime.strip()
        input_size = config.get("input_size")
        if input_size is not None:
            try:
                merged["input_size"] = int(input_size)
            except (TypeError, ValueError):
                log.warning("Ignoring invalid input_size in installed model config", model_dir=model_dir, value=input_size)
        preprocessing = dict(spec.get("preprocessing") or {})
        raw_preprocessing = config.get("preprocessing")
        if isinstance(raw_preprocessing, dict):
            preprocessing.update(raw_preprocessing)
        elif raw_preprocessing is not None:
            log.warning("Ignoring invalid preprocessing block in installed model config", model_dir=model_dir)
        merged["preprocessing"] = preprocessing
        label_grouping = dict(spec.get("label_grouping") or {})
        raw_label_grouping = config.get("label_grouping")
        if isinstance(raw_label_grouping, dict):
            label_grouping.update(raw_label_grouping)
        elif raw_label_grouping is not None:
            log.warning("Ignoring invalid label_grouping block in installed model config", model_dir=model_dir)
        merged["label_grouping"] = label_grouping
        crop_generator = self._normalize_crop_generator_block(spec.get("crop_generator"))
        raw_crop_generator = config.get("crop_generator")
        if isinstance(raw_crop_generator, dict):
            crop_generator.update(raw_crop_generator)
        elif raw_crop_generator is not None:
            log.warning("Ignoring invalid crop_generator block in installed model config", model_dir=model_dir)
        merged["crop_generator"] = self._normalize_crop_generator_block(crop_generator)
        providers = config.get("supported_inference_providers")
        if isinstance(providers, list) and providers:
            merged["supported_inference_providers"] = list(providers)
        return merged

    def _resolve_family_variant_meta(
        self,
        model_meta: dict[str, Any],
        *,
        country: Optional[str] = None,
        override: Optional[str] = None,
    ) -> dict[str, Any]:
        country, override = self._resolve_region_inputs(country=country, override=override)
        variants = model_meta.get("region_variants") or {}
        effective_region = resolve_bird_model_region(country=country, override=override)
        selected_region = effective_region if effective_region in variants else None
        if selected_region is None:
            default_region = str(model_meta.get("default_region") or "").strip()
            if default_region in variants:
                selected_region = default_region
        if selected_region is None and variants:
            selected_region = next(iter(variants.keys()))
        if selected_region is None:
            return dict(model_meta)
        return self._merge_family_variant_meta(model_meta, region=selected_region)

    def _resolve_installed_family_variant(
        self,
        target_dir: str,
        model_meta: dict[str, Any],
        *,
        country: Optional[str] = None,
        override: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        variants = model_meta.get("region_variants") or {}
        preferred = self._resolve_family_variant_meta(model_meta, country=country, override=override)
        candidate_regions: list[str] = []
        preferred_region = str(preferred.get("resolved_region") or "").strip()
        if preferred_region:
            candidate_regions.append(preferred_region)
        default_region = str(model_meta.get("default_region") or "").strip()
        if default_region and default_region not in candidate_regions:
            candidate_regions.append(default_region)
        for region in variants.keys():
            if region not in candidate_regions:
                candidate_regions.append(region)

        for region in candidate_regions:
            merged = self._merge_family_variant_meta(model_meta, region=region)
            variant_dir = os.path.join(target_dir, region)
            model_path = os.path.join(variant_dir, self._model_filename_for_runtime(str(merged.get("runtime") or "tflite")))
            labels_path = os.path.join(variant_dir, "labels.txt")
            if os.path.exists(model_path):
                spec = {
                    "model_id": str(model_meta.get("id") or model_meta.get("family_id") or ""),
                    "family_id": str(merged.get("family_id") or model_meta.get("family_id") or model_meta.get("id") or ""),
                    "model_path": model_path,
                    "labels_path": labels_path,
                    "input_size": int(merged.get("input_size", 224) or 224),
                    "preprocessing": dict(merged.get("preprocessing") or {}),
                    "runtime": str(merged.get("runtime") or "tflite"),
                    "label_grouping": dict(merged.get("label_grouping") or {}),
                    "supported_inference_providers": list(merged.get("supported_inference_providers") or []),
                    "weights_url": merged.get("weights_url"),
                    "resolved_region": region,
                    "model_config_url": merged.get("model_config_url"),
                    "crop_generator": self._normalize_crop_generator_block(merged.get("crop_generator")),
                }
                return self._apply_crop_overrides(
                    self._apply_installed_model_config(spec, model_dir=variant_dir)
                )
        return None

    def get_active_model_spec(
        self,
        *,
        country: Optional[str] = None,
        override: Optional[str] = None,
    ) -> dict[str, Any]:
        model_id = self.active_model_id
        model_meta = self._get_registry_model_meta(model_id)
        target_dir = os.path.join(MODELS_DIR, model_id)

        if model_meta and self._is_family_model(model_meta):
            resolved = self._resolve_installed_family_variant(
                target_dir,
                model_meta,
                country=country,
                override=override,
            )
            if resolved:
                resolved["model_id"] = model_id
                return resolved

        if model_meta:
            runtime = str(model_meta.get("runtime", "tflite") or "tflite")
            model_path = os.path.join(target_dir, self._model_filename_for_runtime(runtime))
            labels_path = os.path.join(target_dir, "labels.txt")
            if os.path.exists(model_path):
                spec = {
                    "model_id": model_id,
                    "model_path": model_path,
                    "labels_path": labels_path,
                    "input_size": int(model_meta.get("input_size", 224) or 224),
                    "preprocessing": dict(model_meta.get("preprocessing") or {}),
                    "runtime": runtime,
                    "label_grouping": dict(model_meta.get("label_grouping") or {}),
                    "supported_inference_providers": list(model_meta.get("supported_inference_providers") or []),
                    "weights_url": model_meta.get("weights_url"),
                    "model_config_url": model_meta.get("model_config_url"),
                    "crop_generator": self._normalize_crop_generator_block(model_meta.get("crop_generator")),
                }
                return self._apply_crop_overrides(
                    self._apply_installed_model_config(spec, model_dir=target_dir)
                )

        return self._apply_crop_overrides({
            "model_id": "mobilenet_v2_birds",
            "model_path": "model.tflite",
            "labels_path": "labels.txt",
            "input_size": 224,
            "preprocessing": {},
            "runtime": "tflite",
            "label_grouping": {},
            "supported_inference_providers": ["cpu"],
            "weights_url": None,
            "crop_generator": self._normalize_crop_generator_block(None),
        })

    async def list_available_models(self) -> List[ModelMetadata]:
        """Fetch list of available models from remote registry."""
        resolved_models: list[ModelMetadata] = []
        for model in sorted(REMOTE_REGISTRY, key=lambda item: item.get("sort_order", 0)):
            payload = (
                self._resolve_family_variant_meta(model)
                if self._is_family_model(model)
                else dict(model)
            )
            payload = self._apply_crop_overrides(payload)
            resolved_models.append(ModelMetadata(**payload))
        return resolved_models

    async def get_resolved_bird_model_families(
        self,
        *,
        country: str | None,
        override: str | None,
    ) -> dict[str, dict]:
        available = await self.list_available_models()
        by_id = {model.id: model for model in available}
        effective_region = resolve_bird_model_region(country=country, override=override)
        selection_source = "manual" if (override or "auto").strip().lower() != "auto" else "auto"

        resolved: dict[str, dict] = {}
        for family_id in ("small_birds", "medium_birds"):
            family = by_id.get(family_id)
            if not family:
                continue
            region_variants = family.region_variants or {}
            variant = region_variants.get(effective_region) or region_variants.get(family.default_region or "") or {}
            resolved[family_id] = {
                "effective_region": effective_region,
                "selection_source": selection_source,
                "family_id": family.id,
                "variant": variant,
            }
        return resolved

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
                    metadata = available_map.get(item)
                    if metadata and self._is_family_model(metadata.model_dump()):
                        resolved = self._resolve_installed_family_variant(
                            model_dir,
                            metadata.model_dump(),
                        )
                        if resolved:
                            installed.append(InstalledModel(
                                id=item,
                                path=str(resolved["model_path"]),
                                labels_path=str(resolved["labels_path"]),
                                is_active=(item == self.active_model_id),
                                metadata=metadata,
                            ))
                            seen_ids.add(item)
                            continue

                    tflite_path = os.path.join(model_dir, "model.tflite")
                    onnx_path = os.path.join(model_dir, "model.onnx")
                    labels_path = os.path.join(model_dir, "labels.txt")
                    
                    if os.path.exists(tflite_path) or os.path.exists(onnx_path):
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

    def _update_download_status(self, model_id: str, progress: DownloadProgress) -> None:
        self.active_downloads[model_id] = (progress, datetime.now())

    def _build_download_progress(self, phase: str, downloaded: int, total: int, *, has_weights: bool = True) -> float:
        if phase == 'model':
            start, end = 0.0, (80.0 if has_weights else 98.0)
        elif phase == 'weights':
            start, end = 80.0, 98.0
        elif phase == 'labels':
            return 99.0
        else:
            raise ValueError(f'Unknown download phase: {phase}')

        if total <= 0:
            return start

        fraction = max(0.0, min(1.0, downloaded / total))
        return start + ((end - start) * fraction)

    def _create_staging_dir(self, model_id: str) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        staged_dir = os.path.join(MODELS_DIR, f".{model_id}.download-{stamp}")
        os.makedirs(staged_dir, exist_ok=False)
        return staged_dir

    def _validate_download_payload(self, model_meta: dict, staged_dir: str, model_filename: str) -> None:
        required_files = [model_filename, "labels.txt"]
        if model_meta.get("runtime") == "onnx" and model_meta.get("weights_url"):
            required_files.append(f"{model_filename}.data")
        if model_meta.get("model_config_url"):
            required_files.append("model_config.json")

        missing = [name for name in required_files if not os.path.exists(os.path.join(staged_dir, name))]
        if missing:
            missing_csv = ", ".join(missing)
            raise RuntimeError(f"Downloaded model payload is missing required files: {missing_csv}")

    def _swap_model_dirs(self, staged_dir: str, target_dir: str) -> None:
        had_existing = os.path.isdir(target_dir)
        backup_dir = f"{target_dir}.backup-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"

        if had_existing:
            os.rename(target_dir, backup_dir)

        try:
            os.rename(staged_dir, target_dir)
        except Exception:
            if had_existing and os.path.isdir(backup_dir) and not os.path.exists(target_dir):
                try:
                    os.rename(backup_dir, target_dir)
                except Exception as rollback_error:
                    log.error(
                        "Failed to rollback model directory after swap error",
                        target_dir=target_dir,
                        backup_dir=backup_dir,
                        rollback_error=str(rollback_error),
                    )
            raise
        else:
            if had_existing and os.path.isdir(backup_dir):
                shutil.rmtree(backup_dir, ignore_errors=True)

    def _scale_progress(self, value: float, *, start: float, end: float) -> float:
        clamped = max(0.0, min(100.0, float(value)))
        return start + ((end - start) * (clamped / 100.0))

    async def _download_payload_to_dir(
        self,
        *,
        client: httpx.AsyncClient,
        model_meta: dict[str, Any],
        staged_dir: str,
        progress: DownloadProgress,
        progress_model_id: str,
        progress_start: float,
        progress_end: float,
    ) -> None:
        runtime = str(model_meta.get("runtime", "tflite") or "tflite")
        model_filename = self._model_filename_for_runtime(runtime)
        has_weights = runtime == "onnx" and bool(model_meta.get("weights_url"))

        # 1. Download model file
        log.info("Downloading model", url=model_meta["download_url"], runtime=runtime, staged_dir=staged_dir)
        async with client.stream("GET", model_meta["download_url"], follow_redirects=True) as response:
            response.raise_for_status()
            total_header = response.headers.get("content-length")
            total = int(total_header) if total_header else 0
            downloaded = 0
            async with aiofiles.open(os.path.join(staged_dir, model_filename), 'wb') as f:
                async for chunk in response.aiter_bytes():
                    await f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        raw_progress = self._build_download_progress('model', downloaded, total, has_weights=has_weights)
                        progress.progress = self._scale_progress(raw_progress, start=progress_start, end=progress_end)
                        self._update_download_status(progress_model_id, progress)
        progress.progress = self._scale_progress(
            self._build_download_progress('model', 1, 1, has_weights=has_weights),
            start=progress_start,
            end=progress_end,
        )
        self._update_download_status(progress_model_id, progress)

        # 2. Download weights (optional)
        if has_weights:
            weights_filename = f"{model_filename}.data"
            log.info("Downloading model weights", url=model_meta["weights_url"], staged_dir=staged_dir)
            async with client.stream("GET", model_meta["weights_url"], follow_redirects=True) as response:
                response.raise_for_status()
                total_header = response.headers.get("content-length")
                total = int(total_header) if total_header else 0
                downloaded = 0
                async with aiofiles.open(os.path.join(staged_dir, weights_filename), 'wb') as f:
                    async for chunk in response.aiter_bytes():
                        await f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            raw_progress = self._build_download_progress('weights', downloaded, total)
                            progress.progress = self._scale_progress(raw_progress, start=progress_start, end=progress_end)
                            self._update_download_status(progress_model_id, progress)
            progress.progress = self._scale_progress(
                self._build_download_progress('weights', 1, 1),
                start=progress_start,
                end=progress_end,
            )
            self._update_download_status(progress_model_id, progress)

        # 3. Download labels
        log.info("Downloading labels", url=model_meta["labels_url"], staged_dir=staged_dir)
        resp = await client.get(model_meta["labels_url"], follow_redirects=True)
        resp.raise_for_status()
        async with aiofiles.open(os.path.join(staged_dir, "labels.txt"), 'wb') as f:
            await f.write(resp.content)
        progress.progress = self._scale_progress(
            self._build_download_progress('labels', 1, 1, has_weights=has_weights),
            start=progress_start,
            end=progress_end,
        )
        self._update_download_status(progress_model_id, progress)

        # 4. Download sidecar model config (optional for backward compatibility, required when configured)
        model_config_url = str(model_meta.get("model_config_url") or "").strip()
        if model_config_url:
            try:
                log.info("Downloading model config", url=model_config_url, staged_dir=staged_dir)
                resp = await client.get(model_config_url, follow_redirects=True)
                resp.raise_for_status()
                parsed = json.loads(resp.content.decode("utf-8"))
                if not isinstance(parsed, dict):
                    raise ValueError("model_config.json did not contain a JSON object")
                self._write_model_config_payload(staged_dir, parsed)
            except Exception as exc:
                log.warning(
                    "Failed to download model config; synthesizing from registry metadata",
                    url=model_config_url,
                    staged_dir=staged_dir,
                    error=str(exc),
                )
                self._write_model_config_payload(staged_dir, self._build_model_config_payload(model_meta))

        self._validate_download_payload(model_meta, staged_dir, model_filename)

    async def download_model(self, model_id: str) -> bool:
        """Download a model from the registry (supports TFLite and ONNX)."""
        model_meta = self._get_registry_model_meta(model_id)
        if not model_meta:
            log.error("Model ID not found in registry", model_id=model_id)
            return False

        existing_status = self.active_downloads.get(model_id)
        if existing_status and existing_status[0].status in {"pending", "downloading"}:
            log.warning("Model download already in progress", model_id=model_id)
            return False

        download_units: list[tuple[str, dict[str, Any]]] = []
        if self._is_family_model(model_meta):
            for region in (model_meta.get("region_variants") or {}).keys():
                variant_meta = self._merge_family_variant_meta(model_meta, region=region)
                if variant_meta.get("download_url") == "pending" or variant_meta.get("labels_url") == "pending":
                    log.error("Family variant download URL not configured yet", model_id=model_id, region=region)
                    progress = DownloadProgress(
                        model_id=model_id,
                        status="error",
                        progress=0.0,
                        error=f"Model download URL not configured yet for region {region}",
                    )
                    self._update_download_status(model_id, progress)
                    return False
                download_units.append((region, variant_meta))
        else:
            if model_meta.get('download_url') == 'pending':
                log.error("Model download URL not configured yet", model_id=model_id)
                progress = DownloadProgress(
                    model_id=model_id,
                    status="error",
                    progress=0.0,
                    error="Model download URL not configured yet"
                )
                self._update_download_status(model_id, progress)
                return False
            download_units.append(("", dict(model_meta)))

        # Initialize progress
        progress = DownloadProgress(
            model_id=model_id,
            status="downloading",
            progress=0.0
        )
        self._update_download_status(model_id, progress)

        target_dir = os.path.join(MODELS_DIR, model_id)
        staged_dir = self._create_staging_dir(model_id)

        try:
            max_runtime = "onnx" if any(str(meta.get("runtime", "")) == "onnx" for _, meta in download_units) else "tflite"
            timeout = httpx.Timeout(30.0, read=300.0) if max_runtime == 'onnx' else httpx.Timeout(30.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                total_units = max(1, len(download_units))
                for idx, (region, unit_meta) in enumerate(download_units):
                    unit_start = (100.0 * idx) / total_units
                    unit_end = (100.0 * (idx + 1)) / total_units
                    unit_dir = os.path.join(staged_dir, region) if region else staged_dir
                    os.makedirs(unit_dir, exist_ok=True)
                    await self._download_payload_to_dir(
                        client=client,
                        model_meta=unit_meta,
                        staged_dir=unit_dir,
                        progress=progress,
                        progress_model_id=model_id,
                        progress_start=unit_start,
                        progress_end=unit_end,
                    )

                self._swap_model_dirs(staged_dir, target_dir)

                progress.progress = 100.0
                progress.status = "completed"
                self._update_download_status(model_id, progress)

            log.info("Model downloaded successfully", model_id=model_id, runtime=max_runtime)
            return True
        except Exception as e:
            log.error("Failed to download model", model_id=model_id, error=str(e))
            if model_id in self.active_downloads:
                progress.status = "error"
                progress.error = str(e)
                self._update_download_status(model_id, progress)
            shutil.rmtree(staged_dir, ignore_errors=True)
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
        spec = self.get_active_model_spec()
        return (
            str(spec.get("model_path") or "model.tflite"),
            str(spec.get("labels_path") or "labels.txt"),
            int(spec.get("input_size") or 224),
        )

model_manager = ModelManager()
