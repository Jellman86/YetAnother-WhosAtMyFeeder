# Issue 22 Follow-Up Isolation And Health Design

**Date:** 2026-03-10

**Goal**
Close the remaining robustness gaps after the issue `#22` live-event pipeline fix by:
- fully isolating live MQTT snapshot classification from non-live image work, and
- making `/health` recovery-aware instead of permanently degraded after a single historical critical failure.

## Context

The March 7, 2026 issue-22 fix corrected the most important failure mode: live snapshot inference no longer releases logical capacity early when the outer await is cancelled or times out. That materially improves correctness under sustained load.

Two follow-up issues remain:

1. Live and non-live image classification still submit into the same executor, so cross-traffic can still delay live work even though admission accounting is now better.
2. Event-pipeline `critical_failures` is cumulative for the lifetime of the process, while `/health` treats any non-zero count as current degradation. That makes health sticky even after recovery.

## Requirements

### Functional
- Live Frigate MQTT snapshot classification must have real executor isolation from non-live image classification.
- Existing live overload semantics (`classify_snapshot_overloaded`) must be preserved.
- Existing cumulative diagnostics must remain available for soak analysis and issue investigation.
- `/health` must reflect current or recent event-pipeline health, not only startup-cumulative counters.

### Non-Functional
- Keep changes contained to backend classifier/event-pipeline/health code.
- Preserve current public diagnostics fields where possible.
- Add targeted regression tests for both follow-up fixes.

## Approaches Considered

### 1. Dedicated live executor plus recovery-aware health
- Add a dedicated live executor for live MQTT snapshot classification.
- Preserve separate live admission control and live inflight tracking.
- Keep cumulative counters, but add recovery-aware event-pipeline health fields for `/health`.

**Pros**
- Strongest correctness guarantee for issue `#22`.
- Cleanly separates live and non-live contention domains.
- Preserves observability while improving the meaning of top-level health.

**Cons**
- Slightly more code and one more executor to manage.

### 2. Shared executor with stricter admission/priority
- Keep one executor and try to improve fairness using semaphores/timeouts/priority policy.

**Pros**
- Smaller change.

**Cons**
- No hard isolation guarantee.
- Still vulnerable to queueing behind non-live work.

### 3. Keep current executor model, only improve health
- Accept current isolation gap and only fix sticky-degraded health.

**Pros**
- Minimal code churn.

**Cons**
- Leaves the main second-order correctness gap unresolved.

## Recommended Design

### Fix 1: Dedicated live image executor

Add `_live_image_executor` to `ClassifierService` and route `classify_async_live(...)` through that executor instead of the shared `_image_executor`.

Key rules:
- Live MQTT snapshot classification uses `_live_image_executor`.
- Non-live `classify_async(...)` continues to use `_image_executor`.
- Background image classification keeps using `_background_image_executor`.
- Live semaphore and inflight-future tracking stay in place to preserve overload shedding and accurate capacity accounting.

Expected outcome:
- Saturating non-live image classification can no longer starve admitted live MQTT image work.

### Fix 2: Recovery-aware event-pipeline health

Keep cumulative counters such as `critical_failures`, `stage_timeouts`, and `stage_failures` for diagnostics and soak delta analysis.

Add a separate current/recent health view to the event pipeline status, for example:
- a recovery-aware `status`,
- recent critical activity timestamp(s), and/or
- a bounded time-window indicator for current degradation.

Top-level `/health` should use the recovery-aware signal rather than raw cumulative `critical_failures > 0`.

Expected outcome:
- Historical failures remain visible for debugging.
- `/health` returns to `ok` after the pipeline has been healthy for a defined recovery window.

## Data Flow

### Live classification
1. MQTT event reaches `EventProcessor`.
2. `classify_async_live(...)` acquires live admission.
3. Live work is submitted to `_live_image_executor`.
4. Live inflight tracking holds the slot until the executor future actually finishes.
5. Overload still raises `LiveImageClassificationOverloadedError`.

### Health recovery
1. Event pipeline records critical stage failures/timeouts cumulatively.
2. Event pipeline also tracks the timestamp of the most recent critical failure.
3. `get_status()` reports both cumulative counters and a recovery-aware health signal.
4. `/health` uses that recovery-aware signal for top-level degraded vs ok.

## Error Handling

- If live executor submission fails, release the live semaphore immediately and propagate the error.
- If live classification overload occurs, continue dropping the individual event quickly with `classify_snapshot_overloaded`.
- If a critical event-pipeline failure occurs, keep the cumulative counter and timestamp, but allow health to return to `ok` after the recovery window expires.

## Testing Strategy

### Fix 1
- Add a failing regression test that saturates non-live image executor capacity and verifies `classify_async_live(...)` still completes promptly through the dedicated live executor.
- Keep existing live overload and inflight-release tests green.

### Fix 2
- Add a failing test showing cumulative critical failures remain non-zero while event-pipeline recovery-aware status returns to `ok` after the configured recovery window.
- Add a failing health test showing `/health` no longer stays degraded forever after a stale historical critical failure.

## Acceptance Criteria

- Live and non-live image classification are executor-isolated.
- Targeted backend tests pass for classifier, event processor, MQTT, health, and issue-22 soak harness behavior.
- Event-pipeline historical diagnostics remain intact.
- `/health` becomes recovery-aware without hiding recent or active critical failures.
