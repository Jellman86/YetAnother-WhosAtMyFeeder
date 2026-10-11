"""The owner's profile picture.

An upload is never stored as sent: it is decoded, turned upright from its EXIF orientation,
centre-cropped to a square, scaled to AVATAR_SIZE and re-encoded as a JPEG, which drops every
byte of metadata (location included) and anything that is not an image. The file lives beside
the config so it survives an image update, and is written to a temporary name and renamed so a
reader never sees half a file.
"""

from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

AVATAR_PATH = Path(os.getenv("AVATAR_PATH", "/config/profile/avatar.jpg"))
AVATAR_SIZE = 256
AVATAR_MAX_UPLOAD_BYTES = 8 * 1024 * 1024
# Far beyond any phone photo; refuses decompression bombs before Pillow's own warning.
AVATAR_MAX_PIXELS = 40_000_000


class AvatarError(ValueError):
    """An upload that is not a usable image; the message is safe to show."""


def render_avatar(data: bytes) -> bytes:
    """Decode an upload and return the stored JPEG. Raises AvatarError for anything unusable."""
    if not data:
        raise AvatarError("empty")
    if len(data) > AVATAR_MAX_UPLOAD_BYTES:
        raise AvatarError("too_large")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
            if width * height > AVATAR_MAX_PIXELS:
                raise AvatarError("too_many_pixels")
            probe.verify()
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB")
    except AvatarError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
        raise AvatarError("not_an_image") from exc
    square = ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE), method=Image.Resampling.LANCZOS)
    out = io.BytesIO()
    square.save(out, format="JPEG", quality=88, optimize=True)
    return out.getvalue()


def avatar_version(path: Path | None = None) -> int | None:
    """The stored picture's version (its modification time in ms), or None when there is none."""
    target = path or AVATAR_PATH
    try:
        return int(target.stat().st_mtime * 1000)
    except FileNotFoundError:
        return None


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


async def save_avatar(data: bytes, path: Path | None = None) -> int:
    target = path or AVATAR_PATH
    content = await asyncio.to_thread(render_avatar, data)
    await asyncio.to_thread(_write, target, content)
    version = avatar_version(target)
    if version is None:
        raise OSError("avatar was written but cannot be read back")
    return version


async def delete_avatar(path: Path | None = None) -> None:
    target = path or AVATAR_PATH
    await asyncio.to_thread(target.unlink, missing_ok=True)


async def read_avatar(path: Path | None = None) -> bytes | None:
    target = path or AVATAR_PATH
    try:
        return await asyncio.to_thread(target.read_bytes)
    except FileNotFoundError:
        return None
