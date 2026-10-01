from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import sqlite3
from typing import Iterator

from fastapi import HTTPException

from app.config import settings
from app.database import DatabasePoolTimeout
from app.utils.api_datetime import utc_naive_datetime


@dataclass
class PublicCalendarScope:
    day: date | None = None
    active: bool = True

    def close(self) -> None:
        # Child tasks inherit the same object; resetting only our token would
        # leave their copied contexts holding yesterday's policy after response.
        self.active = False


_request_calendar: ContextVar[PublicCalendarScope | None] = ContextVar("public_request_calendar", default=None)


@contextmanager
def public_calendar_scope() -> Iterator[PublicCalendarScope]:
    calendar = PublicCalendarScope()
    token = _request_calendar.set(calendar)
    try:
        yield calendar
    finally:
        calendar.close()
        _request_calendar.reset(token)


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


def public_utc_day(now: datetime | None = None) -> date:
    """Share one lazily captured UTC day within a response, including child queries."""
    if now is not None and (now.tzinfo is None or now.utcoffset() is None):
        raise ValueError("Public calendar bounds require an aware datetime")
    calendar = _request_calendar.get()
    if calendar is not None and calendar.active and calendar.day is not None:
        return calendar.day
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Public calendar bounds require an aware datetime")
    day = instant.astimezone(timezone.utc).date()
    if calendar is not None and calendar.active:
        calendar.day = day
    return day


def _public_window(days: int, now: datetime | None = None) -> tuple[datetime, datetime | None]:
    start = datetime.combine(public_utc_day(now) - timedelta(days=days), datetime.min.time(), tzinfo=timezone.utc)
    return start, start + timedelta(days=1) if days == 0 else None


def public_events_window(now: datetime | None = None) -> tuple[datetime, datetime | None]:
    """Read one policy instant for an inclusive start and exclusive today-only end."""
    return _public_window(effective_public_events_days(), now)


def public_event_query_bounds(now: datetime | None = None) -> dict[str, datetime | None]:
    """Repository history queries share the same single-instant UTC admission bounds."""
    start, end = public_events_window(now)
    return {"start_date": start, "end_date": end}


def public_events_cutoff(now: datetime | None = None) -> datetime:
    """Inclusive midnight UTC boundary for shared event history."""
    return public_events_window(now)[0]


def public_events_end(now: datetime | None = None) -> datetime | None:
    """Exclusive next midnight UTC in today-only mode."""
    return public_events_window(now)[1]


def public_media_window(now: datetime | None = None) -> tuple[datetime, datetime | None]:
    """Shared photographs and clips use the same UTC calendar policy as history."""
    return _public_window(effective_public_media_days(), now)


def public_event_visible(event, now: datetime | None = None) -> bool:
    if event is None or event.is_hidden:
        return False
    stamp = utc_naive_datetime(event.detection_time)
    cutoff, end = public_events_window(now)
    return stamp >= cutoff.replace(tzinfo=None) and (end is None or stamp < end.replace(tzinfo=None))


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
