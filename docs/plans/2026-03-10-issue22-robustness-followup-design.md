# Issue 22 Robustness Follow-Up Design

**Date:** 2026-03-10

**Goal**
Address the remaining robustness concerns after the issue-22 follow-up implementation:
- explicitly manage classifier executor shutdown, and
- tighten recovery-aware event-pipeline health so it does not report `ok` while unresolved pipeline work still remains after a recent critical failure.

## Context

The current issue-22 follow-up already:
- isolates live MQTT snapshot classification onto a dedicated live executor, and
- makes `/health` recovery-aware rather than permanently degraded after one historical failure.

Two follow-up robustness concerns remain:
1. `ClassifierService` owns multiple thread pools but has no explicit shutdown path in application lifespan teardown.
2. Event-pipeline health can recover purely by elapsed time even if incomplete work remains after the critical period.

## Approaches Considered

### 1. Add classifier shutdown + degrade while incomplete work remains after critical failure
- Add `ClassifierService.shutdown()` and call it from app shutdown.
- Keep cumulative counters and recovery window, but require both:
  - no active recovery-window critical failure, and
  - no incomplete events after a critical failure
  before reporting event-pipeline `status: ok`.

**Pros**
- Minimal change with clear operational semantics.
- Closes the unmanaged thread-pool lifecycle gap.
- Makes `/health` less optimistic during partial recovery.

**Cons**
- `incomplete_events` remains a coarse signal rather than a direct task-state tracker.

### 2. Add shutdown only
- Fix thread-pool lifecycle and leave recovery semantics unchanged.

**Pros**
- Smallest change.

**Cons**
- Leaves the remaining health optimism issue unaddressed.

### 3. Add shutdown + more elaborate event aging/decay logic
- Track event ages or per-event recovery metadata before clearing degraded state.

**Pros**
- More nuanced health signal.

**Cons**
- More state and complexity than needed for this pass.

## Recommended Design

### Classifier lifecycle
- Add `shutdown()` to `ClassifierService`.
- Shut down `_image_executor`, `_live_image_executor`, `_background_image_executor`, and `_video_executor`.
- Call classifier shutdown from backend app lifespan teardown after other background services stop.

### Event-pipeline health tightening
- Preserve cumulative `critical_failures`.
- Preserve recovery window behavior via `last_critical_failure`.
- Add a derived condition that keeps pipeline status `degraded` if:
  - the critical failure window is still active, or
  - incomplete events remain and a critical failure has occurred since startup.

This keeps `/health` from returning to `ok` while the pipeline still appears to have unresolved work after a critical period.

## Testing Strategy

- Add a failing test proving `ClassifierService.shutdown()` shuts down all executors.
- Add a failing test proving event-pipeline `status` remains `degraded` when a historical critical failure exists and `incomplete_events > 0`, even after the pure time window has elapsed.
- Run the targeted backend regression subset after implementation.
