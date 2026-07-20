"""Inference-runtime image flavor identity and provider-family contracts."""

from collections.abc import Mapping
import os


PUBLISHED_IMAGE_FLAVORS = frozenset({"full", "cpu", "intel", "cuda", "rpi"})

_PACKAGED_INFERENCE_PROVIDERS: dict[str, tuple[str, ...]] = {
    "full": ("cpu", "cuda", "intel_cpu", "intel_gpu", "intel_npu"),
    "cpu": ("cpu",),
    "intel": ("cpu", "intel_cpu", "intel_gpu", "intel_npu"),
    "cuda": ("cpu", "cuda"),
    "rpi": ("cpu",),
}


def get_image_flavor(env: Mapping[str, str | None] | None = None) -> str:
    """Return a normalized published image flavor or ``unknown`` outside an image."""
    source = env if env is not None else os.environ
    value = str(source.get("YAWAMF_IMAGE_FLAVOR") or "").strip().lower()
    return value if value in PUBLISHED_IMAGE_FLAVORS else "unknown"


def packaged_inference_providers(flavor: str) -> tuple[str, ...]:
    """Return providers intentionally packaged by an image flavor.

    This is a packaging contract, not a hardware-availability claim. Runtime probes
    remain authoritative for whether a packaged provider can execute on this host.
    """
    normalized = str(flavor or "").strip().lower()
    return _PACKAGED_INFERENCE_PROVIDERS.get(normalized, ())


def image_flavor_warning(flavor: str, selected_provider: str | None) -> str | None:
    """Report an explicit provider selection that the image cannot package."""
    packaged = packaged_inference_providers(flavor)
    selected = str(selected_provider or "").strip().lower()
    if not packaged or selected in {"", "auto"}:
        return None
    if selected not in packaged:
        return "selected_provider_not_packaged"
    return None
