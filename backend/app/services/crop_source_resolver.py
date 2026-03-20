from __future__ import annotations

from io import BytesIO
from typing import Any, Callable

from PIL import Image
import structlog

from app.models.ai_models import ClassificationInputContext
from app.services.media_cache import media_cache

log = structlog.get_logger()


class CropSourceResolver:
    """Resolve a better source image for crop generation when available."""

    def __init__(
        self,
        *,
        snapshot_loader: Callable[[str], bytes | None] | None = None,
    ):
        self._snapshot_loader = snapshot_loader or media_cache.get_snapshot_sync

    def resolve(
        self,
        image: Image.Image,
        *,
        input_context: Any | None,
        source_preference: str,
    ) -> tuple[Image.Image, dict[str, Any]]:
        normalized_input_context = self._normalize_input_context(input_context)
        normalized_preference = str(source_preference or "standard").strip().lower()
        if normalized_preference != "high_quality":
            return image, {"source_reason": "standard"}
        if bool(normalized_input_context.is_cropped):
            return image, {"source_reason": "input_already_cropped"}

        event_id = self._extract_event_id(normalized_input_context)
        if not event_id:
            return image, {"source_reason": "missing_event_id"}

        try:
            snapshot_bytes = self._snapshot_loader(event_id)
        except Exception as exc:
            log.warning("High-quality crop source lookup failed", event_id=event_id, error=str(exc))
            return image, {"source_reason": "high_quality_lookup_failed"}

        if not snapshot_bytes:
            return image, {"source_reason": "high_quality_unavailable"}

        try:
            resolved = Image.open(BytesIO(snapshot_bytes)).convert("RGB")
        except Exception as exc:
            log.warning("High-quality crop source decode failed", event_id=event_id, error=str(exc))
            return image, {"source_reason": "high_quality_decode_failed"}

        return resolved, {"source_reason": "high_quality_snapshot"}

    def _normalize_input_context(self, input_context: Any | None) -> ClassificationInputContext:
        if isinstance(input_context, ClassificationInputContext):
            return input_context
        if input_context is None:
            return ClassificationInputContext()
        payload: dict[str, Any]
        if isinstance(input_context, dict):
            payload = dict(input_context)
        else:
            payload = dict(getattr(input_context, "__dict__", {}) or {})
        try:
            return ClassificationInputContext.model_validate(payload)
        except Exception:
            return ClassificationInputContext()

    def _extract_event_id(self, input_context: ClassificationInputContext) -> str | None:
        extra = getattr(input_context, "__pydantic_extra__", {}) or {}
        event_id = extra.get("event_id")
        if event_id is None:
            event_id = getattr(input_context, "event_id", None)
        normalized = str(event_id or "").strip()
        return normalized or None


crop_source_resolver = CropSourceResolver()
