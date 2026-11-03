"""The audio correlation buffer stays bounded and cheap to maintain (#314).

The buffer holds up to a day of raw MQTT payloads. It used to rebuild the whole
deque on every append and rescan every entry to refuse a broker redelivery, so
a day of audio traffic meant billions of string operations of pure allocation
churn, and an entry that never expired was held forever.
"""

from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.services.audio import audio_service as audio_service_module
from app.services.audio.audio_service import AudioDetection, AudioService


def _service(hours: float = 24.0) -> AudioService:
    service = AudioService.__new__(AudioService)
    service._buffer = deque()
    service._buffered_source_ids = set()
    service._buffer_duration = timedelta(hours=hours)
    return service


def _detection(source_event_id: str | None, age_seconds: float = 0.0) -> AudioDetection:
    return AudioDetection(
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        species="Eurasian Wren",
        confidence=0.9,
        sensor_id="garden",
        raw_data={"detectionId": 1},
        source_event_id=source_event_id,
    )


def test_a_redelivered_message_is_refused():
    service = _service()

    assert service._append_to_buffer_once(_detection("garden:1")) is True
    assert service._append_to_buffer_once(_detection("garden:1")) is False
    assert len(service._buffer) == 1


def test_an_expired_entry_leaves_no_trace():
    """Expiry must release the identity too, or a day-old id blocks forever."""
    service = _service(hours=1.0)

    assert service._append_to_buffer_once(_detection("garden:1", age_seconds=7200)) is True
    assert service._append_to_buffer_once(_detection("garden:2")) is True

    assert len(service._buffer) == 1
    assert service._append_to_buffer_once(_detection("garden:1")) is True


def test_the_buffer_never_exceeds_its_backstop():
    """A payload storm must not grow the buffer without bound within the window."""
    service = _service()

    with patch.object(audio_service_module, "MAX_BUFFER_ENTRIES", 3):
        for index in range(5):
            service._append_to_buffer_once(_detection(f"garden:{index}"))

    assert len(service._buffer) == 3
    # The evicted identities are released with their entries.
    assert service._append_to_buffer_once(_detection("garden:0")) is True
