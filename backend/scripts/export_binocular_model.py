import argparse
from pathlib import Path
from typing import Callable

from app.utils.classifier_labels import normalize_classifier_labels

try:
    import torch
except ImportError:  # pragma: no cover - exercised only in lightweight test envs
    torch = None


_DEFAULT_REPO_ID = "jiujiuche/binocular"
_DEFAULT_FILENAME = "artifacts/dinov2_vitb14_nabirds.pth"


if torch is not None:
    import torch.nn as nn

    class BinocularEncoderWrapper(nn.Module):
        def __init__(self, encoder):
            super().__init__()
            self.model = encoder

    class BinocularClassifierWrapper(nn.Module):
        def __init__(self, linear_layer):
            super().__init__()
            self.classifier = linear_layer

    class BinocularBirdModel(nn.Module):
        def __init__(
            self,
            *,
            encoder_name: str,
            num_classes: int,
            encoder_loader: Callable[[str, str], object],
        ):
            super().__init__()
            encoder = encoder_loader("facebookresearch/dinov2", encoder_name)
            self.encoder = BinocularEncoderWrapper(encoder)
            self.classifier = BinocularClassifierWrapper(
                nn.Sequential(nn.Linear(768, num_classes))
            )

        def forward(self, x):
            return self.classifier.classifier(self.encoder.model(x))
else:
    class BinocularEncoderWrapper:
        def __init__(self, encoder):
            self.model = encoder

    class BinocularClassifierWrapper:
        def __init__(self, linear_layer):
            self.classifier = linear_layer


def _default_checkpoint_loader(*, repo_id: str, filename: str) -> str:
    from huggingface_hub import hf_hub_download

    return hf_hub_download(repo_id=repo_id, filename=filename)


def _default_torch_load(path: str, map_location: str = "cpu", weights_only: bool = False):
    if torch is None:
        raise RuntimeError("torch is required to load Binocular checkpoints")
    return torch.load(path, map_location=map_location, weights_only=weights_only)


def _default_model_builder(*, encoder_name: str, num_classes: int, encoder_loader):
    if torch is None:
        raise RuntimeError("torch is required to build Binocular export model")
    return BinocularBirdModel(
        encoder_name=encoder_name,
        num_classes=num_classes,
        encoder_loader=encoder_loader,
    )


def _default_encoder_loader(repo: str, model: str):
    if torch is None:
        raise RuntimeError("torch is required to load Binocular encoders")
    return torch.hub.load(repo, model)


def _default_export_fn():
    if torch is None:
        raise RuntimeError("torch is required to export Binocular models")
    return torch.onnx.export


def _build_dummy_input(input_size: int):
    if torch is not None:
        return torch.randn(1, 3, input_size, input_size)

    class DummyInput:
        shape = (1, 3, input_size, input_size)

    return DummyInput()


def _build_export_kwargs() -> dict:
    return {
        "input_names": ["input"],
        "output_names": ["output"],
        "opset_version": 18,
        "dynamo": True,
    }


def load_binocular_model(
    *,
    repo_id: str = _DEFAULT_REPO_ID,
    filename: str = _DEFAULT_FILENAME,
    checkpoint_loader: Callable[..., str] = _default_checkpoint_loader,
    torch_load: Callable[..., dict] = _default_torch_load,
    model_builder: Callable[..., object] = _default_model_builder,
    encoder_loader: Callable[[str, str], object] = _default_encoder_loader,
):
    checkpoint_path = checkpoint_loader(repo_id=repo_id, filename=filename)
    checkpoint = torch_load(checkpoint_path, map_location="cpu", weights_only=False)
    config = dict(checkpoint.get("config") or {})
    class_names = list(checkpoint.get("class_names") or [])
    if not class_names:
        raise RuntimeError(f"No class names were found in Binocular checkpoint: {repo_id}/{filename}")

    encoder_name = str(config.get("encoder_name") or "dinov2_vitb14")
    model = model_builder(
        encoder_name=encoder_name,
        num_classes=len(class_names),
        encoder_loader=encoder_loader,
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    return model, class_names, config


def export_binocular_model(
    *,
    repo_id: str = _DEFAULT_REPO_ID,
    filename: str = _DEFAULT_FILENAME,
    output_dir: str | Path,
    loader: Callable[..., tuple[object, list[str], dict]] = load_binocular_model,
    export_fn=None,
) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    model_path = output_path / "model.onnx"
    labels_path = output_path / "labels.txt"

    model, labels, config = loader(repo_id=repo_id, filename=filename)
    if hasattr(model, "eval"):
        model = model.eval()

    normalized_labels = normalize_classifier_labels(str(label).strip() for label in labels if str(label).strip())
    if not normalized_labels:
        raise RuntimeError(f"No labels were provided for Binocular model: {repo_id}")

    with labels_path.open("w", encoding="utf-8") as handle:
        for label in normalized_labels:
            handle.write(f"{label}\n")

    input_size = int(config.get("image_size") or 224)
    export_callable = export_fn or _default_export_fn()
    dummy_input = _build_dummy_input(input_size)
    export_callable(model, dummy_input, str(model_path), **_build_export_kwargs())

    return {
        "model_id": repo_id,
        "model_path": str(model_path),
        "labels_path": str(labels_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Binocular NABirds model to ONNX")
    parser.add_argument("--repo_id", default=_DEFAULT_REPO_ID, help="Hugging Face repo id")
    parser.add_argument("--filename", default=_DEFAULT_FILENAME, help="Checkpoint filename inside the repo")
    parser.add_argument("--output_dir", required=True, help="Output directory for model.onnx and labels.txt")
    args = parser.parse_args()

    report = export_binocular_model(
        repo_id=args.repo_id,
        filename=args.filename,
        output_dir=args.output_dir,
    )
    for key, value in report.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
