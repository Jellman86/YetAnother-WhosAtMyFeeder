"""Normalize which image representation reached the species classifier."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
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


@dataclass(frozen=True)
class ClassificationInputProvenance:
    input_source: str
    is_cropped: bool


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

    snapshot = await client.get_snapshot(event_id, crop=True, quality=95)
    return snapshot, frigate_snapshot_input_provenance(event_data)
