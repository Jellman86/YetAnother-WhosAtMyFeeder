import asyncio
import json
from unittest.mock import patch

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


class _OverloadedProcessor:
    def __init__(self):
        self.calls = 0

    async def process_mqtt_message(self, payload: bytes):
        del payload
        self.calls += 1
        raise RuntimeError("classify_snapshot_overloaded")

    async def process_audio_message(self, payload: bytes):
        del payload


class _ExplodingProcessor:
    async def process_mqtt_message(self, payload: bytes):
        del payload
        raise RuntimeError("boom")

    async def process_audio_message(self, payload: bytes):
        del payload
        raise RuntimeError("boom-audio")


class _DummyMessage:
    def __init__(self, topic: str, payload: bytes):
        self.topic = type("Topic", (), {"value": topic})()
        self.payload = payload


class _FakeMessages:
    def __init__(self, messages):
        self._messages = list(messages)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._messages):
            raise StopAsyncIteration
        value = self._messages[self._index]
        self._index += 1
        return value


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
async def test_dispatch_frigate_message_logs_unexpected_failure():
    service = MQTTService("test+abc123")
    service.running = True

    with patch("app.services.mqtt_service.log") as mock_log:
        await service._dispatch_frigate_message(_ExplodingProcessor(), _frigate_payload("evt-fail", "new"))

    mock_log.error.assert_any_call(
        "Frigate MQTT handler failed",
        event_id="evt-fail",
        error="boom",
    )


@pytest.mark.asyncio
async def test_dispatch_frigate_message_returns_promptly_on_overload():
    service = MQTTService("test+abc123")
    service.running = True
    processor = _OverloadedProcessor()

    await asyncio.wait_for(
        service._dispatch_frigate_message(processor, _frigate_payload("evt-overload", "new")),
        timeout=0.1,
    )

    assert processor.calls == 1


@pytest.mark.asyncio
async def test_parse_frigate_payload_meta_skips_non_actionable_updates():
    service = MQTTService("test+abc123")

    payload = _frigate_payload("evt-update", "update", false_positive=False)
    meta = service._parse_frigate_payload_meta(payload)

    assert meta is not None
    assert meta["event_id"] == "evt-update"
    assert meta["should_process"] is False


@pytest.mark.asyncio
async def test_parse_frigate_payload_meta_processes_end_events():
    service = MQTTService("test+abc123")

    payload = _frigate_payload("evt-end", "end", false_positive=False)
    meta = service._parse_frigate_payload_meta(payload)

    assert meta is not None
    assert meta["event_id"] == "evt-end"
    assert meta["should_process"] is True


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


def test_should_reconnect_when_birdnet_stays_active_after_stall_reconnect(monkeypatch):
    service = MQTTService("test+abc123")
    service.running = True

    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 30.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 120.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_MIN_BIRDNET_MESSAGES", 10, raising=False)

    service._connection_started_monotonic = 100.0
    service._last_reconnect_reason = "frigate_topic_stalled_watchdog"
    service._topic_last_message_monotonic = {
        "birdnet/detections": 400.0,
    }
    service._topic_message_counts = {
        "frigate/events": 0,
        "birdnet/detections": 50,
    }
    service._topic_message_counts_lifetime = {
        "frigate/events": 12,
        "birdnet/detections": 120,
    }

    should_reconnect = service._should_reconnect_for_stalled_frigate_topic(
        frigate_topic="frigate/events",
        birdnet_topic="birdnet/detections",
        now=400.0,
    )
    assert should_reconnect is True


def test_repeated_post_reconnect_no_frigate_sets_warning_and_records_diagnostic(monkeypatch):
    service = MQTTService("test+abc123")
    service.running = True
    service._topic_liveness_reconnects = 1
    service._last_reconnect_reason = "frigate_topic_stalled"
    service._topic_message_counts = {
        "frigate/events": 0,
        "birdnet/detections": 24,
    }

    recorded: list[dict] = []

    def _record(**kwargs):
        recorded.append(kwargs)
        return kwargs

    monkeypatch.setattr(mqtt_module.error_diagnostics_history, "record", _record)

    service._note_stall_reconnect(
        reason="frigate_topic_stalled",
        now=410.0,
        frigate_topic="frigate/events",
        birdnet_topic="birdnet/detections",
        no_frigate_after_previous_reconnect=True,
    )

    status = service.get_status()
    assert service._topic_liveness_reconnects == 2
    assert status["stall_recovery_consecutive_no_frigate_reconnects"] == 1
    assert status["stall_recovery_warning_active"] is True
    assert recorded[0]["reason_code"] == "frigate_recovery_no_frigate_resume"


def test_first_frigate_message_after_reconnect_warning_resets_counter(monkeypatch):
    service = MQTTService("test+abc123")
    service._stall_recovery_consecutive_no_frigate_reconnects = 2
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)

    service._record_topic_message("frigate/events", now=123.0)

    assert service._stall_recovery_consecutive_no_frigate_reconnects == 0


