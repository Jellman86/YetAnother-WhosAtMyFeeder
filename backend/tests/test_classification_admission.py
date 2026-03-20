import asyncio

import pytest

from app.services import classification_admission as classification_admission_module
from app.services.classification_admission import (
    ClassificationAdmissionCoordinator,
    ClassificationLeaseExpiredError,
)


@pytest.mark.asyncio
async def test_live_work_reclaims_stale_lease_and_allows_next_live_request():
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=0.01,
        background_lease_timeout_seconds=1.0,
    )
    release_first = asyncio.Event()
    first_started = asyncio.Event()

    async def first_live():
        first_started.set()
        await release_first.wait()
        return "first"

    async def second_live():
        return "second"

    first_task = asyncio.create_task(
        coordinator.submit(
            priority="live",
            kind="snapshot_classification",
            runner=first_live,
        )
    )
    await asyncio.wait_for(first_started.wait(), timeout=1.0)

    with pytest.raises(ClassificationLeaseExpiredError):
        await first_task

    result = await coordinator.submit(
        priority="live",
        kind="snapshot_classification",
        runner=second_live,
    )
    assert result == "second"

    release_first.set()
    await asyncio.sleep(0.05)

    metrics = coordinator.get_metrics()
    assert metrics["live"]["abandoned"] == 1
    assert metrics["live"]["running"] == 0

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_stale_completion_after_reclaim_is_ignored():
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=0.01,
        background_lease_timeout_seconds=1.0,
    )
    release_first = asyncio.Event()
    first_started = asyncio.Event()

    async def first_live():
        first_started.set()
        await release_first.wait()
        return "late"

    task = asyncio.create_task(
        coordinator.submit(
            priority="live",
            kind="snapshot_classification",
            runner=first_live,
        )
    )
    await asyncio.wait_for(first_started.wait(), timeout=1.0)

    with pytest.raises(ClassificationLeaseExpiredError):
        await task

    release_first.set()
    await asyncio.sleep(0.05)

    metrics = coordinator.get_metrics()
    assert metrics["late_completions_ignored"] == 1
    assert metrics["live"]["completed"] == 0

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_background_work_waits_while_live_pressure_is_active():
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=1.0,
        background_lease_timeout_seconds=1.0,
    )
    release_live = asyncio.Event()
    live_started = asyncio.Event()
    background_started = asyncio.Event()

    async def live_runner():
        live_started.set()
        await release_live.wait()
        return "live"

    async def background_runner():
        background_started.set()
        return "background"

    live_task = asyncio.create_task(
        coordinator.submit(
            priority="live",
            kind="snapshot_classification",
            runner=live_runner,
        )
    )
    await asyncio.wait_for(live_started.wait(), timeout=1.0)

    background_task = asyncio.create_task(
        coordinator.submit(
            priority="background",
            kind="snapshot_classification",
            runner=background_runner,
            queue_timeout_seconds=1.0,
        )
    )

    await asyncio.sleep(0.05)
    assert background_started.is_set() is False

    release_live.set()
    assert await live_task == "live"
    assert await background_task == "background"

    metrics = coordinator.get_metrics()
    assert metrics["background"]["completed"] == 1

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_live_queue_is_served_before_background_queue_when_capacity_returns():
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=1.0,
        background_lease_timeout_seconds=1.0,
    )
    release_live = asyncio.Event()
    first_live_started = asyncio.Event()
    second_live_started = asyncio.Event()
    background_started = asyncio.Event()
    order: list[str] = []

    async def first_live():
        first_live_started.set()
        order.append("live-1-start")
        await release_live.wait()
        order.append("live-1-done")
        return "live-1"

    async def second_live():
        second_live_started.set()
        order.append("live-2-start")
        return "live-2"

    async def background_runner():
        background_started.set()
        order.append("background-start")
        return "background"

    first_task = asyncio.create_task(
        coordinator.submit(
            priority="live",
            kind="snapshot_classification",
            runner=first_live,
        )
    )
    await asyncio.wait_for(first_live_started.wait(), timeout=1.0)

    background_task = asyncio.create_task(
        coordinator.submit(
            priority="background",
            kind="snapshot_classification",
            runner=background_runner,
            queue_timeout_seconds=1.0,
        )
    )
    second_live_task = asyncio.create_task(
        coordinator.submit(
            priority="live",
            kind="snapshot_classification",
            runner=second_live,
            queue_timeout_seconds=1.0,
        )
    )

    await asyncio.sleep(0.05)
    assert background_started.is_set() is False
    assert second_live_started.is_set() is False

    release_live.set()

    assert await first_task == "live-1"
    assert await second_live_task == "live-2"
    assert await background_task == "background"
    assert order.index("live-2-start") < order.index("background-start")

    await coordinator.shutdown()


@pytest.mark.asyncio
async def test_submit_tolerates_timeout_race_after_item_was_already_admitted(monkeypatch: pytest.MonkeyPatch):
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=1.0,
        background_lease_timeout_seconds=1.0,
    )

    real_wait_for = classification_admission_module.asyncio.wait_for
    raised_once = False

    async def fake_wait_for(awaitable, timeout):
        nonlocal raised_once
        if not raised_once:
            raised_once = True
            raise asyncio.TimeoutError()
        return await real_wait_for(awaitable, timeout)

    monkeypatch.setattr(classification_admission_module.asyncio, "wait_for", fake_wait_for)

    async def runner():
        return "background"

    result = await coordinator.submit(
        priority="background",
        kind="snapshot_classification",
        runner=runner,
        queue_timeout_seconds=1.0,
    )

    assert result == "background"

    await coordinator.shutdown()
