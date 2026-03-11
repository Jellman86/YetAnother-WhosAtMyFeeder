# Issue 22 Classification Coordinator Hardening Design

**Date:** 2026-03-11

**Goal**
Replace the current loosely-coupled live/background image-classification admission paths with a single robust coordinator that:
- preserves live Frigate event processing under sustained pressure,
- reclaims wedged classification capacity without requiring a backend restart,
- reports the true failure mode in health and diagnostics,
- and keeps backfill job telemetry accurate when jobs are throttled, paused, or restarted.

## Problem Summary

Issue 22 is still reproducible on `dev` as of March 11, 2026. The latest reporter attachments show:
- MQTT ingress is still alive,
- `event_pipeline.last_completed` is stuck at detection `1773216928.362848-x1ffvu`,
- subsequent live events are repeatedly dropped,
- diagnostics bundles remain frozen across multiple exports,
- and the UI can show a misleading `Detection backfill running` state like `0/200`.

The current architecture has two core weaknesses:
1. Live classification capacity is bounded, but the service relies on executor completion callbacks plus outer timeouts rather than an authoritative admission/lease model.
2. Event processing and backfill telemetry are coupled to inferred state, so failure and recovery semantics can drift from reality.

## Root Causes And Failure Modes

### 1. Live work can become permanently unschedulable

`ClassifierService` currently exposes separate live and non-live executors with semaphore-based admission. This improves isolation, but it still treats the executor as the source of truth for lease completion. If executor work stalls or never calls back in a useful time window, the service can remain effectively unschedulable for live work until process restart.

### 2. Overload is masked as generic unavailability

`EventProcessor._classify_snapshot()` currently catches all exceptions and collapses them to `None`. This destroys the distinction between:
- live admission overload,
- genuine snapshot unavailability,
- and unexpected classifier failures.

That masking causes incorrect drop reasons and prevents diagnostics from telling the operator what actually failed.

### 3. Backfill progress can inherit stale totals

Backfill UI/job telemetry currently merges totals optimistically across polling and SSE updates. That makes the UI resilient to sparse progress payloads, but it also means a new job can briefly inherit an older job total, which matches the reporter’s `0/200` screenshot.

## Design Principles

- The coordinator state is authoritative; executor completion is advisory.
- Live ingress must be protected first. Background work is optional and should yield under pressure.
- Timeouts must reclaim scheduling capacity without allowing stale completions to mutate state later.
- Drop reasons, health, and exported diagnostics must distinguish overload, timeout, abandonment, and snapshot-fetch failures.
- Backfill UI must be job-scoped, never total-scoped across unrelated job IDs.

## Recommended Architecture

### A. Introduce a backend `ClassificationAdmissionCoordinator`

Create a dedicated service module to own image-classification admission and recovery.

Responsibilities:
- maintain separate bounded queues for `live` and `background` work,
- issue unique `work_id` and `lease_token` values,
- track queued, admitted, running, abandoned, completed, and rejected work,
- apply priority-aware scheduling so live work preempts background work,
- reclaim stale leases when work exceeds the configured deadline,
- ignore stale completions whose `lease_token` no longer matches the active lease,
- expose runtime metrics for health, diagnostics, and tests.

### B. Replace direct semaphore/executor admission with coordinator-driven submission

`ClassifierService` remains the owner of the underlying executors and model inference calls, but admission moves behind the coordinator.

The coordinator should accept:
- priority (`live` or `background`),
- task kind (`snapshot_classification`, with room for future extension),
- a callable for executor execution,
- queue timeout and lease deadline,
- and a discard callback or completion policy.

The coordinator decides when the callable is allowed to run and whether its eventual completion is still valid.

### C. Explicit stale-lease reclamation

The coordinator should periodically or opportunistically detect leases whose `deadline_at` has passed.

When that happens:
- mark the work item `abandoned`,
- increment reclaim counters,
- release capacity for newer work,
- leave the underlying executor thread alone if it cannot be interrupted safely,
- and ensure any later completion is dropped unless the active lease token still matches.

This keeps the service schedulable even when the ML/runtime layer is effectively hung.

### D. Background throttling and pause semantics

Background backfill classification should no longer compete implicitly with live work. Instead:
- live work gets reserved capacity,
- background work runs only when live pressure is below threshold,
- and backfill jobs can surface `running`, `throttled`, or `paused_by_live_pressure` semantics internally even if the existing API status remains `running` initially for compatibility.

This prevents backfill from making the live path more fragile and explains why a job appears stalled.

## Detailed Behavior

### Work lifecycle

