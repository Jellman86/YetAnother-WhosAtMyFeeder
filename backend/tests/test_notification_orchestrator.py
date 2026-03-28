from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services.notification_orchestrator import NotificationOrchestrator


def _event(event_id: str = "evt-notify"):
    return SimpleNamespace(
        frigate_event=event_id,
        camera="cam_1",
        detection_dt=datetime.now(timezone.utc),
        type="new",
    )


def test_effective_video_wait_timeout_uses_pipeline_budget(monkeypatch):
    orchestrator = NotificationOrchestrator()

    monkeypatch.setattr(settings.notifications, "video_fallback_timeout", 45)
    monkeypatch.setattr(settings.classification, "video_classification_delay", 120)
    monkeypatch.setattr(settings.classification, "video_classification_max_retries", 3)
    monkeypatch.setattr(settings.classification, "video_classification_retry_interval", 15)

    assert orchestrator._effective_video_wait_timeout() == 240


def test_effective_video_wait_timeout_respects_larger_manual_override(monkeypatch):
    orchestrator = NotificationOrchestrator()

    monkeypatch.setattr(settings.notifications, "video_fallback_timeout", 300)
    monkeypatch.setattr(settings.classification, "video_classification_delay", 120)
    monkeypatch.setattr(settings.classification, "video_classification_max_retries", 3)
    monkeypatch.setattr(settings.classification, "video_classification_retry_interval", 15)

    assert orchestrator._effective_video_wait_timeout() == 300


@pytest.mark.asyncio
async def test_notify_after_video_uses_completed_video_result(monkeypatch):
    orchestrator = NotificationOrchestrator()
    event = _event()
    classification = {
        "label": "Unknown Bird",
        "score": 0.22,
        "audio_confirmed": False,
        "audio_species": None,
    }

    pending = SimpleNamespace(video_classification_status="pending")
    completed = SimpleNamespace(
        video_classification_status="completed",
        video_classification_label="Blue Jay",
        video_classification_score=0.93,
    )
    orchestrator._get_detection = AsyncMock(side_effect=[pending, completed])  # type: ignore[method-assign]
    orchestrator._send_notification = AsyncMock(return_value=True)  # type: ignore[method-assign]
    orchestrator._mark_notified = AsyncMock()  # type: ignore[method-assign]

    monkeypatch.setattr(settings.notifications, "video_fallback_timeout", 2)
    monkeypatch.setattr(settings.classification, "threshold", 0.8)
    monkeypatch.setattr(settings.classification, "video_classification_delay", 120)
    monkeypatch.setattr(settings.classification, "video_classification_max_retries", 3)
    monkeypatch.setattr(settings.classification, "video_classification_retry_interval", 15)

    with patch(
        "app.services.notification_orchestrator.video_classification_waiter.wait_for_final_status",
        new=AsyncMock(return_value={"status": "completed", "label": "Blue Jay", "score": 0.93}),
    ) as wait_for:
        await orchestrator._notify_after_video(event, classification, False, None)

    wait_for.assert_awaited_once_with(event.frigate_event, timeout=240)
    orchestrator._send_notification.assert_awaited_once()
    kwargs = orchestrator._send_notification.call_args.kwargs
    assert kwargs["label"] == "Blue Jay"
    assert kwargs["score"] == pytest.approx(0.93)
    orchestrator._mark_notified.assert_awaited_once_with(event.frigate_event)


