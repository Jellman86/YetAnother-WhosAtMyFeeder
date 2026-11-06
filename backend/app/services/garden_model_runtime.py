"""Shared, independently checked SpeciesNet preprocessing and strict runtimes.

Native callers must be supervised by an external process deadline. No bird
normalisation, automatic provider fallback, catalogue writes or settings imports.
"""

import hashlib
import math
from pathlib import Path
import time

import numpy as np
from PIL import Image


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def preprocess(image: Image.Image, variant: str, box: tuple[float, ...] | None) -> np.ndarray:
    """Tensor bilinear, align_corners=False, antialias=False, uint8 round-trip.

    NumPy avoids adding PyTorch to the running application. Compare the resulting
    quantized pixels and predictions against upstream before qualifying a model.
    """
    if image.width * image.height > 16_000_000:
        raise ValueError("Image exceeds prototype pixel limit")
    pixels = np.asarray(image.convert("RGB"), dtype=np.float32) / np.float32(255)
    if variant == "4.0.3a" and box is not None:
        if len(box) != 4 or any(not math.isfinite(v) for v in box):
            raise ValueError("Invalid normalized XYWH crop")
        x, y, width, height = box
        if min(x, y) < 0 or min(width, height) <= 0 or x + width > 1.000001 or y + height > 1.000001:
            raise ValueError("Crop must be inside the source frame")
        left, top = int(x * image.width), int(y * image.height)
        w, h = int(width * image.width), int(height * image.height)
        if min(w, h) < 1:
            raise ValueError("Crop is smaller than one pixel")
        pixels = pixels[top : top + h, left : left + w]
    elif variant == "4.0.3b":
        height = max(int(image.height * 0.7), image.height - 400)
        top = round((image.height - height) / 2)
        pixels = pixels[top : top + height]
    elif variant != "4.0.3a":
        raise ValueError("Unsupported SpeciesNet variant")
    height, width = pixels.shape[:2]
    xs = np.maximum((np.arange(480, dtype=np.float32) + 0.5) * np.float32(width / 480) - 0.5, 0)
    ys = np.maximum((np.arange(480, dtype=np.float32) + 0.5) * np.float32(height / 480) - 0.5, 0)
    x0, y0 = xs.astype(np.int32), ys.astype(np.int32)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    wx, wy = (xs - x0).astype(np.float32)[None, :, None], (ys - y0).astype(np.float32)[:, None, None]
    upper = pixels[y0[:, None], x0] * (1 - wx) + pixels[y0[:, None], x1] * wx
    lower = pixels[y1[:, None], x0] * (1 - wx) + pixels[y1[:, None], x1] * wx
    resized = upper * (1 - wy) + lower * wy
    quantized = (np.clip(resized, 0, 1) * np.float32(255.999)).astype(np.uint8)
    return np.ascontiguousarray(quantized[None].astype(np.float32) / np.float32(255))


def execution_devices(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


class Runtime:
    def __init__(self, model: Path, provider: str) -> None:
        if provider not in {"cpu", "intel_cpu", "intel_gpu", "intel_npu", "cuda"}:
            raise ValueError("Unsupported garden inference provider")
        self.provider = provider
        self.timings: list[float] = []
        if provider.startswith("intel_"):
            import openvino as ov

            device = {"intel_cpu": "CPU", "intel_gpu": "GPU", "intel_npu": "NPU"}[provider]
            self.compiled = ov.Core().compile_model(str(model), device, {"PERFORMANCE_HINT": "LATENCY"})
            self.actual = execution_devices(self.compiled.get_property("EXECUTION_DEVICES"))
            if not self.actual or any(not name.startswith(device) for name in self.actual):
                raise RuntimeError("Requested OpenVINO device was not used")
        else:
            import onnxruntime as ort

            if provider == "cuda":
                from app.utils.cuda_runtime import preload_packaged_cuda_libraries

                preload_packaged_cuda_libraries(ort)
            primary = "CUDAExecutionProvider" if provider == "cuda" else "CPUExecutionProvider"
            options = ort.SessionOptions()
            options.intra_op_num_threads = 2
            self.session = ort.InferenceSession(str(model), providers=[primary], sess_options=options)
            self.session.disable_fallback()
            self.actual = self.session.get_providers()
            if self.actual[0] != primary:
                raise RuntimeError("Requested ONNX provider was not used")

    def infer(self, value: np.ndarray) -> np.ndarray:
        started = time.monotonic()
        if self.provider.startswith("intel_"):
            result = np.asarray(self.compiled([value])[self.compiled.output(0)]).copy()
        else:
            result = self.session.run(None, {self.session.get_inputs()[0].name: value})[0]
            if self.session.get_providers() != self.actual:
                raise RuntimeError("Provider changed during replay")
        self.timings.append(time.monotonic() - started)
        if not np.isfinite(result).all():
            raise ValueError("Model returned non-finite output")
        return result
