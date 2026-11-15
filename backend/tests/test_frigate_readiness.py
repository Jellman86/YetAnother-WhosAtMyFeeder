"""Event reads wait for Frigate to answer instead of failing, and warning, one by one."""

import asyncio

import httpx
import pytest
import pytest_asyncio
from structlog.testing import capture_logs

from app.services.frigate_client import FrigateClient
from app.services.frigate_readiness import FRIGATE_NOT_READY, FrigateReadinessGate


class FakeFrigate:
    """A Frigate whose web server is up while the API behind it may still be starting."""

    def __init__(self) -> None:
        self.api_started = False
        self.broken_events: set[str] = set()
        self.paths: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        if not self.api_started:
            return httpx.Response(500, text="auth upstream refused")
        if request.url.path == "/api/version":
            return httpx.Response(200, text="0.16.0")
        event_id = request.url.path.rsplit("/", 1)[-1]
        if event_id in self.broken_events:
            return httpx.Response(500, text="database is locked")
        return httpx.Response(200, json={"id": event_id, "has_clip": True})

    def event_reads(self) -> list[str]:
        return [path for path in self.paths if path.startswith("/api/events/")]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)


@pytest.fixture
def frigate():
    return FakeFrigate()


@pytest.fixture
def clock():
    return Clock()


@pytest_asyncio.fixture
async def client(frigate, clock):
    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(frigate.handler))
    client.readiness = FrigateReadinessGate(
        client._answers_readiness_check, clock=clock, sleep=clock.sleep, summary_delay_seconds=0
    )
    yield client
    await client.close()


async def _settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


def _levels(records: list[dict], level: str) -> list[dict]:
    return [record for record in records if record.get("log_level") == level]


@pytest.mark.asyncio
async def test_a_burst_of_reads_while_frigate_starts_logs_one_summary_and_no_warnings(client, frigate):
    with capture_logs() as records:
        results = await asyncio.gather(*(client.get_event_with_error(f"evt-{n}") for n in range(50)))
        await _settle()

    assert all(result == (None, FRIGATE_NOT_READY) for result in results)
    assert _levels(records, "warning") == []
    assert _levels(records, "error") == []
    summaries = [record for record in records if record["event"] == "Frigate not ready; retrying event reads"]
    assert len(summaries) == 1
    assert summaries[0]["log_level"] == "info"
    assert summaries[0]["deferred_reads"] == 50


@pytest.mark.asyncio
async def test_reads_are_not_sent_to_a_frigate_known_to_be_starting(client, frigate):
    await client.get_event_with_error("evt-1")
    reads_before = len(frigate.event_reads())

    results = await asyncio.gather(*(client.get_event_with_error(f"evt-{n}") for n in range(20)))

    assert all(result == (None, FRIGATE_NOT_READY) for result in results)
    assert len(frigate.event_reads()) == reads_before


@pytest.mark.asyncio
async def test_a_deferred_read_succeeds_once_frigate_is_ready(client, frigate, clock):
    assert await client.get_event_with_error("evt-1") == (None, FRIGATE_NOT_READY)

    frigate.api_started = True
    clock.now += 1.0
    with capture_logs() as records:
        event, error = await client.get_event_with_error("evt-1")

    assert error is None
    assert event == {"id": "evt-1", "has_clip": True}
    resumed = [record for record in records if record["event"] == "Frigate is ready; event reads resumed"]
    assert len(resumed) == 1
    assert resumed[0]["deferred_reads"] == 1


@pytest.mark.asyncio
async def test_readiness_checks_back_off_while_frigate_stays_down(client, frigate, clock):
    await client.get_event_with_error("evt-1")
    checks = lambda: frigate.paths.count("/api/version")  # noqa: E731
    assert checks() == 1

    await client.get_event_with_error("evt-1")
    assert checks() == 1, "a second read inside the retry interval must reuse the last check"

    clock.now += 1.0
    await client.get_event_with_error("evt-1")
    assert checks() == 2

    clock.now += 1.0
    await client.get_event_with_error("evt-1")
    assert checks() == 2, "the interval doubles after each failed check"

    clock.now += 1.0
    await client.get_event_with_error("evt-1")
    assert checks() == 3


@pytest.mark.asyncio
async def test_a_server_error_after_frigate_is_ready_is_still_a_warning(client, frigate):
    frigate.api_started = True
    frigate.broken_events.add("evt-broken")
    assert (await client.get_event_with_error("evt-ok"))[1] is None

    with capture_logs() as records:
        result = await client.get_event_with_error("evt-broken")

    assert result == (None, "event_http_500")
    warnings = _levels(records, "warning")
    assert [record["event"] for record in warnings] == ["Failed to fetch event"]
    assert warnings[0]["status"] == 500


@pytest.mark.asyncio
async def test_background_work_waits_for_frigate_before_its_first_read(client, frigate, clock):
    async def start_api_later() -> None:
        while clock.now < 7.0:
            await asyncio.sleep(0)
        frigate.api_started = True

    starter = asyncio.create_task(start_api_later())
    with capture_logs() as records:
        ready = await client.readiness.wait_until_ready(timeout_seconds=120.0)
        event, error = await client.get_event_with_error("evt-1")
    await starter

    assert ready is True
    assert error is None and event is not None
    assert frigate.event_reads() == ["/api/events/evt-1"], "no event was read before Frigate answered"
    assert _levels(records, "warning") == []


@pytest.mark.asyncio
async def test_waiting_for_frigate_is_bounded(client, frigate, clock):
    ready = await client.readiness.wait_until_ready(timeout_seconds=20.0)

    assert ready is False
    assert clock.now == pytest.approx(20.0)
    assert frigate.event_reads() == []


@pytest.mark.asyncio
async def test_a_connection_failure_while_frigate_is_down_is_the_same_transient_condition(clock):
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    client.readiness = FrigateReadinessGate(
        client._answers_readiness_check, clock=clock, sleep=clock.sleep, summary_delay_seconds=0
    )
    try:
        with capture_logs() as records:
            results = await asyncio.gather(*(client.get_event_with_error(f"evt-{n}") for n in range(10)))
            await _settle()
    finally:
        await client.close()

    assert all(result == (None, FRIGATE_NOT_READY) for result in results)
    assert _levels(records, "warning") == []
    assert _levels(records, "error") == []
    assert [r["deferred_reads"] for r in records if r["event"] == "Frigate not ready; retrying event reads"] == [10]


@pytest.mark.asyncio
async def test_a_refused_token_is_not_mistaken_for_frigate_starting(clock):
    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    client = FrigateClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(unauthorized))
    client.readiness = FrigateReadinessGate(client._answers_readiness_check, clock=clock, sleep=clock.sleep)
    try:
        with capture_logs() as records:
            result = await client.get_event_with_error("evt-1")
    finally:
        await client.close()

    assert result == (None, "event_http_401")
    assert [record["event"] for record in _levels(records, "warning")] == ["Failed to fetch event"]
