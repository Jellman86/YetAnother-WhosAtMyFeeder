# Issue 22 Classification Coordinator Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace fragile live/background image-classification admission with a robust coordinator that can reclaim wedged capacity, report truthful failure modes, and keep backfill telemetry job-scoped and accurate.

**Architecture:** Add a dedicated backend classification-admission coordinator that owns queueing, lease issuance, stale-lease reclamation, and stale-completion rejection for live and background image classification. Wire `ClassifierService`, `EventProcessor`, `BackfillService`, health/diagnostics, and frontend backfill telemetry to this coordinator-driven model while preserving existing public APIs.

**Tech Stack:** Python 3.12, FastAPI, asyncio, ThreadPoolExecutor, pytest, Svelte 5, Vitest

---

### Task 1: Add Coordinator Model And Unit Tests

**Files:**
- Create: `backend/app/services/classification_admission.py`
- Create: `backend/tests/test_classification_admission.py`

**Step 1: Write the failing tests**

Add tests covering:
- live work admitted ahead of background work,
- stale live lease reclamation frees capacity for a later live request,
- stale completion after reclamation is ignored,
- background work is throttled when live pressure is active.

Example test skeleton:

```python
@pytest.mark.asyncio
async def test_reclaims_stale_live_lease_and_accepts_new_live_work():
    coordinator = ClassificationAdmissionCoordinator(
        live_capacity=1,
        background_capacity=1,
        live_lease_timeout_seconds=0.01,
        background_lease_timeout_seconds=1.0,
    )
    # submit one wedged live task, then verify a second live task can run after reclaim
```

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classification_admission.py -q
```

Expected: FAIL because `classification_admission.py` and the coordinator do not exist yet.

**Step 3: Write minimal implementation**

Implement:
- `ClassificationAdmissionCoordinator`
- work item state tracking
- lease tokens
- queue admission and scheduling
- stale-lease reclamation
- stale-completion rejection
- runtime metrics export

Core API target:

```python
result = await coordinator.submit(
    priority="live",
    kind="snapshot_classification",
    fn=callable_obj,
    args=(image,),
)
```

**Step 4: Run test to verify it passes**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classification_admission.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening add backend/app/services/classification_admission.py backend/tests/test_classification_admission.py
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening commit -m "test(classifier): add admission coordinator core coverage"
```

### Task 2: Wire `ClassifierService` Through The Coordinator

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/tests/test_classifier_service.py`

**Step 1: Write the failing tests**

Add tests proving:
- `classify_async_live()` uses coordinator-managed live admission,
- stale live work does not keep the service permanently unschedulable,
- stale completion is ignored,
- runtime metrics include coordinator live/background queue and reclaim fields.

Example test skeleton:

```python
@pytest.mark.asyncio
async def test_classifier_service_ignores_stale_live_completion_after_reclaim():
    service = ClassifierService()
    ...
```

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -q
```

Expected: FAIL on new coordinator-backed behavior assertions.

**Step 3: Write minimal implementation**

Update `ClassifierService` to:
- instantiate the coordinator,
- submit live/background image inference via coordinator APIs,
- preserve executor ownership in `ClassifierService`,
- export coordinator metrics from `check_health()` / `get_status()`,
- shut down the coordinator during service shutdown.

**Step 4: Run test to verify it passes**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening add backend/app/services/classifier_service.py backend/tests/test_classifier_service.py
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening commit -m "feat(classifier): route image admission through coordinator"
```

### Task 3: Preserve True Failure Reasons In Event Processing

**Files:**
- Modify: `backend/app/services/event_processor.py`
- Modify: `backend/tests/test_event_processor.py`
- Modify: `backend/tests/test_mqtt_service.py`

**Step 1: Write the failing tests**

Add tests proving:
- live overload propagates as `classify_snapshot_overloaded`,
- true snapshot fetch failure remains distinct from overload,
- reclaimed/abandoned live work does not later save detections or notify,
- MQTT dispatch still returns promptly on overload and timeout.

Example test skeleton:

```python
@pytest.mark.asyncio
async def test_process_mqtt_message_records_overload_without_collapsing_to_unavailable():
    ...
```

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_event_processor.py backend/tests/test_mqtt_service.py -q
```

Expected: FAIL because `_classify_snapshot()` still collapses overload into generic unavailability.

**Step 3: Write minimal implementation**

Update `EventProcessor` to:
- stop swallowing coordinator/live-overload exceptions,
- keep overload, timeout, unavailable, and failure reasons distinct,
- reject stale completions from affecting save/notify flow,
- keep drop reasons and recent outcomes aligned with actual root cause.

**Step 4: Run test to verify it passes**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_event_processor.py backend/tests/test_mqtt_service.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening add backend/app/services/event_processor.py backend/tests/test_event_processor.py backend/tests/test_mqtt_service.py
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening commit -m "fix(event-pipeline): preserve coordinator failure semantics"
```

### Task 4: Move Backfill Classification To Coordinated Background Admission

**Files:**
- Modify: `backend/app/services/backfill_service.py`
- Modify: `backend/app/routers/backfill.py`
- Modify: `backend/tests/test_backfill_service.py`
- Modify: `backend/tests/test_backfill_router_messages.py`

**Step 1: Write the failing tests**

Add tests proving:
- background classification submits through coordinator,
- live pressure throttles background progress,
- backfill status/message stays truthful while throttled,
- starting a new backfill job does not inherit prior-job totals or state.

Example test skeleton:

```python
@pytest.mark.asyncio
async def test_backfill_background_work_pauses_under_live_pressure():
    ...
