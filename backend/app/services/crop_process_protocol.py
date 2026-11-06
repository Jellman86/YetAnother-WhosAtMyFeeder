"""Bounded detector tensors and metadata; never pickle native-child output."""

import base64
from io import BytesIO
import json
import math
from typing import Any, BinaryIO

import numpy as np

from app.services.classifier_worker_protocol import GPU_RUNTIME_FAILURE_CODES

MAX_MESSAGE_BYTES = 48 * 1024 * 1024
MAX_ARRAY_BYTES = 32 * 1024 * 1024
DEVICE_FAILURE_CODES = frozenset(
    (
        *GPU_RUNTIME_FAILURE_CODES,
        "CL_DEVICE_NOT_AVAILABLE",
        "CL_OUT_OF_RESOURCES",
        "CL_OUT_OF_HOST_MEMORY",
        "CL_EXEC_STATUS_ERROR_FOR_EVENTS_IN_WAIT_LIST",
        "ZE_RESULT_ERROR_DEVICE_LOST",
    )
)
_ALLOWED_DTYPES = {"float16", "float32", "float64", "uint8", "int32", "int64"}


def encode_array(value: np.ndarray) -> str:
    if value.dtype.name not in _ALLOWED_DTYPES or value.nbytes > MAX_ARRAY_BYTES or value.ndim > 5:
        raise ValueError("Detector tensor exceeds its contract")
    stream = BytesIO()
    np.save(stream, value, allow_pickle=False)
    return base64.b64encode(stream.getvalue()).decode("ascii")


def decode_array(encoded: str) -> np.ndarray:
    if not isinstance(encoded, str) or len(encoded) > (MAX_ARRAY_BYTES + 8192) * 4 // 3 + 4:
        raise ValueError("Detector tensor exceeds its contract")
    raw = base64.b64decode(encoded, validate=True)
    if not raw.startswith(b"\x93NUMPY"):
        raise ValueError("Only a single numeric tensor is accepted")
    stream = BytesIO(raw)
    if np.lib.format.read_magic(stream) != (1, 0):
        raise ValueError("Unsupported tensor header")
    shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream, max_header_size=4096)
    size = math.prod(shape) * dtype.itemsize
    if dtype.name not in _ALLOWED_DTYPES or size > MAX_ARRAY_BYTES or len(shape) > 5:
        raise ValueError("Detector tensor exceeds its contract")
    if size != len(raw) - stream.tell():
        raise ValueError("Detector tensor size does not match its header")
    return np.frombuffer(raw, dtype=dtype, offset=stream.tell()).reshape(shape, order="F" if fortran else "C").copy()


def message_bytes(message: dict[str, Any]) -> bytes:
    raw = json.dumps(message, allow_nan=False, separators=(",", ":")).encode() + b"\n"
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ValueError("Detector message exceeds its limit")
    return raw


def parse_message(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_MESSAGE_BYTES:
        raise ValueError("Detector message is missing or oversized")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Expected detector object")
    return value


def read_message(stream: BinaryIO) -> dict[str, Any]:
    return parse_message(stream.readline(MAX_MESSAGE_BYTES + 1))


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    stream.write(message_bytes(message))
    stream.flush()


def validate_metadata(value: dict[str, Any]) -> None:
    """Reject malformed native metadata before the caller uses tensor ports."""
    if value.get("ready") is not True:
        raise ValueError("Detector is not ready")
    for direction in ("inputs", "outputs"):
        ports = value.get(direction)
        if not isinstance(ports, list) or not 1 <= len(ports) <= 16:
            raise ValueError("Invalid detector ports")
        for port in ports:
            if not isinstance(port, dict) or set(port) != {"name", "shape", "type"}:
                raise ValueError("Invalid detector port")
            if any(not isinstance(port[k], str) or not 1 <= len(port[k]) <= 256 for k in ("name", "type")):
                raise ValueError("Invalid detector port name or type")
            shape = port["shape"]
            if (
                not isinstance(shape, list)
                or len(shape) > 5
                or any(
                    not ((type(d) is int and -1 <= d <= 2**31) or (isinstance(d, str) and len(d) <= 128)) for d in shape
                )
            ):
                raise ValueError("Invalid detector port dimensions")
    providers = value.get("providers")
    if (
        not isinstance(providers, list)
        or not 1 <= len(providers) <= 8
        or any(not isinstance(p, str) or not 1 <= len(p) <= 128 for p in providers)
    ):
        raise ValueError("Invalid detector providers")
