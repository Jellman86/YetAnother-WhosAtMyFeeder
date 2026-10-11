"""Export the pinned iNat DINOv2 checkpoint with a portable metadata input.

Requires the upstream source checkout at d468bf1c3d6ac05eec656102614ffbc84f5cf026,
the E4a checkpoint, the official iNat validation annotation archive, and CPU
torch/onnx. The checkpoint's class-order fingerprint must match the annotations.
No installation coordinates are baked into the graph.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
from pathlib import Path


CHECKPOINT_SHA256 = "1eee0f1df655c48f95d250a70492e95dda04601e2d6480bf61788abcaaec5367"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with args.checkpoint.open("rb") as handle:
        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    if checksum != CHECKPOINT_SHA256:
        raise SystemExit("Checkpoint does not match the reviewed E4a release")

    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch

    sys.path.insert(0, str(args.source.resolve()))
    from config import Config
    from data import build_class_mapping
    from model import INatClassifier

    torch.set_num_threads(2)
    # The checkpoint includes numpy RNG values; permit their value constructors
    # without enabling arbitrary pickle globals or weights_only=False.
    allowed = [
        np.core.multiarray._reconstruct,
        np.ndarray,
        np.dtype,
        np.dtypes.UInt32DType,
        np.core.multiarray.scalar,
        np.dtypes.Float64DType,
    ]
    with torch.serialization.safe_globals(allowed):
        checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    config = Config.from_dict(checkpoint["config"])
    config.pretrained, config.device, config.grad_checkpointing = False, "cpu", False
    with tarfile.open(args.annotations, "r:gz") as archive:
        member = next(item for item in archive.getmembers() if item.name.endswith(".json"))
        annotations = json.load(archive.extractfile(member))
    mapping = build_class_mapping(annotations["categories"])
    if mapping.fingerprint() != checkpoint["mapping_fingerprint"]:
        raise SystemExit("Annotation class order differs from the checkpoint fingerprint")
    network = INatClassifier(config, len(mapping.names), None)
    network.load_state_dict(checkpoint["model"], strict=True)
    network.eval()
    del checkpoint

    class PortableClassifier(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.model = network

        def forward(self, image, metadata):
            return self.model(image, metadata).primary

    wrapper = PortableClassifier().eval()
    args.output.mkdir(parents=True, exist_ok=False)
    output = args.output / "model.onnx"
    image = torch.zeros(1, 3, config.eval_size, config.eval_size)
    metadata = torch.zeros(1, 8)
    torch.onnx.export(
        wrapper,
        (image, metadata),
        str(output),
        input_names=["input", "metadata"],
        output_names=["output"],
        opset_version=20,
        dynamo=True,
        external_data=True,
    )
    onnx.checker.check_model(str(output))
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(str(output), options, providers=["CPUExecutionProvider"])
    checks = []
    for features in ([0] * 8, [1, 0, 0, 0, 0, 0, 1, 0], [0, 0, 1, 0, 0, 0, 1, 0]):
        meta = torch.tensor([features], dtype=torch.float32)
        with torch.inference_mode():
            expected = wrapper(image, meta).numpy()
        actual = session.run(None, {"input": image.numpy(), "metadata": meta.numpy()})[0]
        np.testing.assert_allclose(actual, expected, atol=1e-4, rtol=1e-4)
        checks.append(
            {
                "finite": bool(np.isfinite(actual).all()),
                "top1_agrees": bool(actual.argmax() == expected.argmax()),
                "max_abs_error": float(np.max(np.abs(actual - expected))),
            }
        )
    (args.output / "class-mapping.json").write_text(
        json.dumps(
            {
                "fingerprint": mapping.fingerprint(),
                "scientific_names": mapping.names,
                "category_ids": mapping.index_to_cat_id.tolist(),
            },
            indent=2,
        )
        + "\n"
    )
    (args.output / "conversion.json").write_text(
        json.dumps(
            {
                "checkpoint_sha256": checksum,
                "mapping_fingerprint": mapping.fingerprint(),
                "reference_checks": checks,
                "metadata_policy": "Configured location at runtime; date and uncertainty absent; eight zeros when location unavailable",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
