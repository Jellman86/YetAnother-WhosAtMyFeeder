from typing import Optional, Dict, Any

import structlog

from app.config import settings
from app.database import get_db
from app.repositories.detection_repository import DetectionRepository
from app.services.frigate_client import frigate_client
from app.services.notification_service import notification_service
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.services.video_classification_waiter import video_classification_waiter
from app.utils.tasks import create_background_task

log = structlog.get_logger()


class NotificationOrchestrator:
    """Handle notification decisioning and dispatch for detections."""

    def _should_notify(
        self,
        event_type: str,
        notify_mode: str,
        changed: bool,
        was_inserted: bool,
        already_notified: bool
    ) -> tuple[bool, bool]:
        """Determine notification behavior for an event."""
        was_updated = changed and not was_inserted
        if notify_mode == "silent":
            return False, was_updated
        if notify_mode == "final":
            return event_type == "end" and not already_notified, was_updated
        if notify_mode == "standard":
            return event_type == "new" and not already_notified, was_updated
        if notify_mode == "realtime":
            if event_type == "new":
                return not already_notified, was_updated
            return was_updated, was_updated
        if event_type == "new":
            return settings.notifications.notify_on_insert and not already_notified, was_updated
        return settings.notifications.notify_on_update and was_updated and not already_notified, was_updated

    async def _mark_notified(self, event_id: str) -> None:
        async with get_db() as db:
            repo = DetectionRepository(db)
            await repo.mark_notified(event_id)

    async def _get_detection(self, event_id: str):
        async with get_db() as db:
            repo = DetectionRepository(db)
            return await repo.get_by_frigate_event(event_id)

    async def _send_notification(
        self,
        event: Any,
        label: str,
        score: float,
        audio_confirmed: bool,
        audio_species: Optional[str],
        snapshot_data: Optional[bytes],
        channels: Optional[list[str]] = None
    ) -> bool:
        snapshot_url = f"{settings.frigate.frigate_url}/api/events/{event.frigate_event}/snapshot.jpg"

        needs_snapshot = (
            (settings.notifications.pushover.enabled and settings.notifications.pushover.include_snapshot) or
            (settings.notifications.telegram.enabled and settings.notifications.telegram.include_snapshot) or
            (settings.notifications.discord.enabled and settings.notifications.discord.include_snapshot) or
            (settings.notifications.email.enabled and settings.notifications.email.include_snapshot)
        )

        if snapshot_data is None and needs_snapshot:
            snapshot_data = await frigate_client.get_snapshot(event.frigate_event, crop=True, quality=85)

        taxonomy = await taxonomy_service.get_names(label)

        return await notification_service.notify_detection(
            frigate_event=event.frigate_event,
            species=label,
            scientific_name=taxonomy.get("scientific_name"),
            common_name=taxonomy.get("common_name"),
            confidence=score,
            camera=event.camera,
            timestamp=event.detection_dt,
            snapshot_url=snapshot_url,
            event_type=event.type,
            channels=channels,
            audio_confirmed=audio_confirmed,
            audio_species=audio_species,
            snapshot_data=snapshot_data
        )

    async def _send_and_mark_notified(
        self,
        event: Any,
        classification: Dict[str, Any],
        snapshot_data: Optional[bytes],
        channels: Optional[list[str]] = None
    ) -> None:
        sent = await self._send_notification(
            event,
            label=classification['label'],
            score=classification['score'],
            audio_confirmed=classification['audio_confirmed'],
            audio_species=classification['audio_species'],
            snapshot_data=snapshot_data,
            channels=channels
        )
        if sent:
            await self._mark_notified(event.frigate_event)

    async def _notify_after_video(
        self,
        event: Any,
        classification: Dict[str, Any],
        audio_confirmed: bool,
        audio_species: Optional[str]
    ):
        timeout = settings.notifications.video_fallback_timeout
        snapshot_confirmed = (
            classification['score'] >= settings.classification.threshold
            or classification['audio_confirmed']
        )
        if timeout <= 0:
            if snapshot_confirmed:
                sent = await self._send_notification(
                    event,
                    label=classification['label'],
                    score=classification['score'],
                    audio_confirmed=audio_confirmed,
                    audio_species=audio_species,
                    snapshot_data=None
                )
                if sent:
                    await self._mark_notified(event.frigate_event)
            else:
                log.info("Notification skipped: snapshot not confirmed",
                         event_id=event.frigate_event,
                         label=classification['label'],
                         score=classification['score'])
            return

        label = classification['label']
        score = classification['score']
        video_confirmed = False
        final_status = None

        det = await self._get_detection(event.frigate_event)
        if det and det.video_classification_status in {"completed", "failed"}:
            final_status = det.video_classification_status
        else:
            waiter_state = await video_classification_waiter.wait_for_final_status(
                event.frigate_event,
                timeout=timeout
            )
            if waiter_state:
                final_status = waiter_state.get("status")
            det = await self._get_detection(event.frigate_event)
            if det and det.video_classification_status in {"completed", "failed"}:
                final_status = det.video_classification_status

        if final_status == "completed" and det and det.video_classification_label and det.video_classification_score is not None:
            label = det.video_classification_label
            score = det.video_classification_score
            video_confirmed = det.video_classification_score >= settings.classification.threshold

        if video_confirmed or snapshot_confirmed:
            sent = await self._send_notification(
                event,
                label=label,
                score=score,
                audio_confirmed=audio_confirmed,
                audio_species=audio_species,
                snapshot_data=None
            )
            if sent:
                await self._mark_notified(event.frigate_event)
        else:
            log.info("Notification skipped: video/snapshot not confirmed",
                     event_id=event.frigate_event,
                     label=label,
                     score=score)

    async def handle_notifications(
        self,
        event: Any,
        classification: Dict[str, Any],
        snapshot_data: Optional[bytes],
        changed: bool,
        was_inserted: bool
    ) -> None:
        event_type = (event.type or "new").lower()
        detection = await self._get_detection(event.frigate_event)
        already_notified = bool(detection and detection.notified_at)

        notify_mode = (settings.notifications.mode or "standard").lower()
        should_notify, _was_updated = self._should_notify(
            event_type=event_type,
            notify_mode=notify_mode,
            changed=changed,
            was_inserted=was_inserted,
            already_notified=already_notified
        )

        email_only_on_end = (
            notify_mode == "custom"
            and settings.notifications.email.enabled
            and settings.notifications.email.only_on_end
            and event_type == "end"
            and detection is not None
            and not already_notified
        )

        if should_notify:
            snapshot_confirmed = (
                classification['score'] >= settings.classification.threshold
                or classification['audio_confirmed']
            )
            delay_until_video = settings.notifications.delay_until_video
            if notify_mode == "final":
                delay_until_video = settings.classification.auto_video_classification

            if delay_until_video and settings.classification.auto_video_classification:
                create_background_task(self._notify_after_video(
                    event,
                    classification,
                    audio_confirmed=classification['audio_confirmed'],
                    audio_species=classification['audio_species']
                ), name=f"notify_after_video:{event.frigate_event}")
            else:
                if snapshot_confirmed:
                    await self._send_and_mark_notified(event, classification, snapshot_data)
                else:
                    log.info("Notification skipped: snapshot not confirmed",
                             event_id=event.frigate_event,
                             label=classification['label'],
                             score=classification['score'])
        elif email_only_on_end:
            snapshot_confirmed = (
                classification['score'] >= settings.classification.threshold
                or classification['audio_confirmed']
            )
            if snapshot_confirmed:
                await self._send_and_mark_notified(event, classification, snapshot_data, channels=["email"])
            else:
                log.info("Email notification skipped: snapshot not confirmed",
                         event_id=event.frigate_event,
                         label=classification['label'],
                         score=classification['score'])
