"""Synchronous image decoding helpers intended for ``asyncio.to_thread`` calls."""

from io import BytesIO
from pathlib import Path

from PIL import Image

# Shared bounds for image bytes from untrusted sources (uploads, Frigate,
# cached media). A 4K frame is about 8 megapixels, so these limits only
# refuse decompression-bomb shaped input.
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 80_000_000


def _reject_over_pixel_limit(image: Image.Image) -> None:
    width, height = image.size
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError(f"Image of {width}x{height} exceeds the {MAX_IMAGE_PIXELS // 1_000_000} megapixel pixel limit")


# Pillow's ICO/CUR plugins decode the embedded image inside Image.open()
# itself, before a size check could run, so their bytes are refused on the
# magic header instead of being expanded in memory first. Photo uploads
# are JPEG/PNG/WebP everywhere else in the app.
_EAGER_DECODE_MAGICS = (b"\x00\x00\x01\x00", b"\x00\x00\x02\x00")


def decode_image_bytes(contents: bytes, *, convert_rgb: bool = False) -> Image.Image:
    """Fully decode image bytes so later pixel access performs no file I/O."""
    if contents[:4] in _EAGER_DECODE_MAGICS:
        raise ValueError("ICO/CUR images are not supported")
    image = Image.open(BytesIO(contents))
    _reject_over_pixel_limit(image)
    image.load()
    return image.convert("RGB") if convert_rgb else image


def load_rgb_image(path: str | Path) -> Image.Image:
    """Load and detach an RGB image from its source file."""
    with open(path, "rb") as header:
        if header.read(4) in _EAGER_DECODE_MAGICS:
            raise ValueError("ICO/CUR images are not supported")
    with Image.open(path) as image:
        _reject_over_pixel_limit(image)
        return image.convert("RGB")
