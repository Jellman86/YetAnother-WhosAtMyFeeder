import structlog
import asyncio
import httpx
from datetime import datetime, timezone
from typing import Optional
from collections.abc import Coroutine

from app.config import settings
from app.services.i18n_service import i18n_service
from app.services.notification_links import notification_link
from app.services.notifications.message import Attachment, NotificationMessage, SubjectLink
from app.services.notifications.transports.email import EmailCredentials, EmailOptions, EmailTransport
from app.services.notifications.transports.discord import DiscordCredentials, DiscordOptions, DiscordTransport
from app.services.notifications.transports.pushover import PushoverCredentials, PushoverOptions, PushoverTransport
from app.services.notifications.transports.telegram import TelegramCredentials, TelegramOptions, TelegramTransport
from app.utils.blocked_species import matches_species_filter


log = structlog.get_logger()


def _species_entry_list(value: object) -> list:
    return list(value) if isinstance(value, list) else []


def _species_filter_mode(filters: object) -> str | None:
    raw_mode = getattr(filters, "species_mode", None)
    mode = raw_mode if raw_mode in {"none", "blacklist", "whitelist"} else None
    return mode


# Bird alerts on Telegram are the detection sentence in bold after a bird.
BIRD_TELEGRAM = TelegramOptions(icon="🐦")
# Bird Discord embeds are teal, with every line in bold.
BIRD_DISCORD_COLOR = 3066993


