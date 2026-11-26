"""Pure tests for ReelImageService: LRU bounds, TTLs, breaker, concurrency, and coalescing."""

from __future__ import annotations

import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image
import pytest

from app.services.reel_image_service import (
    REEL_IMAGE_MAX_EDGE,
    REEL_TILE_MAX_EDGE,
    REEL_UPSTREAM_MAX_BYTES,
    ReelImageService,
    ReelImageUnavailableError,
    resize_for_reel,
)


class _Clock:
    def __init__(self, start: float = 100.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _jpeg(width: int = 800, height: int = 600, color: tuple[int, int, int] = (40, 120, 70)) -> bytes:
    out = BytesIO()
    Image.new("RGB", (width, height), color).save(out, format="JPEG")
    return out.getvalue()


@pytest.mark.asyncio
async def test_fallback_lru_evicts_oldest_and_expires_on_clock():
    clock = _Clock()
    service = ReelImageService(clock=clock, max_fallback_entries=2, positive_ttl_seconds=60.0)
    calls: list[str] = []

    async def fake_fetch(event_id: str, **_kwargs):
        calls.append(event_id)
        return _jpeg(600, 400), None

    with (
        patch("app.services.reel_image_service.frigate_client.readiness.admit", new=AsyncMock(return_value=True)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=fake_fetch),
    ):
        a = await service.from_frigate("evt-a", "tile")
        b = await service.from_frigate("evt-b", "tile")
        assert a is not None and b is not None
        # Re-read evt-a so evt-b becomes oldest
        assert await service.from_frigate("evt-a", "tile") == a
        c = await service.from_frigate("evt-c", "tile")
        assert c is not None
        assert calls == ["evt-a", "evt-b", "evt-c"]

        # evt-b was evicted by LRU bound (2); evt-a is still warm
        assert await service.from_frigate("evt-a", "tile") == a
        assert calls == ["evt-a", "evt-b", "evt-c"]
        await service.from_frigate("evt-b", "tile")
        assert calls == ["evt-a", "evt-b", "evt-c", "evt-b"]

        # Advancing past TTL forces a fresh upstream fetch
        clock.advance(61.0)
        await service.from_frigate("evt-b", "tile")
        assert calls == ["evt-a", "evt-b", "evt-c", "evt-b", "evt-b"]


@pytest.mark.asyncio
async def test_negative_404_is_cached_until_ttl_expires_and_bounded():
    clock = _Clock()
    service = ReelImageService(clock=clock, max_missing_entries=2, negative_ttl_seconds=30.0)
    fetch = AsyncMock(return_value=(None, "snapshot_not_found"))

    with (
        patch("app.services.reel_image_service.frigate_client.readiness.admit", new=AsyncMock(return_value=True)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=fetch),
    ):
        assert await service.from_frigate("gone-1", "tile") is None
        assert await service.from_frigate("gone-1", "card") is None
        assert fetch.await_count == 1

        # Fill past max_missing_entries=2 to verify LRU eviction on missing cache
        assert await service.from_frigate("gone-2", "tile") is None
        assert await service.from_frigate("gone-3", "tile") is None
        assert fetch.await_count == 3
        assert await service.from_frigate("gone-1", "tile") is None
        assert fetch.await_count == 4

        # Advancing past negative TTL allows a retry for gone-1
        clock.advance(31.0)
        assert await service.from_frigate("gone-1", "tile") is None
        assert fetch.await_count == 5


@pytest.mark.asyncio
async def test_transient_error_trips_breaker_is_not_negative_cached_and_recovers():
    clock = _Clock()
    service = ReelImageService(clock=clock, breaker_seconds=20.0)
    responses = iter([(None, "snapshot_timeout"), (_jpeg(600, 400), None)])
    fetch = AsyncMock(side_effect=lambda *_a, **_kw: next(responses))

    with (
        patch("app.services.reel_image_service.frigate_client.readiness.admit", new=AsyncMock(return_value=True)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=fetch),
    ):
        with pytest.raises(ReelImageUnavailableError):
            await service.from_frigate("evt-flaky", "tile")
        assert fetch.await_count == 1

        # Breaker open: fails fast without calling Frigate
        with pytest.raises(ReelImageUnavailableError):
            await service.from_frigate("evt-other", "tile")
        assert fetch.await_count == 1

        # After breaker window elapses, same event retries and succeeds (was never negative-cached)
        clock.advance(21.0)
        result = await service.from_frigate("evt-flaky", "tile")
        assert result is not None
        assert fetch.await_count == 2


@pytest.mark.asyncio
async def test_not_ready_gate_fails_fast_without_fetching():
    service = ReelImageService()
    fetch = AsyncMock(return_value=(_jpeg(), None))
    note_deferred = MagicMock()

    with (
        patch("app.services.reel_image_service.frigate_client.readiness.admit", new=AsyncMock(return_value=False)),
        patch("app.services.reel_image_service.frigate_client.readiness.note_deferred", new=note_deferred),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=fetch),
    ):
        with pytest.raises(ReelImageUnavailableError):
            await service.from_frigate("evt-1", "tile")
    assert fetch.await_count == 0


