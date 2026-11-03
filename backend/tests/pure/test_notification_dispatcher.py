import asyncio

import pytest

import app.services.notification_dispatcher as notification_dispatcher_module


@pytest.mark.asyncio
async def test_notification_dispatcher_stop_drains_pending_jobs(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(notification_dispatcher_module, "NOTIFICATION_DISPATCH_WORKERS", 1, raising=False)

    dispatcher = notification_dispatcher_module.NotificationDispatcher()
    first_job_started = asyncio.Event()
    release_first_job = asyncio.Event()
    second_job_called = False

    async def first_job():
        first_job_started.set()
        await release_first_job.wait()

    async def second_job():
        nonlocal second_job_called
        second_job_called = True

    await dispatcher.enqueue("job-1", lambda: first_job())
    await asyncio.wait_for(first_job_started.wait(), timeout=0.2)
    await dispatcher.enqueue("job-2", lambda: second_job())

    assert dispatcher.get_status()["queue_size"] == 1

    await dispatcher.stop()

    assert dispatcher.get_status()["running"] is False
    assert dispatcher.get_status()["queue_size"] == 0

    await dispatcher.start()
    await asyncio.sleep(0.05)
    await dispatcher.stop()

    assert second_job_called is False


@pytest.mark.asyncio
async def test_notification_dispatcher_counts_loop_reset_drops(monkeypatch: pytest.MonkeyPatch):
    dispatcher = notification_dispatcher_module.NotificationDispatcher()
    await dispatcher.start()

    orphaned_job = asyncio.Event()
    assert dispatcher._queue is not None
    dispatcher._queue.put_nowait(("orphaned-job", lambda: orphaned_job.wait()))
    dispatcher._loop = object()  # Force a loop-state reset on the next enqueue.

    records: list[dict] = []
    monkeypatch.setattr(
        notification_dispatcher_module.error_diagnostics_history,
        "record",
        lambda **kwargs: records.append(kwargs),
    )

    await dispatcher.enqueue("job-1", lambda: asyncio.sleep(0))

    status = dispatcher.get_status()
    assert status["dropped_jobs"] == 1
    assert any(record.get("reason_code") == "loop_reset_drop" for record in records)

    await dispatcher.stop()
