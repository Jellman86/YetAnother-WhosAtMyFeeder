# Issue 22 Subprocess Classifier Supervisor Design

## Problem

The current issue `#22` hardening work fixed scheduler-level recovery, observability, and truthful failure reporting. It still leaves one serious class of failure only partially addressed: native inference runtimes can hang inside a worker thread and cannot be forcefully terminated from inside the Python backend process.

That means the system can now:
- abandon stale work,
- free logical capacity,
- continue serving new live work,
- tell the truth in health/diagnostics,

but it still cannot fully recover the compute boundary itself when ONNX/OpenVINO/TFLite wedge inside native code. Over time, repeated hangs can accumulate dead compute and memory pressure until restart.

## Goals

- Replace in-process image classification execution with supervised subprocess workers.
- Preserve the current admission semantics:
  - live priority first,
  - background throttled under live pressure,
  - stale completions ignored.
- Add actual runtime-level healing:
  - missed heartbeat -> kill worker -> replace worker,
  - hard deadline breach -> kill worker -> replace worker,
  - worker crash -> replace worker.
- Add restart budgets and circuit breakers so repeated crashes do not cause restart storms.
- Add live-event coalescing and stale-event shedding ahead of admission to reduce load.
- Keep health, diagnostics, and backfill UX aligned with the new failure modes.

## Non-Goals

- Splitting the classifier into a separate deployed service/container.
- Reworking unrelated auto-video classification architecture in the same pass.
- Changing model selection logic or accuracy behavior.

## Proposed Architecture

### 1. Main-process supervisor

Introduce a `ClassifierSupervisor` in the backend process. It owns:
- the live/background worker pools,
- worker generation IDs,
- rolling restart counters,
- per-worker heartbeat timestamps,
- in-flight work assignment bookkeeping,
- worker exit reasons and replacement policy,
- circuit breaker state per pool.

The existing `ClassificationAdmissionCoordinator` remains the admission authority. It should stay responsible for queueing, lease deadlines, reclaim semantics, and late-completion rejection. The supervisor becomes the execution backend for admitted work.

### 2. Dedicated classifier worker subprocesses

Create a worker module launched as a subprocess. Each worker:
- initializes the configured model/runtime in its own process,
- accepts classification requests over IPC,
- sends heartbeats while idle and while work is executing,
- returns results or structured errors only,
- never writes DB state or sends notifications directly.

This isolates native inference faults to the worker process boundary.

### 3. Pool separation

Maintain separate pools:
- `live` pool: reserved for MQTT snapshot classification,
- `background` pool: used for backfill/manual classification.

Background workers are throttled before live workers. If live pressure or recovery instability is active, background work is paused rather than consuming classifier capacity.

### 4. Coalescing and stale shedding

Before admission for live work:
- coalesce duplicate requests for the same effective snapshot identity,
- drop events older than a freshness threshold,
- track counts for coalesced and stale-dropped live work.

This reduces queue churn during bursts and lowers the probability of saturation-driven recovery.

## IPC Model

Use a simple framed JSON protocol over subprocess stdin/stdout, with base64 payloads for image bytes if needed. Messages should include:
- `worker_generation`
- `request_id`
- `work_id`
- `lease_token`
- `kind`
- `sent_at`

Worker-to-parent messages:
- `heartbeat`
- `ready`
- `result`
- `error`
- `fatal`

Parent-to-worker messages:
- `classify`
- `shutdown`

The parent remains authoritative. Worker responses are accepted only if:
- the worker generation still matches,
- the `work_id` and `lease_token` still match the active assignment,
- the work has not already been abandoned/rejected.

## Failure Policy

### Worker misses heartbeat

If a worker heartbeat exceeds a configured threshold:
- mark any assigned work abandoned,
- kill the worker process,
- record `worker_heartbeat_timeout`,
- replace the worker if restart budget allows.

### Worker exceeds hard deadline

If a worker has an active assignment past a hard execution deadline:
- mark work abandoned,
- kill worker,
- record `worker_deadline_kill`,
- replace if restart budget allows.

### Worker exits unexpectedly

On crash/non-zero exit:
- classify exit reason,
- abandon assigned work,
- increment rolling restart counters,
- restart worker unless the circuit breaker opens.

### Circuit breaker

Each pool gets a rolling restart window and failure threshold.

If the threshold is exceeded:
- open the circuit for that pool,
- live requests fail fast with `classify_snapshot_circuit_open`,
- background work pauses with an explicit paused/recovering message,
- health becomes degraded with cooldown visibility.

## Health And Diagnostics

Expose at least:
- worker pool sizes and busy counts,
- max heartbeat age,
- rolling restarts in window,
- breaker state and cooldown remaining,
- last worker exit reason,
- worker generation IDs,
- live coalesced count,
- stale-live drops count,
- existing abandoned and late-ignored counts.

Diagnostics exports should include supervisor and worker pool state in a dedicated section so issue reporters can prove whether recovery happened and whether it is stable.

## Backward Compatibility / Rollout

Ship behind a config flag:
- `in_process` mode: current coordinator + thread execution,
- `subprocess` mode: coordinator + supervisor workers.

Start with `in_process` default while tests and soak runs harden the subprocess path. Once stable, flip the default to `subprocess`.

## Testing Strategy

### Unit / component tests

- worker protocol encode/decode
- supervisor worker spawn / ready handshake
- heartbeat timeout kills worker and replaces it
- deadline breach kills worker and replaces it
- stale worker result after restart is ignored
- restart storm opens breaker
- breaker cooldown allows recovery
- coalescing merges duplicate live requests
- stale-live events are dropped before admission

### Integration tests

- live classification recovers after worker hang without backend restart
- background work pauses while live pool is recovering
- health and diagnostics surface worker crash / timeout / breaker state
- backfill UI shows paused/recovering instead of fake progress

### Fault injection

Add test worker behaviors:
- sleep forever,
- stop heartbeating,
- exit abruptly,
- return after parent already killed/restarted generation.

## Risks

### Startup overhead

Workers will pay model-load overhead at spawn time. Mitigation:
- eager startup at app boot,
- bounded pool sizes,
- visible warmup state in health.

### IPC payload cost

Image transfer across process boundaries is more expensive than thread execution. Mitigation:
- keep payloads minimal,
- use compressed bytes when possible,
- reserve subprocess mode for classification only, not broad data fan-out.

### Restart storms

Without breaker logic, a bad runtime build could churn endlessly. Mitigation:
- rolling restart budget,
- breaker cooldown,
- explicit degraded status.

### Complexity

This is materially more complex than thread execution. Mitigation:
- keep the admission coordinator authoritative,
- keep worker protocol narrow,
- test each failure mode explicitly before switching defaults.
