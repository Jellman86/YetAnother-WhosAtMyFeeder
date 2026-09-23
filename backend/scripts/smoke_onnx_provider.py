"""Check real CPU/CUDA execution through the application's ONNX classifier.

Requires the optional `onnx` package to build a deterministic three-class
fixture. This checks preprocessing, finite scores, provider execution and CPU
agreement, not bird-model accuracy. It writes only disposable temporary files.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
import onnx
import onnxruntime as ort
from PIL import Image

from app.services.classifier_service import ONNXModelInstance


def exercise(provider: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="yawamf-onnx-smoke-") as folder:
        root = Path(folder)
        graph = onnx.helper.make_graph(
            [
                onnx.helper.make_node("GlobalAveragePool", ["image"], ["average"]),
                onnx.helper.make_node("Flatten", ["average"], ["logits"], axis=1),
            ],
            "classifier-smoke",
            [onnx.helper.make_tensor_value_info("image", onnx.TensorProto.FLOAT, [1, 3, 32, 32])],
            [onnx.helper.make_tensor_value_info("logits", onnx.TensorProto.FLOAT, [1, 3])],
        )
        fixture = onnx.helper.make_model(graph, opset_imports=[onnx.helper.make_opsetid("", 13)], ir_version=8)
        onnx.save(fixture, root / "model.onnx")
        (root / "labels.txt").write_text("red\ngreen\nblue\n")
        images = [Image.new("RGB", (48, 32), color) for color in ("red", "green", "blue")]
        outputs = {}
        kernels = {}
        original_options = ort.SessionOptions
        for selected in dict.fromkeys(["CPUExecutionProvider", provider]):

            def profiled_options():
                options = original_options()
                options.enable_profiling = True
                options.profile_file_prefix = str(root / selected)
                return options

            model = ONNXModelInstance(
                "provider-smoke",
                str(root / "model.onnx"),
                str(root / "labels.txt"),
                input_size=32,
                ort_providers=[selected],
            )
            try:
                with patch.object(ort, "SessionOptions", side_effect=profiled_options):
                    assert model.load(), model.error
                assert model.session.get_providers()[0] == selected, "runtime silently fell back"
                values = np.stack([model.classify_raw(image) for image in images])
                assert np.isfinite(values).all()
                np.testing.assert_allclose(values.sum(axis=1), 1, atol=1e-6)
                assert values.argmax(axis=1).tolist() == [0, 1, 2]
                profile = json.loads(Path(model.session.end_profiling()).read_text())
                executed = {row.get("args", {}).get("provider") for row in profile if row.get("cat") == "Node"}
                assert selected in executed, "provider was registered but executed no kernels"
                outputs[selected] = values
                kernels[selected] = sorted(value for value in executed if value)
            finally:
                model.cleanup()
        np.testing.assert_allclose(outputs[provider], outputs["CPUExecutionProvider"], atol=1e-5, rtol=1e-5)
        return {
            "ok": True,
            "runtime_version": ort.__version__,
            "provider": provider,
            "kernel_providers": kernels,
            "cpu_agreement": True,
            "fixture_classes": 3,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["CPUExecutionProvider", "CUDAExecutionProvider"], required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.provider), indent=2))


if __name__ == "__main__":
    main()