Each request moves through:
- `queued`
- `admitted`
- `running`
- terminal state: `completed`, `rejected`, `timed_out`, `abandoned`, or `failed`

Each admitted request receives:
- `work_id`
- `lease_token`
- `priority`
- `queued_at`
- `admitted_at`
- `deadline_at`

### Completion validation

On executor completion:
- if the active record still has the same `lease_token`, accept the result,
- otherwise discard the result as stale and record a `late_completion_ignored` metric.

This blocks second-order corruption such as:
- duplicate DB writes,
- duplicate notifications,
- backfill counters advancing after reclamation,
- and stale event completions mutating the pipeline after recovery.

### Event-processor integration

`EventProcessor` should stop swallowing overload and timeout distinctions.

Expected outcomes:
- `live_overloaded` or `classify_snapshot_overloaded` when admission is rejected promptly,
- `classify_snapshot_timeout` when admitted live work exceeds its lease deadline,
- `classify_snapshot_failed` for genuine unexpected exceptions,
- `snapshot_unavailable` only when Frigate snapshot fetch actually fails or returns empty.

### Backfill integration

`BackfillService` should submit background classification through the same coordinator, but with:
- background priority,
- longer queue wait tolerance than live,
- and progress semantics derived from the backfill job’s own item counters rather than reused global totals.

If background work is paused due to live pressure, the backfill job should remain truthful:
- processed count stays where it is,
- total stays tied to that job ID only,
- message can indicate throttling/pressure,
- and UI should not imply active forward progress when none is occurring.

## Health, Diagnostics, And UI

### Backend health

Add coordinator metrics under ML/classifier health:
- live queued/running/completed/rejected/abandoned
- background queued/running/completed/rejected/abandoned
- stale lease reclaim count
- late completion ignored count
- oldest active live lease age
- oldest active background lease age
- live pressure state
- background throttled boolean

Top-level health should degrade when:
- stale lease reclamations are actively occurring beyond a small threshold,
- live queue admission timeouts are growing,
- or active live lease age exceeds a configured danger threshold.

### Diagnostics bundles

Diagnostics history should record coordinator-originated events distinctly, including:
- admission rejected,
- lease timed out,
- lease abandoned and reclaimed,
- late completion ignored,
- background throttled due to live pressure.

This allows support bundles to show whether the system is overloaded, wedged, recovering, or merely snapshot-starved.

### Frontend/backfill telemetry

Backfill totals should be keyed by `{kind, job_id}` rather than merged generically.

Rules:
- a new job starts with only its own known `total`,
- if `total` is unknown, UI shows an indeterminate state rather than inheriting an older number,
- terminal state closes only the matching job,
- throttled/paused messages should not be shown as `0/N` progress if no new units were actually processed.

## Second- And Third-Order Effects Considered

### Stale completion side effects

Without token validation, reclaimed executor work could still:
- save detections after the system has moved on,
- send notifications for stale work,
- or increment backfill counts after the slot was already recovered.

The lease-token guard is mandatory to prevent that.

### Thread accumulation

Coordinator reclamation does not magically stop a hard-hung underlying thread. Over time, abandoned executor threads can accumulate if the runtime is severely unhealthy.

Mitigations:
- track abandoned-running thread count,
- rotate the live executor when abandoned count crosses a threshold,
- and surface that state loudly in health/diagnostics.

### Background starvation

With strict live priority, backfill can starve under constant live load. That is acceptable operationally, but UI and diagnostics must say so explicitly. A stalled background queue is better than lost live detections.

### Retry storms

If the coordinator requeues too aggressively after reclaiming stale work, it can amplify pressure. The design should avoid automatic blind retries for live events and instead drop with a precise reason once bounded admission or lease time is exhausted.

### Health optimism

The current issue attachments show a backend that looks `ok` while making no useful progress. The new health rules must prefer truth over optimism: a backend reclaiming stale live leases repeatedly is degraded even if the HTTP process is still responsive.

## Testing Strategy

Add regression coverage for:
- live work lease timeout and reclaim without process restart,
- stale completion ignored after reclaim,
- overload reason propagation through `EventProcessor`,
- background throttling while live queue pressure exists,
- backfill job totals isolated by job ID,
- health payload including coordinator metrics,
- diagnostics history including reclaim/late-completion events,
- and soak-harness evaluation against reclaimed live pressure growth.

## Rollout Strategy

Implement behind internal defaults first, but keep the public API stable:
- same backfill endpoints,
- same event-processing entrypoints,
- richer health payloads,
- more precise diagnostics reasons.

If needed, queue sizes, lease deadlines, and reclaim thresholds can remain environment-configurable for soak testing.
