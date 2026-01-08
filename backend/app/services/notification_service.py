import structlog
import asyncio
import httpx
from datetime import datetime
from typing import Optional, Any

from app.config import settings

log = structlog.get_logger()

class NotificationService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)

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
        audio_confirmed: bool = False,
        audio_species: Optional[str] = None,
        snapshot_data: Optional[bytes] = None
    ):
        """Send notifications to all enabled platforms."""
        
        # Check filters
        if not await self._should_notify(species, confidence, audio_confirmed, camera):
            return

        tasks = []

        # Discord
        if settings.notifications.discord.enabled:
            tasks.append(self._send_discord(
                species, common_name, confidence, camera, timestamp, snapshot_url, audio_confirmed
            ))

        # Pushover
        if settings.notifications.pushover.enabled:
            tasks.append(self._send_pushover(
                species, common_name, confidence, camera, timestamp, snapshot_url, snapshot_data
            ))

        # Telegram
        if settings.notifications.telegram.enabled:
            tasks.append(self._send_telegram(
                species, common_name, confidence, camera, timestamp, snapshot_url, snapshot_data
            ))

        if tasks:
            log.info("Sending notifications", species=species, platforms=len(tasks))
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_discord(
        self,
        species: str,
        common_name: Optional[str],
        confidence: float,
        camera: str,
        timestamp: datetime,
        snapshot_url: str,
        audio_confirmed: bool
    ):
        """Send Discord webhook notification."""
        if not settings.notifications.discord.webhook_url:
            return

        title = f"🐦 {common_name or species} Detected!"
        description = f"**Camera:** {camera}\n**Confidence:** {confidence:.0%}"
        if audio_confirmed:
            description += "\n🎤 **Audio Confirmed**"
        
        embed = {
            "title": title,
            "description": description,
            "color": 3066993,  # Teal-ish
            "timestamp": timestamp.isoformat(),
            "footer": {"text": "YA-WAMF"},
        }
        
        if settings.notifications.discord.include_snapshot:
            embed["image"] = {"url": snapshot_url}

        payload = {
            "username": settings.notifications.discord.username,
            "embeds": [embed]
        }

        try:
            resp = await self.client.post(settings.notifications.discord.webhook_url, json=payload)
            resp.raise_for_status()
        except Exception as e:
            log.error("Discord notification failed", error=str(e))

    async def _send_pushover(
        self,
        species: str,
        common_name: Optional[str],
        confidence: float,
        camera: str,
        timestamp: datetime,
        snapshot_url: str,
        snapshot_data: Optional[bytes]
    ):
        """Send Pushover notification."""
        cfg = settings.notifications.pushover
        if not cfg.user_key or not cfg.api_token:
            return

        title = f"{common_name or species} at {camera}"
        message = f"Confidence: {confidence:.0%}\nTime: {timestamp.strftime('%H:%M:%S')}"
        
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

    async def _send_telegram(
        self,
        species: str,
        common_name: Optional[str],
        confidence: float,
        camera: str,
        timestamp: datetime,
        snapshot_url: str,
        snapshot_data: Optional[bytes]
    ):
        """Send Telegram notification."""
        cfg = settings.notifications.telegram
        if not cfg.bot_token or not cfg.chat_id:
            return

        caption = f"🐦 *{common_name or species}*\n📹 {camera}\n🎯 {confidence:.0%}"
        base_url = f"https://api.telegram.org/bot{cfg.bot_token}"

        try:
            if cfg.include_snapshot and snapshot_data:
                # Send Photo
                url = f"{base_url}/sendPhoto"
                data = {
                    "chat_id": cfg.chat_id,
                    "caption": caption,
                    "parse_mode": "Markdown"
                }
                files = {"photo": ("snapshot.jpg", snapshot_data, "image/jpeg")}
                resp = await self.client.post(url, data=data, files=files)
            else:
                # Send Message
                url = f"{base_url}/sendMessage"
                # If no snapshot, maybe include link in text
                caption += f"\n[View Snapshot]({snapshot_url})"
                data = {
                    "chat_id": cfg.chat_id,
                    "text": caption,
                    "parse_mode": "Markdown"
                }
                resp = await self.client.post(url, json=data)
            
            resp.raise_for_status()
        except Exception as e:
            log.error("Telegram notification failed", error=str(e))

notification_service = NotificationService()
