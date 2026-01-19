"""Centralized Frigate HTTP client service.

Provides a single source of truth for all Frigate API interactions,
with connection pooling, authentication, and consistent error handling.
"""

import httpx
import structlog
from typing import Optional
from app.config import settings

log = structlog.get_logger()


class FrigateClient:
    """HTTP client for Frigate API interactions.

    Features:
    - Connection pooling for efficiency
    - Centralized auth header management
    - Consistent timeout and error handling
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    def _get_headers(self) -> dict:
        """Build headers for Frigate requests, including auth token if configured."""
        headers = {}
        if settings.frigate.frigate_auth_token:
            headers['Authorization'] = f'Bearer {settings.frigate.frigate_auth_token}'
        return headers

    @property
    def base_url(self) -> str:
        """Get the configured Frigate base URL."""
        return settings.frigate.frigate_url

    async def get(
        self,
        path: str,
        params: Optional[dict] = None,
        timeout: float = 30.0
    ) -> httpx.Response:
        """Make a GET request to Frigate API.

        Args:
            path: API path (e.g., '/api/events' or 'api/version')
            params: Optional query parameters
            timeout: Request timeout in seconds

        Returns:
            httpx.Response object
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        client = self._get_client()
        return await client.get(
            url,
            params=params,
            headers=self._get_headers(),
            timeout=timeout
        )

    async def post(
        self,
        path: str,
        json: Optional[dict] = None,
        timeout: float = 30.0
    ) -> httpx.Response:
        """Make a POST request to Frigate API.

        Args:
            path: API path
            json: Optional JSON body
            timeout: Request timeout in seconds

        Returns:
            httpx.Response object
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        client = self._get_client()
        return await client.post(
            url,
            json=json,
            headers=self._get_headers(),
            timeout=timeout
        )

    async def get_version(self) -> Optional[str]:
        """Get Frigate version string."""
        try:
            resp = await self.get("api/version", timeout=10.0)
            if resp.status_code == 200:
                return resp.text.strip().strip('"')
        except Exception as e:
            log.error("Failed to get Frigate version", error=str(e))
        return None

    async def get_snapshot(
        self,
        event_id: str,
        crop: bool = True,
        quality: int = 95
    ) -> Optional[bytes]:
        """Fetch snapshot image for an event.

        Args:
            event_id: Frigate event ID
            crop: Whether to crop to detection region
            quality: JPEG quality (1-100)

        Returns:
            Image bytes or None if failed
        """
        params = {"crop": 1 if crop else 0, "quality": quality}
        try:
            resp = await self.get(f"api/events/{event_id}/snapshot.jpg", params=params)
            if resp.status_code == 200:
                return resp.content
            log.warning("Failed to fetch snapshot", event_id=event_id, status=resp.status_code)
        except Exception as e:
            log.error("Error fetching snapshot", event_id=event_id, error=str(e))
        return None

    async def get_clip_with_error(self, event_id: str, timeout: float = 20.0) -> tuple[Optional[bytes], Optional[str]]:
        """Fetch video clip for an event with explicit error reason."""
        try:
            resp = await self.get(f"api/events/{event_id}/clip.mp4", timeout=timeout)
            if resp.status_code == 200:
                return resp.content, None
            if resp.status_code == 404:
                log.warning("Clip not found", event_id=event_id)
                return None, "clip_not_found"
            log.warning("Failed to fetch clip", event_id=event_id, status=resp.status_code)
            return None, f"clip_http_{resp.status_code}"
        except httpx.TimeoutException:
            log.warning("Clip fetch timed out", event_id=event_id)
            return None, "clip_timeout"
        except httpx.RequestError as e:
            log.error("Error fetching clip", event_id=event_id, error=str(e))
            return None, "clip_request_error"
        except Exception as e:
            log.error("Unexpected error fetching clip", event_id=event_id, error=str(e))
            return None, "clip_unknown_error"

    async def get_clip(self, event_id: str) -> Optional[bytes]:
        """Fetch video clip for an event."""
        clip, _ = await self.get_clip_with_error(event_id)
        return clip

    async def get_thumbnail(self, event_id: str) -> Optional[bytes]:
        """Fetch thumbnail image for an event."""
        try:
            resp = await self.get(f"api/events/{event_id}/thumbnail.jpg")
            if resp.status_code == 200:
                return resp.content
        except Exception as e:
            log.error("Error fetching thumbnail", event_id=event_id, error=str(e))
        return None

    async def get_event(self, event_id: str) -> Optional[dict]:
        """Fetch event details."""
        try:
            resp = await self.get(f"api/events/{event_id}")
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            log.error("Error fetching event", event_id=event_id, error=str(e))
        return None

    async def set_sublabel(self, event_id: str, sublabel: str) -> bool:
        """Set sublabel on a Frigate event.

        Args:
            event_id: Frigate event ID
            sublabel: Label to set (max 20 chars)

        Returns:
            True if successful
        """
        try:
            resp = await self.post(
                f"api/events/{event_id}/sub_label",
                json={"subLabel": sublabel[:20]},
                timeout=10.0
            )
            return resp.status_code == 200
        except Exception as e:
            log.error("Failed to set sublabel", event_id=event_id, error=str(e))
            return False

    async def get_config(self) -> Optional[dict]:
        """Fetch Frigate configuration."""
        try:
            resp = await self.get("api/config")
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            log.error("Error fetching Frigate config", error=str(e))
        return None

    async def list_events(
        self,
        after: Optional[float] = None,
        before: Optional[float] = None,
        label: Optional[str] = None,
        camera: Optional[str] = None,
        has_snapshot: bool = True,
        limit: int = 100
    ) -> list[dict]:
        """List events from Frigate.

        Args:
            after: Start timestamp (Unix)
            before: End timestamp (Unix)
            label: Filter by label (e.g., 'bird')
            camera: Filter by camera name
            has_snapshot: Only events with snapshots
            limit: Max events to return

        Returns:
            List of event dictionaries
        """
        params = {"limit": limit}
        if after is not None:
            params["after"] = after
        if before is not None:
            params["before"] = before
        if label:
            params["label"] = label
        if camera:
            params["camera"] = camera
        if has_snapshot:
            params["has_snapshot"] = 1

        try:
            resp = await self.get("api/events", params=params)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            log.error("Error listing events", error=str(e))
        return []

    async def close(self):
        """Close the HTTP client and release resources."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Global singleton instance
frigate_client = FrigateClient()
