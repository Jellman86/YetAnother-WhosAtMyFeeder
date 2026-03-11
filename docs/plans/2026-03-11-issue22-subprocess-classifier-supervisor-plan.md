# Issue 22 Subprocess Classifier Supervisor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace in-process image classification execution with supervised subprocess workers that can be killed and restarted on hangs/crashes while preserving live-priority admission, truthful health, and operator-visible recovery state.

**Architecture:** Keep `ClassificationAdmissionCoordinator` as the authoritative scheduler and lease manager, but move actual inference execution behind a `ClassifierSupervisor` that manages live/background subprocess worker pools, heartbeat/deadline enforcement, restart budgets, and circuit breakers. Add live coalescing and stale shedding ahead of admission so the system reduces avoidable pressure before recovery logic activates.

**Tech Stack:** Python 3.12, asyncio, subprocess IPC, pytest, FastAPI, Svelte/Vitest.

---

### Task 1: Add supervisor configuration model

**Files:**
- Modify: `backend/app/config_models.py`
- Modify: `backend/app/config_loader.py`
- Test: `backend/tests/test_classifier_service.py`

**Step 1: Write the failing test**

Add a test asserting classifier configuration exposes mode, pool sizes, heartbeat timeout, deadline timeout, restart window, breaker threshold, stale-live age, and coalescing toggle with sane defaults.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -k supervisor_config -v`

Expected: FAIL because fields/defaults are missing.

**Step 3: Write minimal implementation**

Add config fields for:
- `image_execution_mode`
- `live_worker_count`
- `background_worker_count`
- `worker_heartbeat_timeout_seconds`
- `worker_hard_deadline_seconds`
- `worker_restart_window_seconds`
- `worker_restart_threshold`
- `worker_breaker_cooldown_seconds`
- `live_event_stale_drop_seconds`
- `live_event_coalescing_enabled`

Thread them through config loading.

**Step 4: Run test to verify it passes**

Run the same pytest command.

**Step 5: Commit**

```bash
git add backend/app/config_models.py backend/app/config_loader.py backend/tests/test_classifier_service.py
git commit -m "feat: add classifier supervisor config"
```

### Task 2: Add worker protocol module

**Files:**
- Create: `backend/app/services/classifier_worker_protocol.py`
- Test: `backend/tests/test_classifier_worker_protocol.py`

**Step 1: Write the failing test**

Add tests for request/response framing and parsing:
- `ready`
- `heartbeat`
- `result`
- `error`
- malformed message rejection

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_worker_protocol.py -v`

Expected: FAIL because module/functions do not exist.

**Step 3: Write minimal implementation**

Implement a narrow JSON-line protocol helper with:
- encode parent request
- encode worker event
- parse message with validation

**Step 4: Run test to verify it passes**

Run the same pytest command.

**Step 5: Commit**

```bash
git add backend/app/services/classifier_worker_protocol.py backend/tests/test_classifier_worker_protocol.py
git commit -m "feat: add classifier worker protocol"
```

### Task 3: Create the worker subprocess entrypoint

**Files:**
- Create: `backend/app/services/classifier_worker_process.py`
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_classifier_worker_process.py`

**Step 1: Write the failing test**

Add tests for worker behavior using stub classification hooks:
- emits `ready`
- emits heartbeats while idle
- handles a classify request and returns a structured result
- emits structured error on runner failure

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_worker_process.py -v`

Expected: FAIL because worker entrypoint does not exist.

**Step 3: Write minimal implementation**

Create the subprocess entrypoint that:
- boots classifier runtime in-process for the worker,
- reads protocol messages from stdin,
- executes classification requests,
- emits heartbeats and structured responses.

Keep worker execution isolated from DB and notification logic.

**Step 4: Run test to verify it passes**

Run the same pytest command.

**Step 5: Commit**

```bash
git add backend/app/services/classifier_worker_process.py backend/app/services/classifier_service.py backend/tests/test_classifier_worker_process.py
git commit -m "feat: add classifier worker subprocess entrypoint"
```

### Task 4: Add a supervised worker wrapper

**Files:**
- Create: `backend/app/services/classifier_worker_client.py`
- Test: `backend/tests/test_classifier_worker_client.py`

**Step 1: Write the failing test**

Add tests for:
- spawn + ready handshake
- heartbeat tracking
- non-zero exit detection
- kill/terminate behavior

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_worker_client.py -v`

Expected: FAIL because client wrapper does not exist.

**Step 3: Write minimal implementation**

Implement a wrapper around `asyncio.create_subprocess_exec` that:
- starts the worker,
- reads stdout protocol events,
- tracks last heartbeat,
- exposes current assignment,
- supports terminate/kill/restart.

**Step 4: Run test to verify it passes**

Run the same pytest command.

**Step 5: Commit**

```bash
git add backend/app/services/classifier_worker_client.py backend/tests/test_classifier_worker_client.py
git commit -m "feat: add classifier worker client"
```

### Task 5: Implement the classifier supervisor

**Files:**
- Create: `backend/app/services/classifier_supervisor.py`
- Test: `backend/tests/test_classifier_supervisor.py`

**Step 1: Write the failing test**

Add tests for:
- live and background pool startup
- assignment to idle worker
- heartbeat timeout -> kill + replace
- hard deadline -> kill + replace
- crash -> replace
- stale result from old generation ignored

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_supervisor.py -v`

