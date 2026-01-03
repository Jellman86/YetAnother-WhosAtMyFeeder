import torch
import timm
import os
import argparse
from pathlib import Path

def export_model(model_name: str, output_path: str, input_size: int = 384):
    print(f"Loading model: {model_name}...")
    model = timm.create_model(f"hf-hub:{model_name}", pretrained=True)
    model.eval()

    print(f"Exporting to ONNX (input size: {input_size}x{input_size})...")
    dummy_input = torch.randn(1, 3, input_size, input_size)
    
    # Export the model
    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        input_names=['input'],
        output_names=['output'],
        opset_version=16,
        dynamic_axes={'input': {0: 'batch'}, 'output': {0: 'batch'}}
    )
    print(f"Model exported to {output_path}")

    # Simplify if onnxsim is available
    try:
        import onnxsim
        print("Simplifying ONNX model...")
        model_simp, check = onnxsim.simplify(output_path)
        if check:
            onnxsim.save(model_simp, output_path)
            print("Model simplified successfully")
        else:
            print("Simplification check failed, keeping original ONNX")
    except ImportError:
        print("onnx-simplifier not installed, skipping simplification")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export timm model to ONNX")
    parser.add_argument("--model", type=str, default="timm/convnext_large_mlp.laion2b_ft_augreg_inat21", help="timm model name")
    parser.add_argument("--output", type=str, default="convnext_large_inat21.onnx", help="Output ONNX file path")
    parser.add_argument("--size", type=int, default=384, help="Input size")
    
    args = parser.parse_args()
    
    export_model(args.model, args.output, args.size)
