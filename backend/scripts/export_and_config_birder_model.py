"""Export a Birder pretrained model to ONNX and write a model_config.json sidecar.

Usage:
    python scripts/export_and_config_birder_model.py \
        --model focalnet_b_lrf_intermediate-eu-common \
        --output_dir data/models/eu_medium_focalnet_b \
        --taxonomy_scope birds_only

The script:
  1. Downloads the pretrained .pt weights via birder (cached in data/models/.birder-cache/)
  2. Extracts rgb_stats (mean/std), input resolution, and class labels from the checkpoint
  3. Exports to ONNX
  4. Writes model_config.json with all preprocessing parameters
  5. Writes labels.txt with normalized species labels
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure the backend package is importable when running this script directly
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

try:
    import torch
except ImportError:
    torch = None


def _normalize_model_id(model_id: str) -> str:
    if model_id.startswith("birder-project/"):
        return model_id.split("/", 1)[1]
    return model_id


def _build_export_kwargs(model_id: str) -> dict:
    # Models that use ops (e.g. rms_norm) unsupported in opset 18 — require dynamo export
    _DYNAMO_MODELS = {
        "vit_reg4_m16_rms_avg_i-jepa-inat21-256px",
        "flexivit_reg1_s16_rms_ls_dino-v2-il-all",
    }
    normalized = _normalize_model_id(model_id)
    if normalized in _DYNAMO_MODELS:
        return {
            "input_names": ["input"],
            "output_names": ["output"],
            "opset_version": 20,
            "dynamo": True,
            "external_data": True,
        }
    return {
        "input_names": ["input"],
        "output_names": ["output"],
        "opset_version": 18,
        "dynamo": False,
        "dynamic_axes": {"input": {0: "batch"}, "output": {0: "batch"}},
    }


def export_and_config(
    model_id: str,
    output_dir: str | Path,
    *,
    taxonomy_scope: str = "birds_only",
) -> dict:
    import birder
    from app.utils.classifier_labels import normalize_classifier_labels

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    normalized_id = _normalize_model_id(model_id)
    cache_dir = output_path.parent / ".birder-cache" / f"{normalized_id}.pt"
    cache_dir.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading {normalized_id} (cache: {cache_dir}) ...")
    model, model_info = birder.load_pretrained_model(
        normalized_id,
        dst=cache_dir,
        inference=True,
    )
    model = model.eval()

    # --- Extract labels ---
    class_to_idx = getattr(model_info, "class_to_idx", None)
    if isinstance(class_to_idx, dict) and class_to_idx:
        labels_raw = [lbl for lbl, _ in sorted(class_to_idx.items(), key=lambda kv: kv[1])]
    else:
        labels_raw = list(getattr(model_info, "labels", None) or [])
    if not labels_raw:
        raise RuntimeError(f"No labels found for {model_id}")

    labels = normalize_classifier_labels(str(label).strip() for label in labels_raw if str(label).strip())
    labels_path = output_path / "labels.txt"
    labels_path.write_text("\n".join(labels) + "\n", encoding="utf-8")
    print(f"  {len(labels)} labels written to {labels_path}")

    # --- Extract preprocessing stats ---
    rgb_stats = getattr(model_info, "rgb_stats", None)
    signature = getattr(model_info, "signature", None)

    # rgb_stats is typically {"mean": [r,g,b], "std": [r,g,b]}
    if isinstance(rgb_stats, dict):
        mean = rgb_stats.get("mean", [0.485, 0.456, 0.406])
        std = rgb_stats.get("std", [0.229, 0.224, 0.225])
    else:
        print("  WARNING: rgb_stats not found in model_info; using ImageNet defaults")
        mean = [0.485, 0.456, 0.406]
        std = [0.229, 0.224, 0.225]

    # Input size from signature or manifest
    input_size: int = 224
    if isinstance(signature, dict):
        inputs = signature.get("inputs", [])
        if inputs:
            shape = inputs[0].get("data_shape", [])
            if len(shape) >= 4:
                input_size = int(shape[-1])
    if input_size == 224:
        # Fall back to manifest resolution
        from birder.model_registry.model_registry import registry
        meta = registry.get_pretrained_metadata(normalized_id)
        if meta and hasattr(meta, "resolution"):
            res = meta.resolution
            if isinstance(res, (list, tuple)) and res:
                input_size = int(res[-1])

    print(f"  input_size={input_size}, mean={mean}, std={std}")

    # --- Export ONNX ---
    model_path = output_path / "model.onnx"
    dummy_input = torch.randn(1, 3, input_size, input_size)
    kwargs = _build_export_kwargs(normalized_id)
    print(f"  Exporting ONNX to {model_path} ...")
    torch.onnx.export(model, dummy_input, str(model_path), **kwargs)
    onnx_size_mb = model_path.stat().st_size / 1024 / 1024

    # Check for external data sidecar
    external_data = Path(f"{model_path}.data")
    if external_data.exists():
        onnx_size_mb += external_data.stat().st_size / 1024 / 1024
        print(f"  External data: {external_data}")

    print(f"  ONNX size: {onnx_size_mb:.1f} MB")

    # --- Write model_config.json ---
    config = {
        "input_size": input_size,
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": "center_crop",
            "interpolation": "bicubic",
            "crop_pct": 1.0,
            "mean": [round(v, 6) for v in mean],
            "std": [round(v, 6) for v in std],
            "normalization": "float32",
        },
        "taxonomy_scope": taxonomy_scope,
        "num_classes": len(labels),
        "source_model_id": normalized_id,
    }
    config_path = output_path / "model_config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"  model_config.json written to {config_path}")

    return {
        "model_path": str(model_path),
        "labels_path": str(labels_path),
        "config_path": str(config_path),
        "input_size": input_size,
        "num_classes": len(labels),
        "mean": mean,
        "std": std,
        "file_size_mb": round(onnx_size_mb, 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a Birder pretrained model to ONNX with model_config.json sidecar"
    )
    parser.add_argument("--model", required=True, help="Birder model alias (e.g. focalnet_b_lrf_intermediate-eu-common)")
    parser.add_argument("--output_dir", required=True, help="Output directory")
    parser.add_argument(
        "--taxonomy_scope",
        default="birds_only",
        choices=["birds_only", "wildlife_wide"],
        help="Taxonomy scope written into model_config.json",
    )
    args = parser.parse_args()

    if torch is None:
        print("ERROR: torch is required. Install it with: pip install torch", file=sys.stderr)
        return 1

    result = export_and_config(args.model, args.output_dir, taxonomy_scope=args.taxonomy_scope)
    print("\nExport complete:")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
