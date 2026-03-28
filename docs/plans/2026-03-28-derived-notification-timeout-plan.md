# Derived Notification Timeout Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make delayed notifications wait for at least the real video-classification pipeline budget, with the stored timeout acting only as a larger override.

**Architecture:** Add a single backend helper that mirrors the video clip polling budget and returns the effective notification wait. Use it from the notification orchestrator, then update tests and settings copy to reflect the new behavior.

**Tech Stack:** Python, FastAPI backend services, pytest, Svelte settings UI

---

### Task 1: Document the derived timeout behavior

**Files:**
- Create: `docs/plans/2026-03-28-derived-notification-timeout-design.md`
- Create: `docs/plans/2026-03-28-derived-notification-timeout-plan.md`

**Step 1: Save the approved design**

Write the short design note describing the derived timeout rule and scope.

**Step 2: Save the implementation plan**

Write this plan so the implementation can be executed predictably.

### Task 2: Add failing backend tests

**Files:**
- Modify: `backend/tests/test_notification_orchestrator.py`

**Step 1: Write the failing tests**

Add tests for:
- the derived timeout budget calculation
- the orchestrator using the derived timeout when waiting for video
- a larger manual timeout still being honored as an override

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_notification_orchestrator.py -q`

Expected: FAIL because the derived-timeout helper/behavior does not exist yet.

### Task 3: Implement the minimal backend change

**Files:**
- Modify: `backend/app/services/notification_orchestrator.py`

**Step 1: Add a helper for the effective wait**

Mirror the video classification delay plus clip polling backoff and add a small fixed buffer.

**Step 2: Use the helper in delayed notification flow**

Replace direct use of `settings.notifications.video_fallback_timeout` in the wait call with the effective value.

**Step 3: Run tests to verify they pass**

Run: `pytest backend/tests/test_notification_orchestrator.py -q`

Expected: PASS

### Task 4: Update settings copy

**Files:**
- Modify: `apps/ui/src/lib/components/settings/NotificationSettings.svelte`
- Modify: `apps/ui/src/lib/i18n/locales/en.json`

**Step 1: Update the label/description**

Explain that the timeout is auto-managed as a minimum and that manual values only extend the wait.

**Step 2: Keep the existing input**

Do not redesign the settings form in this change.

### Task 5: Verify the changed behavior

**Files:**
- Test: `backend/tests/test_notification_orchestrator.py`

**Step 1: Run targeted backend tests**

Run: `pytest backend/tests/test_notification_orchestrator.py -q`

Expected: PASS

**Step 2: Run targeted frontend verification**

Run: `npm --prefix apps/ui run check`

Expected: no errors or warnings
