"""What an alert says, separate from the channel that carries it and from the rules that send it.

Bird and Garden alerts build their own messages and keep their own delivery policies; the
per-channel transports in `notifications.transports` only render and deliver a message.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Attachment:
    """A photo sent with the alert as bytes, never as a link that could carry a media token."""

    filename: str
    content: bytes = field(repr=False)
    content_type: str = "image/jpeg"


@dataclass(frozen=True)
class SubjectLink:
    url: str
    label: str


@dataclass(frozen=True)
class NotificationMessage:
    title: str
    body: str = ""
    # The subject's own page, shown as each channel's link or button.
    link: SubjectLink | None = None
    # Where a text-only alert points when the subject has no page of its own (a bird snapshot).
    fallback_link: SubjectLink | None = None
    attachment: Attachment | None = None
    # A photo a channel may show by address when none is attached (a bird snapshot on Frigate).
    image_url: str | None = None
    # When the subject was seen; a naive time is UTC.
    occurred_at: datetime | None = None

    def occurred_utc(self) -> datetime | None:
        if self.occurred_at is None:
            return None
        if self.occurred_at.tzinfo is None:
            return self.occurred_at.replace(tzinfo=timezone.utc)
        return self.occurred_at.astimezone(timezone.utc)


@dataclass(frozen=True)
class DeliveryResult:
    """Whether the channel accepted the alert. Failures carry a type and status, never provider text."""

    sent: bool
    error_type: str | None = None
    status_code: int | None = None
