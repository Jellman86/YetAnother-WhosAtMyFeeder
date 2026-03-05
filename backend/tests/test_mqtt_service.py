import asyncio
import json

import pytest

import app.services.mqtt_service as mqtt_module
from app.services.mqtt_service import MQTTService


class _RecordingProcessor:
    def __init__(self):
        self.actions: list[str] = []
        self.active = 0
        self.max_active = 0
        self._lock = asyncio.Lock()

    async def process_mqtt_message(self, payload: bytes):
        data = json.loads(payload)
        async with self._lock:
            self.active += 1
            if self.active > self.max_active:
                self.max_active = self.active
        try:
            if data.get("type") == "new":
                await asyncio.sleep(0.05)
                self.actions.append("new")
            else:
                self.actions.append("fp")
        finally:
            async with self._lock:
                self.active -= 1

    async def process_audio_message(self, payload: bytes):
        del payload


class _SlowProcessor:
    async def process_mqtt_message(self, payload: bytes):
        del payload
        await asyncio.sleep(0.2)

    async def process_audio_message(self, payload: bytes):
        del payload
        await asyncio.sleep(0.2)


def _frigate_payload(event_id: str, event_type: str, false_positive: bool = False) -> bytes:
    return json.dumps(
        {
            "type": event_type,
            "after": {
                "id": event_id,
                "label": "bird",
                "camera": "cam1",
                "start_time": 1700000000,
                "false_positive": false_positive,
            },
        }
    ).encode()


@pytest.mark.asyncio
async def test_schedule_frigate_message_preserves_order_for_same_event_id():
    service = MQTTService("test+abc123")
    service.running = True
    processor = _RecordingProcessor()

    new_payload = _frigate_payload("evt-1", "new")
    fp_payload = _frigate_payload("evt-1", "update", false_positive=True)

    task_new = service._schedule_frigate_message(processor, new_payload)
    task_fp = service._schedule_frigate_message(processor, fp_payload)

    await asyncio.gather(task_new, task_fp)
    assert processor.actions == ["new", "fp"]


@pytest.mark.asyncio
async def test_schedule_frigate_message_allows_parallel_processing_for_different_event_ids():
    service = MQTTService("test+abc123")
    service.running = True
    processor = _RecordingProcessor()

    payload_a = _frigate_payload("evt-a", "new")
    payload_b = _frigate_payload("evt-b", "new")

    task_a = service._schedule_frigate_message(processor, payload_a)
    task_b = service._schedule_frigate_message(processor, payload_b)

    await asyncio.gather(task_a, task_b)
    assert processor.max_active >= 2


@pytest.mark.asyncio
async def test_dispatch_frigate_message_times_out_and_returns(monkeypatch):
    service = MQTTService("test+abc123")
    service.running = True
    processor = _SlowProcessor()
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_HANDLER_TIMEOUT_SECONDS", 0.01, raising=False)

    await asyncio.wait_for(
        service._dispatch_frigate_message(processor, _frigate_payload("evt-timeout", "new")),
        timeout=0.1,
    )


@pytest.mark.asyncio
async def test_parse_frigate_payload_meta_skips_non_actionable_updates():
    service = MQTTService("test+abc123")

    payload = _frigate_payload("evt-update", "update", false_positive=False)
    meta = service._parse_frigate_payload_meta(payload)

    assert meta is not None
    assert meta["event_id"] == "evt-update"
    assert meta["should_process"] is False


def test_get_status_reports_pressure_level_and_thresholds(monkeypatch):
    service = MQTTService("test+abc123")
    monkeypatch.setattr(mqtt_module, "MQTT_MAX_IN_FLIGHT_MESSAGES", 10, raising=False)
    service._in_flight_tasks = set(range(2))
    assert service.get_status()["pressure_level"] == "normal"
    assert service.is_under_pressure() is False

    service._in_flight_tasks = set(range(6))
    assert service.get_status()["pressure_level"] == "elevated"
    assert service.is_under_pressure(min_level="elevated") is True
    assert service.is_under_pressure(min_level="high") is False

    service._in_flight_tasks = set(range(8))
    assert service.get_status()["pressure_level"] == "high"
    assert service.is_under_pressure() is True

    service._in_flight_tasks = set(range(10))
    assert service.get_status()["pressure_level"] == "critical"


def test_should_reconnect_when_frigate_topic_is_stale_but_birdnet_is_active(monkeypatch):
    service = MQTTService("test+abc123")
    service.running = True

    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 30.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 120.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_MIN_BIRDNET_MESSAGES", 10, raising=False)

    service._connection_started_monotonic = 100.0
    service._topic_last_message_monotonic = {
        "frigate/events": 200.0,
        "birdnet/detections": 400.0,
    }
    service._topic_message_counts = {
        "frigate/events": 5,
        "birdnet/detections": 50,
    }

    should_reconnect = service._should_reconnect_for_stalled_frigate_topic(
        frigate_topic="frigate/events",
        birdnet_topic="birdnet/detections",
        now=400.0,
    )
    assert should_reconnect is True


def test_should_not_reconnect_without_prior_frigate_traffic(monkeypatch):
    service = MQTTService("test+abc123")
    service.running = True

    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 30.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 120.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_MIN_BIRDNET_MESSAGES", 10, raising=False)

    service._connection_started_monotonic = 100.0
    service._topic_last_message_monotonic = {
        "birdnet/detections": 400.0,
    }
    service._topic_message_counts = {
        "frigate/events": 0,
        "birdnet/detections": 50,
    }

    should_reconnect = service._should_reconnect_for_stalled_frigate_topic(
        frigate_topic="frigate/events",
        birdnet_topic="birdnet/detections",
        now=400.0,
    )
    assert should_reconnect is False
