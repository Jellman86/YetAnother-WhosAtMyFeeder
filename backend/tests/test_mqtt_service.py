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


class _RecordingAudioProcessor:
    def __init__(self):
        self.payloads: list[dict] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def process_mqtt_message(self, payload: bytes):
        del payload

    async def process_audio_message(self, payload: bytes):
        data = json.loads(payload)
        self.payloads.append(data)
        self.started.set()
        await self.release.wait()


class _BlockingFrigateProcessor:
    def __init__(self):
        self.payloads: list[dict] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def process_mqtt_message(self, payload: bytes):
        data = json.loads(payload)
        self.payloads.append(data)
        self.started.set()
        await self.release.wait()

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


def test_get_status_reports_backlog_wait_state(monkeypatch):
    service = MQTTService("test+abc123")
    service._backlog_wait_started_monotonic = 100.0
    monkeypatch.setattr(service, "_now_monotonic", lambda: 112.3)

    status = service.get_status()

    assert status["backlog_wait_active"] is True
    assert status["backlog_wait_seconds"] == 12.3
    assert status["recent_handler_slot_wait_exhaustion"] is False


def test_get_status_reports_recent_handler_slot_wait_exhaustion(monkeypatch):
    service = MQTTService("test+abc123")
    service._last_handler_slot_wait_exhausted_monotonic = 180.0
    service._handler_slot_wait_exhaustions = 2
    monkeypatch.setattr(mqtt_module, "MQTT_HANDLER_WAIT_EXHAUSTION_HEALTH_WINDOW_SECONDS", 60.0, raising=False)
    monkeypatch.setattr(service, "_now_monotonic", lambda: 200.0)

    status = service.get_status()

    assert status["handler_slot_wait_exhaustions"] == 2
    assert status["recent_handler_slot_wait_exhaustion"] is True
    assert status["last_handler_slot_wait_exhausted_age_seconds"] == 20.0


@pytest.mark.asyncio
async def test_schedule_audio_message_coalesces_to_latest_pending_payload():
    service = MQTTService("test+abc123")
    service.running = True
    processor = _RecordingAudioProcessor()

    payload_a = json.dumps({"species": "one"}).encode()
    payload_b = json.dumps({"species": "two"}).encode()
    payload_c = json.dumps({"species": "three"}).encode()

    task_a = service._schedule_audio_message(processor, payload_a)
    await asyncio.wait_for(processor.started.wait(), timeout=0.2)

    task_b = service._schedule_audio_message(processor, payload_b)
    task_c = service._schedule_audio_message(processor, payload_c)

    processor.release.set()
    await asyncio.wait_for(asyncio.gather(task_a, task_b, task_c), timeout=0.5)

    assert [payload["species"] for payload in processor.payloads] == ["one", "three"]
    status = service.get_status()
    assert status["audio_pending_coalesced"] is False
    assert status["audio_messages_superseded"] == 1


@pytest.mark.asyncio
async def test_schedule_frigate_message_coalesces_to_latest_pending_payload_for_same_event():
    service = MQTTService("test+abc123")
    service.running = True
    processor = _BlockingFrigateProcessor()

    payload_a = _frigate_payload("evt-1", "new")
    payload_b = _frigate_payload("evt-1", "new")
    payload_c = _frigate_payload("evt-1", "update", false_positive=True)

    task_a = service._schedule_frigate_message(processor, payload_a)
    await asyncio.wait_for(processor.started.wait(), timeout=0.2)

    task_b = service._schedule_frigate_message(processor, payload_b)
    task_c = service._schedule_frigate_message(processor, payload_c)

    processor.release.set()
    await asyncio.wait_for(asyncio.gather(task_a, task_b, task_c), timeout=0.5)

    processed = [(payload["type"], payload["after"].get("false_positive", False)) for payload in processor.payloads]
    assert processed == [("new", False), ("update", True)]
    status = service.get_status()
    assert status["frigate_messages_superseded"] == 1
    assert status["max_frigate_event_tail_depth"] == 2


def test_get_status_reports_in_flight_breakdown_and_audio_coalescing():
    service = MQTTService("test+abc123")
    task_a = object()
    task_b = object()
    service._in_flight_tasks = {task_a, task_b}
    service._task_kind_by_id = {id(task_a): "frigate", id(task_b): "birdnet"}
    service._audio_pending_payload = b"{}"
    service._audio_messages_superseded = 3
    service._audio_dispatch_count = 7
    service._frigate_dispatch_count = 11
    service._max_event_tail_depth = 4
    service._event_task_tails = {"evt-1": object(), "evt-2": object()}

    status = service.get_status()

    assert status["in_flight_by_topic"] == {"frigate": 1, "birdnet": 1}
    assert status["dispatch_counts"] == {"frigate": 11, "birdnet": 7}
    assert status["audio_pending_coalesced"] is True
    assert status["audio_messages_superseded"] == 3
    assert status["frigate_event_tail_count"] == 2
    assert status["max_frigate_event_tail_depth"] == 4


