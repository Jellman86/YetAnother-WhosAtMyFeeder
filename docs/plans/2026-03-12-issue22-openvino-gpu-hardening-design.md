# Issue 22 OpenVINO GPU Hardening Design

## Goal

Harden YA-WAMF's bird-classification runtime so Intel GPU / OpenVINO failures degrade predictably, recover automatically, and report truthful health without silently wedging live detections, backfill, or video analysis.

## Problem Summary

Issue #22 and subsequent live debugging exposed a broader class of problems than a single queue stall:

- live snapshot inference could wedge or degrade behind native runtime instability
- the main backend and supervised workers both loaded bird models, increasing cold-start cost and runtime pressure
- worker replacement failures could threaten the supervision loop itself
- status/diagnostics mixed main-process and worker-process truth
- `/api/classifier/status` re-probed OpenVINO on demand, turning observability into extra runtime churn
- video, live snapshots, and background snapshots still shared too much inference machinery

The result was a system that had the beginnings of self-healing, but not a fully coherent or resource-defensible runtime boundary.

## Requirements

### Functional

- Bird inference must run behind supervised workers in subprocess mode.
- Live, background, and video bird inference must be isolated enough that slow or unstable video work cannot poison live snapshot latency.
- Runtime invalid output must trigger bounded fallback behavior and surface the actual recovery state.
- Health and diagnostics must reflect the worker-derived runtime truth, not stale or unrelated main-process state.

### Robustness

- Worker startup/replacement failures must never kill the watchdog loop.
- Repeated startup/runtime failures must trip a circuit breaker instead of causing unbounded churn.
- Capability probing must be bounded and cached.
- The system must avoid avoidable duplicate model residency and parallel GPU cold-start spikes.

### Operational

- Existing owner/debug workflows must still work, but through the supervised boundary.
- Failure reasons must stay explicit across live detections, backfill, health, and diagnostics.

## Approaches Considered

### 1. Supervised-only bird inference

Move all bird inference behind worker subprocesses and make the main process an orchestrator only.

Pros:

- one runtime boundary
- lower duplicate GPU/CPU model residency
- clear health semantics
- strongest self-healing story

Cons:

- larger refactor
- sync/debug/video paths need routing through supervised workers

### 2. Hybrid model

Keep main-process bird inference for sync/debug/video but force it to CPU, while live/background remain supervised.

Pros:

- smaller diff
- easier migration

Cons:

- still two inference paths
- duplicated lifecycle/state
- weaker guarantees

### 3. Patch current architecture

Keep split inference ownership and only harden supervisor replacement and telemetry.

Pros:

- minimal changes

Cons:

- does not remove the core architectural ambiguity
- keeps duplicate model residency
- keeps higher startup/runtime pressure

## Decision

Adopt approach 1: supervised-only bird inference.

This is the only option that makes the OpenVINO/GPU path coherent. The main backend should not behave like both a controller and an inference runtime for the same bird model under the same deployment mode.

## Architecture

### Main process

The main backend process owns:

- admission control and priority separation
- worker pool supervision
- restart budgeting and circuit breaking
- health/status aggregation
- request/result validation
- static capability diagnostics

The main process does not own an actively loaded bird inference runtime in subprocess mode.

### Worker processes

Worker subprocesses own:

- bird model loading
- OpenVINO / ONNX Runtime / TFLite fallback behavior
- actual image/video bird inference
- heartbeat emission
- structured lifecycle and runtime recovery events

Workers are treated as untrusted execution boundaries. Their results are accepted only when they still own the active assignment token.

### Pools

Bird inference is separated into supervised pools:

- `live`: latency-sensitive MQTT snapshot classification
- `background`: backfill/manual snapshot classification
- `video`: long-running clip classification
- `debug`: owner-triggered explicit test/debug calls, routed through a non-live supervised path

`video` must not share the same worker pool or deadline budget as `live`.

## Data Flow

