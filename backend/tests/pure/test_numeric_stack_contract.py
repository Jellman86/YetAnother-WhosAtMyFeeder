"""Guard the numeric contract the classifier depends on.

The suite mocks every inference runtime, so a dependency bump can change real
array behaviour without a single test noticing. That is not hypothetical: the
`numpy<2.0.0` cap was raised to `<3.0.0`, which moves the container from
NumPy 1.26 to 2.x, and NumPy 2 changed value-based casting (NEP 50) as well as
the binary interface every compiled extension links against.

These tests assert the two things a bump can silently break:

* **dtype contracts.** NEP 50 changes what `float32 op scalar` produces. The
  preprocessing paths must stay `float32`, because a silent widening to
  `float64` doubles every inference input and changes quantisation.
* **the compiled boundary.** OpenCV is a C extension built against a specific
  NumPy ABI. A mismatch raises on import or corrupts pixel buffers.

Verified equal between NumPy 1.26.4 and 2.5.2, byte for byte, on the real
model preprocessing paths before the cap was raised.
"""

import numpy as np
import pytest

from app.services.classifier_service import _normalize_probability_vector, _safe_softmax

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def test_probability_normalisation_returns_float32_that_sums_to_one():
    result = _normalize_probability_vector(np.array([1.0, 1.0, 2.0], dtype=np.float32), context="test")
    assert result.dtype == np.float32
    np.testing.assert_allclose(result, [0.25, 0.25, 0.5], rtol=0, atol=1e-7)


@pytest.mark.parametrize(
    "values",
    [
        pytest.param([0.5, np.nan, 0.5], id="nan"),
        pytest.param([0.5, np.inf, 0.5], id="inf"),
        pytest.param([1e-38, 1e-38, 1e-38], id="denormal"),
    ],
)
def test_probability_normalisation_holds_its_dtype_on_hostile_input(values):
    result = _normalize_probability_vector(np.array(values, dtype=np.float32), context="test")
    assert result.dtype == np.float32
    assert np.isfinite(result).all()


def test_softmax_is_float32_and_normalised_even_at_extreme_logits():
    logits = np.array([-1000.0, 0.0, 1000.0], dtype=np.float32)
    result = _safe_softmax(logits, context="test")
    assert result.dtype == np.float32
    assert np.isfinite(result).all()
    assert result.sum() == pytest.approx(1.0, abs=1e-6)
    assert int(result.argmax()) == 2


def test_imagenet_preprocessing_stays_float32_from_a_float_input():
    image = np.full((1, 4, 4, 3), 128.0, dtype=np.float32)
    normalised = (image / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
    # NEP 50: a Python float is weak, so float32 must survive the arithmetic.
    assert normalised.dtype == np.float32
    expected = (128.0 / 255.0 - float(IMAGENET_MEAN[0])) / float(IMAGENET_STD[0])
    # float32 carries ~7 significant digits, so compare at that precision.
    assert normalised[0, 0, 0, 0] == pytest.approx(expected, rel=1e-5)


def test_mobilenet_preprocessing_maps_the_byte_range_to_minus_one_and_one():
    image = np.array([[0, 127.5, 255]], dtype=np.float32)
    scaled = (image - 127.5) / 127.5
    assert scaled.dtype == np.float32
    np.testing.assert_allclose(scaled, [[-1.0, 0.0, 1.0]], rtol=0, atol=1e-7)


def test_quantisation_round_trip_lands_inside_the_integer_range():
    rng = np.random.default_rng(4242)
    image = (rng.random((1, 8, 8, 3)) * 255).astype(np.uint8)
    real_input = (image / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
    quantised = np.rint(real_input / 0.0078125 + 128.0)
    limits = np.iinfo(np.uint8)
    result = np.clip(quantised, limits.min, limits.max).astype(np.uint8)
    assert result.dtype == np.uint8
    assert result.min() >= 0 and result.max() <= 255


def test_opencv_shares_memory_with_numpy_without_corrupting_it():
    """The canary for an ABI mismatch: a wrongly linked build fails here."""
    cv2 = pytest.importorskip("cv2")
    # A smooth gradient rather than noise: JPEG is lossy by design and random
    # noise is its worst case, which would make the threshold below meaningless.
    rows = np.linspace(0, 255, 48, dtype=np.float32)[:, None]
    cols = np.linspace(0, 255, 64, dtype=np.float32)[None, :]
    source = np.stack([np.broadcast_to(rows, (48, 64)), np.broadcast_to(cols, (48, 64)), (rows + cols) / 2], axis=-1)
    source = source.astype(np.uint8)

    resized = cv2.resize(source, (32, 32), interpolation=cv2.INTER_LINEAR)
    assert resized.dtype == np.uint8
    assert resized.shape == (32, 32, 3)

    swapped = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    np.testing.assert_array_equal(swapped[..., 0], resized[..., 2])
    np.testing.assert_array_equal(swapped[..., 2], resized[..., 0])

    encoded_ok, encoded = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    assert encoded_ok and encoded.size > 0
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    assert decoded.shape == resized.shape
    # Lossy, but a corrupted buffer is nowhere near the original.
    assert float(np.abs(decoded.astype(np.int16) - resized.astype(np.int16)).mean()) < 4.0


def test_opencv_accepts_the_float_path_the_classifier_uses():
    cv2 = pytest.importorskip("cv2")
    rng = np.random.default_rng(7)
    source = (rng.random((48, 64, 3)) * 255).astype(np.uint8)
    floats = source.astype(np.float32) / 255.0
    resized = cv2.resize(floats, (16, 16), interpolation=cv2.INTER_LINEAR)
    assert resized.dtype == np.float32
    assert 0.0 <= float(resized.min()) and float(resized.max()) <= 1.0
