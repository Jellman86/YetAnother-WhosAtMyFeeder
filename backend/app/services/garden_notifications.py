"""Garden alerts for newly named animals: their own opt-in, freshness and per-visit dedupe.

Bird filters, notification mode and the bird cooldown do not apply. Garden alerts are already
limited to one attempt per channel per visit, and a shared cooldown would let a bird alert
silence an animal one (or the reverse) for reasons the owner cannot see.
"""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from datetime import datetime, timedelta, timezone

import structlog

from app.config import settings
from app.database import get_db
from app.repositories.garden_notification_repository import GardenNotificationRepository
from app.repositories.garden_repository import GardenCapture
from app.services.notification_dispatcher import notification_dispatcher
from app.utils.api_datetime import utc_naive_now

log = structlog.get_logger()
Sender = Callable[[str, GardenCapture, bytes | None], Awaitable[bool]]
PhotoLoader = Callable[[GardenCapture], Awaitable[bytes | None]]

CHANNELS: tuple[str, ...] = ("discord", "telegram", "pushover", "email")
# A name decided this recently is news. Naming runs minutes after the sighting (measured median
# 417 s for Frigate events and 631 s for motion photos), so freshness starts at the decision.
DECISION_FRESHNESS = timedelta(minutes=5)
# However recent the decision, an older sighting is history: enabling alerts, a restart or a
# late backlog never sends it as a new visit.
SIGHTING_MAX_AGE = timedelta(hours=2)


def _utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.removesuffix("Z"))
        except ValueError:
            return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def decision_time(capture: GardenCapture, accepted_at: datetime | None) -> datetime | None:
    """When the name was decided: the automatic check that named it, or the owner's acceptance."""
    identity = capture.identification
    if identity is not None and identity.automatic:
        return _utc(capture.automatic_check.checked_at) if capture.automatic_check else None
    return _utc(accepted_at)


def eligible(
    capture: GardenCapture | None,
    *,
    enabled: bool,
    cameras: list[str],
    decided_at: datetime | None,
    now: datetime,
) -> bool:
    if not enabled or capture is None or capture.camera not in cameras or capture.status != "confirmed":
        return False
    # A correction does not replay alerts or send the superseded model name.
    if capture.owner_identification is not None:
        return False
    identity = capture.identification
    if not identity or identity.outcome != "suggestion" or identity.review != "accepted" or not identity.name:
        return False
    current, decided, observed = _utc(now), _utc(decided_at), _utc(capture.observed_at)
    if current is None or decided is None or observed is None:
        return False
    return (
        timedelta(0) <= current - decided <= DECISION_FRESHNESS
        and timedelta(0) <= current - observed <= SIGHTING_MAX_AGE
    )


def delivery_channels(
    *,
    use_bird_channels: bool,
    selected: Iterable[str],
    bird_enabled: Mapping[str, bool],
    configured: Mapping[str, bool],
) -> list[str]:
    """Channels a Garden alert goes to now.

    Following the bird channels means those switched on and able to send; an explicit choice is
    kept as chosen, so a channel missing credentials is attempted and reported as failed.
    """
    if use_bird_channels:
        return [channel for channel in CHANNELS if bird_enabled.get(channel) and configured.get(channel)]
    return [channel for channel in dict.fromkeys(selected) if channel in CHANNELS]


def bird_channel_switches() -> dict[str, bool]:
    cfg = settings.notifications
    return {
        "discord": cfg.discord.enabled,
        "telegram": cfg.telegram.enabled,
        "pushover": cfg.pushover.enabled,
        "email": cfg.email.enabled,
    }


def configured_channels() -> dict[str, bool]:
    from app.services.garden_notification_transport import channel_configured

    return {channel: channel_configured(channel) for channel in CHANNELS}


def current_delivery_channels() -> list[str]:
    return delivery_channels(
        use_bird_channels=settings.frigate.garden_notifications_use_bird_channels,
        selected=settings.frigate.garden_notification_channels,
        bird_enabled=bird_channel_switches(),
        configured=configured_channels(),
    )


class GardenNotificationService:
    def __init__(self, sender: Sender | None = None, photo_loader: PhotoLoader | None = None) -> None:
        if sender is None or photo_loader is None:
            from app.services.garden_notification_transport import garden_photo, send_garden_notification

            sender = sender or send_garden_notification
            photo_loader = photo_loader or garden_photo
        self.sender = sender
        self.photo_loader = photo_loader

    def enabled(self) -> bool:
        return settings.system.beta_garden_animals and settings.frigate.garden_notifications_enabled

    def _eligible(self, capture: GardenCapture | None, accepted_at: datetime | None) -> bool:
        return eligible(
            capture,
            enabled=self.enabled(),
            cameras=settings.frigate.garden_cameras,
            decided_at=decision_time(capture, accepted_at) if capture else None,
            now=utc_naive_now(),
        )

    async def schedule(self, capture_id: str, accepted_at: datetime | None = None) -> None:
        """Queue one delivery; `accepted_at` is when the owner accepted the name, if they did."""
        if self.enabled() and current_delivery_channels():
            await notification_dispatcher.enqueue(
                "garden:" + capture_id, lambda: self.deliver(capture_id, accepted_at=accepted_at)
            )

    async def status_counts(self) -> dict[str, int]:
        async with get_db() as db:
            return await GardenNotificationRepository(db).counts()

    async def deliver(self, capture_id: str, *, accepted_at: datetime | None = None) -> None:
        photo: bytes | None = None
        photo_loaded = False
        for channel in current_delivery_channels():
            async with get_db() as db:
                repo = GardenNotificationRepository(db)
                capture = await repo.get(capture_id)
                if not self._eligible(capture, accepted_at):
                    return
                if not await repo.claim(capture_id, channel, utc_naive_now().isoformat()):
                    continue
            # The photo is read before the final check, so a privacy change while it loads still stops the send.
            if not photo_loaded and settings.frigate.garden_notifications_include_photo:
                photo_loaded = True
                try:
                    photo = await self.photo_loader(capture)
                except Exception as error:
                    # The alert still goes, as text: a missing photo is not a reason to drop it.
                    log.warning("garden_notification_photo_unavailable", error_type=type(error).__name__)
            async with get_db() as db:
                current = await GardenNotificationRepository(db).get(capture_id)
            # The review token covers status, review and identity; a crop saved meanwhile changes none of them.
            attachment = photo if settings.frigate.garden_notifications_include_photo else None
            if (
                current is None
                or current.review_token != capture.review_token
                or current.camera != capture.camera
                or channel not in current_delivery_channels()
                or not self._eligible(current, accepted_at)
            ):
                state = "skipped"
            else:
                try:
                    state = "sent" if await self.sender(channel, current, attachment) else "failed"
                except Exception as error:
                    log.warning("garden_notification_failed", channel=channel, error_type=type(error).__name__)
                    state = "failed"
            async with get_db() as db:
                await GardenNotificationRepository(db).finish(capture_id, channel, state)
            log.info("garden_notification_attempt", channel=channel, outcome=state, with_photo=attachment is not None)


garden_notification_service = GardenNotificationService()
