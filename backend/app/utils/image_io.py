"""Synchronous image decoding helpers intended for ``asyncio.to_thread`` calls."""

from io import BytesIO
from pathlib import Path

from PIL import Image


def decode_image_bytes(contents: bytes, *, convert_rgb: bool = False) -> Image.Image:
    """Fully decode image bytes so later pixel access performs no file I/O."""
    image = Image.open(BytesIO(contents))
    image.load()
    return image.convert("RGB") if convert_rgb else image


def load_rgb_image(path: str | Path) -> Image.Image:
    """Load and detach an RGB image from its source file."""
    with Image.open(path) as image:
        return image.convert("RGB")