Expected: FAIL because supervisor does not exist.

**Step 3: Write minimal implementation**

Implement `ClassifierSupervisor` with:
- separate live/background pools,
- worker generations,
- assignment tracking,
- watchdog loop,
- replacement logic,
- metrics snapshot.

Do not add breaker logic yet.

**Step 4: Run test to verify it passes**

Run the same pytest command.

**Step 5: Commit**

```bash
git add backend/app/services/classifier_supervisor.py backend/tests/test_classifier_supervisor.py
git commit -m "feat: add classifier supervisor"
```

### Task 6: Add restart budget and circuit breakers

**Files:**
- Modify: `backend/app/services/classifier_supervisor.py`
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_classifier_supervisor.py`
- Test: `backend/tests/test_classifier_service.py`

**Step 1: Write the failing test**

Add tests for:
- repeated worker failures open live breaker,
- live requests fail fast with circuit-open reason,
- background breaker pauses background work,
- cooldown expiry allows recovery.

**Step 2: Run test to verify it fails**

Run:
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_supervisor.py -k breaker -v`
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -k circuit_open -v`

Expected: FAIL because breaker behavior does not exist.

**Step 3: Write minimal implementation**

Add rolling restart counters and per-pool breaker state. Surface explicit errors:
- `classify_snapshot_circuit_open`
- background paused/recovering state

**Step 4: Run test to verify it passes**

Run the same pytest commands.

**Step 5: Commit**

```bash
git add backend/app/services/classifier_supervisor.py backend/app/services/classifier_service.py backend/tests/test_classifier_supervisor.py backend/tests/test_classifier_service.py
git commit -m "feat: add classifier worker circuit breakers"
```

### Task 7: Integrate supervisor into classifier execution

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/services/event_processor.py`
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_event_processor.py`

**Step 1: Write the failing test**

Add tests proving:
- subprocess mode routes live/background classification through supervisor,
- lease-expired and circuit-open reasons remain visible to event processing,
- stale worker results do not notify/save.

**Step 2: Run test to verify it fails**

Run:
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -k subprocess_mode -v`
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_event_processor.py -k circuit_open -v`

Expected: FAIL because classifier service still uses in-process execution only.

**Step 3: Write minimal implementation**

Wire `ClassifierService` to choose between:
- existing in-process path,
- new supervisor path.

Preserve admission coordinator ownership and existing public methods:
- `classify_async_live`
- `classify_async_background`
- `check_health`
- `get_status`
- `get_admission_status`

**Step 4: Run test to verify it passes**

Run the same pytest commands.

**Step 5: Commit**

```bash
git add backend/app/services/classifier_service.py backend/app/services/event_processor.py backend/tests/test_classifier_service.py backend/tests/test_event_processor.py
git commit -m "feat: route classifier execution through supervisor"
```

### Task 8: Add live coalescing and stale shedding

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/services/event_processor.py`
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_event_processor.py`

**Step 1: Write the failing test**

Add tests for:
- duplicate live requests for the same snapshot are coalesced,
- stale live events are dropped before admission,
- metrics include coalesced and stale-drop counters.

**Step 2: Run test to verify it fails**

Run:
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -k coalesc -v`
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_event_processor.py -k stale_live -v`

Expected: FAIL because coalescing/shedding does not exist.

**Step 3: Write minimal implementation**

Add a live request identity and bounded in-memory coalescing map. Add event freshness checks before live admission and explicit drop reasons/metrics.

**Step 4: Run test to verify it passes**

Run the same pytest commands.

**Step 5: Commit**

```bash
git add backend/app/services/classifier_service.py backend/app/services/event_processor.py backend/tests/test_classifier_service.py backend/tests/test_event_processor.py
git commit -m "feat: add live classification coalescing and stale shedding"
```

### Task 9: Surface supervisor state in health and diagnostics

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/classifier_service.py`
- Modify: `apps/ui/src/lib/stores/job_diagnostics.svelte.ts`
- Test: `backend/tests/test_health_readiness.py`
- Test: `apps/ui/src/lib/stores/job_diagnostics.test.ts`

**Step 1: Write the failing test**

Add tests for:
- health includes worker pool and breaker fields,
- degraded status reflects active breaker/restart instability,
- diagnostics export preserves supervisor pool data.

**Step 2: Run test to verify it fails**