@pytest.mark.asyncio
async def test_notify_after_video_skips_unconfirmed_snapshot_and_failed_video(monkeypatch):
    orchestrator = NotificationOrchestrator()
    event = _event("evt-skip")
    classification = {
        "label": "Unknown Bird",
        "score": 0.10,
        "audio_confirmed": False,
        "audio_species": None,
    }

    pending = SimpleNamespace(video_classification_status="pending")
    failed = SimpleNamespace(
        video_classification_status="failed",
        video_classification_label=None,
        video_classification_score=None,
    )
    orchestrator._get_detection = AsyncMock(side_effect=[pending, failed])  # type: ignore[method-assign]
    orchestrator._send_notification = AsyncMock(return_value=True)  # type: ignore[method-assign]
    orchestrator._mark_notified = AsyncMock()  # type: ignore[method-assign]

    monkeypatch.setattr(settings.notifications, "video_fallback_timeout", 2)
    monkeypatch.setattr(settings.classification, "threshold", 0.8)
    monkeypatch.setattr(settings.classification, "video_classification_delay", 120)
    monkeypatch.setattr(settings.classification, "video_classification_max_retries", 3)
    monkeypatch.setattr(settings.classification, "video_classification_retry_interval", 15)

    with patch(
        "app.services.notification_orchestrator.video_classification_waiter.wait_for_final_status",
        new=AsyncMock(return_value={"status": "failed"}),
    ):
        await orchestrator._notify_after_video(event, classification, False, None)

    orchestrator._send_notification.assert_not_awaited()
    orchestrator._mark_notified.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_after_video_does_not_wait_when_db_is_already_final(monkeypatch):
    orchestrator = NotificationOrchestrator()
    event = _event("evt-final")
    classification = {
        "label": "Cardinal",
        "score": 0.3,
        "audio_confirmed": False,
        "audio_species": None,
    }

    completed = SimpleNamespace(
        video_classification_status="completed",
        video_classification_label="Northern Cardinal",
        video_classification_score=0.91,
    )
    orchestrator._get_detection = AsyncMock(return_value=completed)  # type: ignore[method-assign]
    orchestrator._send_notification = AsyncMock(return_value=True)  # type: ignore[method-assign]
    orchestrator._mark_notified = AsyncMock()  # type: ignore[method-assign]

    monkeypatch.setattr(settings.notifications, "video_fallback_timeout", 5)
    monkeypatch.setattr(settings.classification, "threshold", 0.8)

    with patch(
        "app.services.notification_orchestrator.video_classification_waiter.wait_for_final_status",
        new=AsyncMock(),
    ) as wait_for:
        await orchestrator._notify_after_video(event, classification, False, None)

    wait_for.assert_not_awaited()
    orchestrator._send_notification.assert_awaited_once()
    kwargs = orchestrator._send_notification.call_args.kwargs
    assert kwargs["label"] == "Northern Cardinal"
    assert kwargs["score"] == pytest.approx(0.91)


@pytest.mark.asyncio
async def test_handle_notifications_sends_email_on_end_even_if_already_notified(monkeypatch):
    orchestrator = NotificationOrchestrator()
    event = _event("evt-email-end")
    event.type = "end"
    classification = {
        "label": "Blue Tit",
        "score": 0.95,
        "audio_confirmed": False,
        "audio_species": None,
    }

    detection = SimpleNamespace(notified_at=datetime.now(timezone.utc))
    orchestrator._get_detection = AsyncMock(return_value=detection)  # type: ignore[method-assign]
    orchestrator._send_notification = AsyncMock(return_value=True)  # type: ignore[method-assign]
    orchestrator._mark_notified = AsyncMock()  # type: ignore[method-assign]

    monkeypatch.setattr(settings.notifications, "mode", "standard")
    monkeypatch.setattr(settings.notifications.email, "enabled", True)
    monkeypatch.setattr(settings.notifications.email, "only_on_end", True)
    monkeypatch.setattr(settings.classification, "threshold", 0.8)

    await orchestrator.handle_notifications(
        event=event,
        classification=classification,
        snapshot_data=None,
        changed=False,
        was_inserted=False,
    )

    orchestrator._send_notification.assert_awaited_once()
    kwargs = orchestrator._send_notification.call_args.kwargs
    assert kwargs["channels"] == ["email"]
    orchestrator._mark_notified.assert_awaited_once_with(event.frigate_event)


@pytest.mark.asyncio
async def test_handle_notifications_does_not_send_email_on_end_in_silent_mode(monkeypatch):
    orchestrator = NotificationOrchestrator()
    event = _event("evt-email-silent")
    event.type = "end"
    classification = {
        "label": "Blue Tit",
        "score": 0.95,
        "audio_confirmed": False,
        "audio_species": None,
    }

    detection = SimpleNamespace(notified_at=datetime.now(timezone.utc))
    orchestrator._get_detection = AsyncMock(return_value=detection)  # type: ignore[method-assign]
    orchestrator._send_notification = AsyncMock(return_value=True)  # type: ignore[method-assign]
    orchestrator._mark_notified = AsyncMock()  # type: ignore[method-assign]

    monkeypatch.setattr(settings.notifications, "mode", "silent")
    monkeypatch.setattr(settings.notifications.email, "enabled", True)
    monkeypatch.setattr(settings.notifications.email, "only_on_end", True)
    monkeypatch.setattr(settings.classification, "threshold", 0.8)

    await orchestrator.handle_notifications(
        event=event,
        classification=classification,
        snapshot_data=None,
        changed=False,
        was_inserted=False,
    )

    orchestrator._send_notification.assert_not_awaited()
    orchestrator._mark_notified.assert_not_awaited()
