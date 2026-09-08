"""Single-use tickets that open the live stream without a session token in the URL.

``EventSource`` cannot set headers, so whatever authenticates the stream has to ride
in the query string, and nginx writes the full request line to its error log every
time the upstream refuses a connection: a few seconds on every container start, in
practice, because the browser reconnects the stream immediately. A session token
logged there is a week of owner access. A ticket logged there is worthless sixty
seconds later and was spent on its first use anyway.

The store keeps only a hash of each ticket, so even a process dump does not hold a
redeemable secret. It owns no clock: callers pass ``now`` (monotonic seconds) so the
behaviour is deterministic in tests.
"""

import hashlib
import secrets
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Optional

STREAM_TICKET_TTL_SECONDS = 60
# Bounded so a client looping on the exchange endpoint cannot grow memory; a real
# owner needs one outstanding ticket per browser tab, briefly.
STREAM_TICKET_MAX_OUTSTANDING = 256


@dataclass(frozen=True)
class StreamTicketGrant:
    """What a redeemed ticket entitles the stream to: the session it was issued for."""

    auth_level: str
    username: Optional[str]
    # The session's own expiry, so the stream can end when the session would have.
    session_exp: Optional[datetime]

    @property
    def is_owner(self) -> bool:
        return self.auth_level == "owner"


@dataclass(frozen=True)
class _Record:
    grant: StreamTicketGrant
    expires_at: float


class StreamTicketStore:
    def __init__(
        self,
        ttl_seconds: float = STREAM_TICKET_TTL_SECONDS,
        max_outstanding: int = STREAM_TICKET_MAX_OUTSTANDING,
    ) -> None:
        self._ttl_seconds = float(ttl_seconds)
        self._max_outstanding = int(max_outstanding)
        # Insertion-ordered so the bound evicts the oldest ticket first.
        self._records: "OrderedDict[str, _Record]" = OrderedDict()

    def issue(
        self,
        auth_level: str,
        username: Optional[str],
        session_exp: Optional[datetime],
        now: Optional[float] = None,
    ) -> str:
        """Mint a ticket for this session. The returned string is the only copy."""
        moment = monotonic() if now is None else now
        self._sweep(moment)
        ticket = secrets.token_urlsafe(32)
        self._records[self._key(ticket)] = _Record(
            grant=StreamTicketGrant(auth_level=auth_level, username=username, session_exp=session_exp),
            expires_at=moment + self._ttl_seconds,
        )
        while len(self._records) > self._max_outstanding:
            self._records.popitem(last=False)
        return ticket

    def redeem(self, ticket: str, now: Optional[float] = None) -> Optional[StreamTicketGrant]:
        """Spend a ticket. A second redemption, or a late one, gets nothing."""
        moment = monotonic() if now is None else now
        record = self._records.pop(self._key(ticket), None)
        if record is None or moment >= record.expires_at:
            return None
        return record.grant

    def outstanding_keys(self) -> list[str]:
        """The stored keys, for tests proving the raw ticket is never kept."""
        return list(self._records)

    def clear(self) -> None:
        self._records.clear()

    def _sweep(self, now: float) -> None:
        expired = [key for key, record in self._records.items() if now >= record.expires_at]
        for key in expired:
            del self._records[key]

    @staticmethod
    def _key(ticket: str) -> str:
        return hashlib.sha256(ticket.encode("utf-8")).hexdigest()


stream_tickets = StreamTicketStore()
