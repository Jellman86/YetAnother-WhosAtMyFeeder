# Issue 22 OpenVINO GPU Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make bird inference in subprocess mode fully supervised and resource-defensible, with robust worker recovery, truthful OpenVINO/GPU telemetry, and isolated live/background/video behavior.

**Architecture:** In subprocess mode, the main backend becomes an orchestrator for bird inference instead of a second inference runtime. Bird classification and video classification run through supervised worker pools that emit authoritative runtime-recovery state, while the main process caches capability probes and exposes health/status from supervisor state rather than mixed main-process model state.

**Tech Stack:** FastAPI, asyncio subprocess workers, OpenVINO, ONNX Runtime, TFLite, pytest, Svelte UI status consumers

---

### Task 1: Make Worker Replacement Failure Non-Fatal

**Files:**
- Modify: `backend/app/services/classifier_supervisor.py`
- Test: `backend/tests/test_classifier_supervisor.py`

**Step 1: Write the failing test**

Add a test in `backend/tests/test_classifier_supervisor.py` that:
- creates a supervisor with a fake worker
- simulates a worker deadline/heartbeat replacement
- makes `_spawn_worker()` fail on replacement
- verifies the watchdog logic does not die and the pool transitions into explicit degraded/circuit-open metrics instead of crashing

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest backend/tests/test_classifier_supervisor.py -k replacement_failure -v
```

Expected:
- FAIL because replacement failure currently propagates out of `_replace_worker()`

**Step 3: Write minimal implementation**

In `backend/app/services/classifier_supervisor.py`:
- catch replacement-start failures inside `_replace_worker()`
- preserve the assignment failure to the caller
- record explicit replacement/startup failure metrics and stderr
- keep the watchdog alive
- open the circuit when restart budget is exceeded instead of leaving the pool half-replaced

**Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest backend/tests/test_classifier_supervisor.py -k replacement_failure -v
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add backend/app/services/classifier_supervisor.py backend/tests/test_classifier_supervisor.py
git commit -m "fix(issue22): keep classifier watchdog alive on replacement failure"
```

### Task 2: Stop Eager Main-Process Bird Model Loading In Subprocess Mode

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/routers/classifier.py`
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_classifier_status_api.py`

**Step 1: Write the failing test**

Add tests that verify:
- when `image_execution_mode=subprocess`, constructing `ClassifierService` does not eagerly load the bird model in the main process
- sync bird test/debug endpoints no longer require direct main-process bird-model access

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest backend/tests/test_classifier_service.py -k subprocess_eager_load -v
python -m pytest backend/tests/test_classifier_status_api.py -k subprocess_status -v
```

Expected:
- FAIL because `ClassifierService.__init__()` currently always calls `_init_bird_model()`

**Step 3: Write minimal implementation**

In `backend/app/services/classifier_service.py`:
- skip eager bird-model initialization in subprocess mode
- keep only the state needed for capability diagnostics and supervisor orchestration
- ensure non-bird models still load correctly where needed

In `backend/app/routers/classifier.py`:
- route owner bird test/debug operations through supervised inference or explicit subprocess-safe status paths
- remove direct assumptions that the main process owns a live bird interpreter/session

**Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest backend/tests/test_classifier_service.py -k subprocess_eager_load -v
python -m pytest backend/tests/test_classifier_status_api.py -k subprocess_status -v
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add backend/app/services/classifier_service.py backend/app/routers/classifier.py backend/tests/test_classifier_service.py backend/tests/test_classifier_status_api.py
git commit -m "refactor(issue22): remove eager bird model load in subprocess mode"
```

### Task 3: Add Structured Worker Runtime-Recovery Telemetry

**Files:**
- Modify: `backend/app/services/classifier_worker_protocol.py`
- Modify: `backend/app/services/classifier_worker_process.py`
- Modify: `backend/app/services/classifier_worker_client.py`
- Modify: `backend/app/services/classifier_supervisor.py`
- Test: `backend/tests/test_classifier_worker_protocol.py`
- Test: `backend/tests/test_classifier_worker_process.py`
- Test: `backend/tests/test_classifier_worker_client.py`
- Test: `backend/tests/test_classifier_supervisor.py`

**Step 1: Write the failing tests**

Add tests covering:
- worker emits a structured `runtime_recovery` event when invalid OpenVINO output falls back to another backend/provider
- client preserves that event
- supervisor records latest runtime recovery per pool

**Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest backend/tests/test_classifier_worker_protocol.py -k runtime_recovery -v
python -m pytest backend/tests/test_classifier_worker_process.py -k runtime_recovery -v
python -m pytest backend/tests/test_classifier_worker_client.py -k runtime_recovery -v
python -m pytest backend/tests/test_classifier_supervisor.py -k runtime_recovery -v
```

Expected:
- FAIL because runtime recovery is currently only local worker state and not part of the protocol

**Step 3: Write minimal implementation**

Update the worker protocol to support a bounded `runtime_recovery` event carrying:
- failed backend/provider
- recovered backend/provider
- recovery status
- detail
- timestamp

Update worker process/client/supervisor to:
- emit the event after successful recovery
- retain the latest event per worker/pool
- surface recent recovery data in supervisor metrics

**Step 4: Run tests to verify they pass**

Run the same four test commands as Step 2.

Expected:
- PASS

**Step 5: Commit**

```bash
git add backend/app/services/classifier_worker_protocol.py backend/app/services/classifier_worker_process.py backend/app/services/classifier_worker_client.py backend/app/services/classifier_supervisor.py backend/tests/test_classifier_worker_protocol.py backend/tests/test_classifier_worker_process.py backend/tests/test_classifier_worker_client.py backend/tests/test_classifier_supervisor.py
git commit -m "feat(issue22): propagate worker runtime recovery telemetry"
```

### Task 4: Cache OpenVINO Capability Probes

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_classifier_status_api.py`

**Step 1: Write the failing tests**

Add tests that verify:
- repeated `get_status()` calls in the same TTL window do not re-run `_detect_acceleration_capabilities()`
- probe refresh still occurs after TTL expiry or explicit reload

**Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest backend/tests/test_classifier_service.py -k accel_probe_cache -v
python -m pytest backend/tests/test_classifier_status_api.py -k accel_probe_cache -v
```

Expected:
- FAIL because `get_status()` currently reprobes every call

**Step 3: Write minimal implementation**

In `backend/app/services/classifier_service.py`:
- add a bounded TTL cache for capability probe results
- refresh on startup, explicit reload, or expired TTL only
- keep current static diagnostic fields intact

**Step 4: Run tests to verify they pass**

Run the same two test commands as Step 2.

Expected:
- PASS

**Step 5: Commit**

```bash
git add backend/app/services/classifier_service.py backend/tests/test_classifier_service.py backend/tests/test_classifier_status_api.py
git commit -m "fix(issue22): cache openvino capability probes"
```

### Task 5: Introduce Dedicated Supervised Video Pool

**Files:**
- Modify: `backend/app/config_models.py`
- Modify: `backend/app/services/classifier_supervisor.py`
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/services/auto_video_classifier_service.py`
- Test: `backend/tests/test_classifier_supervisor.py`
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_auto_video_classifier_pressure.py`

**Step 1: Write the failing tests**

Add tests that verify:
- video classification uses its own supervised pool
- live snapshot work can proceed while video work is running/blocked
- video worker failures do not consume live/background pool state

**Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest backend/tests/test_classifier_supervisor.py -k video_pool -v
python -m pytest backend/tests/test_classifier_service.py -k video_pool -v
python -m pytest backend/tests/test_auto_video_classifier_pressure.py -v
```

Expected:
- FAIL because video currently bypasses the supervised worker pools

**Step 3: Write minimal implementation**

Add a distinct `video` worker pool with separate worker count/deadline settings if needed. Route bird video inference through that pool, keeping the existing progress-callback behavior intact and preserving non-bird video orchestration above it.

**Step 4: Run tests to verify they pass**

Run the same three test commands as Step 2.

Expected:
- PASS

**Step 5: Commit**

```bash
git add backend/app/config_models.py backend/app/services/classifier_supervisor.py backend/app/services/classifier_service.py backend/app/services/auto_video_classifier_service.py backend/tests/test_classifier_supervisor.py backend/tests/test_classifier_service.py backend/tests/test_auto_video_classifier_pressure.py
git commit -m "feat(issue22): isolate video inference in supervised workers"
```

### Task 6: Make Health And Status Worker-Authoritative In Subprocess Mode

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/routers/backfill.py`
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_health_readiness.py`
- Test: `backend/tests/test_backfill_router_messages.py`

**Step 1: Write the failing tests**

Add tests that verify in subprocess mode:
- health/status reflects worker pool runtime recovery and startup failures
- top-level health degrades correctly on worker/runtime failure without depending on a main-process bird model
- backfill status messages use worker-derived reasons

