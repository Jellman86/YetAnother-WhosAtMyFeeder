"""One rule for where OpenVINO keeps its compiled-kernel cache.

A cold GPU compile of a large model takes minutes; the cache is what makes
that a one-time cost. Under /tmp it dies with the container, so every image
pull recompiles from scratch — on slow hardware that is the difference
between a worker that warms up once and one that gets killed mid-load on
every start. Prefer the persistent models volume when it exists.
"""

import os

_PERSISTENT_CACHE_DIR = "/data/models/.openvino_cache"
_EPHEMERAL_CACHE_DIR = "/tmp/openvino_cache"


def resolve_openvino_cache_dir() -> str:
    configured = os.getenv("OPENVINO_CACHE_DIR")
    if configured:
        return configured
    if os.path.isdir("/data/models"):
        return _PERSISTENT_CACHE_DIR
    return _EPHEMERAL_CACHE_DIR
