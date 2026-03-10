# Issue 22 Follow-Up Isolation And Health Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the remaining issue-22 follow-up work by isolating live MQTT image classification from non-live image work and making event-pipeline health recovery-aware.

**Architecture:** Add a dedicated live image executor to `ClassifierService` so live MQTT snapshot classification has hard isolation from non-live image calls. Preserve cumulative event-pipeline diagnostics, but add a recovery-aware health signal and update `/health` to use that signal instead of startup-cumulative counters.

**Tech Stack:** Python 3.12, FastAPI, asyncio, pytest

---

### Task 1: Isolate live classification executor

**Files:**
- Modify: `backend/tests/test_classifier_service.py`
- Modify: `backend/app/services/classifier_service.py`

**Step 1: Write the failing test**

Add a regression test that blocks the non-live `_image_executor` and verifies `classify_async_live(...)` still completes via a separate live executor.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_classifier_service.py::test_classifier_service_classify_async_live_isolated_from_non_live_executor -v`

Expected: FAIL because live work still queues behind the shared image executor.

**Step 3: Write minimal implementation**

Add `_live_image_executor` and route `_run_live_image_inference(...)` through it while preserving current live semaphore and inflight tracking.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_classifier_service.py::test_classifier_service_classify_async_live_isolated_from_non_live_executor -v`

Expected: PASS

### Task 2: Verify issue-22 backend regression subset after executor isolation

**Files:**
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_event_processor.py`
- Test: `backend/tests/test_mqtt_service.py`
- Test: `backend/tests/test_health_readiness.py`
- Test: `backend/tests/test_issue22_soak_harness.py`

**Step 1: Run targeted regression tests**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_classifier_service.py tests/test_event_processor.py tests/test_mqtt_service.py tests/test_health_readiness.py tests/test_issue22_soak_harness.py`

Expected: PASS

### Task 3: Make event-pipeline status recovery-aware

**Files:**
- Modify: `backend/tests/test_event_processor.py`
- Modify: `backend/app/services/event_processor.py`

**Step 1: Write the failing test**

Add a test showing cumulative `critical_failures` stays non-zero while the event-pipeline `status` returns to `ok` after the recovery window expires.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_event_processor.py::test_event_processor_status_recovers_after_stale_critical_failure -v`

Expected: FAIL because current status remains degraded forever.

**Step 3: Write minimal implementation**

Track the timestamp of the most recent critical stage timeout/failure and derive a recovery-aware pipeline status from a bounded recovery window while retaining cumulative counters.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_event_processor.py::test_event_processor_status_recovers_after_stale_critical_failure -v`

Expected: PASS

### Task 4: Make top-level health use the recovery-aware signal

**Files:**
- Modify: `backend/tests/test_health_readiness.py`
- Modify: `backend/app/main.py`

**Step 1: Write the failing test**

Add a test showing `/health` stays `ok` when event-pipeline historical `critical_failures` are non-zero but recovery-aware pipeline status is `ok`.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_health_readiness.py::test_health_not_degraded_by_historical_event_pipeline_failures -v`

Expected: FAIL because `/health` currently degrades on cumulative `critical_failures > 0`.

**Step 3: Write minimal implementation**

Change `/health` to use the event-pipeline `status` field rather than raw cumulative `critical_failures`.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_health_readiness.py::test_health_not_degraded_by_historical_event_pipeline_failures -v`

Expected: PASS

### Task 5: Run the targeted backend regression suite

**Files:**
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_event_processor.py`
- Test: `backend/tests/test_mqtt_service.py`
- Test: `backend/tests/test_health_readiness.py`
- Test: `backend/tests/test_issue22_soak_harness.py`

**Step 1: Run verification**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_classifier_service.py tests/test_event_processor.py tests/test_mqtt_service.py tests/test_health_readiness.py tests/test_issue22_soak_harness.py`

Expected: PASS
