import pytest

from app.services.guest_history_signal import (
    PUBLIC_HISTORY_CHANGED,
    PUBLIC_HISTORY_NARROWED,
    guest_history_signal,
)


@pytest.mark.parametrize(
    "message",
    [
        {"type": "detection_deleted", "data": {"frigate_event": "e1", "timestamp": "2026-11-28T10:00:00Z"}},
        {"type": "detection_deleted"},
        {"type": "detection_deleted", "data": "not-a-dict"},
        {"type": "detection_updated", "data": {"frigate_event": "e1", "is_hidden": True}},
    ],
)
def test_a_delete_or_a_record_now_hidden_narrows_guest_history(message):
    assert guest_history_signal(message) == PUBLIC_HISTORY_NARROWED


@pytest.mark.parametrize(
    "message",
    [
        {"type": "detection", "data": {"frigate_event": "e1"}},
        {"type": "detection_updated", "data": {"frigate_event": "e1", "is_hidden": False}},
        {"type": "detection_updated", "data": {"frigate_event": "e1"}},
        {"type": "audio_history_changed"},
    ],
)
def test_a_capture_an_unhide_or_another_update_only_changes_guest_history(message):
    assert guest_history_signal(message) == PUBLIC_HISTORY_CHANGED


@pytest.mark.parametrize(
    "data",
    [None, "hidden", ["is_hidden"], {"is_hidden": 1}, {"is_hidden": "true"}, {"is_hidden": None}],
)
def test_malformed_update_data_falls_back_to_a_plain_change(data):
    assert guest_history_signal({"type": "detection_updated", "data": data}) == PUBLIC_HISTORY_CHANGED


@pytest.mark.parametrize(
    "message",
    [
        {"type": "settings_updated", "data": {"changed_fields": ["public_access.enabled"]}},
        {"type": "garden_history_changed"},
        {"type": "unknown_future_owner_message", "data": {"is_hidden": True}},
        {"type": None},
        {},
    ],
)
def test_messages_that_are_not_detection_history_have_no_history_signal(message):
    assert guest_history_signal(message) is None