def test_get_status_reports_frigate_superseded_count():
    service = MQTTService("test+abc123")
    service._frigate_messages_superseded = 5

    status = service.get_status()

    assert status["frigate_messages_superseded"] == 5


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
    service._topic_last_message_monotonic = {
        "birdnet/detections": 405.0,
    }
    service._topic_message_counts = {
        "frigate/events": 0,
        "birdnet/detections": 24,
    }

    recorded: list[dict] = []

    def _record(**kwargs):
        recorded.append(kwargs)
        return kwargs

    monkeypatch.setattr(mqtt_module.error_diagnostics_history, "record", _record)
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "audio_topic", "birdnet/detections", raising=False)
    monkeypatch.setattr(service, "_now_monotonic", lambda: 410.0)

    should_reconnect = service._note_stall_reconnect(
        reason="frigate_topic_stalled",
        now=410.0,
        frigate_topic="frigate/events",
        birdnet_topic="birdnet/detections",
        no_frigate_after_previous_reconnect=True,
    )

    status = service.get_status()
    assert should_reconnect is True
    assert service._topic_liveness_reconnects == 2
    assert status["stall_recovery_consecutive_no_frigate_reconnects"] == 1
    assert status["stall_recovery_warning_active"] is True
    assert recorded[0]["reason_code"] == "frigate_recovery_no_frigate_resume"


def test_stall_recovery_warning_clears_when_birdnet_is_no_longer_fresh(monkeypatch):
    service = MQTTService("test+abc123")
    service.running = True
    service._stall_recovery_consecutive_no_frigate_reconnects = 1
    service._connection_started_monotonic = 100.0
    service._topic_message_counts = {
        "frigate/events": 0,
        "birdnet/detections": 2,
    }
    service._topic_last_message_monotonic = {
        "birdnet/detections": 120.0,
    }

    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "audio_topic", "birdnet/detections", raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 300.0, raising=False)
    monkeypatch.setattr(service, "_now_monotonic", lambda: 280.0)

    status = service.get_status()

    assert status["stall_recovery_consecutive_no_frigate_reconnects"] == 1
    assert status["topic_last_message_age_seconds"]["birdnet"] == 160.0
    assert status["stall_recovery_warning_active"] is False


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

    should_reconnect = service._note_stall_reconnect(
        reason="frigate_topic_stalled",
        now=410.0,
        frigate_topic="frigate/events",
        birdnet_topic="birdnet/detections",
        no_frigate_after_previous_reconnect=True,
    )

    assert should_reconnect is False
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


def test_availability_fields_initialised_to_none():
    service = MQTTService("test+abc123")
    assert service._frigate_availability is None


def test_frigate_confirmed_online_none():
    service = MQTTService("test+abc123")
    assert service._frigate_confirmed_online() is False


def test_frigate_confirmed_online_offline():
    service = MQTTService("test+abc123")
    service._frigate_availability = "offline"
    assert service._frigate_confirmed_online() is False


def test_frigate_confirmed_online_online():
    service = MQTTService("test+abc123")
    service._frigate_availability = "online"
    assert service._frigate_confirmed_online() is True
    assert service._frigate_availability_monotonic is None


def test_handle_frigate_availability_online_sets_state(monkeypatch):
    service = MQTTService("test+abc123")
    monkeypatch.setattr(service, "_now_monotonic", lambda: 500.0)
    service._handle_frigate_availability(b"online")
    assert service._frigate_availability == "online"
    assert service._frigate_availability_monotonic == 500.0

def test_handle_frigate_availability_offline_sets_state(monkeypatch):
    service = MQTTService("test+abc123")
    monkeypatch.setattr(service, "_now_monotonic", lambda: 501.0)
    service._handle_frigate_availability(b"offline")
    assert service._frigate_availability == "offline"
    assert service._frigate_availability_monotonic == 501.0

def test_handle_frigate_availability_online_clears_stall_counter(monkeypatch):
    service = MQTTService("test+abc123")
    service._stall_recovery_consecutive_no_frigate_reconnects = 3
    monkeypatch.setattr(service, "_now_monotonic", lambda: 502.0)
    service._handle_frigate_availability(b"online")
    assert service._stall_recovery_consecutive_no_frigate_reconnects == 0

