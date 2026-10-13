"""Export the checksum-pinned Cedar checkpoint as raw RGB 640 ONNX proposals.

Run in an isolated environment with an external deadline/resource guard.
The pinned upstream checkpoint contains Python objects, so only that exact
trusted checksum is unpickled. No training or application database is used.
"""

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

CHECKPOINT_SHA256 = "48f72a8b086dfd6a3ef6defaef422bd4a250b9084981044dcc2bb35764c93ca5"
SOURCE_REVISION = "5b1ea9a8b3f0ffe4fe0e203ec6232d788bb3fcff"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing export")
    with args.checkpoint.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != CHECKPOINT_SHA256:
            raise SystemExit("Checkpoint differs from the reviewed Cedar release")
    revision = subprocess.check_output(["git", "-C", str(args.source), "rev-parse", "HEAD"], text=True).strip()
    if revision != SOURCE_REVISION or subprocess.check_output(
        ["git", "-C", str(args.source), "diff", "HEAD"], text=True
    ):
        raise SystemExit("Architecture source must match the pinned, unmodified revision")
    sys.path.insert(0, str(args.source.resolve()))
    import numpy as np
    import onnxruntime as ort
    import torch

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    model = torch.load(args.checkpoint, map_location="cpu", weights_only=False)["model"].float().fuse().eval()
    if list(model.names.values()) != ["animal", "person", "vehicle"]:
        raise SystemExit("Checkpoint class order changed")
    model.model[-1].export = True
    model.model[-1].dynamic = False

    class Wrapped(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.base = model

        def forward(self, value):
            output = self.base(value)
            return output[0] if isinstance(output, (tuple, list)) else output

    wrapped = Wrapped().eval()
    value = torch.zeros((1, 3, 640, 640))
    with torch.no_grad():
        if tuple(wrapped(value).shape) != (1, 7, 8400):
            raise SystemExit("Cedar must export its raw seven-channel head")
        torch.onnx.export(
            wrapped,
            value,
            str(args.output),
            opset_version=17,
            dynamo=False,
            input_names=["images"],
            output_names=["predictions"],
            do_constant_folding=True,
        )
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    runtime = ort.InferenceSession(str(args.output), sess_options=options, providers=["CPUExecutionProvider"])
    for seed in range(3):
        pixels = np.random.default_rng(seed).random((1, 3, 640, 640), dtype=np.float32)
        with torch.no_grad():
            reference = wrapped(torch.from_numpy(pixels)).numpy()
        actual = runtime.run(None, {"images": pixels})[0]
        if (
            not np.isfinite(actual).all()
            or np.max(np.abs(actual[:, :4] - reference[:, :4])) >= 0.1
            or np.max(np.abs(actual[:, 4:] - reference[:, 4:])) >= 0.0001
        ):
            raise SystemExit("ONNX output differs from the original checkpoint")


if __name__ == "__main__":
    main()
