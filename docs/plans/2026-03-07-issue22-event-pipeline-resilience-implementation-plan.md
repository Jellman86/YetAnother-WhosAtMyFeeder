# Issue 22 Event Pipeline Resilience Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent live Frigate event processing from degrading under snapshot-classification overload by adding bounded admission, accurate in-flight accounting, and explicit overload shedding.

**Architecture:** Keep the existing MQTT and event-processing structure, but replace the current optimistic executor admission with a live-specific path that tracks admitted inference futures until they really finish. The event pipeline should fail fast when live capacity is unavailable, record distinct overload diagnostics, and remain healthy enough to keep ingesting and recovering without restarts.

**Tech Stack:** FastAPI, Python async services, `asyncio`, `ThreadPoolExecutor`, YA-WAMF MQTT/event pipeline, pytest

---

### Task 1: Lock in the issue-22 failure with tests around live admission

**Files:**
- Modify: `backend/tests/test_event_processor.py`
- Modify: `backend/tests/test_mqtt_service.py`
- Modify: `backend/tests/test_issue22_soak_harness.py`

**Step 1: Write the failing test**
Add tests covering:
- live classification overload produces a distinct drop reason instead of a generic timeout
- event processing returns promptly when live capacity is unavailable
- soak evaluation fails when event critical failures grow while MQTT ingress continues

**Step 2: Run test to verify it fails**
Run: `python3 -m pytest backend/tests/test_event_processor.py backend/tests/test_mqtt_service.py backend/tests/test_issue22_soak_harness.py -q`
Expected: FAIL because overload is not yet represented separately and live admission is still optimistic

**Step 3: Write minimal implementation**
Do not change production code yet beyond what is required to express the failing tests cleanly.

**Step 4: Run test to verify it still fails for the intended reason**
Run: `python3 -m pytest backend/tests/test_event_processor.py backend/tests/test_mqtt_service.py backend/tests/test_issue22_soak_harness.py -q`
Expected: FAIL with missing overload/admission behavior

**Step 5: Commit**
```bash
git add backend/tests/test_event_processor.py backend/tests/test_mqtt_service.py backend/tests/test_issue22_soak_harness.py
git commit -m "test: capture issue 22 live classification overload behavior"
```

### Task 2: Add accurate live image admission and in-flight accounting in the classifier

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_classifier_service.py`

**Step 1: Write the failing test**
Add tests for a live-classification helper that:
- refuses admission after a short timeout when no live slots are available
- tracks admitted futures until executor work actually finishes
- does not immediately free logical capacity when the awaiter is cancelled or times out

**Step 2: Run test to verify it fails**
Run: `python3 -m pytest backend/tests/test_classifier_service.py -q`
Expected: FAIL because the live admission helper and accounting do not exist

**Step 3: Write minimal implementation**
Implement a focused live path, for example:
- `classify_async_live(...)`
- a live admission timeout constant
- a tracked set/counter of admitted live futures
- completion callbacks that release capacity only when the executor future actually finishes

Keep the existing generic/background paths intact unless they share code cleanly.

**Step 4: Run test to verify it passes**
Run: `python3 -m pytest backend/tests/test_classifier_service.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/classifier_service.py backend/tests/test_classifier_service.py
git commit -m "fix: add bounded live image classification admission"
```

### Task 3: Wire live overload semantics into the event processor

**Files:**
- Modify: `backend/app/services/event_processor.py`
- Test: `backend/tests/test_event_processor.py`

**Step 1: Write the failing test**
Add tests covering:
- admission refusal records `classify_snapshot_overloaded`
- stage timeout after admission still records a true stage timeout
- overload does not increment the same counters as a genuine runtime failure unless intentionally designed

**Step 2: Run test to verify it fails**
Run: `python3 -m pytest backend/tests/test_event_processor.py -q`
Expected: FAIL because event processor still collapses overload and timeout into the same fallback path

**Step 3: Write minimal implementation**
Update the classification stage to:
- call the new live classifier path
- distinguish overload vs timeout vs failure
- record a dedicated drop reason and diagnostics payload for overload
- preserve existing behavior for real timeouts/failures where still appropriate

**Step 4: Run test to verify it passes**
Run: `python3 -m pytest backend/tests/test_event_processor.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/event_processor.py backend/tests/test_event_processor.py
git commit -m "fix: distinguish live classification overload from timeout"
```

### Task 4: Surface live overload in health and diagnostics

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/services/error_diagnostics.py` only if needed
- Test: `backend/tests/test_health_readiness.py`
- Test: `backend/tests/test_error_diagnostics_service.py`

**Step 1: Write the failing test**
Add tests asserting that health/diagnostics expose:
- live image admission timeouts
- live image in-flight count or similar bounded-capacity signal
- overload reason codes separately from stage timeouts

**Step 2: Run test to verify it fails**
Run: `python3 -m pytest backend/tests/test_health_readiness.py backend/tests/test_error_diagnostics_service.py -q`
Expected: FAIL because the new live overload telemetry is missing

**Step 3: Write minimal implementation**
Expose only the status needed for debugging and soak validation. Avoid a large new diagnostics subsystem.

**Step 4: Run test to verify it passes**
Run: `python3 -m pytest backend/tests/test_health_readiness.py backend/tests/test_error_diagnostics_service.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/classifier_service.py backend/app/main.py backend/app/services/error_diagnostics.py backend/tests/test_health_readiness.py backend/tests/test_error_diagnostics_service.py
git commit -m "feat: expose live classification overload health signals"
```

### Task 5: Add a targeted regression/soak harness for issue 22

**Files:**
- Modify: `backend/app/utils/issue22_soak_harness.py`
- Test: `backend/tests/test_issue22_soak_harness.py`

**Step 1: Write the failing test**
Extend soak expectations to catch:
- growing live admission timeouts
- growing event critical failures
- event started/completed divergence under continued MQTT ingress

**Step 2: Run test to verify it fails**
Run: `python3 -m pytest backend/tests/test_issue22_soak_harness.py -q`
Expected: FAIL because the additional resilience signals are not yet evaluated

**Step 3: Write minimal implementation**
Update the soak harness to incorporate the new health payload fields without widening scope beyond issue `#22`.

**Step 4: Run test to verify it passes**
Run: `python3 -m pytest backend/tests/test_issue22_soak_harness.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/utils/issue22_soak_harness.py backend/tests/test_issue22_soak_harness.py
git commit -m "test: harden issue 22 soak evaluation"
```

### Task 6: Run focused verification and then broader regression

**Files:**
- Modify: none unless verification exposes defects

**Step 1: Run focused tests**
Run: `python3 -m pytest backend/tests/test_classifier_service.py backend/tests/test_event_processor.py backend/tests/test_health_readiness.py backend/tests/test_error_diagnostics_service.py backend/tests/test_issue22_soak_harness.py backend/tests/test_mqtt_service.py -q`
Expected: PASS

**Step 2: Run broader backend regression**
Run: `python3 -m pytest backend/tests -q`
Expected: PASS, or any unrelated pre-existing failures clearly identified

**Step 3: Manual review**
Check that:
- overload is reported distinctly
- no code path still treats timed-out live inference as immediately capacity-free
- diagnostics remain readable in the Errors UI/export path

**Step 4: Commit**
```bash
git add .
git commit -m "fix: harden live event pipeline against issue 22 overload"
```
