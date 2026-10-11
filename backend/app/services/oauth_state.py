"""Short-lived, single-use capabilities issued only by owner authorization routes."""

import secrets
import time
from typing import Literal

OAuthProvider = Literal["gmail", "outlook", "inaturalist"]
OAUTH_CALLBACK_PATHS = frozenset(
    {"/api/email/oauth/gmail/callback", "/api/email/oauth/outlook/callback", "/api/inaturalist/oauth/callback"}
)


class OAuthStateStore:
    def __init__(self, *, ttl_seconds: float = 600, maximum: int = 256) -> None:
        self.ttl_seconds = ttl_seconds
        self.maximum = maximum
        self._expires: dict[tuple[OAuthProvider, str], float] = {}

    def issue(self, provider: OAuthProvider) -> str:
        state = secrets.token_urlsafe(32)
        self.remember(provider, state)
        return state

    def remember(self, provider: OAuthProvider, state: str) -> None:
        now = time.monotonic()
        self._expires = {key: expiry for key, expiry in self._expires.items() if expiry > now}
        key = (provider, state)
        if key not in self._expires and len(self._expires) >= self.maximum:
            self._expires.pop(min(self._expires, key=self._expires.__getitem__))
        self._expires[key] = now + self.ttl_seconds

    def consume(self, provider: OAuthProvider, state: str | None) -> bool:
        if not state:
            return False
        # No await separates validation from removal. Wrong-provider requests
        # cannot consume an owner's legitimate callback for another provider.
        expiry = self._expires.pop((provider, state), None)
        return expiry is not None and expiry > time.monotonic()


oauth_states = OAuthStateStore()
