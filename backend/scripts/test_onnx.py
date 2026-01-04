import onnxruntime as ort
import numpy as np

model_path = "YA-WAMF/backend/data/models/eva02_large_inat21/model.onnx"
labels_path = "YA-WAMF/backend/data/models/eva02_large_inat21/labels.txt"

def test_inference():
    print(f"Loading model from {model_path}...")
    try:
        session = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
        print("Model loaded successfully!")
        
        input_name = session.get_inputs()[0].name
        input_shape = session.get_inputs()[0].shape
        print(f"Input name: {input_name}, Shape: {input_shape}")
        
        # Create dummy input
        dummy_input = np.random.randn(1, 3, 336, 336).astype(np.float32)
        
        # Run inference
        outputs = session.run(None, {input_name: dummy_input})
        logits = outputs[0]
        print(f"Inference successful! Output shape: {logits.shape}")
        
        # Load labels
        with open(labels_path, 'r') as f:
            labels = [line.strip() for line in f.readlines()]
        print(f"Loaded {len(labels)} labels.")
        
        top_idx = np.argmax(logits[0])
        print(f"Top prediction index: {top_idx}, Label: {labels[top_idx] if top_idx < len(labels) else 'Unknown'}")
        
    except Exception as e:
        print(f"Inference failed: {e}")

if __name__ == "__main__":
    test_inference()
