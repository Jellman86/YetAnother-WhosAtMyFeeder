import structlog
import asyncio
import httpx
import html
from datetime import datetime, timezone
from typing import Optional, Any
import json

from app.config import settings
from app.services.i18n_service import i18n_service

log = structlog.get_logger()

def escape_html(text: str) -> str:
    """Escape text for Telegram HTML parse mode."""
    return html.escape(text, quote=True)

class NotificationService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)
        self.last_notification_time = datetime.min.replace(tzinfo=timezone.utc)

    async def _should_notify(
        self,
        species: str,
        confidence: float,
        audio_confirmed: bool,
        camera: str
    ) -> bool:
        """Determine if a notification should be sent based on filters."""
        filters = settings.notifications.filters

        # 1. Species Whitelist
        if filters.species_whitelist:
            if species not in filters.species_whitelist:
                log.debug("Notification skipped: species not in whitelist", species=species)
                return False

        # 2. Min Confidence
        if confidence < filters.min_confidence:
            log.debug("Notification skipped: low confidence", confidence=confidence, min=filters.min_confidence)
            return False

        # 3. Audio Confirmed Only
        if filters.audio_confirmed_only and not audio_confirmed:
            log.debug("Notification skipped: audio confirmation required")
            return False

        # 4. Per-Camera Filters (Advanced)
        # Assuming camera_filters is dict of {camera_name: {min_confidence: 0.8, etc}}
        if camera in filters.camera_filters:
            cam_filters = filters.camera_filters[camera]
            if "min_confidence" in cam_filters and confidence < cam_filters["min_confidence"]:
                return False
            # Add more per-camera logic here if needed

        # 5. Global Cooldown
        cooldown = settings.notifications.notification_cooldown_minutes
        if cooldown > 0:
            now = datetime.now(timezone.utc)
            elapsed_minutes = (now - self.last_notification_time).total_seconds() / 60
            if elapsed_minutes < cooldown:
                log.info("Notification skipped: cooldown active", elapsed=f"{elapsed_minutes:.1f}m", cooldown=f"{cooldown}m")
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
        snapshot_data: Optional[bytes] = None
    ) -> bool:
        """Send notifications to all enabled platforms."""
        
        # Check filters
        if not await self._should_notify(species, confidence, audio_confirmed, camera):
            return False

        lang = settings.notifications.notification_language
        display_name = common_name or species
        tasks = []
        channel_filter = set(channels) if channels else None
        allow_channel = (lambda name: channel_filter is None or name in channel_filter)

        # Discord
        if settings.notifications.discord.enabled and allow_channel("discord"):
            tasks.append(self._send_discord(
                display_name, confidence, camera, timestamp, snapshot_url, audio_confirmed, lang, snapshot_data
            ))

        # Pushover
        if settings.notifications.pushover.enabled and allow_channel("pushover"):
            tasks.append(self._send_pushover(
                display_name, confidence, camera, timestamp, snapshot_url, snapshot_data, lang
            ))

        # Telegram
        if settings.notifications.telegram.enabled and allow_channel("telegram"):
            tasks.append(self._send_telegram(
                display_name, confidence, camera, timestamp, snapshot_url, snapshot_data, lang
            ))

        # Email
        email_event_type = (event_type or "").lower()
        email_allowed = not settings.notifications.email.only_on_end or email_event_type == "end"
        if settings.notifications.email.enabled and email_allowed and allow_channel("email"):
            tasks.append(self._send_email(
                display_name, scientific_name, confidence, camera, timestamp, snapshot_url, snapshot_data, audio_confirmed, lang
            ))

        if tasks:
            log.info("Sending notifications", species=species, platforms=len(tasks), lang=lang)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Consider it sent if at least one platform succeeded
            success = any(not isinstance(result, Exception) for result in results)
            if success:
                self.last_notification_time = datetime.now(timezone.utc)
            return success

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
        snapshot_data: Optional[bytes]
    ):
        """Send Discord webhook notification."""
        if not settings.notifications.discord.webhook_url:
            return

        title = i18n_service.translate("notification.new_detection", lang=lang, species=species)
        description = i18n_service.translate(
            "notification.detection_body", 
            lang=lang, 
            species=species, 
            camera=camera, 
            confidence=int(confidence * 100)
        )
        # Bold formatting for Discord
        description = f"**{description}**"
        
        if audio_confirmed:
            audio_text = i18n_service.translate("notification.audio_confirmed", lang=lang)
            description += f"\n**{audio_text}**"

        # Ensure timestamp is timezone-aware for Discord
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        embed = {
            "title": title,
            "description": description,
            "color": 3066993,  # Teal-ish
            "timestamp": timestamp.isoformat(),
            "footer": {"text": "YA-WAMF"},
        }
        
        if settings.notifications.discord.include_snapshot:
            if snapshot_data:
                embed["image"] = {"url": "attachment://snapshot.jpg"}
            else:
                embed["image"] = {"url": snapshot_url}

        payload = {
            "username": settings.notifications.discord.username,
            "embeds": [embed]
        }

        try:
            if snapshot_data and settings.notifications.discord.include_snapshot:
                 resp = await self.client.post(
                     settings.notifications.discord.webhook_url,
                     data={"payload_json": json.dumps(payload)},
                     files={"file": ("snapshot.jpg", snapshot_data, "image/jpeg")}
                 )
            else:
                resp = await self.client.post(settings.notifications.discord.webhook_url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            # Log the response body for debugging
            log.error("Discord notification failed",
                     error=str(e),
                     status_code=e.response.status_code,
                     response_body=e.response.text,
                     payload=payload)
            raise
        except Exception as e:
            log.error("Discord notification failed", error=str(e), payload=payload)
            raise

    async def _send_pushover(
        self,
        species: str,
        confidence: float,
        camera: str,
        timestamp: datetime,
        snapshot_url: str,
        snapshot_data: Optional[bytes],
        lang: str
    ):
        """Send Pushover notification."""
        cfg = settings.notifications.pushover
        if not cfg.user_key or not cfg.api_token:
            return

        title = i18n_service.translate("notification.new_detection", lang=lang, species=species)
        message = i18n_service.translate(
            "notification.detection_body", 
            lang=lang, 
            species=species, 
            camera=camera, 
            confidence=int(confidence * 100)
        )
        
        data = {
            "token": cfg.api_token,
            "user": cfg.user_key,
            "title": title,
            "message": message,
            "priority": str(cfg.priority),
            "timestamp": int(timestamp.timestamp()),
            "url": snapshot_url,
            "url_title": "View Snapshot"
        }

        files = {}
        if cfg.include_snapshot and snapshot_data:
            files["attachment"] = ("snapshot.jpg", snapshot_data, "image/jpeg")

        try:
            if files:
                resp = await self.client.post("https://api.pushover.net/1/messages.json", data=data, files=files)
            else:
                resp = await self.client.post("https://api.pushover.net/1/messages.json", data=data)
            resp.raise_for_status()
        except Exception as e:
            log.error("Pushover notification failed", error=str(e))
            raise

    async def _send_telegram(
        self,
        species: str,
        confidence: float,
        camera: str,
        timestamp: datetime,
        snapshot_url: str,
        snapshot_data: Optional[bytes],
        lang: str
    ):
        """Send Telegram notification."""
        cfg = settings.notifications.telegram
        if not cfg.bot_token or not cfg.chat_id:
            return

        def truncate(text: str, limit: int) -> str:
            if text is None:
                return ""
            if len(text) <= limit:
                return text
            return text[: max(0, limit - 1)].rstrip() + "…"

        body = i18n_service.translate(
            "notification.detection_body", 
            lang=lang, 
            species=species, 
            camera=camera, 
            confidence=int(confidence * 100)
        )
        base_url = f"https://api.telegram.org/bot{cfg.bot_token}"

        try:
            if cfg.include_snapshot and snapshot_data:
                # Send Photo
                url = f"{base_url}/sendPhoto"
                # Caption hard limit is 1024 chars. Truncate raw text before escaping to avoid breaking entities.
                clipped_body = truncate(body, 900)
                safe_body = escape_html(clipped_body)
                caption = f"🐦 <b>{safe_body}</b>"
                data = {
                    "chat_id": cfg.chat_id,
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                files = {"photo": ("snapshot.jpg", snapshot_data, "image/jpeg")}
                resp = await self.client.post(url, data=data, files=files)
            else:
                # Send Message
                url = f"{base_url}/sendMessage"
                # If no snapshot, maybe include link in text
                safe_url = escape_html(snapshot_url)
                clipped_body = truncate(body, 3600)
                safe_body = escape_html(clipped_body)
                caption = f"🐦 <b>{safe_body}</b>\n<a href=\"{safe_url}\">View Snapshot</a>"
                data = {
                    "chat_id": cfg.chat_id,
                    "text": caption,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                }
                resp = await self.client.post(url, json=data)
            
            resp.raise_for_status()
        except Exception as e:
            log.error("Telegram notification failed", error=str(e))
            raise

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
        lang: str
    ):
        """Send email notification"""
        try:
            from app.services.smtp_service import smtp_service
            from jinja2 import Template
            import os
            import aiofiles

            cfg = settings.notifications.email

            if not cfg.to_email:
                log.warning("Email notifications enabled but no recipient configured")
                return

            # Load email templates asynchronously
            template_dir = os.path.join(os.path.dirname(__file__), "..", "templates", "email")

            async with aiofiles.open(os.path.join(template_dir, "bird_detection.html"), 'r') as f:
                html_template = Template(await f.read())

            async with aiofiles.open(os.path.join(template_dir, "bird_detection.txt"), 'r') as f:
                text_template = Template(await f.read())

            # Prepare template data
            from app.utils.font_theme import get_email_font_family
            font_family = get_email_font_family(
                getattr(settings, "appearance", None).font_theme if getattr(settings, "appearance", None) else "classic",
                settings.accessibility.dyslexia_font
            )
            template_data = {
                "species": species,
                "scientific_name": scientific_name,
                "confidence": int(confidence * 100),
                "camera": camera,
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "audio_confirmed": audio_confirmed,
                "has_image": snapshot_data is not None and cfg.include_snapshot,
                "dashboard_url": cfg.dashboard_url,
                "font_family": font_family,
                "weather": None  # TODO: Add weather data if available
            }

            # Render templates
            html_body = html_template.render(**template_data)
            plain_body = text_template.render(**template_data)

            # Translate subject
            from app.services.i18n_service import i18n_service
            subject = i18n_service.translate("notification.new_detection", lang, species=species)

            # Fetch snapshot if needed
            image_data = None
            if cfg.include_snapshot and snapshot_data:
                image_data = snapshot_data
            elif cfg.include_snapshot and snapshot_url:
                try:
                    async with self.client.get(snapshot_url) as resp:
                        if resp.status_code == 200:
                            image_data = resp.content
                except:
                    log.warning("Failed to fetch snapshot for email")

            # Send email
            if cfg.use_oauth and cfg.oauth_provider:
                success = await smtp_service.send_email_oauth(
                    provider=cfg.oauth_provider,
                    to_email=cfg.to_email,
                    subject=subject,
                    html_body=html_body,
                    plain_body=plain_body,
                    image_data=image_data
                )
            else:
                # Traditional SMTP
                if not cfg.smtp_host or not cfg.from_email:
                    log.error("Email SMTP configuration incomplete")
                    return

                success = await smtp_service.send_email_password(
                    smtp_host=cfg.smtp_host,
                    smtp_port=cfg.smtp_port,
                    username=cfg.smtp_username,
                    password=cfg.smtp_password,
                    from_email=cfg.from_email,
                    to_email=cfg.to_email,
                    subject=subject,
                    html_body=html_body,
                    plain_body=plain_body,
                    use_tls=cfg.smtp_use_tls,
                    image_data=image_data
                )

            if success:
                log.info("Email notification sent", to=cfg.to_email, species=species)
            else:
                log.error("Email notification failed")

        except Exception as e:
            log.error("Email notification failed", error=str(e))
            raise

notification_service = NotificationService()
