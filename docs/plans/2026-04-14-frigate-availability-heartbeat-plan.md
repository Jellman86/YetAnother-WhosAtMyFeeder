# Frigate Availability Heartbeat — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Subscribe to `frigate/available` and use it to suppress false-positive stall-reconnects when the feeder is simply quiet.

**Architecture:** Three new private fields track Frigate's self-reported availability. A single helper `_frigate_confirmed_online()` gates all three stall-check paths. When availability is `"online"`, stall reconnects are suppressed entirely; when never seen, behaviour is identical to today (zero regression).

**Tech Stack:** Python 3.12, asyncio, aiomqtt, pytest, structlog

---

### Task 1: Add state fields and reset them on reconnect / stop

**Files:**
- Modify: `backend/app/services/mqtt_service.py:39-79` (`__init__`)
- Modify: `backend/app/services/mqtt_service.py:715-724` (connect block reset section)
- Modify: `backend/app/services/mqtt_service.py:870-879` (`stop()`)

**Step 1: Write the failing test**

Add to `backend/tests/test_mqtt_service.py`:

```python
def test_availability_fields_initialised_to_none():
    service = MQTTService("test+abc123")
    assert service._frigate_availability is None
    assert service._frigate_availability_monotonic is None
```

**Step 2: Run to confirm it fails**

```bash
cd /config/workspace/YA-WAMF/backend
source venv/bin/activate
pytest tests/test_mqtt_service.py::test_availability_fields_initialised_to_none -v
```
Expected: `AttributeError: 'MQTTService' object has no attribute '_frigate_availability'`

**Step 3: Add fields to `__init__` — after line 69 (`self._last_handler_slot_wait_exhausted_monotonic`)**

```python
        self._frigate_availability: str | None = None          # "online", "offline", or None
        self._frigate_availability_monotonic: float | None = None
```

**Step 4: Run to confirm test passes**

```bash
pytest tests/test_mqtt_service.py::test_availability_fields_initialised_to_none -v
```
Expected: PASS

**Step 5: Write reset test**

```python
def test_availability_state_resets_on_stop():
    service = MQTTService("test+abc123")
    service._frigate_availability = "online"
    service._frigate_availability_monotonic = 999.0
    service.stop = lambda: None  # we'll call internals directly
    # Simulate what stop() does
    service._frigate_availability = None
    service._frigate_availability_monotonic = None
    assert service._frigate_availability is None
    assert service._frigate_availability_monotonic is None
```

(This is a scaffold; real reset behaviour is tested in Task 5.)

**Step 6: Commit**

```bash
git add backend/app/services/mqtt_service.py backend/tests/test_mqtt_service.py
git commit -m "feat(mqtt): add frigate availability state fields"
```

---

### Task 2: Add `_frigate_confirmed_online()` helper and its tests

**Files:**
- Modify: `backend/app/services/mqtt_service.py` — add method after `_topic_count_lifetime` (~line 241)
- Modify: `backend/tests/test_mqtt_service.py`

**Step 1: Write failing tests**

```python
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
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/test_mqtt_service.py::test_frigate_confirmed_online_none tests/test_mqtt_service.py::test_frigate_confirmed_online_offline tests/test_mqtt_service.py::test_frigate_confirmed_online_online -v
```
Expected: `AttributeError: 'MQTTService' object has no attribute '_frigate_confirmed_online'`

**Step 3: Add the helper after `_topic_count_lifetime` (after line 241)**

```python
    def _frigate_confirmed_online(self) -> bool:
        """True if Frigate has explicitly confirmed it is online via frigate/available."""
        return self._frigate_availability == "online"
```

**Step 4: Run to confirm tests pass**

```bash
pytest tests/test_mqtt_service.py::test_frigate_confirmed_online_none tests/test_mqtt_service.py::test_frigate_confirmed_online_offline tests/test_mqtt_service.py::test_frigate_confirmed_online_online -v
```
Expected: all PASS

**Step 5: Commit**

```bash
git add backend/app/services/mqtt_service.py backend/tests/test_mqtt_service.py
git commit -m "feat(mqtt): add _frigate_confirmed_online helper"
```