**Step 2: Run tests to verify they fail**

Run:

```bash
python -m pytest backend/tests/test_classifier_service.py -k worker_authoritative -v
python -m pytest backend/tests/test_health_readiness.py -k worker_authoritative -v
python -m pytest backend/tests/test_backfill_router_messages.py -k worker_authoritative -v
```

Expected:
- FAIL because subprocess-mode health still mixes in main-process bird-model state

**Step 3: Write minimal implementation**

In `backend/app/services/classifier_service.py` and dependent health paths:
- switch subprocess-mode health/status to supervisor-derived truth
- expose latest runtime recovery event and startup failure details from worker metrics
- preserve current non-subprocess behavior for explicit `in_process` fallback mode

**Step 4: Run tests to verify they pass**

Run the same three test commands as Step 2.

Expected:
- PASS

**Step 5: Commit**

```bash
git add backend/app/services/classifier_service.py backend/app/main.py backend/app/routers/backfill.py backend/tests/test_classifier_service.py backend/tests/test_health_readiness.py backend/tests/test_backfill_router_messages.py
git commit -m "fix(issue22): make subprocess health worker authoritative"
```

### Task 7: Route Owner Debug/Test Bird Calls Through Supervised Workers

**Files:**
- Modify: `backend/app/routers/classifier.py`
- Test: `backend/tests/test_classifier_status_api.py`

**Step 1: Write the failing test**

Add tests for owner bird debug/test endpoints that verify:
- they still succeed in subprocess mode
- they do not depend on direct main-process bird interpreter/session access

**Step 2: Run test to verify it fails**

Run:

```bash
python -m pytest backend/tests/test_classifier_status_api.py -k owner_debug_subprocess -v
```

Expected:
- FAIL because these endpoints currently inspect or invoke the main-process bird model directly

**Step 3: Write minimal implementation**

Update the router so owner bird debug/test operations:
- use supervised inference requests where applicable
- return subprocess-safe diagnostics for bird runtime state
- avoid direct `interpreter`/session assumptions

**Step 4: Run test to verify it passes**

Run:

```bash
python -m pytest backend/tests/test_classifier_status_api.py -k owner_debug_subprocess -v
```

Expected:
- PASS

**Step 5: Commit**

```bash
git add backend/app/routers/classifier.py backend/tests/test_classifier_status_api.py
git commit -m "fix(issue22): make classifier debug routes subprocess safe"
```

### Task 8: Widen Verification And Update Changelog

**Files:**
- Modify: `CHANGELOG.md`
- Verify: `backend/tests/test_classifier_service.py`
- Verify: `backend/tests/test_classifier_supervisor.py`
- Verify: `backend/tests/test_classifier_worker_client.py`
- Verify: `backend/tests/test_classifier_worker_process.py`
- Verify: `backend/tests/test_classifier_worker_protocol.py`
- Verify: `backend/tests/test_health_readiness.py`
- Verify: `backend/tests/test_backfill_service.py`
- Verify: `backend/tests/test_backfill_router_messages.py`
- Verify: `backend/tests/test_event_processor.py`
- Verify: `backend/tests/test_auto_video_classifier_pressure.py`
- Verify: `backend/tests/test_classifier_status_api.py`

**Step 1: Update changelog**

Add concise entries covering:
- supervised-only bird inference in subprocess mode
- watchdog hardening
- cached OpenVINO probing
- dedicated video worker pool
- worker-authoritative runtime recovery telemetry

**Step 2: Run widened verification**

Run:

```bash
python -m pytest \
  backend/tests/test_classifier_service.py \
  backend/tests/test_classifier_supervisor.py \
  backend/tests/test_classifier_worker_client.py \
  backend/tests/test_classifier_worker_process.py \
  backend/tests/test_classifier_worker_protocol.py \
  backend/tests/test_health_readiness.py \
  backend/tests/test_backfill_service.py \
  backend/tests/test_backfill_router_messages.py \
  backend/tests/test_event_processor.py \
  backend/tests/test_auto_video_classifier_pressure.py \
  backend/tests/test_classifier_status_api.py -q
```

Expected:
- all pass

**Step 3: Optional UI/type verification if API shapes changed**

Run:

```bash
npm --prefix apps/ui run check
```

Expected:
- `svelte-check` reports `0 errors and 0 warnings`

**Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "chore(issue22): document openvino gpu hardening"
```

