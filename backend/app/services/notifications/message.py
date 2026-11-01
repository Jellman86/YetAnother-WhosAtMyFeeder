"""What an alert says, separate from the channel that carries it and from the rules that send it.

Bird and Garden alerts build their own messages and keep their own delivery policies; the
per-channel transports in `notifications.transports` only render and deliver a message.
"""

from dataclasses import dataclass, field


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


@dataclass(frozen=True)
class DeliveryResult:
    """Whether the channel accepted the alert. Failures carry a type and status, never provider text."""

    sent: bool
    error_type: str | None = None
    status_code: int | None = None
