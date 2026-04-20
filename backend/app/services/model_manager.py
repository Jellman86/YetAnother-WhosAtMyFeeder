import errno
import hashlib
import json
import os
import shutil
import threading
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

_PERSISTENT_MODELS_DIR = "/data/models"
_PACKAGED_DEFAULT_MODEL_DIR = "/app/data/models"

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
        "input_size": 300,
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "direct_resize",
            "interpolation": "bilinear",
            "normalization": "uint8"
        },
        "tier": "fast",
        "taxonomy_scope": "system",
        "recommended_for": "Required dependency for crop-enabled bird classification.",
        "estimated_ram_mb": 256,
        "advanced_only": True,
        "sort_order": 5,
        "status": "stable",
        "notes": "Install this once to enable crop-assisted classification for models that opt into bird cropping."
    },
    {
        "id": "bird_crop_detector_accurate_yolox_tiny",
        "name": "Bird Crop Detector Accurate (YOLOX-Tiny)",
        "description": "Experimental higher-accuracy bird-localization detector tier for tighter crop proposals.",
        "architecture": "YOLOX-Tiny",
        "artifact_kind": "crop_detector",
        "file_size_mb": 19.3,
        "accuracy_tier": "Higher",
        "inference_speed": "Medium",
        "runtime": "onnx",
        "supported_inference_providers": ["cpu", "intel_cpu", "cuda"],
        "download_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/bird_crop_detector_accurate_yolox_tiny.onnx",
        "labels_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/bird_crop_detector_accurate_yolox_tiny_labels.txt",
        "model_config_url": "https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/download/models/bird_crop_detector_accurate_yolox_tiny_model_config.json",
        "sha256": "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7",
        "labels_sha256": "bd17f1ee35d5f3c862a4894605855abbb9dda4b0621fdb0ac4c2c8c7bb7e730a",
        "input_size": 416,
        "preprocessing": {
            "color_space": "BGR",
            "resize_mode": "letterbox",
            "interpolation": "bilinear",
            "normalization": "none",
            "pad_alignment": "top_left",
        },
        "detector": {
            "parser": "yolox",
            "box_format": "cxcywh",
            "target_class_id": 14,
            "confidence_mode": "object_times_class",
        },
        "tier": "accurate",
        "taxonomy_scope": "system",
        "recommended_for": "Optional higher-accuracy crop proposals when CPU budget allows.",
        "estimated_ram_mb": 512,
        "advanced_only": True,
        "sort_order": 6,
        "status": "experimental",
        "notes": "Experimental accurate crop-detector tier. Falls back to the fast SSD detector when unavailable."
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
        "advanced_only": True,
        "sort_order": 10,
        "status": "stable",
        "notes": "Legacy TFLite model — lower accuracy than the ONNX models. Kept for CPU-only environments with very limited RAM."
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
        "supported_inference_providers": ["cpu", "intel_cpu"],
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
                "supported_inference_providers": ["cpu", "intel_cpu"],
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
                    "resize_mode": "direct_resize",
                    "interpolation": "bilinear",
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
        "supported_inference_providers": ["cpu", "cuda", "intel_cpu"],
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
        "crop_generator": {
            "enabled": True,
        },
        "notes": "CPU and Intel CPU (OpenVINO) validated. Intel GPU is not supported: compiles and runs without crashing (static reshape applied) but produces entirely wrong predictions — logit spread ~3–7 vs ~15 on CPU, top-1 is wrong species. Root cause: numeric precision degradation in depthwise-conv + LayerNorm on this Intel iGPU. CUDA unverified. Higher-accuracy broad model. Uses a 10,000-class label space; lower confidence scores are normal — recommended threshold is 0.45."
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
        "crop_generator": {
            "enabled": True,
        },
        "notes": "CPU, Intel CPU (OpenVINO), and Intel GPU validated (OpenVINO 2025.4.1, static-batch reshape required). CUDA unverified. Exported from Birder pretrained weights (focalnet_b_lrf_intermediate-eu-common). 707 European species, 384px input."
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
        "supported_inference_providers": ["cpu", "cuda", "intel_cpu"],
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
        "recommended_for": "Global feeder setups or regions without a dedicated regional model (Asia, South America, Africa). Compact and fast.",
        "estimated_ram_mb": 512,
        "advanced_only": True,
        "sort_order": 13,
        "status": "experimental",
        "crop_generator": {
            "enabled": True,
        },
        "notes": "CPU and Intel CPU (OpenVINO) validated. Intel GPU produces non-finite outputs (NaN) and is not supported. CUDA unverified. 550 global bird species, uses ONNX external data file."
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
        "supported_inference_providers": ["cpu", "intel_cpu"],
        "download_url": "pending",
        "labels_url": "pending",
        "input_size": 224,
        "tier": "medium",
        "taxonomy_scope": "birds_only",
        "recommended_threshold": 0.65,
        "recommended_for": "Regional birds-only medium model with auto region selection.",
        "estimated_ram_mb": 1536,
        "advanced_only": False,
        "sort_order": 18,
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
                "supported_inference_providers": ["cpu", "intel_cpu", "intel_gpu"],
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
                    "resize_mode": "direct_resize",
                    "interpolation": "bilinear",
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
        "supported_inference_providers": ["cpu", "cuda", "intel_cpu"],
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
        "recommended_for": "Best all-around wildlife model — strong accuracy across 10,000 species at moderate speed. Recommended default for most setups.",
        "estimated_ram_mb": 1536,
        "advanced_only": False,
        "sort_order": 17,
        "status": "experimental",
        "crop_generator": {
            "enabled": True,
        },
        "notes": "CPU and Intel CPU (OpenVINO) validated. Intel GPU produces non-finite outputs (NaN) with this RoPE-attention architecture and is not supported. CUDA unverified. Uses a 10,000-class label space; recommended threshold is 0.45."
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
        "supported_inference_providers": ["cpu", "cuda", "intel_cpu"],
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
        "crop_generator": {
            "enabled": True,
        },
        "notes": "Elite accuracy model. CPU and Intel CPU (OpenVINO) validated. Intel GPU causes a fatal process crash (CL_OUT_OF_RESOURCES / clWaitForEvents -14) confirmed on OpenVINO 2024.6, 2025.4, and 2026.0 — do not use with Intel GPU. CUDA unverified. Uses a 10,000-class label space; recommended threshold is 0.45."
    }
]