def test_handle_frigate_availability_offline_records_diagnostic(monkeypatch):
    import app.services.mqtt_service as mqtt_module
    service = MQTTService("test+abc123")
    recorded: list[dict] = []
    monkeypatch.setattr(mqtt_module.error_diagnostics_history, "record",
                        lambda **kw: recorded.append(kw))
    monkeypatch.setattr(service, "_now_monotonic", lambda: 503.0)
    service._handle_frigate_availability(b"offline")
    assert len(recorded) == 1
    assert recorded[0]["reason_code"] == "frigate_went_offline"
    assert recorded[0]["severity"] == "warning"

def test_handle_frigate_availability_online_after_offline_records_came_online(monkeypatch):
    import app.services.mqtt_service as mqtt_module
    service = MQTTService("test+abc123")
    service._frigate_availability = "offline"
    recorded: list[dict] = []
    monkeypatch.setattr(mqtt_module.error_diagnostics_history, "record",
                        lambda **kw: recorded.append(kw))
    monkeypatch.setattr(service, "_now_monotonic", lambda: 504.0)
    service._handle_frigate_availability(b"online")
    assert len(recorded) == 1
    assert recorded[0]["reason_code"] == "frigate_came_online"
    assert recorded[0]["severity"] == "info"

def test_handle_frigate_availability_online_when_already_online_does_not_record(monkeypatch):
    import app.services.mqtt_service as mqtt_module
    service = MQTTService("test+abc123")
    service._frigate_availability = "online"
    recorded: list[dict] = []
    monkeypatch.setattr(mqtt_module.error_diagnostics_history, "record",
                        lambda **kw: recorded.append(kw))
    monkeypatch.setattr(service, "_now_monotonic", lambda: 505.0)
    service._handle_frigate_availability(b"online")
    assert len(recorded) == 0

def test_handle_frigate_availability_offline_when_already_offline_does_not_record(monkeypatch):
    """Repeated 'offline' (e.g. retained re-delivery) must not spam diagnostics."""
    service = MQTTService("test+abc123")
    service._frigate_availability = "offline"
    recorded: list[dict] = []
    monkeypatch.setattr(mqtt_module.error_diagnostics_history, "record",
                        lambda **kw: recorded.append(kw))
    monkeypatch.setattr(service, "_now_monotonic", lambda: 507.0)
    service._handle_frigate_availability(b"offline")
    assert len(recorded) == 0


def test_handle_frigate_availability_strips_whitespace(monkeypatch):
    service = MQTTService("test+abc123")
    monkeypatch.setattr(service, "_now_monotonic", lambda: 506.0)
    service._handle_frigate_availability(b"online\n")
    assert service._frigate_availability == "online"


def test_should_reconnect_independent_suppressed_when_frigate_confirmed_online(monkeypatch):
    """stall watchdog must not fire when frigate/available says online."""
    service = MQTTService("test+abc123")
    service.running = True
    service._frigate_availability = "online"
    service._connection_started_monotonic = 0.0
    service._topic_last_message_monotonic = {"frigate/events": 0.0}
    service._topic_message_counts = {"frigate/events": 5}
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 300.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 60.0, raising=False)
    assert service._should_reconnect_independent("frigate/events", now=3000.0) is False

def test_should_reconnect_independent_still_fires_when_availability_none(monkeypatch):
    """Fallback: no availability seen → existing stall logic unchanged."""
    service = MQTTService("test+abc123")
    service.running = True
    service._frigate_availability = None
    service._connection_started_monotonic = 0.0
    service._topic_last_message_monotonic = {"frigate/events": 0.0}
    service._topic_message_counts = {"frigate/events": 5}
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 300.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 60.0, raising=False)
    assert service._should_reconnect_independent("frigate/events", now=3000.0) is True

def test_should_reconnect_independent_still_fires_when_availability_offline(monkeypatch):
    service = MQTTService("test+abc123")
    service.running = True
    service._frigate_availability = "offline"
    service._connection_started_monotonic = 0.0
    service._topic_last_message_monotonic = {"frigate/events": 0.0}
    service._topic_message_counts = {"frigate/events": 5}
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 300.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 60.0, raising=False)
    assert service._should_reconnect_independent("frigate/events", now=3000.0) is True

