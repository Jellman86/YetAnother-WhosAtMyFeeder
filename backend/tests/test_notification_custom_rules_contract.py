"""What the notification triggers really do, as Settings and docs/features/notifications.md say it.

The custom-rule switches in Settings → Notifications are worded from these facts. If one of them
changes, the copy (`settings.notifications.custom_rules.*`) and the doc change with it.
"""

import pytest

from app.config import settings
from app.services.notification_orchestrator import NotificationOrchestrator


@pytest.fixture
def rules():
    notifications = settings.notifications
    original = (notifications.notify_on_insert, notifications.notify_on_update)

    def set_rules(*, on_insert: bool, on_update: bool) -> NotificationOrchestrator:
        notifications.notify_on_insert = on_insert
        notifications.notify_on_update = on_update
        return NotificationOrchestrator()

    yield set_rules
    notifications.notify_on_insert, notifications.notify_on_update = original


def _sends(
    orchestrator: NotificationOrchestrator, mode: str, event_type: str, *, inserted: bool, notified: bool
) -> bool:
    should_notify, _ = orchestrator._should_notify(
        event_type=event_type, notify_mode=mode, changed=True, was_inserted=inserted, already_notified=notified
    )
    return should_notify


def test_custom_rules_send_at_most_one_alert_per_visit(rules):
    orchestrator = rules(on_insert=True, on_update=True)
    assert _sends(orchestrator, "custom", "new", inserted=True, notified=False)
    # Once a visit has had its alert, no later event sends another, whatever the switches say.
    for event_type in ("new", "update", "end"):
        assert not _sends(orchestrator, "custom", event_type, inserted=False, notified=True)


def test_custom_on_insert_sends_when_the_visit_starts(rules):
    assert _sends(rules(on_insert=True, on_update=False), "custom", "new", inserted=True, notified=False)
    assert not _sends(rules(on_insert=False, on_update=False), "custom", "new", inserted=True, notified=False)


def test_custom_on_update_sends_the_one_alert_later_only_when_none_has_gone(rules):
    orchestrator = rules(on_insert=False, on_update=True)
    assert _sends(orchestrator, "custom", "update", inserted=False, notified=False)
    assert _sends(orchestrator, "custom", "end", inserted=False, notified=False)
    assert not _sends(orchestrator, "custom", "update", inserted=False, notified=True)
    # Without it, a visit that had no alert at the start never gets one.
    assert not _sends(rules(on_insert=True, on_update=False), "custom", "update", inserted=False, notified=False)


@pytest.mark.parametrize("mode", ["standard", "final", "realtime", "silent"])
def test_a_preset_ignores_the_insert_and_update_switches(rules, mode):
    events = [
        (event_type, inserted, notified)
        for event_type in ("new", "update", "end")
        for inserted in (True, False)
        for notified in (True, False)
    ]

    def decisions(on_insert: bool, on_update: bool) -> list[bool]:
        orchestrator = rules(on_insert=on_insert, on_update=on_update)
        return [_sends(orchestrator, mode, e, inserted=i, notified=n) for e, i, n in events]

    assert decisions(True, True) == decisions(False, False)


def test_only_every_update_repeats_an_alert_for_one_visit(rules):
    orchestrator = rules(on_insert=True, on_update=True)
    assert _sends(orchestrator, "realtime", "update", inserted=False, notified=True)
    for mode in ("standard", "final", "custom"):
        assert not _sends(orchestrator, mode, "update", inserted=False, notified=True)


def test_custom_start_switch_matches_only_new_events_unlike_standard_recovery(rules):
    orchestrator = rules(on_insert=True, on_update=False)
    # Standard treats an update event that first inserted a visit as a start; custom checks event_type == "new".
    assert _sends(orchestrator, "standard", "update", inserted=True, notified=False)
    assert not _sends(orchestrator, "custom", "update", inserted=True, notified=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "event_type", "delay_setting", "expected_delayed"),
    [
        ("standard", "new", True, True),
        ("standard", "new", False, False),
        ("realtime", "new", True, True),
        ("realtime", "new", False, False),
        ("final", "end", False, True),
        ("custom", "new", True, True),
        ("custom", "new", False, False),
    ],
)
async def test_delay_until_video_behavior_by_mode(monkeypatch, mode, event_type, delay_setting, expected_delayed):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from app.services import notification_orchestrator as orchestrator_module

    monkeypatch.setattr(settings.notifications, "mode", mode)
    monkeypatch.setattr(settings.notifications, "notify_on_insert", True)
    monkeypatch.setattr(settings.notifications, "notify_on_update", False)
    monkeypatch.setattr(settings.notifications, "delay_until_video", delay_setting)
    monkeypatch.setattr(settings.classification, "auto_video_classification", True)
    monkeypatch.setattr(settings.classification, "threshold", 0.5)

    orchestrator = NotificationOrchestrator()
    monkeypatch.setattr(orchestrator, "_get_detection", AsyncMock(return_value=None))
    sent = AsyncMock()
    monkeypatch.setattr(orchestrator, "_send_and_mark_notified", sent)
    scheduled: list[str] = []

    def fake_create_background_task(coro, *, name: str):
        scheduled.append(name)
        coro.close()

    monkeypatch.setattr(orchestrator_module, "create_background_task", fake_create_background_task)

    event = SimpleNamespace(type=event_type, frigate_event="evt-delay-contract")
    classification = {"label": "Robin", "score": 0.9, "audio_confirmed": False, "audio_species": None}
    await orchestrator.handle_notifications(event, classification, b"img", changed=True, was_inserted=True)

    if expected_delayed:
        assert scheduled == ["notify_after_video:evt-delay-contract"]
        sent.assert_not_awaited()
    else:
        assert scheduled == []
        sent.assert_awaited_once()
