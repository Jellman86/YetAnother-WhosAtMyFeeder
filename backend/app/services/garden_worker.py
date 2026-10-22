"""One disposable SpeciesNet inference. Only its parent may launch this worker."""

import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

from app.repositories.garden_catalog import read_shipped_package
from app.services.garden_model_runtime import Runtime, digest, preprocess
from app.services.garden_visitors import Taxon, coarse_prediction_mass, animal_presence_prediction


def identify(request: dict) -> dict:
    mode = request.get("mode", "identify")
    if mode not in {"identify", "preview", "automatic"}:
        raise ValueError("Unsupported garden worker operation")
    if mode == "automatic" and request["variant"] != "4.0.3a":
        raise ValueError("Automatic checks require the tracked-crop model")
    model = Path(request["model"])
    if digest(model) != request["model_sha256"]:
        raise ValueError("Model checksum mismatch")
    box = tuple(request["box"]) if request["box"] is not None else None
    if request["variant"] == "4.0.3a" and box is None:
        raise ValueError("Crop model requires a tracked snapshot box")
    package, package_sha = None, None
    if mode in {"preview", "automatic"}:
        if mode == "preview" and request["variant"] != "4.0.3a":
            raise ValueError("Photo checks require the tracked crop model")
        encoded, package_sha = read_shipped_package()
        package = json.loads(encoded)
        if (
            package_sha != request.get("package_sha256")
            or package["model_sha256"][request["variant"]] != request["model_sha256"]
        ):
            raise ValueError("Photo check mapping differs from its requested model/package")
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
    if package is not None:
        outputs = [Taxon(item["id"], item["name"], tuple(item["ranks"])) for item in package["outputs"]]
        if mode == "automatic":
            assessment = animal_presence_prediction(probabilities.tolist(), outputs)
            # The same pass names a confident animal, so naming never needs a second inference.
            return {
                "assessment": {"mass": assessment.mass, "human_winner": assessment.human_winner},
                "predictions": _top_predictions(probabilities),
                "devices": runtime.actual,
                "frame_size": frame_size,
                "package_sha256": package_sha,
            }
        coarse = coarse_prediction_mass(probabilities.tolist(), outputs)
        return {
            "preview": {"suggestion": coarse.suggestion, "mass": coarse.mass, "human_winner": coarse.human_winner},
            "devices": runtime.actual,
            "frame_size": frame_size,
            "package_sha256": package_sha,
        }
    return {
        "predictions": _top_predictions(probabilities),
        "devices": runtime.actual,
        "frame_size": frame_size,
    }


def _top_predictions(probabilities: np.ndarray) -> list[list[float]]:
    return [[int(i), float(probabilities[i])] for i in np.argsort(-probabilities)[:5]]


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
