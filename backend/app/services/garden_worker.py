"""One disposable SpeciesNet inference. Only its parent may launch this worker."""

import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

from app.services.garden_model_runtime import Runtime, digest, preprocess


def identify(request: dict) -> dict:
    model = Path(request["model"])
    if digest(model) != request["model_sha256"]:
        raise ValueError("Model checksum mismatch")
    box = tuple(request["box"]) if request["box"] is not None else None
    if request["variant"] == "4.0.3a" and box is None:
        raise ValueError("Crop model requires a tracked snapshot box")
    with Image.open(request["image"]) as source:
        frame_size = source.size
        value = preprocess(source, request["variant"], box)
    runtime = Runtime(model, request["provider"])
    if hasattr(runtime, "session"):
        inputs = runtime.session.get_inputs()
        if len(inputs) != 1 or inputs[0].shape != [1, 480, 480, 3] or inputs[0].type != "tensor(float)":
            raise ValueError("Unexpected classifier input contract")
    else:
        if list(runtime.compiled.input(0).shape) != [1, 480, 480, 3]:
            raise ValueError("Unexpected classifier input contract")
    logits = runtime.infer(value)
    if logits.shape != (1, 2498):
        raise ValueError("Unexpected classifier output contract")
    logits = logits[0].astype(np.float64)
    probabilities = np.exp(logits - logits.max())
    probabilities /= probabilities.sum()
    indices = np.argsort(-probabilities)[:5]
    return {
        "predictions": [[int(i), float(probabilities[i])] for i in indices],
        "devices": runtime.actual,
        "frame_size": frame_size,
    }


def main() -> None:
    try:
        request = json.loads(sys.stdin.buffer.readline(8192))
        result = identify(request)
        sys.stdout.write("GARDEN_RESULT:" + json.dumps(result, allow_nan=False) + "\n")
        sys.stdout.flush()
    except Exception:
        # No source paths, media, identities or provider stderr enter logs.
        sys.exit(1)


if __name__ == "__main__":
    main()
