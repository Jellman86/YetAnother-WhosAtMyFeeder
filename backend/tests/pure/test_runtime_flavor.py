import pytest

from app.utils.runtime_flavor import (
    get_image_flavor,
    image_flavor_warning,
    packaged_inference_providers,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "unknown"),
        ("", "unknown"),
        ("FULL", "full"),
        (" cpu ", "cpu"),
        ("intel", "intel"),
        ("cuda", "cuda"),
        ("rpi", "rpi"),
        ("unexpected", "unknown"),
    ],
)
def test_get_image_flavor_normalizes_only_published_flavors(raw: str | None, expected: str) -> None:
    assert get_image_flavor({"YAWAMF_IMAGE_FLAVOR": raw} if raw is not None else {}) == expected


@pytest.mark.parametrize(
    ("flavor", "expected"),
    [
        ("full", ("cpu", "cuda", "intel_cpu", "intel_gpu", "intel_npu")),
        ("cpu", ("cpu",)),
        ("intel", ("cpu", "intel_cpu", "intel_gpu", "intel_npu")),
        ("cuda", ("cpu", "cuda")),
        ("rpi", ("cpu",)),
        ("unknown", ()),
    ],
)
def test_packaged_inference_providers_follow_runtime_family(flavor: str, expected: tuple[str, ...]) -> None:
    assert packaged_inference_providers(flavor) == expected


@pytest.mark.parametrize("selected", [None, "", "auto", "cpu"])
def test_image_flavor_warning_accepts_safe_cpu_and_auto_paths(selected: str | None) -> None:
    assert image_flavor_warning("cpu", selected) is None


@pytest.mark.parametrize("flavor", ["full", "intel"])
def test_image_flavor_warning_accepts_intel_npu_in_intel_capable_images(flavor: str) -> None:
    assert image_flavor_warning(flavor, "intel_npu") is None


@pytest.mark.parametrize(
    ("flavor", "selected"),
    [
        ("cpu", "cuda"),
        ("cpu", "intel_gpu"),
        ("intel", "cuda"),
        ("cuda", "intel_npu"),
        ("rpi", "intel_cpu"),
    ],
)
def test_image_flavor_warning_reports_explicit_provider_mismatch(flavor: str, selected: str) -> None:
    assert image_flavor_warning(flavor, selected) == "selected_provider_not_packaged"


def test_image_flavor_warning_does_not_guess_for_unknown_local_environment() -> None:
    assert image_flavor_warning("unknown", "cuda") is None
