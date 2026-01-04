import torch
import timm
import argparse
from pathlib import Path

def export_model(model_name: str, output_dir: str, input_size: int = 336):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    model_path = output_dir / "model.onnx"
    labels_path = output_dir / "labels.txt"

    print(f"Loading model: {model_name}...")
    try:
        model = timm.create_model(f"hf-hub:{model_name}", pretrained=True)
    except Exception:
        model = timm.create_model(model_name, pretrained=True)
        
    model.eval()

    # Get labels
    print("Extracting labels...")
    if hasattr(model, 'pretrained_cfg') and 'label_names' in model.pretrained_cfg:
        labels = model.pretrained_cfg['label_names']
    else:
        # Fallback to loading from the hub directly if needed, 
        # but timm usually has them in pretrained_cfg
        labels = []
        print("Warning: Could not find labels in pretrained_cfg")

    if labels:
        with open(labels_path, "w") as f:
            for label in labels:
                f.write(f"{label}\n")
        print(f"Saved {len(labels)} labels to {labels_path}")

    print(f"Exporting to ONNX (input size: {input_size}x{input_size})...")
    dummy_input = torch.randn(1, 3, input_size, input_size)
    
    # Export the model
    torch.onnx.export(
        model,
        dummy_input,
        str(model_path),
        input_names=['input'],
        output_names=['output'],
        opset_version=16,
        dynamic_axes={'input': {0: 'batch'}, 'output': {0: 'batch'}}
    )
    print(f"Model exported to {model_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export timm model to ONNX")
    parser.add_argument("--model", type=str, default="timm/eva02_large_patch14_clip_336.merged2b_ft_inat21", help="timm model name")
    parser.add_argument("--output_dir", type=str, default="YA-WAMF/backend/data/models/eva02_large_inat21", help="Output directory")
    parser.add_argument("--size", type=int, default=336, help="Input size")
    
    args = parser.parse_args()
    
    export_model(args.model, args.output_dir, args.size)