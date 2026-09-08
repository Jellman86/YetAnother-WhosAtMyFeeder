"""Where a notification sends its reader: the detection here, or the tracked object in Frigate."""

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
    """The page that shows one detection here, or the detections page when there is no event."""
    if not base:
        return None
    if not frigate_event:
        return f"{base}/events"
    return f"{base}/events?event={quote(frigate_event, safe='')}"


def frigate_link(frigate_external_url: str, frigate_event: Optional[str]) -> Optional[str]:
    """The same tracked object in Frigate's Explore page, which reads `event_id` (Frigate 0.15+).

    Frigate's own notifications deep-link by review id, which YA-WAMF never holds; the Explore
    route is the one that works from an event id. No public Frigate address means no link, never
    a fallback to the internal one, which a phone could not reach anyway.
    """
    base = (frigate_external_url or "").strip().rstrip("/")
    if not base:
        return None
    if not frigate_event:
        return f"{base}/explore"
    return f"{base}/explore?event_id={quote(frigate_event, safe='')}"


def notification_link(
    notifications: NotificationSettings, frigate_external_url: str, frigate_event: Optional[str]
) -> Optional[str]:
    """The link every channel carries for this detection, honouring the owner's choice of target."""
    if notifications.link_target == "frigate":
        return frigate_link(frigate_external_url, frigate_event)
    return detection_link(instance_base(notifications), frigate_event)
