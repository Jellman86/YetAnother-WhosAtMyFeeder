from __future__ import annotations

from app.config import settings


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
