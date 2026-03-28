# Notification Timeout Runtime Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the derived delayed-notification timeout floor so it includes clip wait plus video runtime budget.

**Architecture:** Update the existing backend timeout helper to include `video_classification_timeout_seconds`, add a failing test for the expanded formula, and verify the orchestrator tests stay green. No UI/API contract changes are needed.

**Tech Stack:** Python, FastAPI backend services, pytest

---

### Task 1: Save the design and plan

**Files:**
- Create: `docs/plans/2026-03-28-notification-timeout-runtime-hardening-design.md`
- Create: `docs/plans/2026-03-28-notification-timeout-runtime-hardening-plan.md`

**Step 1: Save the approved design**

Write the short design note describing the expanded timeout floor.

**Step 2: Save the implementation plan**

Write this plan for predictable execution.

### Task 2: Add the failing test

**Files:**
- Modify: `backend/tests/test_notification_orchestrator.py`

**Step 1: Write the failing regression**

Update the timeout-budget expectation so the derived wait includes classification runtime.

**Step 2: Run the test to verify it fails**

Run: `pytest backend/tests/test_notification_orchestrator.py -q`

Expected: FAIL because the helper still omits runtime.

### Task 3: Implement the minimal backend change

**Files:**
- Modify: `backend/app/services/notification_orchestrator.py`

**Step 1: Extend the helper**

Add `video_classification_timeout_seconds` to the derived minimum budget.

**Step 2: Run the test to verify it passes**

Run: `pytest backend/tests/test_notification_orchestrator.py -q`

Expected: PASS

### Task 4: Final verification and commit

**Files:**
- Test: `backend/tests/test_notification_orchestrator.py`

**Step 1: Re-run targeted verification**

Run: `pytest backend/tests/test_notification_orchestrator.py -q`

Expected: PASS

**Step 2: Commit**

Commit the hardening change together with the design/plan docs.