```

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_backfill_service.py backend/tests/test_backfill_router_messages.py -q
```

Expected: FAIL because backfill still uses direct background executor submission and simplistic status messaging.

**Step 3: Write minimal implementation**

Update backfill flow to:
- submit image classification through coordinator background priority,
- surface throttled/paused-by-live-pressure messaging internally,
- keep job counts tied to the active job ID only,
- preserve endpoint compatibility.

**Step 4: Run test to verify it passes**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_backfill_service.py backend/tests/test_backfill_router_messages.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening add backend/app/services/backfill_service.py backend/app/routers/backfill.py backend/tests/test_backfill_service.py backend/tests/test_backfill_router_messages.py
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening commit -m "feat(backfill): coordinate background classification admission"
```

### Task 5: Surface Coordinator Recovery In Health And Diagnostics

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/error_diagnostics.py`
- Modify: `backend/tests/test_health_readiness.py`
- Modify: `backend/tests/test_error_diagnostics_service.py`
- Modify: `backend/tests/test_error_diagnostics_api.py`
- Modify: `backend/tests/test_issue22_soak_harness.py`

**Step 1: Write the failing tests**

Add tests proving:
- health includes coordinator queue/reclaim metrics,
- top-level health degrades under active reclaim / severe live pressure,
- diagnostics history/export captures reclaim and late-completion events,
- soak harness fails when reclaimed live pressure keeps growing.

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_health_readiness.py backend/tests/test_error_diagnostics_service.py backend/tests/test_error_diagnostics_api.py backend/tests/test_issue22_soak_harness.py -q
```

Expected: FAIL because coordinator metrics and reclaim-specific diagnostics do not exist yet.

**Step 3: Write minimal implementation**

Extend backend health and diagnostics to expose:
- live/background queued/running/rejected/abandoned counts,
- reclaim counters,
- late-completion ignored counters,
- pressure/throttling state,
- and degraded health when coordinator recovery is active.

**Step 4: Run test to verify it passes**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_health_readiness.py backend/tests/test_error_diagnostics_service.py backend/tests/test_error_diagnostics_api.py backend/tests/test_issue22_soak_harness.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening add backend/app/main.py backend/app/services/error_diagnostics.py backend/tests/test_health_readiness.py backend/tests/test_error_diagnostics_service.py backend/tests/test_error_diagnostics_api.py backend/tests/test_issue22_soak_harness.py
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening commit -m "feat(health): expose coordinator recovery and pressure telemetry"
```

### Task 6: Fix Backfill UI To Be Job-Scoped And Indeterminate When Needed

**Files:**
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Modify: `apps/ui/src/lib/stores/job_progress.svelte.ts`
- Modify: `apps/ui/src/lib/app/live-updates.ts`
- Modify: `apps/ui/src/lib/stores/job_progress.test.ts`
- Modify: `apps/ui/src/lib/app/live-updates.test.ts`

**Step 1: Write the failing tests**

Add tests proving:
- a new backfill job does not inherit a previous job’s `total`,
- unknown totals render as indeterminate rather than `0/old_total`,
- terminal updates settle only the matching job ID,
- throttled background progress does not fake forward movement.

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening/apps/ui test -- job_progress.test.ts live-updates.test.ts
```

Expected: FAIL because totals are still merged too broadly across backfill job lifecycles.

**Step 3: Write minimal implementation**

Update frontend job telemetry to:
- key backfill totals by `{kind, job_id}`,
- preserve sparse updates only within the same job,
- use indeterminate progress when total is unknown,
- and reflect throttled/paused state honestly.

**Step 4: Run test to verify it passes**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening/apps/ui test -- job_progress.test.ts live-updates.test.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening add apps/ui/src/lib/pages/Settings.svelte apps/ui/src/lib/stores/job_progress.svelte.ts apps/ui/src/lib/app/live-updates.ts apps/ui/src/lib/stores/job_progress.test.ts apps/ui/src/lib/app/live-updates.test.ts
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening commit -m "fix(ui): scope backfill totals to active job ids"
```

### Task 7: Run End-To-End Regression Verification

**Files:**
- Test: `backend/tests/test_classification_admission.py`
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_event_processor.py`
- Test: `backend/tests/test_mqtt_service.py`
- Test: `backend/tests/test_backfill_service.py`
- Test: `backend/tests/test_backfill_router_messages.py`
- Test: `backend/tests/test_health_readiness.py`
- Test: `backend/tests/test_error_diagnostics_service.py`
- Test: `backend/tests/test_error_diagnostics_api.py`
- Test: `backend/tests/test_issue22_soak_harness.py`
- Test: `apps/ui/src/lib/stores/job_progress.test.ts`
- Test: `apps/ui/src/lib/app/live-updates.test.ts`

**Step 1: Run backend verification**

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_classification_admission.py \
  backend/tests/test_classifier_service.py \
  backend/tests/test_event_processor.py \
  backend/tests/test_mqtt_service.py \
  backend/tests/test_backfill_service.py \
  backend/tests/test_backfill_router_messages.py \
  backend/tests/test_health_readiness.py \
  backend/tests/test_error_diagnostics_service.py \
  backend/tests/test_error_diagnostics_api.py \
  backend/tests/test_issue22_soak_harness.py
```

Expected: PASS

**Step 2: Run frontend verification**

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening/apps/ui test -- job_progress.test.ts live-updates.test.ts
```

Expected: PASS

**Step 3: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening add .
git -C /config/workspace/YA-WAMF/.worktrees/issue22-coordinator-hardening commit -m "fix(issue22): harden classification admission and backfill telemetry"
```
