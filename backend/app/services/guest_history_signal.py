"""Which field-free invalidation a guest's live stream receives for a history message.

A guest page must drop what it holds at once when records leave the shared history, but it must
not drop anything when a capture arrives, or a busy feeder would keep the page from ever loading.
So a narrowing travels as its own signal. Narrowing is an allowlist: a delete, or an update whose
record is now hidden. Other recognised history messages are ordinary changes. Neither signal
carries an identifier or any other field from the producer.
"""

from collections.abc import Mapping
from typing import Final

PUBLIC_HISTORY_CHANGED: Final = "public_history_changed"
PUBLIC_HISTORY_NARROWED: Final = "public_history_narrowed"

_HISTORY_MESSAGE_TYPES: Final = frozenset(
    {"detection", "detection_updated", "detection_deleted", "audio_history_changed"}
)


def _record_is_now_hidden(message: Mapping[str, object]) -> bool:
    data = message.get("data")
    return isinstance(data, Mapping) and data.get("is_hidden") is True


def guest_history_signal(message: Mapping[str, object]) -> str | None:
    """The guest signal for an owner history message, or None when it is not one."""
    event_type = message.get("type")
    if not isinstance(event_type, str) or event_type not in _HISTORY_MESSAGE_TYPES:
        return None
    if event_type == "detection_deleted":
        return PUBLIC_HISTORY_NARROWED
    if event_type == "detection_updated" and _record_is_now_hidden(message):
        return PUBLIC_HISTORY_NARROWED
    return PUBLIC_HISTORY_CHANGED