### Live/background snapshot flow

1. Caller requests bird inference with a priority.
2. Admission chooses a worker slot in the corresponding pool.
3. Supervisor assigns a `work_id`, `request_id`, worker generation, and lease token.
4. Worker performs inference and may emit:
   - `ready`
   - `heartbeat`
   - `runtime_recovery`
   - `result`
   - `error`
5. Supervisor accepts only the result that still matches the active assignment token.
6. If heartbeat or deadline is missed, the worker is killed and replaced, and the request fails with an explicit reason.

### Video flow

Video classification is routed through the dedicated `video` supervised pool. Snapshot traffic never waits on video worker availability or video deadlines.

### Debug/test flow

Sync owner/debug bird-classification endpoints route through a supervised non-live path instead of calling the bird model directly inside the backend process.

## Failure Handling

### Worker startup failure

- Must not kill the watchdog
- Must record stderr and structured reason
- Must increment restart budget
- Must open the pool circuit if the restart threshold is exceeded
- Must leave the service responsive and diagnosable

### Heartbeat/deadline failure

- Kill the worker
- Fail the active request with an explicit worker-timeout/deadline reason
- Spawn replacement if the circuit budget allows

### Invalid runtime output

- Worker attempts local fallback chain in order:
  - OpenVINO GPU -> OpenVINO CPU
  - OpenVINO CPU -> ONNX Runtime CPU
  - ONNX Runtime CPU -> TFLite
- Worker emits structured `runtime_recovery` details when fallback succeeds
- If fallback fails, worker returns a structured terminal failure and the supervisor records it in health/status

### Circuit breaker

If startup/runtime failures exceed the configured restart budget:

- open the affected pool circuit
- shed live work explicitly
- pause/deprioritize background work
- surface cooldown and reason in health and diagnostics

## Health And Diagnostics

### Capability probing

OpenVINO/device capability probes should be cached with a TTL. Status endpoints must not trigger expensive subprocess probes on every request.

### Authoritative runtime state

In subprocess mode, health/status for bird inference should come from:

- worker pool metrics
- latest worker runtime-recovery events
- cached capability probe state

It should not rely on a separate main-process bird model state.

### Reported fields

Health/diagnostics should distinguish:

- startup failures
- heartbeat timeouts
- hard-deadline kills
- invalid-output recoveries
- invalid-output recovery failures
- circuit-open state
- restart counts and cooldown window
- worker stderr excerpts

## Second- And Third-Order Effects

### Reduced duplicate model residency

By removing eager main-process bird model loading in subprocess mode, the system reduces:

- GPU/CPU memory pressure
- cold-start compile duplication
- cross-process OpenVINO plugin churn

### Controlled startup behavior

Initial worker warm-up should be serialized or staged so the system does not hammer the GPU/plugin with parallel compile requests at boot.

### Truthful observability

Caching capability probes prevents the settings UI and diagnostics from creating extra OpenVINO load just by being viewed.

### Safer failure semantics

Worker replacement failure being non-fatal to the watchdog prevents the self-healing mechanism from collapsing during the very failure mode it exists to recover from.

## Rollout Plan

1. Harden supervisor replacement and worker lifecycle reporting.
2. Remove eager main-process bird model ownership in subprocess mode.
3. Introduce dedicated supervised video/debug routing.
4. Cache capability probes and switch health/status to worker-authoritative runtime reporting.
5. Verify with targeted fault-injection and live validation on Intel GPU / OpenVINO.

## Testing Strategy

Add failing tests first for:

- replacement failure does not kill the watchdog
- subprocess mode does not eagerly load the main bird model
- worker runtime recovery is visible in health/status
- `/api/classifier/status` does not reprobe OpenVINO every call
- video uses a distinct supervised pool and cannot block live snapshot capacity
- startup failure / circuit-open states surface correct reasons

Then run widened backend verification for supervisor, classifier service, health, event processor, backfill, and video paths.
