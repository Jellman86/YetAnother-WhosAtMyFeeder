import httpx
import structlog
from datetime import datetime, timedelta
from typing import Optional

from app.database import get_db
from app.services.frigate_client import frigate_client
from app.services.media_cache import media_cache

log = structlog.get_logger()

INAT_BASE_URL = "https://api.inaturalist.org/v1"
INAT_AUTHORIZE_URL = "https://www.inaturalist.org/oauth/authorize"
INAT_TOKEN_URL = "https://www.inaturalist.org/oauth/token"


class InaturalistService:
    def __init__(self):
        self._connected_user: Optional[str] = None

    async def store_token(
        self,
        email: str,
        access_token: str,
        refresh_token: Optional[str],
        token_type: Optional[str],
        expires_in: Optional[int],
        scope: Optional[str]
    ) -> None:
        expires_at = None
        if expires_in:
            expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))

        async with get_db() as db:
            cursor = await db.execute(
                "SELECT id FROM oauth_tokens WHERE provider = ?",
                ("inaturalist",)
            )
            row = await cursor.fetchone()
            if row:
                await db.execute(
                    """
                    UPDATE oauth_tokens
                    SET email = ?, access_token = ?, refresh_token = ?, token_type = ?,
                        expires_at = ?, scope = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE provider = ?
                    """,
                    (email, access_token, refresh_token, token_type, expires_at, scope, "inaturalist")
                )
            else:
                await db.execute(
                    """
                    INSERT INTO oauth_tokens (provider, email, access_token, refresh_token, token_type, expires_at, scope)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("inaturalist", email, access_token, refresh_token, token_type, expires_at, scope)
                )
            await db.commit()
            self._connected_user = email

    async def get_token(self) -> Optional[dict]:
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT email, access_token, refresh_token, token_type, expires_at, scope
                FROM oauth_tokens WHERE provider = ?
                """,
                ("inaturalist",)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "email": row[0],
                "access_token": row[1],
                "refresh_token": row[2],
                "token_type": row[3],
                "expires_at": row[4],
                "scope": row[5]
            }

    async def delete_token(self) -> bool:
        async with get_db() as db:
            await db.execute("DELETE FROM oauth_tokens WHERE provider = ?", ("inaturalist",))
            await db.commit()
            self._connected_user = None
            return db.total_changes > 0

    def get_connected_user(self) -> Optional[str]:
        return self._connected_user

    async def refresh_connected_user(self) -> Optional[str]:
        token = await self.get_token()
        self._connected_user = token.get("email") if token else None
        return self._connected_user

    async def fetch_user(self, access_token: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{INAT_BASE_URL}/users/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                if results:
                    return results[0].get("login") or results[0].get("name")
        except Exception as e:
            log.warning("inat_user_lookup_failed", error=str(e))
        return None

    async def get_snapshot_bytes(self, event_id: str) -> Optional[bytes]:
        cached = await media_cache.get_snapshot(event_id)
        if cached:
            return cached
        return await frigate_client.get_snapshot(event_id, crop=True, quality=95)

    async def create_observation(self, access_token: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{INAT_BASE_URL}/observations",
                headers={"Authorization": f"Bearer {access_token}"},
                data=payload
            )
            resp.raise_for_status()
            return resp.json()

    async def upload_photo(self, access_token: str, observation_id: int, image_bytes: bytes) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {
                "file": ("snapshot.jpg", image_bytes, "image/jpeg"),
                "observation_photo[observation_id]": (None, str(observation_id))
            }
            resp = await client.post(
                f"{INAT_BASE_URL}/observation_photos",
                headers={"Authorization": f"Bearer {access_token}"},
                files=files
            )
            resp.raise_for_status()


inaturalist_service = InaturalistService()
