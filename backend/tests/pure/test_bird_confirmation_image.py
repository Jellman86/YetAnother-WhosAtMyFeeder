import numpy as np
from PIL import Image
import pytest

from app.services.inference.preprocessing import prepare_bird_confirmation_image, resize_with_preprocessing


@pytest.mark.parametrize("size", [(96, 24), (24, 96), (24, 24)])
@pytest.mark.parametrize("crop_pct", [0.875, 0.9, 1.0])
def test_production_center_crop_keeps_the_entire_subject_extent(size, crop_pct):
    width, height = size
    indices = np.arange(width * height, dtype=np.uint32).reshape(height, width)
    pixels = np.stack([indices % 256, indices // 256, np.full_like(indices, 240)], axis=2).astype(np.uint8)
    image = Image.fromarray(pixels, "RGB")
    preprocessing = {"resize_mode": "center_crop", "crop_pct": crop_pct, "interpolation": "nearest"}

    prepared = prepare_bird_confirmation_image(image, input_size=336, preprocessing=preprocessing)
    processed = resize_with_preprocessing(prepared, 336, preprocessing=preprocessing)

    original_colors = set(map(tuple, pixels.reshape(-1, 3)))
    final_colors = set(map(tuple, np.asarray(processed).reshape(-1, 3)))
    assert original_colors <= final_colors
    assert image.tobytes() == pixels.tobytes()


def test_source_pixels_are_not_borrowed_from_a_neighbour():
    scene = Image.new("RGB", (100, 50), "red")
    scene.paste(Image.new("RGB", (50, 50), "blue"), (50, 0))
    own_crop = scene.crop((0, 0, 40, 40))
    prepared = prepare_bird_confirmation_image(
        own_crop, input_size=336, preprocessing={"resize_mode": "center_crop", "crop_pct": 0.875}
    )
    assert (0, 0, 255) not in set(map(tuple, np.asarray(prepared).reshape(-1, 3)))


@pytest.mark.parametrize("mode", ["letterbox", "direct_resize", "native_aspect_ratio"])
def test_preprocessing_that_preserves_the_subject_does_not_need_extra_padding(mode):
    image = Image.new("RGB", (80, 20), "green")
    result = prepare_bird_confirmation_image(image, input_size=336, preprocessing={"resize_mode": mode})
    assert result.size == image.size
    assert result.tobytes() == image.tobytes()
    assert result is not image


def test_large_subject_has_a_model_sized_evidence_canvas():
    image = Image.new("RGB", (7680, 10), "white")
    result = prepare_bird_confirmation_image(
        image, input_size=336, preprocessing={"resize_mode": "center_crop", "crop_pct": 0.875}
    )
    assert result.size == (384, 384)


@pytest.mark.parametrize("crop_pct", [0, -1, float("nan"), float("inf"), 0.001, True])
def test_invalid_or_unbounded_confirmation_geometry_is_rejected(crop_pct):
    with pytest.raises(ValueError):
        prepare_bird_confirmation_image(
            Image.new("RGB", (40, 20)),
            input_size=336,
            preprocessing={"resize_mode": "center_crop", "crop_pct": crop_pct},
        )


def test_confirmation_canvas_has_an_absolute_allocation_bound():
    with pytest.raises(ValueError):
        prepare_bird_confirmation_image(
            Image.new("RGB", (40, 20)),
            input_size=4096,
            preprocessing={"resize_mode": "center_crop", "crop_pct": 0.25},
        )
