"""What the record is told about a Frigate event, from the HTTP answer to the response field.

The client folds several failures into `frigate_not_ready` once its readiness
check fails: a timeout, an HTTP 503 and a refused connection all arrive as the
same code. The record used to call every one of them "unreachable". The gate
now keeps the failure that closed it, so a timeout is reported as a timeout, a
server error as a failed check, and only a connection that could not be made
as unreachable. Refused credentials are their own cause.
"""

import httpx
import pytest
import pytest_asyncio

from app.routers import events as events_router
from app.services.frigate_client import FrigateClient
from app.services.frigate_readiness import FRIGATE_NOT_READY


class Frigate:
    """A Frigate that answers every request, the readiness check included, one way."""

    def __init__(self) -> None:
        self.answer = "ok"

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.answer == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if self.answer == "refused_connection":
            raise httpx.ConnectError("connection refused", request=request)
        if self.answer == "503":
            return httpx.Response(503, text="service unavailable")
        if self.answer == "401":
            return httpx.Response(401, text="unauthorized")
        if self.answer == "403":
            return httpx.Response(403, text="forbidden")
        if request.url.path == "/api/version":
            return httpx.Response(200, text="0.16.0")
        if self.answer == "404":
            return httpx.Response(404, json={"message": "Event not found"})
        return httpx.Response(200, json={"id": "evt", "has_clip": False, "has_snapshot": True})


@pytest_asyncio.fixture
async def frigate(monkeypatch):
    fake = Frigate()
    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr(events_router, "frigate_client", client)
    for name in ("has_snapshot", "has_clip", "has_recording_clip"):
        monkeypatch.setattr(events_router.media_cache, name, lambda _event: False)
    yield fake, client
    await client.close()


async def _check(event: str = "evt") -> str:
    return (await events_router.batch_check_clips([event]))[event]["frigate_event_check"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("ok", "found"),
        ("404", "not_found"),
        ("timeout", "timed_out"),
        ("503", "failed"),
        ("refused_connection", "unreachable"),
        ("401", "unauthorized"),
        ("403", "unauthorized"),
    ],
)
async def test_each_frigate_answer_reaches_the_record_as_its_own_cause(frigate, answer, expected):
    fake, _client = frigate
    fake.answer = answer

    assert await _check() == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(("answer", "expected"), [("timeout", "timed_out"), ("503", "failed")])
async def test_a_read_put_off_while_frigate_is_not_answering_keeps_the_cause_that_closed_the_gate(
    frigate, answer, expected
):
    fake, client = frigate
    fake.answer = answer
    await _check("evt-first")
    assert client.readiness.ready is False

    # The gate is closed, so this read is not sent at all; it still reports why.
    data, error = await client.get_event_with_error("evt-second")
    assert (data, error) == (None, FRIGATE_NOT_READY)
    assert await _check("evt-second") == expected


@pytest.mark.asyncio
async def test_the_cause_is_forgotten_once_frigate_answers_again(frigate):
    fake, client = frigate
    fake.answer = "timeout"
    assert await _check() == "timed_out"

    fake.answer = "ok"
    client.readiness._last_probe_at = None  # the next check is due
    assert await _check() == "found"
    assert client.readiness.not_ready_cause is None
