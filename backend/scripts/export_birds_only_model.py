import argparse
import json
from pathlib import Path
from typing import Any, Callable, Iterable

from app.utils.classifier_labels import normalize_classifier_labels


try:
    import torch
except ImportError:  # pragma: no cover - exercised only in lightweight test envs
    torch = None


def load_timm_model(model_name: str):
    try:
        import timm
    except ImportError as exc:  # pragma: no cover - depends on local ML env
        raise RuntimeError("timm is required to export birds-only models") from exc

    try:
        return timm.create_model(f"hf-hub:{model_name}", pretrained=True)
    except Exception:
        return timm.create_model(model_name, pretrained=True)


def _default_export_fn():
    if torch is None:
        raise RuntimeError("torch is required to export birds-only models")
    return torch.onnx.export


def _build_dummy_input(input_size: int):
    if torch is not None:
        return torch.randn(1, 3, input_size, input_size)

    class DummyInput:
        shape = (1, 3, input_size, input_size)

    return DummyInput()


def _extract_labels(model) -> list[str]:
    pretrained_cfg = getattr(model, "pretrained_cfg", None)
    if isinstance(pretrained_cfg, dict):
        label_names = pretrained_cfg.get("label_names")
        if isinstance(label_names, (list, tuple)):
            return [str(label).strip() for label in label_names if str(label).strip()]
    return []


def _build_export_kwargs() -> dict:
    return {
        "input_names": ["input"],
        "output_names": ["output"],
        "opset_version": 18,
        "dynamo": False,
        "dynamic_axes": {"input": {0: "batch"}, "output": {0: "batch"}},
    }


def _merge_config_dict(base: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if not isinstance(overrides, dict):
        return merged
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_config_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


_TIMM_CROP_MODE_TO_RESIZE_MODE = {
    "squash": "direct_resize",
    "center": "center_crop",
    "border": "center_crop",
}


def _resolve_resize_mode_from_timm(pretrained_cfg: dict[str, Any]) -> str:
    crop_mode = str(pretrained_cfg.get("crop_mode") or "").strip().lower()
    if crop_mode in _TIMM_CROP_MODE_TO_RESIZE_MODE:
        return _TIMM_CROP_MODE_TO_RESIZE_MODE[crop_mode]
    return "center_crop"


def _extract_model_config(
    model_name: str,
    model,
    input_size: int,
    model_config_overrides: dict[str, Any] | None = None,
) -> dict:
    pretrained_cfg = getattr(model, "pretrained_cfg", None)
    if not isinstance(pretrained_cfg, dict):
        pretrained_cfg = {}

    # Translate timm's `crop_mode` into our `resize_mode` so that models trained
    # with `squash` (direct resize, e.g. EVA-02, CLIP-init ConvNeXt) are not
    # silently served with a `center_crop` at inference.
    resize_mode = _resolve_resize_mode_from_timm(pretrained_cfg)

    base_config = {
        "model_id": model_name,
        "runtime": "onnx",
        "input_size": int(input_size),
        "preprocessing": {
            "color_space": "RGB",
            "resize_mode": resize_mode,
            "interpolation": str(pretrained_cfg.get("interpolation") or "bicubic"),
            "crop_pct": float(pretrained_cfg.get("crop_pct") or 1.0),
            "mean": list(pretrained_cfg.get("mean") or [0.485, 0.456, 0.406]),
            "std": list(pretrained_cfg.get("std") or [0.229, 0.224, 0.225]),
            "normalization": "float32",
        },
    }
    return _merge_config_dict(base_config, model_config_overrides)


def export_birds_only_model(
    model_name: str,
    output_dir: str | Path,
    input_size: int,
    labels: Iterable[str] | None = None,
    model_config_overrides: dict[str, Any] | None = None,
    loader: Callable[[str], object] = load_timm_model,
    export_fn=None,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    model_path = output_path / "model.onnx"
    labels_path = output_path / "labels.txt"
    model_config_path = output_path / "model_config.json"

    model = loader(model_name)
    if hasattr(model, "eval"):
        model = model.eval()

    resolved_labels = list(labels) if labels is not None else _extract_labels(model)
    normalized_labels = normalize_classifier_labels(str(label).strip() for label in resolved_labels if str(label).strip())
    if not normalized_labels:
        raise RuntimeError(f"No labels were provided for birds-only model: {model_name}")

    with labels_path.open("w", encoding="utf-8") as handle:
        for label in normalized_labels:
            handle.write(f"{label}\n")

    model_config = _extract_model_config(
        model_name,
        model,
        input_size,
        model_config_overrides=model_config_overrides,
    )
    model_config_path.write_text(json.dumps(model_config, indent=2, sort_keys=True), encoding="utf-8")

    export_callable = export_fn or _default_export_fn()
    dummy_input = _build_dummy_input(input_size)
    export_callable(model, dummy_input, str(model_path), **_build_export_kwargs())

    report = {
        "model_id": model_name,
        "model_path": str(model_path),
        "labels_path": str(labels_path),
        "model_config_path": str(model_config_path),
    }
    external_data_path = Path(f"{model_path}.data")
    if external_data_path.exists():
        report["external_data_path"] = str(external_data_path)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Export birds-only model to ONNX")
    parser.add_argument("--model", required=True, help="timm or Hugging Face model id")
    parser.add_argument("--output_dir", required=True, help="Output directory for model.onnx and labels.txt")
    parser.add_argument("--size", type=int, required=True, help="Input image size")
    parser.add_argument("--labels_file", help="Optional labels file to use instead of model metadata")
    parser.add_argument(
        "--model_config_overrides_file",
        help="Optional JSON file with model_config.json overrides",
    )
    args = parser.parse_args()

    labels = None
    if args.labels_file:
        labels = Path(args.labels_file).read_text(encoding="utf-8").splitlines()
    model_config_overrides = None
    if args.model_config_overrides_file:
        model_config_overrides = json.loads(
            Path(args.model_config_overrides_file).read_text(encoding="utf-8")
        )

    report = export_birds_only_model(
        model_name=args.model,
        output_dir=args.output_dir,
        input_size=args.size,
        labels=labels,
        model_config_overrides=model_config_overrides,
    )
    for key, value in report.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