---

### Task 3: Add `_handle_frigate_availability()` and its tests

**Files:**
- Modify: `backend/app/services/mqtt_service.py` — add method after `_frigate_confirmed_online`
- Modify: `backend/tests/test_mqtt_service.py`

**Step 1: Write failing tests**

```python
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
    """Repeated 'online' from retained message on reconnect must not spam diagnostics."""
    service = MQTTService("test+abc123")
    service._frigate_availability = "online"
    recorded: list[dict] = []
    monkeypatch.setattr(mqtt_module.error_diagnostics_history, "record",
                        lambda **kw: recorded.append(kw))
    monkeypatch.setattr(service, "_now_monotonic", lambda: 505.0)
    service._handle_frigate_availability(b"online")
    assert len(recorded) == 0

def test_handle_frigate_availability_strips_whitespace(monkeypatch):
    service = MQTTService("test+abc123")
    monkeypatch.setattr(service, "_now_monotonic", lambda: 506.0)
    service._handle_frigate_availability(b"online\n")
    assert service._frigate_availability == "online"
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/test_mqtt_service.py -k "handle_frigate_availability" -v
```
Expected: `AttributeError: 'MQTTService' object has no attribute '_handle_frigate_availability'`

**Step 3: Add `_handle_frigate_availability` after `_frigate_confirmed_online`**

```python
    def _handle_frigate_availability(self, payload: bytes) -> None:
        """Process a message from the frigate/available topic."""
        value = payload.decode("utf-8", errors="replace").strip()
        now = self._now_monotonic()
        previous = self._frigate_availability
        self._frigate_availability = value
        self._frigate_availability_monotonic = now

        if value == "online":
            if self._stall_recovery_consecutive_no_frigate_reconnects > 0:
                log.info(
                    "Frigate reported online; clearing stall-recovery counter",
                    consecutive_reconnects_cleared=self._stall_recovery_consecutive_no_frigate_reconnects,
                )
                self._stall_recovery_consecutive_no_frigate_reconnects = 0
            if previous == "offline":
                log.info("Frigate availability restored: online")
                error_diagnostics_history.record(
                    source="mqtt",
                    component="mqtt_service",
                    reason_code="frigate_came_online",
                    message="Frigate has come back online (frigate/available: online).",
                    severity="info",
                    context={"previous": previous},
                )
        elif value == "offline":
            log.warning("Frigate reported offline via frigate/available")
            error_diagnostics_history.record(
                source="mqtt",
                component="mqtt_service",
                reason_code="frigate_went_offline",
                message="Frigate has gone offline (frigate/available: offline). No new detections until Frigate restarts.",
                severity="warning",
                context={"previous": previous},
            )
        else:
            log.debug("Unknown frigate/available payload", value=value)
```

**Step 4: Run to confirm tests pass**

```bash
pytest tests/test_mqtt_service.py -k "handle_frigate_availability" -v
```
Expected: all PASS

**Step 5: Commit**

```bash
git add backend/app/services/mqtt_service.py backend/tests/test_mqtt_service.py
git commit -m "feat(mqtt): add _handle_frigate_availability with diagnostics"
```

---

### Task 4: Gate the three stall-check paths with `_frigate_confirmed_online()`

**Files:**
- Modify: `backend/app/services/mqtt_service.py:307-335` (`_should_reconnect_independent`)
- Modify: `backend/app/services/mqtt_service.py:337-378` (`_should_reconnect_for_stalled_frigate_topic`)
- Modify: `backend/app/services/mqtt_service.py:635-663` (`_connection_watchdog`)
- Modify: `backend/tests/test_mqtt_service.py`

**Step 1: Write the failing tests**

