"""Normalize which image representation reached the species classifier."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import math
from typing import Any

import structlog


log = structlog.get_logger()


_CROPPED_SNAPSHOT_SOURCES = frozenset(
    {
        "frigate_snapshot_cropped",
        "high_quality_bird_crop",
        "hq_candidate_frigate_hint_crop",
        "hq_candidate_frigate_snapshot_fallback",
        "hq_candidate_model_crop",
    }
)
_FULL_FRAME_SNAPSHOT_SOURCES = frozenset(
    {
        "frigate_snapshot",
        "frigate_snapshot_uncropped",
        "frigate_recording_frame",
        "frigate_thumbnail",
        "high_quality_snapshot",
        "hq_candidate_full_frame",
    }
)
_FRIGATE_HINT_ALIGNED_SNAPSHOT_SOURCES = frozenset(
    {
        "frigate_snapshot",
        "frigate_snapshot_uncropped",
    }
)


@dataclass(frozen=True)
class ClassificationInputProvenance:
    input_source: str
    is_cropped: bool


def _validated_frigate_hint(value: Any) -> list[float | int] | None:
    """Copy a usable Frigate ``[left, top, width, height]`` hint.

    Frigate emits normalized coordinates today, while the classifier also accepts
    pixel coordinates. Keep both contracts, but reject malformed/non-finite data
    before it crosses process boundaries or influences crop selection.
    """
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    if any(isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)) for coordinate in value):
        return None
    if not all(math.isfinite(float(coordinate)) for coordinate in value):
        return None

    left, top, width, height = value
    if float(left) < 0.0 or float(top) < 0.0 or float(width) <= 0.0 or float(height) <= 0.0:
        return None
    return list(value)


def build_snapshot_classification_input_context(
    *,
    event_id: str,
    event_data: dict[str, Any] | None,
    provenance: ClassificationInputProvenance,
) -> dict[str, object]:
    """Build the canonical context for a snapshot classification request.

    Completed Frigate snapshots are fetched explicitly as full frames so their
    representation does not depend on the installed Frigate version or saved
    snapshot format. When that frame is aligned with the event metadata, request
    local reconstruction of Frigate's crop before classification. This is input
    restoration, not the selected model's optional crop-detector policy. A
    snapshot already known to be cropped must never receive those hints, which
    prevents applying full-frame coordinates to a smaller image.
    """
    context: dict[str, object] = {
        "is_cropped": bool(provenance.is_cropped),
        "event_id": str(event_id),
        "input_source": str(provenance.input_source),
    }
    if provenance.is_cropped or provenance.input_source not in _FRIGATE_HINT_ALIGNED_SNAPSHOT_SOURCES:
        return context

    event_payload = event_data if isinstance(event_data, dict) else {}
    payload = event_payload.get("data")
    payload = payload if isinstance(payload, dict) else {}
    frigate_box = _validated_frigate_hint(payload.get("box") or event_payload.get("box"))
    frigate_region = _validated_frigate_hint(payload.get("region") or event_payload.get("region"))
    if frigate_box is not None:
        context["frigate_box"] = frigate_box
    if frigate_region is not None:
        context["frigate_region"] = frigate_region
    if frigate_box is not None or frigate_region is not None:
        context["restore_frigate_snapshot_crop"] = True
    return context


def cached_snapshot_input_provenance(metadata: dict[str, Any] | None) -> ClassificationInputProvenance:
    """Return trusted cache provenance without guessing from image dimensions."""
    source = str((metadata or {}).get("source") or "").strip().lower()
    if source in _CROPPED_SNAPSHOT_SOURCES:
        return ClassificationInputProvenance(input_source=source, is_cropped=True)
    if source in _FULL_FRAME_SNAPSHOT_SOURCES:
        return ClassificationInputProvenance(input_source=source, is_cropped=False)
    return ClassificationInputProvenance(input_source="cached_snapshot_unknown", is_cropped=False)


def frigate_snapshot_input_provenance(event_data: dict[str, Any] | None) -> ClassificationInputProvenance:
    """Reflect Frigate's crop-query semantics for live versus completed events."""
    event_is_live = isinstance(event_data, dict) and "end_time" in event_data and event_data.get("end_time") is None
    if event_is_live:
        return ClassificationInputProvenance(input_source="frigate_snapshot_cropped", is_cropped=True)
    return ClassificationInputProvenance(input_source="frigate_snapshot", is_cropped=False)


async def load_snapshot_classification_input(
    event_id: str,
    *,
    event_data: dict[str, Any] | None = None,
    media_cache_service: Any | None = None,
    frigate_client_service: Any | None = None,
) -> tuple[bytes | None, ClassificationInputProvenance]:
    """Prefer the retained best snapshot and return its trustworthy provenance."""
    from app.services.frigate_client import frigate_client
    from app.services.media_cache import media_cache

    cache = media_cache_service if media_cache_service is not None else media_cache
    client = frigate_client_service if frigate_client_service is not None else frigate_client
    try:
        cached = await cache.get_snapshot(event_id)
    except Exception as exc:
        log.warning(
            "Cached classification snapshot could not be read; trying Frigate",
            event_id=event_id,
            error=str(exc),
        )
        cached = None
    if cached:
        try:
            metadata_result = cache.get_snapshot_metadata(event_id)
            metadata = await metadata_result if inspect.isawaitable(metadata_result) else metadata_result
        except Exception as exc:
            log.warning(
                "Cached classification snapshot metadata could not be read",
                event_id=event_id,
                error=str(exc),
            )
            metadata = None
        return cached, cached_snapshot_input_provenance(metadata)

    provenance = frigate_snapshot_input_provenance(event_data)
    snapshot = await client.get_snapshot(event_id, crop=provenance.is_cropped, quality=95)
    return snapshot, provenance