class NotificationService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)
        self.last_notification_time = datetime.min.replace(tzinfo=timezone.utc)
        self._cooldown_dispatch_active = False

    async def _should_notify(
        self,
        species: str,
        confidence: float,
        audio_confirmed: bool,
        camera: str,
        scientific_name: Optional[str] = None,
        common_name: Optional[str] = None,
        taxa_id: Optional[int] = None,
    ) -> bool:
        """Determine if a notification should be sent based on filters."""
        filters = settings.notifications.filters
        species_mode = _species_filter_mode(filters)
        legacy_mode = species_mode is None

        # 1. Species Blacklist
        if (legacy_mode or species_mode == "blacklist") and matches_species_filter(
            labels=[],
            species_entries=_species_entry_list(getattr(filters, "species_blacklist_structured", [])),
            label=species,
            scientific_name=scientific_name,
            common_name=common_name,
            taxa_id=taxa_id,
        ):
            log.debug("Notification skipped: species in blacklist", species=species)
            return False

        # 2. Species Whitelist
        whitelist_structured = _species_entry_list(getattr(filters, "species_whitelist_structured", []))
        whitelist_active = legacy_mode or species_mode == "whitelist"
        legacy_whitelist = filters.species_whitelist if whitelist_active else []
        active_whitelist_structured = whitelist_structured if whitelist_active else []
        if legacy_whitelist or active_whitelist_structured:
            if not matches_species_filter(
                labels=legacy_whitelist,
                species_entries=active_whitelist_structured,
                label=species,
                scientific_name=scientific_name,
                common_name=common_name,
                taxa_id=taxa_id,
            ):
                log.debug("Notification skipped: species not in whitelist", species=species)
                return False

        # 3. Min Confidence
        if confidence < filters.min_confidence:
            log.debug("Notification skipped: low confidence", confidence=confidence, min=filters.min_confidence)
            return False

        # 4. Audio Confirmed Only
        if filters.audio_confirmed_only and not audio_confirmed:
            log.debug("Notification skipped: audio confirmation required")
            return False

        # 5. Per-Camera Filters (Advanced)
        # Assuming camera_filters is dict of {camera_name: {min_confidence: 0.8, etc}}
        if camera in filters.camera_filters:
            cam_filters = filters.camera_filters[camera]
            if "min_confidence" in cam_filters and confidence < cam_filters["min_confidence"]:
                return False
            # Add more per-camera logic here if needed

        # 6. Global Cooldown
        cooldown = settings.notifications.notification_cooldown_minutes
        if cooldown > 0:
            now = datetime.now(timezone.utc)
            elapsed_minutes = (now - self.last_notification_time).total_seconds() / 60
            if elapsed_minutes < cooldown:
                log.info(
                    "Notification skipped: cooldown active", elapsed=f"{elapsed_minutes:.1f}m", cooldown=f"{cooldown}m"
                )
                return False

        return True

    async def notify_detection(
        self,
        frigate_event: str,
        species: str,
        scientific_name: Optional[str],
        common_name: Optional[str],
        confidence: float,
        camera: str,
        timestamp: datetime,
        snapshot_url: str,
        event_type: Optional[str] = None,
        channels: Optional[list[str]] = None,
        audio_confirmed: bool = False,
        audio_species: Optional[str] = None,
        snapshot_data: Optional[bytes] = None,
        weather: Optional[str] = None,
        taxa_id: Optional[int] = None,
    ) -> bool:
        """Send notifications to all enabled platforms."""

        # Check filters
        if not await self._should_notify(
            species,
            confidence,
            audio_confirmed,
            camera,
            scientific_name=scientific_name,
            common_name=common_name,
            taxa_id=taxa_id,
        ):
            return False

        lang = settings.notifications.notification_language
        display_name = common_name or species
        detection_url = notification_link(settings.notifications, settings.frigate.frigate_external_url, frigate_event)
        tasks: list[tuple[str, Coroutine[None, None, bool]]] = []
        channel_filter = set(channels) if channels else None

        def allow_channel(name: str) -> bool:
            return channel_filter is None or name in channel_filter

        # Discord
        if settings.notifications.discord.enabled and allow_channel("discord"):
            tasks.append(
                (
                    "discord",
                    self._send_discord(
                        display_name,
                        confidence,
                        camera,
                        timestamp,
                        snapshot_url,
                        audio_confirmed,
                        lang,
                        snapshot_data,
                        detection_url=detection_url,
                    ),
                )
            )

        # Pushover
        if settings.notifications.pushover.enabled and allow_channel("pushover"):
            tasks.append(
                (
                    "pushover",
                    self._send_pushover(
                        display_name,
                        confidence,
                        camera,
                        timestamp,
                        snapshot_url,
                        snapshot_data,
                        lang,
                        detection_url=detection_url,
                    ),
                )
            )

        # Telegram
        if settings.notifications.telegram.enabled and allow_channel("telegram"):
            tasks.append(
                (
                    "telegram",
                    self._send_telegram(
                        display_name,
                        confidence,
                        camera,
                        timestamp,
                        snapshot_url,
                        snapshot_data,
                        lang,
                        detection_url=detection_url,
                    ),
                )
            )

        # Email
        email_event_type = (event_type or "").lower()
        email_allowed = not settings.notifications.email.only_on_end or email_event_type == "end"
        if settings.notifications.email.enabled and email_allowed and allow_channel("email"):
            tasks.append(
                (
                    "email",
                    self._send_email(
                        display_name,
                        scientific_name,
                        confidence,
                        camera,
                        timestamp,
                        snapshot_url,
                        snapshot_data,
                        audio_confirmed,
                        lang,
                        weather,
                        detection_url=detection_url,
                    ),
                )
            )
        elif settings.notifications.email.enabled and allow_channel("email"):
            log.debug(
                "Email notification skipped: event type not allowed",
                event_type=email_event_type,
                only_on_end=settings.notifications.email.only_on_end,
                frigate_event=frigate_event,
            )

        if tasks:
            cooldown = settings.notifications.notification_cooldown_minutes
            reserved = cooldown > 0
            # This check and reservation have no await: all workers share this service
            # on the event loop, but channel I/O must never hold a global lock.
            if reserved:
                elapsed = (datetime.now(timezone.utc) - self.last_notification_time).total_seconds() / 60
                if self._cooldown_dispatch_active or elapsed < cooldown:
                    for _, task in tasks:
                        task.close()
                    return False
                self._cooldown_dispatch_active = True

            channel_names = [name for name, _ in tasks]
            log.info("Sending notifications", species=species, channels=channel_names, lang=lang)
            delivery_tasks = [asyncio.create_task(task) for _, task in tasks]
            try:
                results = await asyncio.gather(*delivery_tasks, return_exceptions=True)
            finally:
                # A completed channel still counts when another channel is cancelled.
                success = any(
                    task.done()
                    and not task.cancelled()
                    and task.exception() is None
                    and (task.result() is True or task.result() is None)
                    for task in delivery_tasks
                )
                if success:
                    self.last_notification_time = datetime.now(timezone.utc)
                if reserved:
                    self._cooldown_dispatch_active = False
            channel_results = {}
            for (name, _), result in zip(tasks, results):
                if isinstance(result, BaseException):
                    channel_results[name] = "error"
                    continue
                # Backward-compat: treat legacy None returns from mocks as a sent signal.
                sent = result is True or result is None
                channel_results[name] = "sent" if sent else "skipped_or_failed"
                success = success or sent

            log.info(
                "Notification dispatch complete", species=species, success=success, channel_results=channel_results
            )
            return success

        log.debug("Notification skipped: no eligible channels", species=species, channels=channels)
        return False

    async def _send_discord(
        self,
        species: str,
        confidence: float,
        camera: str,
        timestamp: datetime,
        snapshot_url: str,
        audio_confirmed: bool,
        lang: str,
        snapshot_data: Optional[bytes],
        detection_url: Optional[str] = None,
    ) -> bool:
        """Send Discord webhook notification."""
        cfg = settings.notifications.discord
        if not cfg.webhook_url:
            return False

        title = i18n_service.translate("notification.new_detection", lang=lang, species=species)
        lines = [
            i18n_service.translate(
                "notification.detection_body",
                lang=lang,
                species=species,
                camera=camera,
                confidence=int(confidence * 100),
            )
        ]
        if audio_confirmed:
            lines.append(i18n_service.translate("notification.audio_confirmed", lang=lang))
        photo = snapshot_data if cfg.include_snapshot else None
        message = NotificationMessage(
            title=title,
            body="\n".join(lines),
            link=SubjectLink(detection_url, title) if detection_url else None,
            attachment=Attachment("snapshot.jpg", photo) if photo else None,
            image_url=snapshot_url if cfg.include_snapshot and not photo else None,
            occurred_at=timestamp,
        )
        options = DiscordOptions(username=cfg.username, footer="YA-WAMF", color=BIRD_DISCORD_COLOR, bold_body=True)
        result = await DiscordTransport(self.client).send(message, DiscordCredentials(cfg.webhook_url), options)
        if not result.sent:
            log.error("Discord notification failed", error_type=result.error_type, status_code=result.status_code)
        return result.sent

    async def _send_pushover(
        self,
        species: str,
        confidence: float,
        camera: str,
        timestamp: datetime,
        snapshot_url: str,
        snapshot_data: Optional[bytes],
        lang: str,
        detection_url: Optional[str] = None,
    ) -> bool:
        """Send Pushover notification."""
        cfg = settings.notifications.pushover
        if not cfg.user_key or not cfg.api_token:
            return False

        message = NotificationMessage(
            title=i18n_service.translate("notification.new_detection", lang=lang, species=species),
            body=i18n_service.translate(
                "notification.detection_body",
                lang=lang,
                species=species,
                camera=camera,
                confidence=int(confidence * 100),
            ),
            link=(
                SubjectLink(detection_url, i18n_service.translate("notification.view_detection", lang=lang))
                if detection_url
                else None
            ),
            fallback_link=SubjectLink(snapshot_url, "View Snapshot") if snapshot_url else None,
            attachment=Attachment("snapshot.jpg", snapshot_data) if cfg.include_snapshot and snapshot_data else None,
            occurred_at=timestamp,
        )
        result = await PushoverTransport(self.client).send(
            message,
            PushoverCredentials(cfg.api_token, cfg.user_key),
            PushoverOptions(priority=cfg.priority, device=cfg.device),
        )
        if not result.sent:
            log.error("Pushover notification failed", error_type=result.error_type, status_code=result.status_code)
        return result.sent

    async def _send_telegram(
        self,
        species: str,
        confidence: float,
        camera: str,
        timestamp: datetime,
        snapshot_url: str,
        snapshot_data: Optional[bytes],
        lang: str,
        detection_url: Optional[str] = None,
    ) -> bool:
        """Send Telegram notification."""
        cfg = settings.notifications.telegram
        if not cfg.bot_token or not cfg.chat_id:
            return False

        sentence = i18n_service.translate(
            "notification.detection_body", lang=lang, species=species, camera=camera, confidence=int(confidence * 100)
        )
        # A URL button under the message is Telegram's own deep link: one tap on any client,
        # with the caption left to the detection itself.
        link = (
            SubjectLink(detection_url, i18n_service.translate("notification.view_detection", lang=lang))
            if detection_url
            else None
        )
        message = NotificationMessage(
            title=sentence,
            link=link,
            fallback_link=SubjectLink(snapshot_url, "View Snapshot") if snapshot_url else None,
            attachment=Attachment("snapshot.jpg", snapshot_data) if cfg.include_snapshot and snapshot_data else None,
        )
        result = await TelegramTransport(self.client).send(
            message, TelegramCredentials(cfg.bot_token, cfg.chat_id), BIRD_TELEGRAM
        )
        if not result.sent:
            log.error("Telegram notification failed", error_type=result.error_type, status_code=result.status_code)
        return result.sent

    async def _send_email(
        self,
        species: str,
        scientific_name: Optional[str],
        confidence: float,
        camera: str,
        timestamp: datetime,
        snapshot_url: str,
        snapshot_data: Optional[bytes],
        audio_confirmed: bool,
        lang: str,
        weather: Optional[str] = None,
        detection_url: Optional[str] = None,
    ) -> bool:
        """Send email notification"""
        try:
            from app.services.smtp_service import smtp_service
            from jinja2 import Template
            import os
            import aiofiles

            cfg = settings.notifications.email

            if not cfg.to_email:
                log.warning("Email notifications enabled but no recipient configured")
                return False

            # Load email templates asynchronously
            template_dir = os.path.join(os.path.dirname(__file__), "..", "templates", "email")

            async with aiofiles.open(os.path.join(template_dir, "bird_detection.html"), "r") as f:
                html_template = Template(await f.read())

            async with aiofiles.open(os.path.join(template_dir, "bird_detection.txt"), "r") as f:
                text_template = Template(await f.read())

            # Prepare template data
            from app.utils.font_theme import get_email_font_family

            font_family = get_email_font_family(
                getattr(settings, "appearance", None).font_theme
                if getattr(settings, "appearance", None)
                else "classic",
                settings.accessibility.dyslexia_font,
            )
            template_data = {
                "species": species,
                "scientific_name": scientific_name,
                "confidence": int(confidence * 100),
                "camera": camera,
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "audio_confirmed": audio_confirmed,
                "has_image": snapshot_data is not None and cfg.include_snapshot,
                # The link the owner chose, or none: never a dashboard link the other channels lack.
                "dashboard_url": detection_url,
                "font_family": font_family,
                "weather": weather,
            }

            # Render templates
            html_body = html_template.render(**template_data)
            plain_body = text_template.render(**template_data)

            # Translate subject
            subject = i18n_service.translate("notification.new_detection", lang, species=species)

            # Fetch snapshot if needed
            image_data = None
            if cfg.include_snapshot and snapshot_data:
                image_data = snapshot_data
            elif cfg.include_snapshot and snapshot_url:
                try:
                    resp = await self.client.get(snapshot_url, timeout=10.0)
                    if resp.status_code == 200:
                        image_data = resp.content
                    else:
                        log.warning("Failed to fetch snapshot for email", status=resp.status_code)
                except Exception as fetch_error:
                    log.warning("Failed to fetch snapshot for email", error=str(fetch_error))

            if cfg.use_oauth and cfg.oauth_provider:
                # The OAuth mailbox sends as the address its token belongs to.
                credentials = EmailCredentials(to_email=cfg.to_email, oauth_provider=cfg.oauth_provider)
            else:
                if not cfg.smtp_host or not cfg.from_email:
                    log.error("Email SMTP configuration incomplete")
                    return False
                credentials = EmailCredentials(
                    to_email=cfg.to_email,
                    from_email=cfg.from_email,
                    smtp_host=cfg.smtp_host,
                    smtp_port=cfg.smtp_port,
                    smtp_username=cfg.smtp_username,
                    smtp_password=cfg.smtp_password,
                    use_tls=cfg.smtp_use_tls,
                )
            message = NotificationMessage(
                title=subject, attachment=Attachment("snapshot.jpg", image_data) if image_data else None
            )
            result = await EmailTransport(smtp_service).send(
                message, credentials, EmailOptions(html_body=html_body, plain_body=plain_body)
            )
            success = result.sent

            if success:
                log.info("Email notification sent", to=cfg.to_email, species=species)
                return True
            else:
                log.error("Email notification failed", error_type=result.error_type)
                return False

        except Exception as e:
            log.error("Email notification failed", error=str(e))
            return False


notification_service = NotificationService()
