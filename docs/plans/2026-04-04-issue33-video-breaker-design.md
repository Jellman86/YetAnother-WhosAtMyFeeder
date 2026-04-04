# Issue 33 Video Breaker Hardening Design

## Goal
Prevent owner-triggered bulk video maintenance failures from opening the same circuit breaker that suppresses live auto-video classification, while improving timeout diagnostics enough to identify the real runtime cause.

## Recommended Approach
Treat queued video work as two sources:
- `live` for normal auto-video classification triggered from detections
- `maintenance` for owner-triggered bulk analysis

The queue stays shared, but breaker state becomes source-aware. Live failures continue to protect the live path. Maintenance failures open a separate maintenance breaker without poisoning live auto-video.

## Behavior
- Live auto-video jobs keep current behavior: inference failures like `video_timeout` count toward the live breaker.
- Maintenance jobs use a separate breaker and separate failure counters.
- `trigger_classification()` checks only the live breaker.
- `/maintenance/analyze-unknowns` queues maintenance jobs explicitly.
- Queue/diagnostics status exposes both circuit states.

## Diagnostics
Enrich `video_timeout` diagnostics with:
- job source
- timeout seconds
- clip byte size when known
- event camera
- classifier runtime/provider context when available

This keeps future bundles actionable even when the timeout root cause is still inside the classifier runtime.

## Non-Goals
- No MQTT changes.
- No taxonomy-repair changes.
- No new UI workflow.
- No attempt to solve the underlying classifier performance issue in this pass.
