import argparse
from pathlib import Path
from typing import Callable, Iterable


try:
    import torch
except ImportError:  # pragma: no cover - exercised only in lightweight test envs
    torch = None


def normalize_birder_model_id(model_id: str) -> str:
    if model_id.startswith('birder-project/'):
        return model_id.split('/', 1)[1]
    return model_id


def default_birder_cache_dir(output_dir: str | Path) -> Path:
    return Path(output_dir).parent / '.birder-cache'


def load_birder_model(model_id: str, *, cache_dir: str | Path | None = None):
    import birder

    model, model_info = birder.load_pretrained_model(
        normalize_birder_model_id(model_id),
        dst=cache_dir,
        inference=True,
    )

    labels = []
    class_to_idx = getattr(model_info, "class_to_idx", None)
    if isinstance(class_to_idx, dict) and class_to_idx:
        labels = [label for label, _ in sorted(class_to_idx.items(), key=lambda item: item[1])]
    else:
        labels_attr = getattr(model_info, "labels", None)
        if isinstance(labels_attr, (list, tuple)):
            labels = list(labels_attr)

    if not labels:
        raise RuntimeError(f"Could not extract labels for Birder model: {model_id}")

    return model, labels


def _default_export_fn():
    if torch is None:
        raise RuntimeError("torch is required to export Birder models")
    return torch.onnx.export


def _build_dummy_input(input_size: int):
    if torch is not None:
        return torch.randn(1, 3, input_size, input_size)

    class DummyInput:
        shape = (1, 3, input_size, input_size)

    return DummyInput()


def export_birder_model(
    model_id: str,
    output_dir: str | Path,
    input_size: int,
    loader: Callable[[str], tuple[object, Iterable[str]]] = load_birder_model,
    export_fn=None,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    model_path = output_path / 'model.onnx'
    labels_path = output_path / 'labels.txt'

    normalized_model_id = normalize_birder_model_id(model_id)
    cache_dir = default_birder_cache_dir(output_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    model, labels = loader(normalized_model_id, cache_dir=cache_dir)
    if hasattr(model, 'eval'):
        model = model.eval()

    labels = [str(label).strip() for label in labels if str(label).strip()]
    if not labels:
        raise RuntimeError(f"No labels were provided for Birder model: {model_id}")

    with labels_path.open('w', encoding='utf-8') as handle:
        for label in labels:
            handle.write(f'{label}\n')

    export_callable = export_fn or _default_export_fn()
    dummy_input = _build_dummy_input(input_size)
    export_callable(
        model,
        dummy_input,
        str(model_path),
        input_names=['input'],
        output_names=['output'],
        opset_version=18,
        dynamo=False,
        dynamic_axes={'input': {0: 'batch'}, 'output': {0: 'batch'}},
    )

    return {
        'model_path': str(model_path),
        'labels_path': str(labels_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Export Birder model to ONNX')
    parser.add_argument('--model', required=True, help='Birder or Hugging Face model id')
    parser.add_argument('--output_dir', required=True, help='Output directory for model.onnx and labels.txt')
    parser.add_argument('--size', type=int, required=True, help='Input image size')
    args = parser.parse_args()

    report = export_birder_model(args.model, args.output_dir, args.size)
    for key, value in report.items():
        print(f'{key}: {value}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
