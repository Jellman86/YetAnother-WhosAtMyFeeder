"""Centralized Frigate HTTP client service.

Provides a single source of truth for all Frigate API interactions,
with connection pooling, authentication, and consistent error handling.
"""

import math

import httpx
import structlog
from typing import Optional
from app.config import settings

log = structlog.get_logger()


class FrigateEventsFetchError(RuntimeError):
    """Frigate did not return a confirmed, usable event-history response."""


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
            headers["Authorization"] = f"Bearer {settings.frigate.frigate_auth_token}"
        return headers

    @property
    def base_url(self) -> str:
        """Get the configured Frigate base URL."""
        return settings.frigate.frigate_url

    async def get(self, path: str, params: Optional[dict] = None, timeout: float = 30.0) -> httpx.Response:
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
        return await client.get(url, params=params, headers=self._get_headers(), timeout=timeout)

    async def post(self, path: str, json: Optional[dict] = None, timeout: float = 30.0) -> httpx.Response:
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
        return await client.post(url, json=json, headers=self._get_headers(), timeout=timeout)

    async def get_version(self) -> Optional[str]:
        """Get Frigate version string."""
        try:
            resp = await self.get("api/version", timeout=10.0)
            if resp.status_code == 200:
                return resp.text.strip().strip('"')
        except Exception as e:
            log.error("Failed to get Frigate version", error=str(e))
        return None

    async def get_snapshot(self, event_id: str, crop: bool = True, quality: int = 95) -> Optional[bytes]:
        """Fetch snapshot image for an event.

        Args:
            event_id: Frigate event ID
            crop: Whether to crop to detection region
            quality: JPEG quality (1-100)

        Returns:
            Image bytes or None if failed
        """
        snapshot, _error = await self.get_snapshot_with_error(event_id, crop=crop, quality=quality)
        return snapshot

    async def get_snapshot_with_error(
        self,
        event_id: str,
        crop: bool = True,
        quality: int = 95,
        timeout: float = 30.0,
    ) -> tuple[Optional[bytes], Optional[str]]:
        """Fetch snapshot image for an event with explicit error reason."""
        params = {"crop": 1 if crop else 0, "quality": quality}
        try:
            resp = await self.get(f"api/events/{event_id}/snapshot.jpg", params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp.content, None
            if resp.status_code == 404:
                log.warning("Failed to fetch snapshot", event_id=event_id, status=resp.status_code)
                return None, "snapshot_not_found"
            log.warning("Failed to fetch snapshot", event_id=event_id, status=resp.status_code)
            return None, f"snapshot_http_{resp.status_code}"
        except httpx.TimeoutException:
            log.warning("Snapshot fetch timed out", event_id=event_id)
            return None, "snapshot_timeout"
        except httpx.RequestError as e:
            log.error("Error fetching snapshot", event_id=event_id, error=str(e))
            return None, "snapshot_request_error"
        except Exception as e:
            log.error("Error fetching snapshot", event_id=event_id, error=str(e))
            return None, "snapshot_unknown_error"

    async def get_clean_snapshot_with_error(
        self,
        event_id: str,
        timeout: float = 30.0,
    ) -> tuple[Optional[bytes], Optional[str]]:
        """Fetch Frigate's unannotated, uncropped, full-resolution best frame."""
        try:
            resp = await self.get(f"api/events/{event_id}/snapshot-clean.webp", timeout=timeout)
            if resp.status_code == 200:
                return resp.content, None
            if resp.status_code == 404:
                log.debug("Clean snapshot not found", event_id=event_id)
                return None, "clean_snapshot_not_found"
            log.warning("Failed to fetch clean snapshot", event_id=event_id, status=resp.status_code)
            return None, f"clean_snapshot_http_{resp.status_code}"
        except httpx.TimeoutException:
            log.warning("Clean snapshot fetch timed out", event_id=event_id)
            return None, "clean_snapshot_timeout"
        except httpx.RequestError as e:
            log.error("Error fetching clean snapshot", event_id=event_id, error=str(e))
            return None, "clean_snapshot_request_error"
        except Exception as e:
            log.error("Error fetching clean snapshot", event_id=event_id, error=str(e))
            return None, "clean_snapshot_unknown_error"

    async def get_clip_with_error(self, event_id: str, timeout: float = 20.0) -> tuple[Optional[bytes], Optional[str]]:
        """Fetch video clip for an event with explicit error reason."""
        try:
            resp = await self.get(f"api/events/{event_id}/clip.mp4", timeout=timeout)
            if resp.status_code == 200:
                return resp.content, None
            if resp.status_code == 404:
                log.warning("Clip not found", event_id=event_id)
                return None, "clip_not_found"
            if resp.status_code == 400:
                try:
                    payload = resp.json()
                except Exception:
                    payload = None
                message = str((payload or {}).get("message") or "")
                if "No recordings found for the specified time range" in message:
                    log.warning("Clip recordings not retained", event_id=event_id)
                    return None, "clip_not_retained"
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

    async def get_recording_clip_with_error(
        self, camera: str, after: int, before: int, timeout: float = 20.0
    ) -> tuple[Optional[bytes], Optional[str]]:
        """Fetch a clip from Frigate's continuous recording for a camera/time window.

        Unlike the per-event clip, this reads the continuous recording, which usually
        still covers a briefly-tracked object even when the event snapshot/clip is gone.
        """
        try:
            resp = await self.get(f"api/{camera}/start/{after}/end/{before}/clip.mp4", timeout=timeout)
            if resp.status_code == 200:
                return resp.content, None
            if resp.status_code == 404:
                log.warning("Recording clip not found", camera=camera, after=after, before=before)
                return None, "clip_not_found"
            if resp.status_code == 400:
                try:
                    payload = resp.json()
                except Exception:
                    payload = None
                message = str((payload or {}).get("message") or "")
                if "No recordings found for the specified time range" in message:
                    log.warning("Recording not retained for window", camera=camera, after=after, before=before)
                    return None, "clip_not_retained"
            log.warning("Failed to fetch recording clip", camera=camera, status=resp.status_code)
            return None, f"clip_http_{resp.status_code}"
        except httpx.TimeoutException:
            log.warning("Recording clip fetch timed out", camera=camera, after=after, before=before)
            return None, "clip_timeout"
        except httpx.RequestError as e:
            log.error("Error fetching recording clip", camera=camera, error=str(e))
            return None, "clip_request_error"
        except Exception as e:
            log.error("Unexpected error fetching recording clip", camera=camera, error=str(e))
            return None, "clip_unknown_error"

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

    async def get_event_with_error(self, event_id: str, timeout: float = 10.0) -> tuple[Optional[dict], Optional[str]]:
        """Fetch event details with explicit error reason."""
        try:
            resp = await self.get(f"api/events/{event_id}", timeout=timeout)
            if resp.status_code == 200:
                return resp.json(), None
            if resp.status_code == 404:
                log.warning("Event not found", event_id=event_id)
                return None, "event_not_found"
            log.warning("Failed to fetch event", event_id=event_id, status=resp.status_code)
            return None, f"event_http_{resp.status_code}"
        except httpx.TimeoutException:
            log.warning("Event fetch timed out", event_id=event_id)
            return None, "event_timeout"
        except httpx.RequestError as e:
            log.error("Error fetching event", event_id=event_id, error=str(e))
            return None, "event_request_error"
        except Exception as e:
            log.error("Unexpected error fetching event", event_id=event_id, error=str(e))
            return None, "event_unknown_error"

    async def set_sublabel(self, event_id: str, sublabel: str, *, score: float | None = None) -> bool:
        """Set sublabel on a Frigate event.

        Args:
            event_id: Frigate event ID
            sublabel: Label to set (Frigate accepts up to 100 characters)
            score: Optional species-classification confidence, distinct from the
                Frigate object detector score.

        Returns:
            True if successful
        """
        try:
            payload: dict[str, object] = {"subLabel": str(sublabel).strip()[:100]}
            if score is not None:
                normalized_score = float(score)
                if math.isfinite(normalized_score) and 0.0 <= normalized_score <= 1.0:
                    payload["subLabelScore"] = normalized_score
            resp = await self.post(f"api/events/{event_id}/sub_label", json=payload, timeout=10.0)
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

    def get_camera_recording_clip_url(self, camera: str, after: int, before: int) -> str:
        """Build the Frigate camera clip URL for a recording time window."""
        return f"{self.base_url}/api/{camera}/start/{after}/end/{before}/clip.mp4"

    async def list_events(
        self,
        after: Optional[float] = None,
        before: Optional[float] = None,
        label: Optional[str] = None,
        camera: Optional[str] = None,
        has_snapshot: bool = True,
        limit: int = 100,
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
            List of event dictionaries from a confirmed HTTP 200 response.

        Raises:
            FrigateEventsFetchError: Frigate is unreachable, rejects the query,
                or returns a payload that cannot safely be treated as an event list.
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
        except httpx.TimeoutException as exc:
            log.warning("Frigate event history request timed out", camera=camera)
            raise FrigateEventsFetchError("Frigate event history request timed out") from exc
        except httpx.RequestError as exc:
            log.warning("Frigate event history request failed", camera=camera, error_type=type(exc).__name__)
            raise FrigateEventsFetchError("Frigate event history is unreachable") from exc
        except Exception as exc:
            log.error("Unexpected Frigate event history failure", camera=camera, error_type=type(exc).__name__)
            raise FrigateEventsFetchError("Frigate event history request failed") from exc

        if resp.status_code != 200:
            log.warning("Frigate event history returned an error", camera=camera, status=resp.status_code)
            raise FrigateEventsFetchError(f"Frigate event history request failed (HTTP {resp.status_code})")

        try:
            payload = resp.json()
        except ValueError as exc:
            log.warning("Frigate event history returned invalid JSON", camera=camera)
            raise FrigateEventsFetchError("Frigate returned an invalid event history payload") from exc
        if not isinstance(payload, list) or any(not isinstance(event, dict) for event in payload):
            log.warning("Frigate event history returned an unexpected payload", camera=camera)
            raise FrigateEventsFetchError("Frigate returned an invalid event history payload")
        return payload

    async def close(self):
        """Close the HTTP client and release resources."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Global singleton instance
frigate_client = FrigateClient()
