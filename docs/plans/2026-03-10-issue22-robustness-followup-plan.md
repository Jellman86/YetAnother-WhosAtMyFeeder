# Issue 22 Robustness Follow-Up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add explicit classifier executor shutdown and tighten recovery-aware event-pipeline health semantics.

**Architecture:** Introduce a `ClassifierService.shutdown()` lifecycle hook and invoke it from FastAPI lifespan shutdown. Preserve current recovery-aware health behavior, but keep event-pipeline status degraded while incomplete work remains after a critical failure.

**Tech Stack:** Python 3.12, FastAPI, asyncio, pytest

---

### Task 1: Add classifier shutdown lifecycle

**Files:**
- Modify: `backend/tests/test_classifier_service.py`
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/main.py`

**Step 1: Write the failing test**

Add a test proving `ClassifierService.shutdown()` shuts down all owned executors.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_classifier_service.py::test_classifier_service_shutdown_closes_all_executors -v`

Expected: FAIL because `shutdown()` does not exist.

**Step 3: Write minimal implementation**

Add `shutdown()` and invoke it from app shutdown.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_classifier_service.py::test_classifier_service_shutdown_closes_all_executors -v`

Expected: PASS

### Task 2: Tighten recovery-aware pipeline status

**Files:**
- Modify: `backend/tests/test_event_processor.py`
- Modify: `backend/app/services/event_processor.py`

**Step 1: Write the failing test**

Add a test proving historical critical failures with remaining incomplete events still report pipeline status `degraded`.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_event_processor.py::test_event_processor_status_stays_degraded_when_incomplete_events_remain_after_critical_failure -v`

Expected: FAIL because status currently becomes `ok` after the recovery window elapses.

**Step 3: Write minimal implementation**

Use `incomplete_events` plus historical critical-failure presence to keep status degraded until work is resolved.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_event_processor.py::test_event_processor_status_stays_degraded_when_incomplete_events_remain_after_critical_failure -v`

Expected: PASS

### Task 3: Verify targeted backend regression subset

**Files:**
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_event_processor.py`
- Test: `backend/tests/test_mqtt_service.py`
- Test: `backend/tests/test_health_readiness.py`
- Test: `backend/tests/test_issue22_soak_harness.py`

**Step 1: Run verification**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_classifier_service.py tests/test_event_processor.py tests/test_mqtt_service.py tests/test_health_readiness.py tests/test_issue22_soak_harness.py`

Expected: PASS