Run:
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_health_readiness.py -k supervisor -v`
- `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening/apps/ui run test -- src/lib/stores/job_diagnostics.test.ts`

Expected: FAIL because health/diagnostics do not include supervisor state.

**Step 3: Write minimal implementation**

Expose:
- worker counts
- max heartbeat age
- breaker state/cooldown
- restart counts
- coalesced/stale-drop counts
- last exit reasons

Thread these through diagnostics export and snapshot fingerprints.

**Step 4: Run test to verify it passes**

Run the same commands.

**Step 5: Commit**

```bash
git add backend/app/main.py backend/app/services/classifier_service.py apps/ui/src/lib/stores/job_diagnostics.svelte.ts backend/tests/test_health_readiness.py apps/ui/src/lib/stores/job_diagnostics.test.ts
git commit -m "feat: expose classifier supervisor health and diagnostics"
```

### Task 10: Update backfill pause/recovery UX

**Files:**
- Modify: `backend/app/routers/backfill.py`
- Modify: `apps/ui/src/lib/app/live-updates.ts`
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Test: `backend/tests/test_backfill_router_messages.py`
- Test: `apps/ui/src/lib/app/live-updates.test.ts`

**Step 1: Write the failing test**

Add tests for:
- backfill reports paused while classifier recovers,
- SSE/poll job progress preserves unknown totals during recovery,
- circuit-open background state is rendered as paused/recovering rather than running progress.

**Step 2: Run test to verify it fails**

Run:
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_backfill_router_messages.py -v`
- `/usr/bin/bash -lc 'cd /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening/apps/ui && ./node_modules/.bin/vitest run src/lib/app/live-updates.test.ts'`

Expected: FAIL because recovery/paused states are not fully represented.

**Step 3: Write minimal implementation**

Extend cheap admission/supervisor status snapshots for backfill messages and preserve truthful paused/recovering UI text.

**Step 4: Run test to verify it passes**

Run the same commands.

**Step 5: Commit**

```bash
git add backend/app/routers/backfill.py apps/ui/src/lib/app/live-updates.ts apps/ui/src/lib/pages/Settings.svelte backend/tests/test_backfill_router_messages.py apps/ui/src/lib/app/live-updates.test.ts
git commit -m "feat: expose classifier recovery in backfill UX"
```

### Task 11: Add end-to-end fault-injection coverage

**Files:**
- Create: `backend/tests/test_classifier_supervisor_fault_injection.py`
- Modify: `backend/tests/test_classifier_supervisor.py`

**Step 1: Write the failing test**

Add fault-injection tests using a fake worker process that:
- hangs,
- stops heartbeating,
- crashes,
- returns after generation replacement.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_supervisor_fault_injection.py -v`

Expected: FAIL because the fault-injection harness does not exist.

**Step 3: Write minimal implementation**

Add fixture/helpers that launch a fake worker and drive the supervisor through these failure modes.

**Step 4: Run test to verify it passes**

Run the same pytest command.

**Step 5: Commit**

```bash
git add backend/tests/test_classifier_supervisor_fault_injection.py backend/tests/test_classifier_supervisor.py
git commit -m "test: add classifier supervisor fault injection coverage"
```

### Task 12: Run widened verification and document rollout

**Files:**
- Modify: `docs/plans/2026-03-11-issue22-subprocess-classifier-supervisor-design.md`
- Modify: `docs/plans/2026-03-11-issue22-subprocess-classifier-supervisor-plan.md`

**Step 1: Run backend verification**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_classification_admission.py \
  backend/tests/test_classifier_worker_protocol.py \
  backend/tests/test_classifier_worker_process.py \
  backend/tests/test_classifier_worker_client.py \
  backend/tests/test_classifier_supervisor.py \
  backend/tests/test_classifier_supervisor_fault_injection.py \
  backend/tests/test_classifier_service.py \
  backend/tests/test_event_processor.py \
  backend/tests/test_backfill_router_messages.py \
  backend/tests/test_health_readiness.py -q
```

Expected: PASS

**Step 2: Run UI verification**

Run:

```bash
/usr/bin/bash -lc 'cd /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening/apps/ui && ./node_modules/.bin/vitest run src/lib/app/live-updates.test.ts src/lib/stores/job_diagnostics.test.ts src/lib/stores/job_progress.test.ts src/lib/backfill/progress.test.ts'
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening/apps/ui run check
```

Expected: PASS

**Step 3: Update docs with final config and rollout notes**

Document:
- default mode,
- breaker thresholds,
- soak-test recommendations,
- operational signals to watch after deploy.

**Step 4: Commit**

```bash
git add docs/plans/2026-03-11-issue22-subprocess-classifier-supervisor-design.md docs/plans/2026-03-11-issue22-subprocess-classifier-supervisor-plan.md
git commit -m "docs: finalize subprocess classifier supervisor rollout notes"
```