def _configured_models_dir() -> str:
    return str(os.getenv("MODEL_DIR") or "").strip()


def _is_packaged_legacy_models_dir(path: str) -> bool:
    return os.path.abspath(path) == os.path.abspath(_PACKAGED_DEFAULT_MODEL_DIR)


def _should_prefer_persistent_models_dir(configured_dir: str) -> bool:
    return bool(configured_dir) and _is_packaged_legacy_models_dir(configured_dir) and os.path.isdir("/data")


def _resolve_models_dir() -> str:
    """Return a writable models directory for the current runtime."""
    configured_dir = _configured_models_dir()
    fallback_dir = os.path.join(os.path.dirname(__file__), "../../data/models")
    candidates = []

    if os.path.isdir("/data"):
        candidates.append(_PERSISTENT_MODELS_DIR)
    if configured_dir and not _should_prefer_persistent_models_dir(configured_dir):
        candidates.insert(0, configured_dir)
    elif configured_dir:
        # Older backend images set MODEL_DIR=/app/data/models, which writes into
        # the container filesystem instead of the mounted /data volume.
        candidates.append(configured_dir)
    candidates.append(fallback_dir)

    seen: set[str] = set()
    for candidate in candidates:
        normalized = os.path.abspath(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            os.makedirs(normalized, exist_ok=True)
            return normalized
        except OSError:
            continue
    raise OSError("Unable to resolve a writable models directory")


def _dir_has_entries(path: str) -> bool:
    try:
        with os.scandir(path) as entries:
            return any(True for _ in entries)
    except FileNotFoundError:
        return False


def _maybe_migrate_legacy_models_dir(target_dir: str) -> None:
    configured_dir = _configured_models_dir()
    if not configured_dir or not _is_packaged_legacy_models_dir(configured_dir):
        return
    if not os.path.isdir("/data"):
        return

    legacy_dir = os.path.abspath(configured_dir)
    target_dir = os.path.abspath(target_dir)
    if legacy_dir == target_dir or not os.path.isdir(legacy_dir):
        return
    if not _dir_has_entries(legacy_dir):
        return

    os.makedirs(target_dir, exist_ok=True)

    migrated_entries: list[str] = []
    skipped_entries: list[str] = []
    try:
        with os.scandir(legacy_dir) as entries:
            for entry in entries:
                source_path = entry.path
                destination_path = os.path.join(target_dir, entry.name)
                if os.path.exists(destination_path):
                    skipped_entries.append(entry.name)
                    continue
                shutil.move(source_path, destination_path)
                migrated_entries.append(entry.name)
    except Exception:
        log.exception(
            "Failed migrating legacy model directory contents into persistent models dir",
            legacy_models_dir=legacy_dir,
            persistent_models_dir=target_dir,
            migrated_entries=migrated_entries,
            skipped_entries=skipped_entries,
        )
        raise

    if migrated_entries:
        log.warning(
            "Migrated legacy packaged model directory entries into persistent /data/models",
            legacy_models_dir=legacy_dir,
            persistent_models_dir=target_dir,
            migrated_entries=migrated_entries,
            skipped_entries=skipped_entries,
        )
    elif skipped_entries:
        log.warning(
            "Skipped legacy packaged model directory migration because all entries already exist in persistent /data/models",
            legacy_models_dir=legacy_dir,
            persistent_models_dir=target_dir,
            skipped_entries=skipped_entries,
        )


MODELS_DIR = _resolve_models_dir()
_maybe_migrate_legacy_models_dir(MODELS_DIR)

_PERSISTENT_MODELS_PREFIX = _PERSISTENT_MODELS_DIR
if not MODELS_DIR.startswith(_PERSISTENT_MODELS_PREFIX):
    import warnings
    warnings.warn(
        f"Model directory resolved to '{MODELS_DIR}' which is inside the container "
        f"image filesystem. Downloaded models will be lost on container restart. "
        f"Mount a persistent volume at /data or set MODEL_DIR to a writable host path.",
        stacklevel=2,
    )

class ModelManager:
    def __init__(self):
        # Ensure models directory exists
        os.makedirs(MODELS_DIR, exist_ok=True)
        self._active_model_lock = threading.Lock()
        self.active_model_id = self._load_active_model_id()
        self.active_downloads: Dict[str, tuple[DownloadProgress, datetime]] = {}
        # (model_dir, tuple(sorted(unsupported_providers))) → already-logged marker.
        # get_active_model_spec runs on every inference path; without deduping,
        # the same "unsupported inference providers" warning was emitted on
        # every detection, spamming logs and the diagnostic bundle.
        self._unsupported_provider_warn_cache: set[tuple[str, tuple[str, ...]]] = set()

    def _load_active_model_id(self) -> str:
        """Load the active model ID from a local config file."""
        config_path = os.path.join(MODELS_DIR, "active_model.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    data = json.load(f)
                    model_id = data.get("active_model_id", "")
                    result = str(model_id or "").strip()
                    if result:
                        return result
            except Exception:
                pass
        # No persisted selection — fall back to the configured default
        config_default = str(getattr(settings.classification, "model", "") or "").strip()
        return config_default or "mobilenet_v2_birds"

    def _save_active_model_id(self, model_id: str):
        """Save the active model ID (thread-safe)."""
        config_path = os.path.join(MODELS_DIR, "active_model.json")
        with self._active_model_lock:
            with open(config_path, 'w') as f:
                json.dump({"active_model_id": model_id}, f)
            self.active_model_id = model_id

    def _get_registry_model_meta(self, model_id: str) -> Optional[dict[str, Any]]:
        return next((m for m in REMOTE_REGISTRY if m["id"] == model_id), None)

    def _crop_detector_id_for_tier(self, tier: Optional[str] = None) -> str:
        normalized = str(
            tier
            or getattr(settings.classification, "bird_crop_detector_tier", "fast")
            or "fast"
        ).strip().lower()
        return "bird_crop_detector_accurate_yolox_tiny" if normalized == "accurate" else "bird_crop_detector"

    def get_crop_detector_meta(self, tier: Optional[str] = None) -> Optional[dict[str, Any]]:
        return self._get_registry_model_meta(self._crop_detector_id_for_tier(tier))

    def _build_crop_detector_spec(self, model_id: str, *, selected_tier: str, resolved_tier: str, reason_override: Optional[str] = None) -> dict[str, Any]:
        meta = dict(self._get_registry_model_meta(model_id) or {})
        model_dir = os.path.join(MODELS_DIR, model_id)
        model_path = os.path.join(model_dir, "model.onnx")
        labels_path = os.path.join(model_dir, "labels.txt")
        config_path = os.path.join(model_dir, "model_config.json")
        installed = os.path.exists(model_path)
        healthy = installed and os.path.exists(config_path)
        return {
            "model_id": model_id,
            "artifact_kind": str(meta.get("artifact_kind") or "crop_detector"),
            "selected_tier": selected_tier,
            "resolved_tier": resolved_tier,
            "installed": installed,
            "healthy": healthy,
            "enabled_for_runtime": healthy,
            "reason": reason_override or ("ready" if healthy else ("config_missing" if installed else "not_installed")),
            "model_path": model_path,
            "labels_path": labels_path,
            "model_config_path": config_path,
            "metadata": meta,
        }

    def get_crop_detector_spec(self, selected_tier: Optional[str] = None) -> dict[str, Any]:
        normalized_selected_tier = str(
            selected_tier
            or getattr(settings.classification, "bird_crop_detector_tier", "fast")
            or "fast"
        ).strip().lower()
        if normalized_selected_tier not in {"fast", "accurate"}:
            normalized_selected_tier = "fast"

        requested_model_id = self._crop_detector_id_for_tier(normalized_selected_tier)
        requested_spec = self._build_crop_detector_spec(
            requested_model_id,
            selected_tier=normalized_selected_tier,
            resolved_tier=normalized_selected_tier,
        )
        if normalized_selected_tier != "accurate" or requested_spec["healthy"]:
            return requested_spec

        fallback_spec = self._build_crop_detector_spec(
            "bird_crop_detector",
            selected_tier="accurate",
            resolved_tier="fast",
            reason_override="fallback_fast",
        )
        fallback_spec["enabled_for_runtime"] = bool(fallback_spec["healthy"])
        return fallback_spec

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
        for checksum_key in ("sha256", "labels_sha256", "weights_sha256"):
            checksum_value = str(model_meta.get(checksum_key) or "").strip()
            if checksum_value:
                payload[checksum_key] = checksum_value
        detector = model_meta.get("detector")
        if isinstance(detector, dict) and detector:
            payload["detector"] = dict(detector)
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

    def _sanitize_installed_inference_providers(
        self,
        *,
        installed_providers: list[Any],
        registry_providers: list[Any],
        model_dir: str,
    ) -> tuple[list[str], list[str]]:
        allowed_registry: list[str] = []
        allowed_registry_set: set[str] = set()
        for provider in registry_providers:
            normalized = str(provider or "").strip().lower()
            if not normalized or normalized in allowed_registry_set:
                continue
            allowed_registry.append(normalized)
            allowed_registry_set.add(normalized)

        installed_normalized: list[str] = []
        seen_installed: set[str] = set()
        for provider in installed_providers:
            normalized = str(provider or "").strip().lower()
            if not normalized or normalized in seen_installed:
                continue
            installed_normalized.append(normalized)
            seen_installed.add(normalized)

        supported = [provider for provider in installed_normalized if provider in allowed_registry_set]
        unsupported = [provider for provider in installed_normalized if provider not in allowed_registry_set]

        if not unsupported:
            return supported, []

        unsupported_text = ", ".join(unsupported)
        warn_key = (model_dir, tuple(sorted(unsupported)))
        already_warned = warn_key in self._unsupported_provider_warn_cache
        if not already_warned:
            self._unsupported_provider_warn_cache.add(warn_key)
        if supported:
            warning = (
                "Installed model_config.json advertised providers no longer supported by the current "
                f"registry and they were ignored: {unsupported_text}"
            )
            if not already_warned:
                log.warning(
                    "Installed model config advertised unsupported inference providers; ignoring extras",
                    model_dir=model_dir,
                    unsupported_providers=unsupported,
                    registry_supported_providers=allowed_registry,
                    retained_providers=supported,
                )
            return supported, [warning]

        warning = (
            "Installed model_config.json only advertised providers no longer supported by the current "
            f"registry: {unsupported_text}. Falling back to registry-supported providers."
        )
        if not already_warned:
            log.warning(
                "Installed model config advertised only unsupported inference providers; falling back to registry providers",
                model_dir=model_dir,
                unsupported_providers=unsupported,
                registry_supported_providers=allowed_registry,
            )
        return list(allowed_registry), [warning]

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
        model_config_warnings = list(merged.get("model_config_warnings") or [])
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
            sanitized_providers, provider_warnings = self._sanitize_installed_inference_providers(
                installed_providers=providers,
                registry_providers=list(spec.get("supported_inference_providers") or []),
                model_dir=model_dir,
            )
            if sanitized_providers:
                merged["supported_inference_providers"] = sanitized_providers
            if provider_warnings:
                model_config_warnings.extend(provider_warnings)
        if model_config_warnings:
            merged["model_config_warnings"] = model_config_warnings
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

        log.warning(
            "Active model not found in registry or on disk, falling back to bundled TFLite model",
            active_model_id=model_id,
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

    @staticmethod
    def _verify_checksum(file_path: str, expected_sha256: str) -> None:
        """Verify a file's SHA-256 digest matches the expected value.

        Raises RuntimeError on mismatch. Uses 64 KB chunks to avoid loading
        large model files fully into memory.
        """
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        actual = h.hexdigest()
        if actual != expected_sha256.lower():
            raise RuntimeError(
                f"Checksum mismatch for {os.path.basename(file_path)}: "
                f"expected {expected_sha256.lower()}, got {actual}"
            )

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

        # Build checksum map starting from registry values, then layer in values
        # from the downloaded model_config.json. Config-file values take precedence
        # so that model refreshes on the release page are reflected without a code deploy.
        checksums: dict[str, str | None] = {
            "sha256": model_meta.get("sha256"),
            "labels_sha256": model_meta.get("labels_sha256"),
            "weights_sha256": model_meta.get("weights_sha256"),
        }
        config_path = os.path.join(staged_dir, "model_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    config_data = json.load(f)
                for key in ("sha256", "labels_sha256", "weights_sha256"):
                    if config_data.get(key):
                        checksums[key] = config_data[key]
            except Exception as exc:
                log.warning("Could not read checksums from model_config.json", error=str(exc))

        checksum_map = {
            model_filename: checksums["sha256"],
            "labels.txt": checksums["labels_sha256"],
            f"{model_filename}.data": checksums["weights_sha256"],
        }
        for filename, expected in checksum_map.items():
            file_path = os.path.join(staged_dir, filename)
            if not os.path.exists(file_path):
                continue
            if expected:
                log.info("Verifying checksum", filename=filename)
                self._verify_checksum(file_path, expected)
                log.info("Checksum verified", filename=filename)
            else:
                log.warning(
                    "No checksum configured for downloaded file — integrity not verified",
                    filename=filename,
                    model_id=model_meta.get("id"),
                )

    @staticmethod
    def _rename_or_move(src: str, dst: str) -> None:
        """Rename src to dst, falling back to copy+delete on cross-device (EXDEV) errors."""
        try:
            os.rename(src, dst)
        except OSError as exc:
            if exc.errno != errno.EXDEV:
                raise
            try:
                shutil.copytree(src, dst)
            except Exception:
                shutil.rmtree(dst, ignore_errors=True)  # remove partial copy so caller can roll back
                raise
            shutil.rmtree(src, ignore_errors=True)

    def _swap_model_dirs(self, staged_dir: str, target_dir: str) -> None:
        had_existing = os.path.isdir(target_dir)
        backup_dir = f"{target_dir}.backup-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"

        if had_existing:
            self._rename_or_move(target_dir, backup_dir)

        try:
            self._rename_or_move(staged_dir, target_dir)
        except Exception:
            if had_existing and os.path.isdir(backup_dir) and not os.path.exists(target_dir):
                try:
                    self._rename_or_move(backup_dir, target_dir)
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

            # If the downloaded model is the currently active selection, reload the
            # classifier immediately so the new model takes effect without a restart.
            if model_id == self.active_model_id:
                try:
                    from app.services.classifier_service import get_classifier
                    classifier = get_classifier()
                    log.info("Active model downloaded; reloading classifier", model_id=model_id)
                    await classifier.reload_bird_model()
                except Exception as reload_exc:
                    log.warning(
                        "Classifier reload after download failed",
                        model_id=model_id,
                        error=str(reload_exc),
                    )

            return True
        except Exception as e:
            log.error("Failed to download model", model_id=model_id, error=str(e))
            if model_id in self.active_downloads:
                progress.status = "error"
                progress.error = str(e)
                self._update_download_status(model_id, progress)
            shutil.rmtree(staged_dir, ignore_errors=True)
            return False

    async def _fetch_and_write_model_config(
        self,
        model_meta: dict[str, Any],
        model_dir: str,
    ) -> None:
        """Download model_config.json from model_config_url, or synthesize from registry."""
        model_config_url = str(model_meta.get("model_config_url") or "").strip()
        if model_config_url:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(model_config_url, follow_redirects=True)
                    resp.raise_for_status()
                    parsed = json.loads(resp.content.decode("utf-8"))
                    if not isinstance(parsed, dict):
                        raise ValueError("model_config.json response was not a JSON object")
                    self._write_model_config_payload(model_dir, parsed)
                    log.info("Model config fetched and written", model_dir=model_dir)
                    return
            except Exception as exc:
                log.warning(
                    "Failed to fetch model config; synthesizing from registry",
                    model_dir=model_dir,
                    url=model_config_url,
                    error=str(exc),
                )
        self._write_model_config_payload(model_dir, self._build_model_config_payload(model_meta))
        log.info("Model config synthesized from registry", model_dir=model_dir)

    async def ensure_installed_model_configs(self) -> None:
        """Write model_config.json for every installed model that is missing one.

        Called once at startup to handle upgrades from versions that did not
        write the model_config.json sidecar during download.  Missing sidecars
        are fetched from model_config_url or synthesized from the in-code
        registry as a fallback.
        """
        if not os.path.isdir(MODELS_DIR):
            return
        for entry in os.scandir(MODELS_DIR):
            if not entry.is_dir():
                continue
            model_meta = self._get_registry_model_meta(entry.name)
            if not model_meta:
                continue  # Not in registry (backup dirs, active_model.json, etc.)
            if self._is_family_model(model_meta):
                variants = model_meta.get("region_variants") or {}
                for region in variants:
                    variant_dir = os.path.join(entry.path, region)
                    if not os.path.isdir(variant_dir):
                        continue
                    # Only act on variants that have the model weights on disk
                    runtime = str(
                        (variants[region] or {}).get("runtime")
                        or model_meta.get("runtime")
                        or "tflite"
                    )
                    if not os.path.exists(os.path.join(variant_dir, self._model_filename_for_runtime(runtime))):
                        continue
                    if not os.path.exists(os.path.join(variant_dir, "model_config.json")):
                        merged = self._merge_family_variant_meta(model_meta, region=region)
                        await self._fetch_and_write_model_config(merged, variant_dir)
            else:
                runtime = str(model_meta.get("runtime") or "tflite")
                if not os.path.exists(os.path.join(entry.path, self._model_filename_for_runtime(runtime))):
                    continue
                if not os.path.exists(os.path.join(entry.path, "model_config.json")):
                    await self._fetch_and_write_model_config(model_meta, entry.path)

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
