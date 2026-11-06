"""Runtime adapters behind one contract.

The facade loads, classifies through and releases a model only through the members
below. Optional capabilities such as `probe` (ONNX Runtime and OpenVINO) are reached
by the callers that need them, never assumed of every runtime.
"""

from typing import Any, Optional, Protocol, runtime_checkable

import numpy as np
from PIL import Image


@runtime_checkable
class InferenceAdapter(Protocol):
    name: str
    model_path: str
    labels_path: str
    labels: list[str]
    loaded: bool
    error: Optional[str]
    # The digest of the weights actually loaded: results carry it as provenance.
    loaded_artifact_sha256: Optional[str]
    model_sha256: Optional[str]

    def load(self) -> bool: ...

    def classify(self, image: Image.Image, *args: Any, **kwargs: Any) -> list[dict]: ...

    def classify_raw(self, image: Image.Image) -> np.ndarray: ...

    def cleanup(self) -> None: ...

    def get_status(self) -> dict: ...
