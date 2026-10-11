"""Notification cooldown admission is atomic before remote channel work."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from app.config import settings
from app.services.notification_service import NotificationService
from app.services.notification_dispatcher import NotificationDispatcher


@pytest_asyncio.fixture
async def notification_fixture(monkeypatch):
    monkeypatch.setattr(settings.notifications, "notification_cooldown_minutes", 30)
    monkeypatch.setattr(settings.notifications.filters, "species_mode", "none")
    monkeypatch.setattr(settings.notifications.filters, "min_confidence", 0)
    monkeypatch.setattr(settings.notifications.filters, "audio_confirmed_only", False)
    monkeypatch.setattr(settings.notifications.filters, "camera_filters", {})
    for channel in ("discord", "telegram", "pushover", "email"):
        monkeypatch.setattr(getattr(settings.notifications, channel), "enabled", channel == "telegram")
    service = NotificationService()
    entered, release = asyncio.Event(), asyncio.Event()

    async def send(*args, **kwargs):
        entered.set()
        await release.wait()
        return True

    sender = AsyncMock(side_effect=send)
    monkeypatch.setattr(service, "_send_telegram", sender)

    async def notify(event="first", channels=None):
        return await service.notify_detection(
            event, "Robin", None, None, 0.9, "feeder", datetime.now(timezone.utc), "", channels=channels
        )

    try:
        yield service, sender, entered, release, notify
    finally:
        release.set()
        await service.client.aclose()


@pytest.mark.asyncio
async def test_concurrent_different_events_cannot_bypass_cooldown(notification_fixture):
    service, sender, entered, release, notify = notification_fixture
    first = asyncio.create_task(notify())
    await asyncio.wait_for(entered.wait(), 1)
    try:
        assert await asyncio.wait_for(notify("second"), 0.2) is False
        sender.assert_awaited_once()
    finally:
        release.set()
        await first
    assert await notify("third") is False


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [False, RuntimeError("fixture channel failure")])
async def test_failed_dispatch_releases_admission_for_retry(notification_fixture, failure):
    service, sender, entered, release, notify = notification_fixture
    sender.side_effect = None
    if isinstance(failure, Exception):
        sender.side_effect = failure
    else:
        sender.return_value = failure
    assert await notify() is False
    sender.side_effect = None
    sender.return_value = True
    assert await notify("retry") is True


@pytest.mark.asyncio
async def test_no_eligible_channel_does_not_consume_cooldown(notification_fixture):
    service, sender, entered, release, notify = notification_fixture
    assert await notify(channels=["discord"]) is False
    release.set()
    assert await notify("retry") is True
    sender.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancelled_unsent_dispatch_releases_admission(notification_fixture):
    service, sender, entered, release, notify = notification_fixture
    first = asyncio.create_task(notify())
    await asyncio.wait_for(entered.wait(), 1)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert await notify("retry") is True


@pytest.mark.asyncio
async def test_partial_delivery_keeps_cooldown_after_cancellation(notification_fixture, monkeypatch):
    service, sender, entered, release, notify = notification_fixture
    monkeypatch.setattr(settings.notifications.discord, "enabled", True)
    discord = AsyncMock(return_value=True)
    monkeypatch.setattr(service, "_send_discord", discord)
    first = asyncio.create_task(notify())
    await asyncio.wait_for(entered.wait(), 1)
    discord.assert_awaited_once()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert await asyncio.wait_for(notify("second"), 0.2) is False
    discord.assert_awaited_once()


@pytest.mark.asyncio
async def test_two_dispatcher_workers_share_the_cooldown_reservation(notification_fixture):
    service, sender, entered, release, notify = notification_fixture
    dispatcher = NotificationDispatcher()
    results = []

    async def job(event):
        results.append(await notify(event))

    try:
        await dispatcher.start()
        assert await dispatcher.enqueue("first", lambda: job("first"))
        await asyncio.wait_for(entered.wait(), 1)
        assert await dispatcher.enqueue("second", lambda: job("second"))
        await asyncio.sleep(0.05)
        release.set()
        await asyncio.wait_for(dispatcher._queue.join(), 2)
        assert sorted(results) == [False, True]
        sender.assert_awaited_once()
    finally:
        release.set()
        await dispatcher.stop()


@pytest.mark.asyncio
async def test_disabled_cooldown_allows_concurrent_events(notification_fixture, monkeypatch):
    _service, sender, entered, release, notify = notification_fixture
    monkeypatch.setattr(settings.notifications, "notification_cooldown_minutes", 0)
    first = asyncio.create_task(notify("first"))
    await asyncio.wait_for(entered.wait(), 1)
    second = asyncio.create_task(notify("second"))
    try:
        await asyncio.sleep(0.05)
        assert sender.await_count == 2
    finally:
        release.set()
        assert await first
        assert await second
