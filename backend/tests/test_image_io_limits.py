"""Decoding untrusted image bytes must stay within bounded size and pixels."""

import io

import pytest
from PIL import Image

from app.utils import image_io
from app.utils.image_io import decode_image_bytes


def _png_bytes(size=(20, 20)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color="white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_decode_image_bytes_rejects_images_over_the_pixel_limit(monkeypatch):
    monkeypatch.setattr(image_io, "MAX_IMAGE_PIXELS", 100)

    with pytest.raises(ValueError, match="pixel limit"):
        decode_image_bytes(_png_bytes())


def test_decode_image_bytes_accepts_images_within_the_pixel_limit(monkeypatch):
    monkeypatch.setattr(image_io, "MAX_IMAGE_PIXELS", 100)

    image = decode_image_bytes(_png_bytes(size=(5, 5)))

    assert image.size == (5, 5)