@pytest.mark.asyncio
async def test_garbage_oversized_and_excessive_pixel_payloads_return_none_and_do_not_cache():
    service = ReelImageService()
    payloads = [
        (b"not-a-jpeg", None),
        (b"\xff" * (REEL_UPSTREAM_MAX_BYTES + 1), None),
    ]
    fetch = AsyncMock(side_effect=payloads)

    with (
        patch("app.services.reel_image_service.frigate_client.readiness.admit", new=AsyncMock(return_value=True)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=fetch),
    ):
        assert await service.from_frigate("evt-bad", "tile") is None
        # Not negative-cached, so a subsequent call hits upstream again
        assert await service.from_frigate("evt-bad", "tile") is None
    assert fetch.await_count == 2

    # Pixel dimension guard rejects extreme image sizes before full decode
    with patch("app.services.reel_image_service.REEL_MAX_IMAGE_PIXELS", 100):
        with pytest.raises(ValueError, match="out of bounds"):
            resize_for_reel(_jpeg(20, 20))


@pytest.mark.asyncio
async def test_concurrent_requests_coalesce_tile_and_card_into_one_fetch():
    service = ReelImageService()
    gate = asyncio.Event()
    started = asyncio.Event()
    calls = 0

    async def slow_fetch(_event_id: str, **_kwargs):
        nonlocal calls
        calls += 1
        started.set()
        await gate.wait()
        return _jpeg(1200, 900), None

    with (
        patch("app.services.reel_image_service.frigate_client.readiness.admit", new=AsyncMock(return_value=True)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=slow_fetch),
    ):
        t_tile_1 = asyncio.create_task(service.from_frigate("evt-shared", "tile"))
        await started.wait()
        t_tile_2 = asyncio.create_task(service.from_frigate("evt-shared", "tile"))
        t_card = asyncio.create_task(service.from_frigate("evt-shared", "card"))
        # Let waiters register and block on the per-event lock before releasing fetch
        await asyncio.sleep(0.02)
        gate.set()

        tile_1, tile_2, card = await asyncio.gather(t_tile_1, t_tile_2, t_card)

    assert calls == 1
    assert tile_1 is not None and tile_1 == tile_2
    assert card is not None
    with Image.open(BytesIO(tile_1)) as img:
        assert max(img.size) == REEL_TILE_MAX_EDGE
    with Image.open(BytesIO(card)) as img:
        assert max(img.size) == REEL_IMAGE_MAX_EDGE


@pytest.mark.asyncio
async def test_distinct_events_stay_within_semaphore_and_queue_timeout_fails_cleanly():
    service = ReelImageService(upstream_concurrency=2, upstream_queue_timeout_seconds=0.05)
    gate = asyncio.Event()
    active = 0
    peak = 0
    two_active = asyncio.Event()

    async def tracked_fetch(_event_id: str, **_kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 2:
            two_active.set()
        try:
            await gate.wait()
            return _jpeg(400, 300), None
        finally:
            active -= 1

    with (
        patch("app.services.reel_image_service.frigate_client.readiness.admit", new=AsyncMock(return_value=True)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=tracked_fetch),
    ):
        t1 = asyncio.create_task(service.from_frigate("evt-1", "tile"))
        t2 = asyncio.create_task(service.from_frigate("evt-2", "tile"))
        await two_active.wait()

        # Third distinct event exceeds concurrency=2 and hits queue timeout
        with pytest.raises(ReelImageUnavailableError):
            await service.from_frigate("evt-3", "tile")

        gate.set()
        r1, r2 = await asyncio.gather(t1, t2)
        assert r1 is not None and r2 is not None
        assert peak == 2

        # Semaphore was cleanly released so evt-3 succeeds afterward
        r3 = await service.from_frigate("evt-3", "tile")
        assert r3 is not None


@pytest.mark.asyncio
async def test_cancelled_waiter_leaves_no_stuck_event_lock():
    service = ReelImageService()
    gate = asyncio.Event()
    started = asyncio.Event()

    async def slow_fetch(_event_id: str, **_kwargs):
        started.set()
        await gate.wait()
        return _jpeg(400, 300), None

    with (
        patch("app.services.reel_image_service.frigate_client.readiness.admit", new=AsyncMock(return_value=True)),
        patch("app.services.reel_image_service.frigate_client.get_snapshot_with_error", new=slow_fetch),
    ):
        first = asyncio.create_task(service.from_frigate("evt-cancel", "tile"))
        await started.wait()
        waiter = asyncio.create_task(service.from_frigate("evt-cancel", "card"))
        await asyncio.sleep(0.02)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

        gate.set()
        assert await first is not None
        # Subsequent call for card is not blocked by any leaked lock or pending count
        assert await service.from_frigate("evt-cancel", "card") is not None