# --- _should_reconnect_independent tests ---


def test_should_reconnect_independent_when_frigate_stalled_no_birdnet(monkeypatch):
    """Watchdog fires on a stalled Frigate topic even with zero BirdNET traffic."""
    service = MQTTService("test+abc123")
    service.running = True

    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 30.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 120.0, raising=False)

    service._connection_started_monotonic = 100.0
    service._topic_last_message_monotonic = {"frigate/events": 200.0}
    service._topic_message_counts = {"frigate/events": 5, "birdnet/detections": 0}

    # now=400, last frigate message at 200 → 200s silence > 120s threshold
    assert service._should_reconnect_independent("frigate/events", now=400.0) is True


def test_should_not_reconnect_independent_before_grace_period(monkeypatch):
    """Watchdog respects the grace period after initial connection."""
    service = MQTTService("test+abc123")
    service.running = True

    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 60.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 120.0, raising=False)

    service._connection_started_monotonic = 350.0
    service._topic_last_message_monotonic = {"frigate/events": 200.0}
    service._topic_message_counts = {"frigate/events": 5}

    # now=400, connection started at 350 → only 50s uptime < 60s grace
    assert service._should_reconnect_independent("frigate/events", now=400.0) is False


def test_should_not_reconnect_independent_when_no_prior_frigate_traffic(monkeypatch):
    """Watchdog does not fire when Frigate has never sent a message this session."""
    service = MQTTService("test+abc123")
    service.running = True

    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 30.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 120.0, raising=False)

    service._connection_started_monotonic = 100.0
    service._topic_last_message_monotonic = {}
    service._topic_message_counts = {"frigate/events": 0}

    assert service._should_reconnect_independent("frigate/events", now=400.0) is False


def test_should_not_reconnect_independent_when_frigate_recently_active(monkeypatch):
    """Watchdog does not fire when the Frigate topic is still within the stale window."""
    service = MQTTService("test+abc123")
    service.running = True

    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 30.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 120.0, raising=False)

    service._connection_started_monotonic = 100.0
    service._topic_last_message_monotonic = {"frigate/events": 350.0}
    service._topic_message_counts = {"frigate/events": 10}

    # now=400, last frigate message at 350 → only 50s silence < 120s threshold
    assert service._should_reconnect_independent("frigate/events", now=400.0) is False


def test_should_not_reconnect_independent_when_paused(monkeypatch):
    """Watchdog does not fire while the service is paused."""
    service = MQTTService("test+abc123")
    service.running = True
    service.paused = True

    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 30.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 120.0, raising=False)

    service._connection_started_monotonic = 100.0
    service._topic_last_message_monotonic = {"frigate/events": 200.0}
    service._topic_message_counts = {"frigate/events": 5}

    assert service._should_reconnect_independent("frigate/events", now=400.0) is False


