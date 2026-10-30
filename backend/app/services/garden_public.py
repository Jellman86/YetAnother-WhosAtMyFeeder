"""What a public visitor may see of Garden animals: the bird detection rules, applied to confirmed captures."""

from datetime import datetime, timedelta, timezone

from app.config import settings
from app.utils.public_access import public_events_window, public_media_window

HIDDEN_CAMERA = "Hidden"


def _utc(observed_at: str) -> datetime:
    value = datetime.fromisoformat(observed_at.removesuffix("Z"))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _inside(stamp: datetime, window: tuple[datetime, datetime | None]) -> bool:
    start, end = window
    return stamp >= start and (end is None or stamp < end)


def guest_history_window(
    start: datetime | None, end: datetime | None, now: datetime | None = None
) -> tuple[datetime, datetime | None]:
    """Narrow a requested window to the public history window; never widen it."""
    cutoff, until = public_events_window(now)
    start = max(start, cutoff) if start else cutoff
    if until is not None:
        # The repository's end is inclusive; the public window's is not.
        last = until - timedelta(microseconds=1)
        end = min(end, last) if end else last
    return start, end


def guest_history_visible(observed_at: str, now: datetime | None = None) -> bool:
    return _inside(_utc(observed_at), public_events_window(now))


def guest_photo_visible(observed_at: str, now: datetime | None = None) -> bool:
    return settings.public_access.show_snapshots and _inside(_utc(observed_at), public_media_window(now))


def guest_clip_visible(observed_at: str, now: datetime | None = None) -> bool:
    return settings.public_access.show_clips and _inside(_utc(observed_at), public_media_window(now))


def guest_camera(camera: str) -> str:
    return camera if settings.public_access.show_camera_names else HIDDEN_CAMERA
