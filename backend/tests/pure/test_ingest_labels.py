"""Which Frigate labels YA-WAMF acts on is configuration, not a constant (#252).

Hard-coding `bird` had no good reason behind it: a custom Frigate model that
emits `duck` or `goose` as its own class saw those events silently dropped.
The owner now chooses the labels; the default stays `bird` alone, and labels
compare case-insensitively because Frigate models disagree about casing.
"""

import pytest

from app.config import settings
from app.utils.frigate import is_ingest_label, normalize_ingest_labels


def test_default_stays_bird_alone():
    from app.config_models import FrigateSettings

    fresh = FrigateSettings(frigate_url="http://frigate:5000")
    assert fresh.ingest_labels == ["bird"]


def test_labels_normalize_case_whitespace_and_duplicates():
    assert normalize_ingest_labels([" Bird ", "DUCK", "duck", "", None]) == ["bird", "duck"]
    # An empty configuration must not produce a dead instance.
    assert normalize_ingest_labels([]) == ["bird"]
    assert normalize_ingest_labels(None) == ["bird"]


def test_label_matching_is_case_insensitive():
    labels = ["bird", "duck"]
    assert is_ingest_label("Bird", labels)
    assert is_ingest_label("DUCK", labels)
    assert not is_ingest_label("cat", labels)
    assert not is_ingest_label("", labels)
    assert not is_ingest_label(None, labels)


@pytest.mark.asyncio
async def test_event_processor_admits_configured_labels(monkeypatch):
    from app.services.event_processor import EventProcessor

    monkeypatch.setattr(settings.frigate, "ingest_labels", ["bird", "duck"])
    monkeypatch.setattr(settings.frigate, "camera", ["cam1"])

    processor = EventProcessor.__new__(EventProcessor)

    class _Event:
        frigate_event = "evt_duck"
        label = "duck"
        type = "new"
        is_false_positive = False
        camera = "cam1"

    # The label gate is the first check; a configured non-default label must
    # pass it rather than returning None immediately.
    assert processor._passes_label_gate(_Event()) is True
    _Event.label = "cat"
    assert processor._passes_label_gate(_Event()) is False


def test_mqtt_fast_filter_honours_configured_labels(monkeypatch):
    from app.services.mqtt_service import MQTTService

    monkeypatch.setattr(settings.frigate, "ingest_labels", ["bird", "duck"])
    service = MQTTService.__new__(MQTTService)
    payload = b'{"type": "new", "after": {"id": "evt1", "label": "Duck", "false_positive": false}}'
    result = service._parse_frigate_payload_meta(payload)
    assert result is not None and result["should_process"] is True

    payload_cat = b'{"type": "new", "after": {"id": "evt2", "label": "cat", "false_positive": false}}'
    result = service._parse_frigate_payload_meta(payload_cat)
    assert result is not None and result["should_process"] is False
