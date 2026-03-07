# Issue 22 Event Pipeline Resilience Design

**Date:** 2026-03-07

**Goal**
Robustly prevent YA-WAMF from degrading into a state where Frigate MQTT events continue arriving but live event processing stops making forward progress, as reported in GitHub issue `#22`.

**Why**
Issue `#22` shows repeated `classify_snapshot` stage timeouts, growing `critical_failures`, and continued Frigate MQTT ingress. The current timeout-based guard drops the event after 30 seconds, but it does not guarantee that the underlying inference work has actually stopped. Under sustained load, timed-out live snapshot classifications can continue consuming executor capacity in the background and eventually starve fresh work.

## Summary
- Keep MQTT ingress alive even when live classification is overloaded.
- Bound live snapshot classification before work is admitted, not only after it times out.
- Add explicit overload shedding for live Frigate event classification.
- Preserve and improve diagnostics so overload is distinguishable from model/runtime failure.
- Treat any directly related resilience work as in scope if it closes the issue-22 failure mode.

## Root Cause
### Current behavior
1. `event_processor` wraps `classify_snapshot` in `asyncio.wait_for(..., 30s)`.
2. `classify_snapshot` calls `classifier.classify_async(...)`.
3. `classify_async` runs inference through `run_in_executor(...)`.
4. If the outer stage times out, the awaiting coroutine is cancelled, but the executor thread is not forcefully stopped.
5. The semaphore guarding image inference is released as soon as the await unwinds, even if the worker thread is still busy.
6. New live events are admitted while older timed-out inference work may still be running in the background.

### Why this fails under load
- Timeout does not equal cancellation for executor-backed inference.
- Capacity accounting becomes optimistic and can drift from reality.
- The system keeps admitting work that it cannot actually complete promptly.
- After enough slow or stuck inference tasks accumulate, live event completion can collapse while MQTT traffic still appears healthy.

## Approaches Considered
### 1. Increase timeouts and tune concurrency
- Smallest change.
- Does not fix hidden post-timeout work.
- Risks masking the problem until the next heavier burst.

### 2. Add bounded live admission and overload shedding
- Recommended.
- Fixes the immediate issue by refusing new live classification work when the system cannot safely admit it.
- Keeps MQTT/event processing responsive and recoverable.
- Requires moderate but contained backend changes.

### 3. Move live classification to a separate worker process/service
- Strongest isolation.
- Larger architectural change than necessary for first remediation.
- Good future option if bounded admission still proves insufficient.

## Recommended Architecture
### Core idea
Introduce a dedicated live image-classification admission path that only accepts work when real bounded capacity is available. If capacity is not available quickly, YA-WAMF should fail fast for that event with an explicit overload reason instead of enqueueing more hidden work.

### Design rules
- Live Frigate event classification must be capacity-bounded.
- Admission timeout must be short and intentional.
- Once a live task is admitted, the system should consider that slot occupied until the executor future actually finishes.
- Timeouts after admission are still recorded, but they must not immediately make the system think capacity is free.
- Overload should degrade individual events, not the whole MQTT ingestion path.

## Components
### Classifier service
Add a live-classification execution path with explicit in-flight future tracking.

Responsibilities:
- short admission timeout for live requests
- accurate accounting of admitted futures until they complete
- optional live overload status/counters
- structured outcome reasons such as `admission_timeout` and `inference_timeout`

### Event processor
Change the live classification stage to distinguish:
- admission refused / overloaded
- inference timed out after admission
- genuine classifier failure
- empty classifier result

It should drop the event with a specific reason when live capacity is unavailable, and record diagnostics with reason codes that reflect overload vs stage timeout.

### MQTT service
Preserve current protections and topic-liveness logic, but ensure diagnostics can correlate MQTT health with event-pipeline overload.

The MQTT layer should not try to “fix” inference overload by itself. Its job is to continue ingesting safely and expose pressure signals.

### Diagnostics and health
Expose enough detail for issue-22 style debugging:
- live image admission timeouts
- live image in-flight count
- stage timeouts
- event drop reasons split between overload and downstream failure

## Data Flow
1. Frigate MQTT event arrives.
2. MQTT service schedules live event handling.
3. Event processor validates event and attempts live classification admission.
4. If admission cannot be obtained within a short timeout:
   - drop the event with a dedicated overload reason
   - record diagnostics
   - return quickly
5. If admission succeeds:
   - keep the slot occupied until the executor future actually completes
   - await the classification result under the live stage timeout
6. If inference completes in time:
   - continue normal filtering, context gathering, save, and notify flow
7. If inference exceeds the stage timeout:
   - record timeout/degraded status
   - do not pretend capacity is free until the admitted future actually finishes

## Failure Semantics
### Overload
- New reason code: `classify_snapshot_overloaded`
- Severity: warning or error, but distinct from stage failure
- Expected behavior: some events are shed, but the system remains responsive and recovers automatically

### Timeout after admission
- Existing timeout concept remains valid
- Severity: error
- Indicates admitted work exceeded the allowed latency budget

### Classifier failure
- Keep separate from overload and timeout
- Indicates model/runtime error rather than pressure

## Testing Strategy
### Unit tests
- Live admission refuses quickly when capacity is exhausted.
- Timed-out live inference does not immediately release logical capacity.
- Capacity is released when the executor future actually completes.
- Event processor records `classify_snapshot_overloaded` distinctly from `classify_snapshot_unavailable`.
- Health/diagnostic status reflects admission timeouts and live in-flight work.

### Soak/regression tests
- Extend issue-22 soak evaluation to fail if critical failures grow or if admitted work stops completing while MQTT ingress continues.
- Add a targeted stress test using a fake slow classifier to verify the pipeline sheds load instead of wedging.

### Non-goals
- Hard-killing Python executor threads
- Rewriting live inference into a separate service in this pass
- Solving unrelated backfill behavior unless it shares the exact same admission bug
