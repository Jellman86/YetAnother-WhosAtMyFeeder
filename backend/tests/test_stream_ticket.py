"""The live stream authenticates with a single-use ticket, never the session token.

`EventSource` cannot set headers, so the stream URL has to carry its credential in the
query string, and nginx writes the full request line to its error log whenever the
upstream refuses a connection — which it does for a few seconds on every container
start. A ticket that is worthless a minute later can be logged without handing out
a week-long owner session.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from starlette.requests import Request

from app.auth import AuthLevel, create_access_token, get_stream_auth_context
from app.config import settings
from app.auth import hash_password
from app.main import app, sse_endpoint
from app.services.stream_tickets import STREAM_TICKET_TTL_SECONDS, StreamTicketStore, stream_tickets


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def owner_password_configured():
    original = (
        settings.auth.enabled,
        settings.auth.password_hash,
        settings.auth.username,
        settings.auth.initial_setup_complete,
        settings.public_access.enabled,
        settings.api_key,
    )
    settings.auth.enabled = True
    settings.auth.password_hash = hash_password("correct-horse-1")
    settings.auth.username = "owner"
    settings.auth.initial_setup_complete = True
    settings.public_access.enabled = False
    settings.api_key = None
    stream_tickets.clear()
    yield
    (
        settings.auth.enabled,
        settings.auth.password_hash,
        settings.auth.username,
        settings.auth.initial_setup_complete,
        settings.public_access.enabled,
        settings.api_key,
    ) = original
    stream_tickets.clear()


def _request(query: str = "", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/sse",
            "raw_path": b"/api/sse",
            "query_string": query.encode("utf-8"),
            "headers": headers or [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "root_path": "",
        }
    )


# --- the store: pure, deterministic, owns no clock ---------------------------------


def test_a_ticket_is_redeemed_exactly_once():
    store = StreamTicketStore(ttl_seconds=60)
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    ticket = store.issue(AuthLevel.OWNER, "owner", exp, now=1000.0)

    grant = store.redeem(ticket, now=1010.0)
    assert grant is not None
    assert grant.auth_level == AuthLevel.OWNER
    assert grant.username == "owner"
    assert grant.session_exp == exp

    assert store.redeem(ticket, now=1011.0) is None


def test_an_expired_ticket_is_worthless():
    store = StreamTicketStore(ttl_seconds=60)
    ticket = store.issue(AuthLevel.OWNER, "owner", None, now=1000.0)
    assert store.redeem(ticket, now=1000.0 + 60.0) is None


def test_the_store_never_holds_the_redeemable_secret():
    store = StreamTicketStore(ttl_seconds=60)
    ticket = store.issue(AuthLevel.OWNER, "owner", None, now=1000.0)
    assert ticket not in store.outstanding_keys()
    assert len(ticket) >= 32


def test_outstanding_tickets_are_bounded_oldest_first():
    store = StreamTicketStore(ttl_seconds=60, max_outstanding=2)
    first = store.issue(AuthLevel.OWNER, "owner", None, now=1000.0)
    second = store.issue(AuthLevel.OWNER, "owner", None, now=1001.0)
    third = store.issue(AuthLevel.OWNER, "owner", None, now=1002.0)

    assert store.redeem(first, now=1003.0) is None
    assert store.redeem(second, now=1003.0) is not None
    assert store.redeem(third, now=1003.0) is not None


def test_expired_tickets_are_swept_before_the_bound_applies():
    store = StreamTicketStore(ttl_seconds=10, max_outstanding=1)
    stale = store.issue(AuthLevel.OWNER, "owner", None, now=1000.0)
    fresh = store.issue(AuthLevel.OWNER, "owner", None, now=1020.0)
    assert store.redeem(stale, now=1021.0) is None
    assert store.redeem(fresh, now=1021.0) is not None


# --- the stream's auth dependency ---------------------------------------------------


@pytest.mark.asyncio
async def test_a_ticket_in_the_query_grants_the_session_it_was_issued_for():
    exp = datetime.now(timezone.utc) + timedelta(hours=2)
    ticket = stream_tickets.issue(AuthLevel.OWNER, "owner", exp)

    stream_auth = await get_stream_auth_context(_request(query=f"ticket={ticket}"), None, None, None)

    assert stream_auth.context.is_owner
    assert stream_auth.context.username == "owner"
    assert stream_auth.session_exp == exp


@pytest.mark.asyncio
async def test_the_session_token_in_the_query_no_longer_opens_the_stream():
    token = create_access_token("owner", AuthLevel.OWNER)

    with pytest.raises(HTTPException) as excinfo:
        await get_stream_auth_context(_request(query=f"token={token}"), None, None, None)
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_a_bearer_header_still_opens_the_stream_for_clients_that_can_send_one():
    token = create_access_token("owner", AuthLevel.OWNER)
    request = _request(headers=[(b"authorization", f"Bearer {token}".encode())])

    stream_auth = await get_stream_auth_context(request, None, None, None)

    assert stream_auth.context.is_owner
    assert stream_auth.session_exp is not None


@pytest.mark.asyncio
async def test_a_guest_opens_the_stream_without_any_credential_when_public_access_is_on():
    settings.public_access.enabled = True

    stream_auth = await get_stream_auth_context(_request(), None, None, None)

    assert stream_auth.context.auth_level == AuthLevel.GUEST
    assert stream_auth.session_exp is None


@pytest.mark.asyncio
async def test_a_used_ticket_falls_back_to_whatever_the_bare_request_would_get():
    settings.public_access.enabled = True
    ticket = stream_tickets.issue(AuthLevel.OWNER, "owner", None)
    first = await get_stream_auth_context(_request(query=f"ticket={ticket}"), None, None, None)
    assert first.context.is_owner

    second = await get_stream_auth_context(_request(query=f"ticket={ticket}"), None, None, None)
    assert second.context.auth_level == AuthLevel.GUEST


@pytest.mark.asyncio
async def test_auth_disabled_keeps_the_stream_open_to_everyone():
    settings.auth.enabled = False

    stream_auth = await get_stream_auth_context(_request(), None, None, None)

    assert stream_auth.context.is_owner


# --- issuing a ticket -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_owner_session_is_issued_a_short_lived_ticket(client: httpx.AsyncClient):
    token = create_access_token("owner", AuthLevel.OWNER)

    response = await client.post("/api/auth/stream-ticket", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expires_in_seconds"] == STREAM_TICKET_TTL_SECONDS
    assert body["ticket"] != token
    grant = stream_tickets.redeem(body["ticket"], now=asyncio.get_running_loop().time())
    assert grant is not None and grant.is_owner


@pytest.mark.asyncio
async def test_a_guest_is_not_issued_a_ticket(client: httpx.AsyncClient):
    settings.public_access.enabled = True

    response = await client.post("/api/auth/stream-ticket")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_no_session_means_no_ticket(client: httpx.AsyncClient):
    response = await client.post("/api/auth/stream-ticket")

    assert response.status_code == 401


# --- the mounted endpoint -------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_stream_refuses_a_session_token_in_its_query(client: httpx.AsyncClient):
    token = create_access_token("owner", AuthLevel.OWNER)

    response = await client.get(f"/api/sse?token={token}")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_the_stream_opens_with_a_ticket():
    ticket = stream_tickets.issue(AuthLevel.OWNER, "owner", None)
    request = _request(query=f"ticket={ticket}")
    stream_auth = await get_stream_auth_context(request, None, None, None)

    response = await sse_endpoint(request, stream_auth)
    try:
        first_frame = await asyncio.wait_for(response.body_iterator.__anext__(), timeout=10)
    finally:
        await response.body_iterator.aclose()

    assert response.media_type == "text/event-stream"
    assert '"auth_level": "owner"' in first_frame
