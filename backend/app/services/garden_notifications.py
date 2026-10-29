"""Private, explicitly selected Garden alerts; no bird notification rules or exports."""

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import structlog

from app.config import settings
from app.database import get_db
from app.repositories.garden_notification_repository import GardenNotificationRepository
from app.repositories.garden_repository import GardenCapture
from app.services.notification_dispatcher import notification_dispatcher
from app.utils.api_datetime import utc_naive_now

log = structlog.get_logger()
Sender = Callable[[str, GardenCapture], Awaitable[bool]]


def eligible(capture: GardenCapture | None, *, enabled: bool, cameras: list[str], now: datetime) -> bool:
    if not enabled or capture is None or capture.camera not in cameras or capture.status != "confirmed":
        return False
    # A correction does not replay alerts or send the superseded model name.
    if capture.owner_identification is not None:
        return False
    identity = capture.identification
    if not identity or identity.outcome != "suggestion" or identity.review != "accepted" or not identity.name:
        return False
    observed = datetime.fromisoformat(capture.observed_at).replace(tzinfo=timezone.utc)
    # An opt-in or a delayed queue must not replay old history as a new visit.
    return 0 <= (now.replace(tzinfo=timezone.utc) - observed).total_seconds() <= 300


class GardenNotificationService:
    def __init__(self, sender: Sender | None = None) -> None:
        if sender is None:
            from app.services.garden_notification_transport import send_garden_notification

            sender = send_garden_notification
        self.sender = sender

    def enabled(self) -> bool:
        return settings.system.beta_garden_animals and settings.frigate.garden_notifications_enabled

    async def schedule(self, capture_id: str) -> None:
        if self.enabled() and settings.frigate.garden_notification_channels:
            await notification_dispatcher.enqueue("garden:" + capture_id, lambda: self.deliver(capture_id))

    async def status_counts(self) -> dict[str, int]:
        async with get_db() as db:
            return await GardenNotificationRepository(db).counts()

    async def deliver(self, capture_id: str) -> None:
        for channel in dict.fromkeys(settings.frigate.garden_notification_channels):
            async with get_db() as db:
                repo = GardenNotificationRepository(db)
                capture = await repo.get(capture_id)
                if not eligible(
                    capture, enabled=self.enabled(), cameras=settings.frigate.garden_cameras, now=utc_naive_now()
                ):
                    return
                if not await repo.claim(capture_id, channel, utc_naive_now().isoformat()):
                    continue
            async with get_db() as db:
                current = await GardenNotificationRepository(db).get(capture_id)
            if (
                current != capture
                or channel not in settings.frigate.garden_notification_channels
                or not eligible(
                    current, enabled=self.enabled(), cameras=settings.frigate.garden_cameras, now=utc_naive_now()
                )
            ):
                state = "skipped"
            else:
                try:
                    state = "sent" if await self.sender(channel, current) else "failed"
                except Exception as error:
                    log.warning("garden_notification_failed", channel=channel, error_type=type(error).__name__)
                    state = "failed"
            async with get_db() as db:
                await GardenNotificationRepository(db).finish(capture_id, channel, state)
            log.info("garden_notification_attempt", channel=channel, outcome=state)


garden_notification_service = GardenNotificationService()
