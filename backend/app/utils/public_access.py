from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
import sqlite3

from fastapi import HTTPException

from app.config import settings
from app.database import DatabasePoolTimeout
from app.utils.api_datetime import utc_naive_datetime


def _cap_public_days(value: int) -> int:
    # Public access window is intentionally capped to avoid exposing very deep history.
    return max(0, min(365, int(value)))


def effective_public_events_days() -> int:
    """Effective guest-visible event window in days.

    Returns:
        0 for "today only"
        1..365 for "last N days"
    """
    mode = (settings.public_access.historical_days_mode or "custom").strip().lower()
    if mode == "retention":
        # retention_days: 0 means unlimited; public is capped to 365.
        retention_days = int(settings.maintenance.retention_days or 0)
        return _cap_public_days(retention_days if retention_days > 0 else 365)
    return _cap_public_days(settings.public_access.show_historical_days)


def effective_public_media_days() -> int:
    """Effective guest-visible media window in days (clips/snapshots)."""
    mode = (settings.public_access.media_days_mode or "custom").strip().lower()
    if mode == "retention":
        retention_days = int(settings.maintenance.retention_days or 0)
        return _cap_public_days(retention_days if retention_days > 0 else 365)
    return _cap_public_days(settings.public_access.media_historical_days)


def approximate_coordinate(value: float | None) -> float | None:
    """One decimal place is roughly 11 km: a town, not a garden."""
    if value is None:
        return None
    return round(float(value), 1)


def guest_location() -> tuple[float | None, float | None]:
    """The configured location at the precision the owner shares publicly."""
    lat = settings.location.latitude
    lng = settings.location.longitude
    if settings.public_access.location_precision == "exact":
        return lat, lng
    return approximate_coordinate(lat), approximate_coordinate(lng)


def public_audio_allowed() -> bool:
    return bool(settings.public_access.show_audio)


def hide_public_audio_fields(detection) -> None:
    """Apply the audio switch to visual representations as well as audio routes."""
    detection.audio_confirmed = False
    detection.audio_species = None
    detection.audio_score = None
    detection.audio_context_species = None


def public_events_cutoff() -> datetime:
    """Same date-at-midnight boundary used by the public visual-history routes."""
    return datetime.combine(
        date.today() - timedelta(days=effective_public_events_days()), datetime.min.time(), tzinfo=timezone.utc
    )


def public_events_end() -> datetime | None:
    return public_events_cutoff() + timedelta(days=1) if effective_public_events_days() == 0 else None


def public_event_visible(event) -> bool:
    if event is None or event.is_hidden:
        return False
    stamp = utc_naive_datetime(event.detection_time)
    cutoff = public_events_cutoff().replace(tzinfo=None)
    return stamp >= cutoff and (effective_public_events_days() != 0 or stamp < cutoff + timedelta(days=1))


@asynccontextmanager
async def privacy_checked_db(factory):
    """A failed visibility lookup never grants access or exposes database details."""
    try:
        async with factory() as db:
            yield db
    except (sqlite3.DatabaseError, DatabasePoolTimeout) as exc:
        raise HTTPException(
            status_code=503, detail="History temporarily unavailable.", headers={"Retry-After": "5"}
        ) from exc


async def refresh_public_audio_fields(detection, repo, evidence: dict | None = None) -> None:
    """Authorize stored annotations using the same mapped evidence as public counts."""
    if not settings.public_access.show_audio or not detection.audio_species:
        hide_public_audio_fields(detection)
        return
    if evidence is None:
        batch = await repo.get_public_audio_for_detections([detection])
        evidence = batch.get(detection.frigate_event, {})
    best = evidence.get("primary")
    if best is None:
        hide_public_audio_fields(detection)
        return
    detection.audio_species = best["species"]
    detection.audio_score = best["confidence"]
