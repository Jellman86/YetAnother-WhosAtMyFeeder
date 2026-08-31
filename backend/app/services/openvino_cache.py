"""One rule for where OpenVINO keeps its compiled-kernel cache.

A cold GPU compile of a large model takes minutes; the cache is what makes
that a one-time cost. Under /tmp it dies with the container, so every image
pull recompiles from scratch — on slow hardware that is the difference
between a worker that warms up once and one that gets killed mid-load on
every start. Prefer the persistent models volume when it exists.
"""

import contextlib
import os
import shutil

_PERSISTENT_CACHE_DIR = "/data/models/.openvino_cache"
_EPHEMERAL_CACHE_DIR = "/tmp/openvino_cache"


def resolve_openvino_cache_dir() -> str:
    configured = os.getenv("OPENVINO_CACHE_DIR")
    if configured:
        return configured
    if os.path.isdir("/data/models"):
        return _PERSISTENT_CACHE_DIR
    return _EPHEMERAL_CACHE_DIR


def clear_openvino_cache(cache_dir: str | None = None) -> int:
    """Empty the compile cache, returning the bytes reclaimed.

    Blobs are keyed by opaque model hashes, so a deleted model's kernels
    cannot be reclaimed individually; clearing everything is the honest
    move — surviving models recompile once and re-cache. Safe to call when
    the directory does not exist.
    """
    if cache_dir is None:
        cache_dir = resolve_openvino_cache_dir()
    if not os.path.isdir(cache_dir):
        return 0
    freed = 0
    for entry in os.scandir(cache_dir):
        try:
            if entry.is_file(follow_symlinks=False):
                freed += entry.stat(follow_symlinks=False).st_size
                os.unlink(entry.path)
            elif entry.is_dir(follow_symlinks=False):
                for root, _dirs, files in os.walk(entry.path):
                    for name in files:
                        with contextlib.suppress(OSError):
                            freed += os.path.getsize(os.path.join(root, name))
                shutil.rmtree(entry.path, ignore_errors=True)
        except OSError:
            continue
    return freed
