import asyncio
import gc

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
        try:
            await release_first.wait()
        except asyncio.CancelledError:
            # An abandoned runner is cancelled (#314); this one completes in
            # the same window the cancellation is delivered, and its late
            # result must still be ignored rather than double-counted.
            pass
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
async def test_background_work_gets_relief_after_starvation_threshold():
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=1.0,
        background_lease_timeout_seconds=1.0,
        background_starvation_threshold_seconds=0.01,
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
    assert background_started.is_set() is True
    assert await background_task == "background"

    release_live.set()
    assert await live_task == "live"

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


@pytest.mark.asyncio
async def test_an_abandoned_runner_is_cancelled_not_left_holding_its_work():
    """Reclaiming a lease must cancel the runner, not just forget it.

    An abandoned runner keeps awaiting its work — for image classification an
    executor job holding the full-resolution frame — while the freed slot
    admits a replacement. Under sustained overload that pins one frame per
    abandonment, indefinitely (#314).
    """
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=0.01,
        background_lease_timeout_seconds=1.0,
    )
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def stuck_runner():
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    submit_task = asyncio.create_task(
        coordinator.submit(
            priority="live",
            kind="snapshot_classification",
            runner=stuck_runner,
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1.0)

    with pytest.raises(ClassificationLeaseExpiredError):
        await submit_task

    await asyncio.wait_for(cancelled.wait(), timeout=1.0)

    await coordinator.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("priority", ["live", "background"])
@pytest.mark.parametrize("cancellation", ["explicit", "outer_timeout"])
async def test_cancelled_queued_submission_is_removed_without_running(priority, cancellation):
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=5,
        background_lease_timeout_seconds=5,
    )
    active_started = asyncio.Event()
    release_active = asyncio.Event()
    cancelled_runner_started = asyncio.Event()

    async def active_runner():
        active_started.set()
        await release_active.wait()
        return "active"

    async def cancelled_runner():
        cancelled_runner_started.set()
        return "unwanted"

    async def queued_submission():
        if cancellation == "outer_timeout":
            async with asyncio.timeout(0.02):
                return await coordinator.submit(
                    priority=priority,
                    kind="cancelled",
                    runner=cancelled_runner,
                    queue_timeout_seconds=2,
                )
        return await coordinator.submit(
            priority=priority,
            kind="cancelled",
            runner=cancelled_runner,
            queue_timeout_seconds=2,
        )

    active = asyncio.create_task(coordinator.submit(priority=priority, kind="active", runner=active_runner))
    queued = None
    try:
        await asyncio.wait_for(active_started.wait(), timeout=1)
        queued = asyncio.create_task(queued_submission())
        async with asyncio.timeout(1):
            while coordinator.get_metrics()[priority]["queued"] != 1:
                await asyncio.sleep(0)
        if cancellation == "explicit":
            queued.cancel()
        with pytest.raises(asyncio.CancelledError if cancellation == "explicit" else TimeoutError):
            await queued
        metrics = coordinator.get_metrics()
        assert metrics[priority]["queued"] == 0
        assert metrics[priority]["running"] == 1
        assert metrics[priority]["rejected"] == 1
        assert metrics["recent_outcomes"][-1]["reason"] == "caller_cancelled"
        release_active.set()
        assert await active == "active"
        await asyncio.sleep(0)
        assert not cancelled_runner_started.is_set()
        assert coordinator.get_metrics()[priority]["running"] == 0
    finally:
        release_active.set()
        if queued is not None:
            queued.cancel()
        await asyncio.gather(active, *([queued] if queued else []), return_exceptions=True)
        await coordinator.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("priority", ["live", "background"])
async def test_cancelling_admitted_caller_keeps_capacity_until_runner_finishes(priority):
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=5,
        background_lease_timeout_seconds=5,
    )
    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def runner():
        started.set()
        await release.wait()
        finished.set()
        return "done"

    task = asyncio.create_task(coordinator.submit(priority=priority, kind="active", runner=runner))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert coordinator.get_metrics()[priority]["running"] == 1
        assert not finished.is_set()
        release.set()
        await asyncio.wait_for(finished.wait(), timeout=1)
        await asyncio.sleep(0)
        assert coordinator.get_metrics()[priority]["running"] == 0
        assert coordinator.get_metrics()[priority]["completed"] == 1
        assert coordinator.get_metrics()[priority]["rejected"] == 0
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await coordinator.shutdown()


@pytest.mark.asyncio
async def test_cancellation_during_admission_handoff_preserves_granted_work():
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=5,
        background_lease_timeout_seconds=5,
    )
    first_started, release_first = asyncio.Event(), asyncio.Event()
    next_started, release_next = asyncio.Event(), asyncio.Event()
    next_task = None

    async def first_runner():
        first_started.set()
        await release_first.wait()
        asyncio.get_running_loop().call_soon(next_task.cancel)
        return "first"

    async def next_runner():
        next_started.set()
        await release_next.wait()
        return "next"

    first_task = asyncio.create_task(coordinator.submit(priority="background", kind="first", runner=first_runner))
    try:
        await asyncio.wait_for(first_started.wait(), timeout=1)
        next_task = asyncio.create_task(
            coordinator.submit(
                priority="background",
                kind="next",
                runner=next_runner,
                queue_timeout_seconds=2,
            )
        )
        async with asyncio.timeout(1):
            while coordinator.get_metrics()["background"]["queued"] != 1:
                await asyncio.sleep(0)
        release_first.set()
        assert await first_task == "first"
        with pytest.raises(asyncio.CancelledError):
            await next_task
        await asyncio.wait_for(next_started.wait(), timeout=1)
        assert coordinator.get_metrics()["background"]["running"] == 1
        assert coordinator.get_metrics()["background"]["rejected"] == 0
        release_next.set()
        async with asyncio.timeout(1):
            while coordinator.get_metrics()["background"]["running"]:
                await asyncio.sleep(0)
        assert coordinator.get_metrics()["background"]["completed"] == 2
    finally:
        release_first.set()
        release_next.set()
        await asyncio.gather(first_task, *([next_task] if next_task else []), return_exceptions=True)
        await coordinator.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["runner_exception", "lease_expiry"])
async def test_cancelled_admitted_caller_does_not_leave_unclaimed_failures_or_capacity(failure):
    loop = asyncio.get_running_loop()
    errors = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: errors.append(context))
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=5,
        background_lease_timeout_seconds=0.03 if failure == "lease_expiry" else 5,
    )
    started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def failing_runner():
        started.set()
        try:
            await release.wait()
            raise RuntimeError("fixture runner failure")
        finally:
            finished.set()

    async def next_runner():
        return "next"

    task = asyncio.create_task(coordinator.submit(priority="background", kind="failing", runner=failing_runner))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert coordinator.get_metrics()["background"]["running"] == 1
        if failure == "runner_exception":
            release.set()
        await asyncio.wait_for(finished.wait(), timeout=1)
        async with asyncio.timeout(1):
            while coordinator.get_metrics()["background"]["running"]:
                await asyncio.sleep(0)
        assert coordinator.get_metrics()["background"]["failed" if failure == "runner_exception" else "abandoned"] == 1
        assert await coordinator.submit(priority="background", kind="next", runner=next_runner) == "next"
        del task
        gc.collect()
        await asyncio.sleep(0)
        assert errors == []
    finally:
        release.set()
        await coordinator.shutdown()
        loop.set_exception_handler(previous_handler)
