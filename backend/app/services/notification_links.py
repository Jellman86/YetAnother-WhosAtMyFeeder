"""Where a notification sends its reader: back to the detection on this install."""

from typing import Optional
from urllib.parse import quote

from app.config_models import NotificationSettings


def instance_base(notifications: NotificationSettings) -> Optional[str]:
    """The public address of this install, or None when the owner never set one.

    `email.dashboard_url` predates the shared setting and is honoured as a fallback, so an
    install that only ever configured email links keeps them on every channel.
    """
    for candidate in (notifications.instance_url, notifications.email.dashboard_url):
        base = (candidate or "").strip().rstrip("/")
        if base:
            return base
    return None


def detection_link(base: Optional[str], frigate_event: Optional[str]) -> Optional[str]:
    """The page that shows one detection, or the detections page when there is no event."""
    if not base:
        return None
    if not frigate_event:
        return f"{base}/events"
    return f"{base}/events?event={quote(frigate_event, safe='')}"
