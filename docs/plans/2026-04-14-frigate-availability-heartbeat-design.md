# Design: Frigate Availability-Gated Stall Watchdog

**Date:** 2026-04-14  
**Status:** Approved  
**Motivation:** The MQTT stall watchdog fires false positives when a feeder goes quiet for >30 minutes. Frigate publishes a retained `frigate/available` topic ("online"/"offline") that definitively distinguishes a quiet feeder from a broken connection. YA-WAMF does not currently subscribe to it.

## Problem

The stall watchdog in `mqtt_service.py` monitors `frigate/events` silence. After 1800s of no events, it reconnects. After 5 reconnects with continued silence it gives up, marks status `degraded`, and logs errors. When the feeder is genuinely quiet (no birds), this produces entirely false-positive errors and an incorrect degraded state.

Confirmed on 2026-04-14: user's Frigate instance (v0.17.1) publishes `frigate/available: "online"` as a retained MQTT message. The broker had the correct state the entire time the watchdog was misfiring.

## Approach: Availability-Gated Stall Checks (Option A)

Subscribe to `{main_topic}/available` as a passive liveness signal. Track its value. Gate all stall-reconnect paths: if availability is `"online"`, suppress the reconnect entirely. Fall through to existing logic only when availability has never been seen.

### Why This Is The Right Fix

- `frigate/available` is a retained message — YA-WAMF receives current state immediately on subscribe
- It has existed since Frigate v0.9.0 and cannot be selectively disabled; any user receiving `frigate/events` is also receiving `frigate/available`
- Zero regression: when `frigate/available` is never seen, all stall-check paths behave exactly as today
- Proactive on genuine failure: `"offline"` payload surfaces a diagnostic immediately rather than waiting 30 minutes

## New State

Three new private fields on `MQTTService`:

```python
_frigate_availability: str | None        # "online", "offline", or None (never seen)
_frigate_availability_monotonic: float | None  # monotonic time of last payload
_frigate_availability_topic: str         # "{main_topic}/available"
```

All three reset on every MQTT reconnect (same lifecycle as `_topic_message_counts`).

## Subscription Change

In the connect block, subscribe to `{main_topic}/available` alongside the existing two topics. The availability topic string is constructed once (`f"{settings.frigate.main_topic}/available"`) and stored on `self._frigate_availability_topic` at connect time so it is available in the message dispatcher.

## Message Dispatch

In the `async for message` loop, add a branch before the existing Frigate/BirdNET dispatch:

```python
if topic == self._frigate_availability_topic:
    self._handle_frigate_availability(topic, message.payload)
    continue
```

`_handle_frigate_availability`:
- Decodes payload as UTF-8, strips whitespace
- Stores value and monotonic timestamp
- **`"online"`**: clears `_stall_recovery_consecutive_no_frigate_reconnects`; logs at INFO
- **`"offline"`**: records `frigate_went_offline` diagnostic error at WARNING severity; logs at WARNING. Does NOT force a reconnect — the broker connection is alive, Frigate just stopped.
- Any other value: logs at DEBUG, stores value (forward-compatible)

## Stall Guard

New helper:

```python
def _frigate_confirmed_online(self) -> bool:
    """True if Frigate has explicitly confirmed it is online via frigate/available."""
    return self._frigate_availability == "online"
```

Applied as an early-return guard in all three stall-check paths:

1. **`_should_reconnect_independent`** — return `False` if `_frigate_confirmed_online()`
2. **`_should_reconnect_for_stalled_frigate_topic`** — return `False` if `_frigate_confirmed_online()`
3. **`_connection_watchdog`** — add guard before calling `_should_reconnect_independent`

When `_frigate_availability is None`, all paths fall through unchanged.

## Health / Diagnostics

`health()` dict gains a new `frigate_availability` key:

```python
"frigate_availability": {
    "status": "online" | "offline" | "unknown",  # unknown = never seen
    "last_seen_age_seconds": float | null,
}
```

`stall_recovery_warning_active` is suppressed (forced `False`) in the health output when `_frigate_confirmed_online()`. This prevents the system reporting `degraded` status when Frigate is confirmed alive and the feeder is merely quiet.

New diagnostic reason codes:
- `frigate_went_offline` — `frigate/available: "offline"` received
- `frigate_came_online` — `frigate/available: "online"` received after prior `"offline"` (info, not error)

## What Does Not Change

- All reconnect backoff logic
- The BirdNET-assisted stall path
- `MQTT_FRIGATE_TOPIC_STALE_SECONDS` (1800s default)
- `MQTT_MAX_CONSECUTIVE_NO_FRIGATE_RECONNECTS` (5)
- The independent watchdog timer interval
- Any existing diagnostic reason codes

These all remain as safety nets for the fallback (availability never seen) path.

## Test Cases

1. `_frigate_confirmed_online()` returns `False` when `_frigate_availability` is `None`
2. `_frigate_confirmed_online()` returns `True` when `_frigate_availability == "online"`
3. `_should_reconnect_independent` returns `False` when availability is `"online"`, even with stale Frigate topic
4. `_should_reconnect_for_stalled_frigate_topic` returns `False` when availability is `"online"`
5. Both stall checks still fire correctly when availability is `None` (regression test)
6. `"offline"` payload records diagnostic but does not trigger reconnect
7. `"online"` payload after `"offline"` clears stall counter and records info event
8. `stall_recovery_warning_active` is `False` in health when confirmed online
9. Health reports `frigate_availability.status == "unknown"` when topic never seen
10. State resets correctly on reconnect