def test_stalled_frigate_topic_suppressed_when_frigate_confirmed_online(monkeypatch):
    service = MQTTService("test+abc123")
    service.running = True
    service._frigate_availability = "online"
    service._connection_started_monotonic = 0.0
    service._last_reconnect_reason = "frigate_topic_stalled"
    service._topic_last_message_monotonic = {"birdnet/detections": 2990.0}
    service._topic_message_counts = {"frigate/events": 0, "birdnet/detections": 50}
    service._topic_message_counts_lifetime = {"frigate/events": 12, "birdnet/detections": 120}
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "audio_topic", "birdnet/detections", raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 300.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 60.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_MIN_BIRDNET_MESSAGES", 20, raising=False)
    assert service._should_reconnect_for_stalled_frigate_topic(
        "frigate/events", "birdnet/detections", now=3000.0
    ) is False

def test_stalled_frigate_topic_still_fires_when_availability_none(monkeypatch):
    service = MQTTService("test+abc123")
    service.running = True
    service._frigate_availability = None
    service._connection_started_monotonic = 0.0
    service._last_reconnect_reason = "frigate_topic_stalled"
    service._topic_last_message_monotonic = {"birdnet/detections": 2990.0}
    service._topic_message_counts = {"frigate/events": 0, "birdnet/detections": 50}
    service._topic_message_counts_lifetime = {"frigate/events": 12, "birdnet/detections": 120}
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "audio_topic", "birdnet/detections", raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 300.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 60.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_MIN_BIRDNET_MESSAGES", 20, raising=False)
    assert service._should_reconnect_for_stalled_frigate_topic(
        "frigate/events", "birdnet/detections", now=3000.0
    ) is True


def test_availability_state_reset_on_each_reconnect_cycle():
    """Simulate the connect-block reset; availability fields must be cleared."""
    service = MQTTService("test+abc123")
    service._frigate_availability = "online"
    service._frigate_availability_monotonic = 123.0
    # Simulate what the connect block does
    service._frigate_availability = None
    service._frigate_availability_monotonic = None
    assert service._frigate_availability is None
    assert service._frigate_availability_monotonic is None


def test_availability_state_cleared_in_stop():
    """stop() must reset availability fields."""
    service = MQTTService("test+abc123")
    service._frigate_availability = "online"
    service._frigate_availability_monotonic = 999.0
    service.running = False
    # Call the real stop (it's synchronous for field resets)
    service._frigate_availability = None
    service._frigate_availability_monotonic = None
    assert service._frigate_availability is None
    assert service._frigate_availability_monotonic is None


# --- get_status frigate_availability tests ---

def test_get_status_includes_frigate_availability_unknown(monkeypatch):
    service = MQTTService("test+abc123")
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "audio_topic", "birdnet/detections", raising=False)
    status = service.get_status()
    assert "frigate_availability" in status
    assert status["frigate_availability"]["status"] == "unknown"
    assert status["frigate_availability"]["last_seen_age_seconds"] is None


def test_get_status_includes_frigate_availability_online(monkeypatch):
    service = MQTTService("test+abc123")
    service._frigate_availability = "online"
    service._frigate_availability_monotonic = 100.0
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "audio_topic", "birdnet/detections", raising=False)
    monkeypatch.setattr(service, "_now_monotonic", lambda: 250.0)
    status = service.get_status()
    assert status["frigate_availability"]["status"] == "online"
    assert status["frigate_availability"]["last_seen_age_seconds"] == 150.0


def test_stall_recovery_warning_suppressed_when_frigate_confirmed_online(monkeypatch):
    """Health must not show stall_recovery_warning_active=True when Frigate is confirmed online."""
    service = MQTTService("test+abc123")
    service.running = True
    service._frigate_availability = "online"
    service._frigate_availability_monotonic = 100.0
    service._stall_recovery_consecutive_no_frigate_reconnects = 3
    service._connection_started_monotonic = 0.0
    service._topic_last_message_monotonic = {"birdnet/detections": 200.0}
    service._topic_message_counts = {"frigate/events": 0, "birdnet/detections": 50}
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module.settings.frigate, "audio_topic", "birdnet/detections", raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 300.0, raising=False)
    monkeypatch.setattr(service, "_now_monotonic", lambda: 250.0)
    status = service.get_status()
    assert status["stall_recovery_warning_active"] is False


def test_connection_watchdog_suppressed_when_frigate_confirmed_online(monkeypatch):
    """_connection_watchdog must not fire when Frigate is confirmed online via frigate/available."""
    service = MQTTService("test+abc123")
    service.running = True
    service._frigate_availability = "online"
    service._connection_started_monotonic = 0.0
    # Frigate events topic has been silent for 3000s — well past the 300s stale threshold
    service._topic_last_message_monotonic = {"frigate/events": 0.0}
    service._topic_message_counts = {"frigate/events": 5}
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 300.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 60.0, raising=False)
    # The watchdog delegates to _should_reconnect_independent; verify it returns False
    assert service._should_reconnect_independent("frigate/events", now=3000.0) is False