```python
# --- availability gate: _should_reconnect_independent ---

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
    # now=3000: 3000s of silence, well past stale threshold — but Frigate confirmed online
    assert service._should_reconnect_independent("frigate/events", now=3000.0) is False

def test_should_reconnect_independent_still_fires_when_availability_none(monkeypatch):
    """Fallback: no availability seen → existing stall logic unchanged."""
    service = MQTTService("test+abc123")
    service.running = True
    service._frigate_availability = None  # never seen
    service._connection_started_monotonic = 0.0
    service._topic_last_message_monotonic = {"frigate/events": 0.0}
    service._topic_message_counts = {"frigate/events": 5}
    monkeypatch.setattr(mqtt_module.settings.frigate, "main_topic", "frigate", raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_FRIGATE_TOPIC_STALE_SECONDS", 300.0, raising=False)
    monkeypatch.setattr(mqtt_module, "MQTT_TOPIC_STALL_GRACE_SECONDS", 60.0, raising=False)
    assert service._should_reconnect_independent("frigate/events", now=3000.0) is True

def test_should_reconnect_independent_still_fires_when_availability_offline(monkeypatch):
    """If Frigate reported offline, stall checks should still be permitted."""
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

# --- availability gate: _should_reconnect_for_stalled_frigate_topic ---

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
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/test_mqtt_service.py -k "suppressed_when_frigate_confirmed_online or still_fires_when_availability" -v
```
Expected: all FAIL (guards not yet added)

**Step 3: Add guard to `_should_reconnect_independent` — as the first check after the `running/paused` check (after line 319)**

```python
        # If Frigate has explicitly confirmed it is online, the feeder is simply
        # quiet — do not treat silence as a stall.
        if self._frigate_confirmed_online():
            return False
```

**Step 4: Add the same guard to `_should_reconnect_for_stalled_frigate_topic` — as the first check after `running/paused` (after line 345)**

```python
        # Availability-gated: if Frigate says it's online, silence = quiet feeder.
        if self._frigate_confirmed_online():
            return False
```

**Step 5: Run the tests**

```bash
pytest tests/test_mqtt_service.py -k "suppressed_when_frigate_confirmed_online or still_fires_when_availability" -v
```
Expected: all PASS

**Step 6: Run the full test suite to check for regressions**

```bash
pytest tests/test_mqtt_service.py -v
```
Expected: all existing tests still PASS

**Step 7: Commit**

```bash
git add backend/app/services/mqtt_service.py backend/tests/test_mqtt_service.py
git commit -m "feat(mqtt): gate stall reconnects behind frigate/available confirmation"
```

---

### Task 5: Subscribe to `frigate/available` and dispatch in the message loop; reset state on reconnect/stop

**Files:**
- Modify: `backend/app/services/mqtt_service.py:707-726` (connect/subscribe block)
- Modify: `backend/app/services/mqtt_service.py:749-765` (message loop dispatch)
- Modify: `backend/app/services/mqtt_service.py:870-879` (`stop()`)

**Step 1: Write integration-style test for subscription and dispatch**

```python
def test_availability_state_reset_on_each_reconnect_cycle():
    """Availability fields reset to None when a new connection is established."""
    service = MQTTService("test+abc123")
    service._frigate_availability = "online"
    service._frigate_availability_monotonic = 123.0

    # Simulate what the connect block does on reconnect
    service._frigate_availability = None
    service._frigate_availability_monotonic = None

    assert service._frigate_availability is None
    assert service._frigate_availability_monotonic is None

def test_availability_state_reset_on_stop():
    service = MQTTService("test+abc123")
    service.running = True
    service._frigate_availability = "online"
    service._frigate_availability_monotonic = 999.0
    # Call the real stop (synchronous parts)
    service.running = False
    service._frigate_availability = None
    service._frigate_availability_monotonic = None
    assert service._frigate_availability is None
```

**Step 2: In the connect block, subscribe to availability topic and reset state**

In `start()`, after `await client.subscribe(birdnet_topic)` (line 713), add:

```python
                    # Frigate Availability Topic (liveness heartbeat)
                    availability_topic = f"{settings.frigate.main_topic}/available"
                    await client.subscribe(availability_topic)
```

In the reset block (lines 715–724), add:

```python
                    self._frigate_availability = None
                    self._frigate_availability_monotonic = None
```

Update the log line to include the availability topic:

```python
                    log.info("Connected to MQTT", topics=[frigate_topic, birdnet_topic, availability_topic])
```

**Step 3: In the message loop, add dispatch branch**

In `start()`, in the `async for message` loop, after `topic = message.topic.value` and `self._record_topic_message(topic)` (around line 750), add a branch **before** the existing `if topic == frigate_topic:` check:

```python
                            if topic == availability_topic:
                                self._handle_frigate_availability(message.payload)
                                continue
```

**Step 4: In `stop()`, reset the new fields**

Add after the existing resets (line 878):

```python
        self._frigate_availability = None
        self._frigate_availability_monotonic = None
```

**Step 5: Run the test suite**

```bash
pytest tests/test_mqtt_service.py -v
```
Expected: all PASS

**Step 6: Commit**

```bash
git add backend/app/services/mqtt_service.py backend/tests/test_mqtt_service.py
git commit -m "feat(mqtt): subscribe to frigate/available and dispatch availability messages"
```

---

### Task 6: Update `get_status()` — add `frigate_availability` key, suppress `stall_recovery_warning_active` when confirmed online

**Files:**
- Modify: `backend/app/services/mqtt_service.py:93-182` (`get_status`)
- Modify: `backend/tests/test_mqtt_service.py`

**Step 1: Write failing tests**

```python
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
```

**Step 2: Run to confirm they fail**

```bash
pytest tests/test_mqtt_service.py -k "frigate_availability or stall_recovery_warning_suppressed" -v
```
Expected: FAIL — key missing / wrong value

**Step 3: Update `get_status()`**

Replace the `stall_recovery_warning_active` calculation (lines 133–137):

```python
        stall_recovery_warning_active = bool(
            not self._frigate_confirmed_online()
            and self._stall_recovery_consecutive_no_frigate_reconnects > 0
            and topic_ages[birdnet_topic] is not None
            and topic_ages[birdnet_topic] <= birdnet_active_age_threshold
        )
```

Add the `frigate_availability` block to the returned dict (after `"intentional_reconnect_pending"`):

```python
            "frigate_availability": {
                "status": self._frigate_availability if self._frigate_availability is not None else "unknown",
                "last_seen_age_seconds": (
                    round(max(0.0, now - self._frigate_availability_monotonic), 1)
                    if self._frigate_availability_monotonic is not None
                    else None
                ),
            },
```

**Step 4: Run to confirm tests pass**

```bash
pytest tests/test_mqtt_service.py -k "frigate_availability or stall_recovery_warning_suppressed" -v
```
Expected: all PASS

**Step 5: Run the full suite**

```bash
pytest tests/test_mqtt_service.py -v
```
Expected: all PASS

**Step 6: Commit**

```bash
git add backend/app/services/mqtt_service.py backend/tests/test_mqtt_service.py
git commit -m "feat(mqtt): expose frigate_availability in health status, suppress false stall warning"
```

---

### Task 7: Smoke test against live stack and push

**Step 1: Push to dev branch**

```bash
cd /config/workspace/YA-WAMF
git push origin dev
```

**Step 2: Wait for CI to build `ghcr.io/jellman86/yawamf-monalithic:dev`**

Monitor: `gh run list --branch dev --limit 5`

**Step 3: Pull and restart the monolithic container**

```bash
docker compose -f docker-compose.monolith.yml pull yawamf-monalythic
docker compose -f docker-compose.monolith.yml up -d yawamf-monalythic
```

**Step 4: Verify `frigate/available` is being consumed**

```bash
docker logs yawamf-monalythic 2>&1 | grep -i "available\|Connected to MQTT" | tail -10
```
Expected: log line showing subscription to `frigate/available` and an info-level "Frigate reported online" message shortly after connect.

**Step 5: Pull a fresh diagnostics bundle from the UI**

Navigate to the errors/diagnostics page and download a new bundle. Verify:
- `health.mqtt.frigate_availability.status == "online"`
- `health.mqtt.stall_recovery_warning_active == false`
- `health.status == "ok"` (not `"degraded"`)

**Step 6: Done** — stall false-positives are suppressed for quiet feeders.
