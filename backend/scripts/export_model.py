import argparse

from scripts.export_birds_only_model import export_birds_only_model


def export_model(model_name: str, output_dir: str, input_size: int = 336, labels_file: str | None = None):
    labels = None
    if labels_file:
        with open(labels_file, "r", encoding="utf-8") as handle:
            labels = handle.read().splitlines()

    return export_birds_only_model(
        model_name=model_name,
        output_dir=output_dir,
        input_size=input_size,
        labels=labels,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export model to ONNX")
    parser.add_argument("--model", type=str, required=True, help="timm or Hugging Face model name")
    parser.add_argument("--output_dir", type=str, required=True, help="Output directory")
    parser.add_argument("--size", type=int, default=336, help="Input size")
    parser.add_argument("--labels_file", type=str, help="Optional labels file")

    args = parser.parse_args()

    report = export_model(args.model, args.output_dir, args.size, args.labels_file)
    for key, value in report.items():
        print(f"{key}: {value}")