@pytest.mark.asyncio
async def test_wait_for_handler_slot_breaks_after_max_wait(monkeypatch):
    """_wait_for_handler_slot exits after MAX_HANDLER_WAIT_SECONDS even if tasks never drain."""
    service = MQTTService("test+abc123")
    service.running = True

    # Use a tiny max-wait so the test doesn't actually block for 120 s
    monkeypatch.setattr(mqtt_module, "MAX_HANDLER_WAIT_SECONDS", 0.05, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_MAX_IN_FLIGHT_MESSAGES", 1, raising=False)

    # Plant a never-completing task so the slot is always full
    async def _hang():
        await asyncio.sleep(60)

    hanging = asyncio.ensure_future(_hang())
    service._in_flight_tasks = {hanging}

    try:
        # Should return promptly (well under 1 s) rather than blocking forever
        await asyncio.wait_for(service._wait_for_handler_slot(), timeout=1.0)
    finally:
        hanging.cancel()
        with __import__("contextlib").suppress(asyncio.CancelledError):
            await hanging


@pytest.mark.asyncio
async def test_start_clears_intentional_reconnect_after_clean_reconnect_cycle(monkeypatch):
    service = MQTTService("test+abc123")
    processor = _RecordingProcessor()
    connect_count = 0

    class _FakeClient:
        def __init__(self, **kwargs):
            del kwargs
            nonlocal connect_count
            connect_count += 1
            if connect_count == 1:
                self.messages = _FakeMessages([_DummyMessage("birdnet", b'{"species":"Robin","confidence":0.8}')])
            else:
                service.running = False
                self.messages = _FakeMessages([])

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def subscribe(self, topic):
            del topic

        async def disconnect(self):
            return None

    async def _idle_watchdog(client, frigate_topic):
        del client, frigate_topic
        await asyncio.sleep(3600)

    monkeypatch.setattr(mqtt_module.settings.frigate, "mqtt_server", "mosquitto", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "mqtt_port", 1883, raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "audio_topic", "birdnet", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "mqtt_auth", False, raising=False)
    monkeypatch.setattr(mqtt_module, "Client", _FakeClient)
    monkeypatch.setattr(service, "_connection_watchdog", _idle_watchdog)

    service._intentional_reconnect = True
    await asyncio.wait_for(service.start(processor), timeout=1.0)

    assert connect_count >= 2
    assert service._intentional_reconnect is False


def test_stall_recovery_stops_reconnecting_at_cap(monkeypatch):
    """After MQTT_MAX_CONSECUTIVE_NO_FRIGATE_RECONNECTS the assisted stall path must stop triggering."""
    monkeypatch.setattr(mqtt_module, "MQTT_MAX_CONSECUTIVE_NO_FRIGATE_RECONNECTS", 3, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 30.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 120.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_MIN_BIRDNET_MESSAGES", 5, raising=False)

    service = MQTTService("test+abc123")
    service.running = True
    service._connection_started_monotonic = 100.0
    service._topic_last_message_monotonic = {
        "frigate/events": 100.0,
        "birdnet/detections": 390.0,
    }
    service._topic_message_counts = {
        "frigate/events": 0,
        "birdnet/detections": 25,
    }
    service._topic_message_counts_lifetime = {
        "frigate/events": 10,
        "birdnet/detections": 200,
    }
    service._last_reconnect_reason = "frigate_topic_stalled"

    # Under the cap — should still reconnect.
    service._stall_recovery_consecutive_no_frigate_reconnects = 2
    assert service._should_reconnect_for_stalled_frigate_topic(
        frigate_topic="frigate/events",
        birdnet_topic="birdnet/detections",
        now=400.0,
    ) is True

    # At the cap — should stop.
    service._stall_recovery_consecutive_no_frigate_reconnects = 3
    assert service._should_reconnect_for_stalled_frigate_topic(
        frigate_topic="frigate/events",
        birdnet_topic="birdnet/detections",
        now=400.0,
    ) is False


def test_note_stall_reconnect_records_abandoned_diagnostic_at_cap(monkeypatch):
    """When the reconnect cap is reached, the diagnostic must use the abandoned reason code."""
    monkeypatch.setattr(mqtt_module, "MQTT_MAX_CONSECUTIVE_NO_FRIGATE_RECONNECTS", 2, raising=False)

    service = MQTTService("test+abc123")
    service.running = True
    service._connection_started_monotonic = 100.0
    service._topic_message_counts = {
        "frigate/events": 0,
        "birdnet/detections": 30,
    }
    service._stall_recovery_consecutive_no_frigate_reconnects = 1

    recorded: list[dict] = []
    monkeypatch.setattr(mqtt_module.error_diagnostics_history, "record", lambda **kw: recorded.append(kw))

    service._note_stall_reconnect(
        reason="frigate_topic_stalled",
        now=410.0,
        frigate_topic="frigate/events",
        birdnet_topic="birdnet/detections",
        no_frigate_after_previous_reconnect=True,
    )

    assert service._stall_recovery_consecutive_no_frigate_reconnects == 2
    assert recorded[-1]["reason_code"] == "frigate_recovery_abandoned"
    assert recorded[-1]["context"]["recovery_abandoned"] is True


@pytest.mark.asyncio
async def test_start_clears_intentional_reconnect_on_mqtt_error_path(monkeypatch):
    """When MqttError is raised with _intentional_reconnect set, the flag is cleared and no backoff applied."""
    from aiomqtt import MqttError

    service = MQTTService("test+abc123")
    processor = _RecordingProcessor()
    connect_count = 0

    class _ErrorClient:
        def __init__(self, **kwargs):
            del kwargs
            nonlocal connect_count
            connect_count += 1

        async def __aenter__(self):
            if connect_count == 1:
                # Simulate the watchdog setting the flag right before MqttError
                service._intentional_reconnect = True
                raise MqttError("connection lost")
            # Second connection: stop the loop.
            service.running = False
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def subscribe(self, topic):
            del topic

        @property
        def messages(self):
            return _FakeMessages([])

    async def _idle_watchdog(client, frigate_topic):
        del client, frigate_topic
        await asyncio.sleep(3600)

    monkeypatch.setattr(mqtt_module.settings.frigate, "mqtt_server", "mosquitto", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "mqtt_port", 1883, raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "audio_topic", "birdnet", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "mqtt_auth", False, raising=False)
    monkeypatch.setattr(mqtt_module, "Client", _ErrorClient)
    monkeypatch.setattr(service, "_connection_watchdog", _idle_watchdog)

    await asyncio.wait_for(service.start(processor), timeout=2.0)

    assert connect_count >= 2
    assert service._intentional_reconnect is False
    # Backoff should not have been applied (reconnect_delay stays at initial).
    assert service.reconnect_delay == mqtt_module.INITIAL_BACKOFF
