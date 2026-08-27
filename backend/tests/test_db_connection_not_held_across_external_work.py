"""A pooled connection must not be carried through external work.

The pool holds five connections and serves every request. A handler that keeps
one while it waits on Frigate, iNaturalist, a weather API, an LLM or model
inference removes a fifth of the server's capacity for the duration. A handful
of those at once is what produced the 17.8 s acquire waits, the ten-second
request timeouts and the dashboard that would not load.

These tests assert the property directly: at the moment the slow call runs,
nothing is checked out of the pool.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.database import close_db, get_db, get_db_pool_status, init_db
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def ensure_db_initialized():
    await init_db()
    try:
        yield
    finally:
        await close_db()


@pytest.fixture(autouse=True)
def owner_access():
    original_auth = settings.auth.enabled
    original_public = settings.public_access.enabled
    settings.auth.enabled = False
    settings.public_access.enabled = False
    yield
    settings.auth.enabled = original_auth
    settings.public_access.enabled = original_public


async def _insert_detection(event_id: str, species: str = "Robin", camera: str = "cam1") -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO detections (
                detection_time, detection_index, score, display_name, category_name,
                frigate_event, camera_name, is_hidden
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                datetime.now(timezone.utc).isoformat(sep=" "),
                1,
                0.9,
                species,
                species,
                event_id,
                camera,
            ),
        )
        await db.commit()


async def _delete_detection(event_id: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM detections WHERE frigate_event = ?", (event_id,))
        await db.commit()


class ConnectionHoldProbe:
    """Records how many connections were checked out when the slow call ran."""

    def __init__(self, return_value=None):
        self.return_value = return_value
        self.checked_out_during_call: int | None = None
        self.holder: str | None = None

    async def __call__(self, *args, **kwargs):
        status = get_db_pool_status()
        self.checked_out_during_call = status["checked_out"]
        self.holder = status["longest_active_hold_label"]
        return self.return_value

    def assert_pool_was_free(self) -> None:
        assert self.checked_out_during_call is not None, "The probed call never ran"
        assert self.checked_out_during_call == 0, (
            f"A pooled connection was held across external work by {self.holder!r}. "
            "Release the connection before the call and re-acquire for the write."
        )


@pytest.mark.asyncio
async def test_ai_analysis_does_not_hold_a_connection_across_the_model_call(client: httpx.AsyncClient):
    """An LLM call can run for tens of seconds. Holding a connection through it
    is the single most expensive way to lose pool capacity in the codebase."""
    event_id = "evt-hold-ai-analyze"
    await _insert_detection(event_id)
    probe = ConnectionHoldProbe(return_value="analysis")

    try:
        with (
            patch("app.routers.ai.frigate_client.get_snapshot", new=AsyncMock(return_value=b"snapshot-bytes")),
            patch("app.routers.ai._load_ai_analysis_frames", new=AsyncMock(return_value=([], None))),
            patch("app.routers.ai.ai_service.analyze_detection", new=probe),
        ):
            response = await client.post(f"/api/events/{event_id}/analyze", params={"force": "true"})

        assert response.status_code == 200, response.text
        probe.assert_pool_was_free()
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_ai_analysis_still_persists_its_result(client: httpx.AsyncClient):
    """Splitting the handler around the model call must not lose the write."""
    event_id = "evt-hold-ai-persist"
    await _insert_detection(event_id)

    try:
        with (
            patch("app.routers.ai.frigate_client.get_snapshot", new=AsyncMock(return_value=b"snapshot-bytes")),
            patch("app.routers.ai._load_ai_analysis_frames", new=AsyncMock(return_value=([], None))),
            patch("app.routers.ai.ai_service.analyze_detection", new=AsyncMock(return_value="a fine robin")),
        ):
            response = await client.post(f"/api/events/{event_id}/analyze", params={"force": "true"})

        assert response.status_code == 200, response.text
        assert response.json()["analysis"] == "a fine robin"
        async with get_db() as db:
            cursor = await db.execute("SELECT ai_analysis FROM detections WHERE frigate_event = ?", (event_id,))
            row = await cursor.fetchone()
        assert row[0] == "a fine robin"
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_ai_chat_does_not_hold_a_connection_across_the_model_call(client: httpx.AsyncClient):
    event_id = "evt-hold-ai-chat"
    await _insert_detection(event_id)
    probe = ConnectionHoldProbe(return_value="a reply")

    try:
        with patch("app.routers.ai.ai_service.chat_detection", new=probe):
            response = await client.post(
                f"/api/events/{event_id}/conversation",
                json={"message": "what is it doing?"},
            )

        assert response.status_code == 200, response.text
        probe.assert_pool_was_free()
    finally:
        await _delete_detection(event_id)


class _StubClassifier:
    """Stands in for the loaded model so no inference runs in the test."""

    async def classify_async(self, *args, **kwargs):
        return []

    async def classify_wildlife_async(self, *args, **kwargs):
        return []


def _reclassify_external_phase(on_snapshot):
    """Patch every external call `reclassify` makes, driving the no-result path.

    An empty result set returns 200 with `status="no_result"`, which exercises
    the whole handler without needing a real model or a real Frigate.
    """
    return (
        patch("app.routers.events.get_classifier", return_value=_StubClassifier()),
        patch(
            "app.routers.events.frigate_client.get_event_with_error",
            new=AsyncMock(return_value=({}, None)),
        ),
        patch("app.routers.events.load_snapshot_classification_input", new=on_snapshot),
        patch("app.routers.events.decode_image_bytes", return_value=object()),
        patch("app.routers.events.build_snapshot_classification_input_context", return_value={}),
    )


@pytest.mark.asyncio
async def test_reclassify_does_not_hold_a_connection_across_inference(client: httpx.AsyncClient):
    """Reclassification fetches a snapshot over HTTP and runs model inference.

    Both are slow and neither needs a database connection.
    """
    event_id = "evt-hold-reclassify"
    await _insert_detection(event_id)
    probe = ConnectionHoldProbe()

    async def probing_snapshot_load(*args, **kwargs):
        await probe()
        return (b"snapshot-bytes", _StubProvenance())

    try:
        patches = _reclassify_external_phase(probing_snapshot_load)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            response = await client.post(f"/api/events/{event_id}/reclassify", params={"strategy": "snapshot"})

        assert response.status_code == 200, response.text
        probe.assert_pool_was_free()
    finally:
        await _delete_detection(event_id)


class _StubProvenance:
    input_source = "snapshot"


@pytest.mark.asyncio
async def test_concurrent_reclassification_cannot_deadlock_the_pool(monkeypatch):
    """Every concurrent reclassification must finish with a pool its own size.

    `reclassify` held a connection and then called `apply_video_result`, which
    acquires a second one. With as many concurrent requests as the pool has
    connections, every request held one and every request waited for one that
    could only be released by another request that was also waiting. Nothing
    completed and no timeout existed to break it.
    """
    from app import database as database_module
    from app.database import DatabasePool

    pool_size = 3
    pool = DatabasePool(database_module._get_db_path(), pool_size=pool_size)
    await pool.initialize()
    monkeypatch.setattr(database_module, "_db_pool", pool)
    monkeypatch.setattr(database_module, "DB_POOL_ACQUIRE_TIMEOUT_SECONDS", 5.0)

    event_ids = [f"evt-deadlock-{i}" for i in range(pool_size)]
    for event_id in event_ids:
        await _insert_detection(event_id)

    all_inside = asyncio.Event()
    release_inference = asyncio.Event()
    in_flight = 0

    async def slow_snapshot_load(*args, **kwargs):
        """Hold every request inside the external phase simultaneously."""
        nonlocal in_flight
        in_flight += 1
        if in_flight >= pool_size:
            all_inside.set()
        await all_inside.wait()
        await release_inference.wait()
        return (b"snapshot-bytes", _StubProvenance())

    transport = httpx.ASGITransport(app=app)
    try:
        patches = _reclassify_external_phase(slow_snapshot_load)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as concurrent_client:
                pending = asyncio.gather(
                    *[
                        concurrent_client.post(f"/api/events/{event_id}/reclassify", params={"strategy": "snapshot"})
                        for event_id in event_ids
                    ]
                )
                await asyncio.wait_for(all_inside.wait(), timeout=5.0)

                # The property under test: while every request is inside the
                # external phase, the pool must be completely free.
                assert pool.get_status()["checked_out"] == 0, (
                    "Requests are holding connections while waiting on Frigate; "
                    f"{pool.get_status()['longest_active_hold_label']} still holds one."
                )

                release_inference.set()
                responses = await asyncio.wait_for(pending, timeout=10.0)

        assert [r.status_code for r in responses] == [200] * pool_size
        assert pool.get_status()["acquire_timeouts"] == 0
    finally:
        release_inference.set()
        for event_id in event_ids:
            await _delete_detection(event_id)
        await pool.close_all()


@pytest.mark.asyncio
async def test_species_filter_does_not_hold_a_connection_across_taxonomy_lookups(client: httpx.AsyncClient):
    """The species filter resolves names for every species it offers.

    On a cache miss each of those is an iNaturalist request with a ten-second
    timeout, and the handler resolves five at a time — against a pool of five.
    Holding a connection across that loop is what made this filter the slowest
    of the three (reported as the Explorer species filter loading slowly, and
    then not loading at all).
    """
    event_id = "evt-hold-filters"
    await _insert_detection(event_id, species="Eurasian Blue Tit")
    probe = ConnectionHoldProbe(return_value={"scientific_name": "Cyanistes caeruleus", "common_name": None})

    try:
        with patch("app.routers.events.taxonomy_service.get_names", new=probe):
            response = await client.get("/api/events/filters", params={"force_refresh": "true"})

        assert response.status_code == 200, response.text
        probe.assert_pool_was_free()
    finally:
        await _delete_detection(event_id)


@pytest.mark.asyncio
async def test_the_mqtt_ingest_entry_point_is_marked_as_durable_work():
    """Ingest must be marked at its boundary, not somewhere downstream.

    `process_mqtt_message` is the single point every Frigate event passes
    through, and the point at which an exception becomes a dropped detection.
    Marking it here covers the whole pipeline below it.
    """
    from app.database import is_durable_work
    from app.services.event_processor import EventProcessor

    seen: dict[str, bool] = {}

    processor = EventProcessor.__new__(EventProcessor)

    async def record(_data):
        seen["durable"] = is_durable_work()

    processor._process_event_payload = record

    await EventProcessor.process_mqtt_message(processor, b'{"after": {"id": "evt-durable"}}')

    assert seen.get("durable") is True, "Frigate event ingest must never be refused a connection"
    assert is_durable_work() is False, "The marking must not leak past the message it covers"


@pytest.mark.asyncio
async def test_the_audio_ingest_entry_point_is_marked_as_durable_work():
    """A heard bird is delivered once too.

    `process_audio_message` drops on any exception in exactly the way the
    Frigate handler does, and `audio_detections` is user data by the same
    argument as `detections`.
    """
    from app.database import is_durable_work
    from app.services.event_processor import EventProcessor

    seen: dict[str, bool] = {}

    async def record(_data):
        seen["durable"] = is_durable_work()

    with patch("app.services.event_processor.audio_service.add_detection", new=record):
        await EventProcessor.process_audio_message(EventProcessor.__new__(EventProcessor), b'{"commonName": "Robin"}')

    assert seen.get("durable") is True
    assert is_durable_work() is False
