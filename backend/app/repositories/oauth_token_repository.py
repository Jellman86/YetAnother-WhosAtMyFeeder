"""Persistence helpers for OAuth tokens."""

import aiosqlite


class OAuthTokenRepository:
    """Own OAuth-token persistence operations shared by HTTP routes."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self.db = db

    async def delete_all(self) -> None:
        """Delete every persisted OAuth token."""
        await self.db.execute("DELETE FROM oauth_tokens")
        await self.db.commit()
