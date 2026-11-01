"""Pure image preprocessing driven by a model spec's `preprocessing` contract."""

import math
from typing import Any, Optional

import numpy as np
from PIL import Image

from app.config import settings


def classifier_wants_bgr(preprocessing: Optional[dict[str, Any]]) -> bool:
    """True when a classifier model declares BGR tensor input.

    PIL decoding always gives RGB, so when a model was trained on BGR tensors
    (unusual for classifiers, but possible) we must reverse the channel axis
    before normalization. Previously `color_space: "BGR"` was silently dropped
    on the classifier path — only the crop-detector path honored it.
    """
    return str((preprocessing or {}).get("color_space") or "RGB").strip().upper() == "BGR"


def resolve_color_space(preprocessing: Optional[dict[str, Any]]) -> str:
    color_space = str((preprocessing or {}).get("color_space") or "RGB").strip().upper() or "RGB"
    # Only "RGB" and "L" (grayscale) are valid for classification preprocessing.
    # RGBA is excluded: alpha channels are not used by any supported model and produce
    # 4-channel tensors that break 3-element mean/std normalisation.
    # BGR is not a PIL mode; models requiring BGR must be handled explicitly.
    return color_space if color_space in {"RGB", "L"} else "RGB"


def resolve_resize_mode(preprocessing: Optional[dict[str, Any]], *, default: str = "letterbox") -> str:
    mode = str((preprocessing or {}).get("resize_mode") or default).strip().lower()
    if mode not in {"letterbox", "center_crop", "direct_resize", "native_aspect_ratio"}:
        return default
    return mode


def resolve_padding_color(preprocessing: Optional[dict[str, Any]], *, default: int = 128) -> tuple[int, int, int]:
    raw = (preprocessing or {}).get("padding_color", default)
    if isinstance(raw, int):
        value = max(0, min(255, int(raw)))
        return (value, value, value)
    if isinstance(raw, (list, tuple)) and len(raw) == 3:
        return tuple(max(0, min(255, int(v))) for v in raw)
    value = max(0, min(255, int(default)))
    return (value, value, value)


def resolve_interpolation(preprocessing: Optional[dict[str, Any]]) -> Image.Resampling:
    interpolation = str((preprocessing or {}).get("interpolation") or "bicubic").strip().lower()
    return {
        "nearest": Image.Resampling.NEAREST,
        "bilinear": Image.Resampling.BILINEAR,
        "bicubic": Image.Resampling.BICUBIC,
        "lanczos": Image.Resampling.LANCZOS,
    }.get(interpolation, Image.Resampling.BICUBIC)


def resize_preserving_aspect_shortest_edge(
    image: Image.Image,
    shortest_edge: int,
    *,
    interpolation: Image.Resampling,
    rounding: str = "round",
) -> Image.Image:
    width, height = image.size
    if width <= 0 or height <= 0:
        return image
    if width <= height:
        new_width = shortest_edge
        new_height = max(
            1,
            int(shortest_edge * height / width)
            if rounding == "floor"
            else int(round(height * (shortest_edge / width))),
        )
    else:
        new_height = shortest_edge
        new_width = max(
            1,
            int(shortest_edge * width / height)
            if rounding == "floor"
            else int(round(width * (shortest_edge / height))),
        )
    return image.resize((new_width, new_height), interpolation)


def center_crop_to_size(image: Image.Image, target_size: int) -> Image.Image:
    width, height = image.size
    left = max(0, int(round((width - target_size) / 2.0)))
    top = max(0, int(round((height - target_size) / 2.0)))
    right = left + target_size
    bottom = top + target_size
    return image.crop((left, top, right, bottom))


def native_aspect_resize(
    image: Image.Image, *, patch_size: int, max_seq_len: int, interpolation: Image.Resampling
) -> Image.Image:
    """Birder's native patch-grid contract (64-step search with ceiling).

    Keeping the token budget, rather than a square edge, preserves the aspect
    ratio the NaFlex encoder was trained to consume.
    """
    if patch_size <= 0 or max_seq_len <= 0:
        raise ValueError("Positive patch size and token budget required")
    width, height = image.size
    low, high = 0.0, max_seq_len / min(height, width)
    for _ in range(64):
        scale = (low + high) / 2.0
        grid_h, grid_w = max(1, math.ceil(height * scale)), max(1, math.ceil(width * scale))
        if grid_h * grid_w <= max_seq_len:
            low = scale
        else:
            high = scale
    grid_h, grid_w = max(1, math.ceil(height * low)), max(1, math.ceil(width * low))
    return image.resize((grid_w * patch_size, grid_h * patch_size), interpolation)


def inat_location_metadata(latitude: Any, longitude: Any) -> np.ndarray:
    """Official iNat DINOv2 eight-feature contract, with date/uncertainty absent.

    A real (0,0) location is distinct from missing coordinates. Never substitute
    today's date for the capture date, or invent a location uncertainty.
    """
    result = np.zeros((1, 8), dtype=np.float32)
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return result
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return result
    if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return result
    lat, lon = math.radians(lat), math.radians(lon)
    result[0, :3] = (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))
    result[0, 6] = 1
    return result


def classifier_auxiliary_inputs(preprocessing: dict[str, Any]) -> dict[str, np.ndarray]:
    contract = preprocessing.get("metadata_input")
    if contract is None:
        return {}
    if contract != "inat2021_location_v1":
        raise ValueError(f"Unsupported classifier metadata contract: {contract}")
    return {"metadata": inat_location_metadata(settings.location.latitude, settings.location.longitude)}


def resize_with_preprocessing(
    image: Image.Image,
    target_size: int,
    *,
    preprocessing: Optional[dict[str, Any]],
    default_resize_mode: str = "letterbox",
    default_padding_color: int = 128,
) -> Image.Image:
    image = image.convert(resolve_color_space(preprocessing))
    interpolation = resolve_interpolation(preprocessing)
    resize_mode = resolve_resize_mode(preprocessing, default=default_resize_mode)

    if resize_mode == "native_aspect_ratio":
        return native_aspect_resize(
            image,
            patch_size=int((preprocessing or {})["patch_size"]),
            max_seq_len=int((preprocessing or {})["max_seq_len"]),
            interpolation=interpolation,
        )

    if resize_mode == "direct_resize":
        return image.resize((target_size, target_size), interpolation)

    if resize_mode == "center_crop":
        crop_pct = float((preprocessing or {}).get("crop_pct") or 1.0)
        if crop_pct <= 0.0:
            crop_pct = 1.0
        scale_size = max(target_size, int(round(target_size / crop_pct)))
        resized = resize_preserving_aspect_shortest_edge(
            image,
            scale_size,
            interpolation=interpolation,
            rounding=str((preprocessing or {}).get("resize_rounding") or "round").strip().lower(),
        )
        return center_crop_to_size(resized, target_size)

    width, height = image.size
    scale = min(target_size / width, target_size / height)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    resized = image.resize((new_width, new_height), interpolation)
    canvas = Image.new(
        "RGB",
        (target_size, target_size),
        resolve_padding_color(preprocessing, default=default_padding_color),
    )
    canvas.paste(resized, ((target_size - new_width) // 2, (target_size - new_height) // 2))
    return canvas
