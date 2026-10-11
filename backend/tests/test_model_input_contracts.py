"""Portable metadata and native-aspect model input contracts."""

from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from app.services import classifier_service as module


@pytest.mark.parametrize(
    "size,expected", [((1920, 1080), (448, 252)), ((1080, 1920), (252, 448)), ((336, 336), (336, 336))]
)
def test_naflex_preserves_patch_grid_and_native_pixels(size, expected):
    image = Image.new("RGB", size, (11, 97, 243))
    result = module._resize_with_preprocessing(
        image,
        336,
        preprocessing={
            "resize_mode": "native_aspect_ratio",
            "patch_size": 14,
            "max_seq_len": 576,
            "interpolation": "bicubic",
        },
    )
    assert result.size == expected
    assert result.tobytes() == image.resize(expected, Image.Resampling.BICUBIC).tobytes()


@pytest.mark.parametrize("lat,lon", [(None, None), (91, 0), (0, 181), (float("nan"), 0), (True, 0)])
def test_metadata_missing_or_invalid_coordinates_have_no_presence_flag(lat, lon):
    result = module._inat_location_metadata(lat, lon)
    np.testing.assert_array_equal(result, np.zeros((1, 8), dtype=np.float32))


def test_metadata_distinguishes_equator_prime_meridian_from_missing():
    np.testing.assert_array_equal(
        module._inat_location_metadata(0, 0), np.array([[1, 0, 0, 0, 0, 0, 1, 0]], dtype=np.float32)
    )


def test_metadata_uses_unit_sphere_and_leaves_date_and_uncertainty_missing():
    np.testing.assert_allclose(
        module._inat_location_metadata(45, 90), [[0, 2**-0.5, 2**-0.5, 0, 0, 0, 1, 0]], atol=1e-7
    )


def test_onnx_passes_configured_location_as_a_separate_model_input(monkeypatch):
    monkeypatch.setattr(module.settings, "location", SimpleNamespace(latitude=0, longitude=0))
    model = module.ONNXModelInstance(
        "portable", "/absent", "/absent", preprocessing={"metadata_input": "inat2021_location_v1"}
    )
    model.session = Mock()
    model.session.get_providers.return_value = ["CPUExecutionProvider"]
    image = np.zeros((1, 3, 336, 336), dtype=np.float32)
    model._run_inference("input", image)
    feed = model.session.run.call_args.args[1]
    assert feed["input"] is image
    np.testing.assert_array_equal(feed["metadata"], [[1, 0, 0, 0, 0, 0, 1, 0]])


def test_catalogue_output_width_mismatch_fails_closed():
    with pytest.raises(ValueError, match="output width"):
        module._check_catalogue_output_width(["One", "Two"], 3, "catalogue")
    module._check_catalogue_output_width(["One", "Two"], 2, "catalogue")
    module._check_catalogue_output_width(["One"], 3, "label_file")
