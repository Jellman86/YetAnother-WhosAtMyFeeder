"""Prepare packaged CUDA libraries, including cuDNN's runtime-loaded DLLs."""

import importlib.util
import os
from pathlib import Path
import sys
import threading
from typing import Any

_loader_lock = threading.Lock()


def _packaged_nvidia_dll_directories() -> list[str]:
    try:
        namespace = importlib.util.find_spec("nvidia")
    except (ImportError, ValueError):
        return []
    roots = getattr(namespace, "submodule_search_locations", None) or []
    return sorted(
        {
            str(directory.resolve())
            for root in roots
            for directory in Path(root).glob("*/bin")
            if directory.is_dir() and any(directory.glob("*.dll"))
        }
    )


def preload_packaged_cuda_libraries(runtime: Any) -> None:
    """Keep cuDNN's secondary DLLs discoverable throughout Windows inference."""
    with _loader_lock:
        if sys.platform == "win32":
            existing = os.environ.get("PATH", "")
            known = {os.path.normpath(part).casefold() for part in existing.split(os.pathsep) if part}
            additions = [
                directory
                for directory in _packaged_nvidia_dll_directories()
                if os.path.normpath(directory).casefold() not in known
            ]
            if additions:
                # cuDNN uses LoadLibrary at inference time. Preloading its main
                # DLL or add_dll_directory alone does not resolve those modules.
                os.environ["PATH"] = os.pathsep.join([*additions, existing]) if existing else os.pathsep.join(additions)
        preload = getattr(runtime, "preload_dlls", None)
        if callable(preload):
            preload(directory="")


def prevent_internal_cuda_fallback(session: Any) -> None:
    """Let the application's recovery policy handle a failed CUDA execution."""
    disable = getattr(session, "disable_fallback", None)
    if callable(disable):
        disable()


def verify_cuda_session_provider(session: Any) -> None:
    """A successful CPU retry must not be reported as successful CUDA inference."""
    providers = list(session.get_providers() or [])
    if not providers or providers[0] != "CUDAExecutionProvider":
        raise RuntimeError(f"ONNX Runtime provider changed from CUDA to {providers!r} during inference")
