# HQ Snapshot JPEG Quality Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a configurable JPEG quality setting for derived high-quality event snapshots.

**Architecture:** Extend media-cache settings with a bounded JPEG quality field, expose it through the settings API/UI, and replace the hard-coded encoder quality in the high-quality snapshot service with the configured value.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Svelte, pytest

---

### Task 1: Add failing backend test for encoder quality wiring

**Files:**
- Modify: `backend/tests/test_high_quality_snapshot_service.py`
- Modify: `backend/app/services/high_quality_snapshot_service.py`

**Step 1: Write the failing test**

Add a test that sets the media-cache JPEG quality to a custom value and verifies the service passes that value into `cv2.imencode`.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_high_quality_snapshot_service.py::test_extract_snapshot_from_clip_uses_configured_jpeg_quality -v`

Expected: FAIL because the encoder quality is still hard-coded.

**Step 3: Write minimal implementation**

Use the configured media-cache JPEG quality in the high-quality snapshot encoder call.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/test_high_quality_snapshot_service.py::test_extract_snapshot_from_clip_uses_configured_jpeg_quality -v`

Expected: PASS

### Task 2: Add backend settings exposure/update

**Files:**
- Modify: `backend/app/config_models.py`
- Modify: `backend/app/routers/settings.py`
- Modify: relevant backend settings tests if needed

**Step 1: Add the setting**

Add `high_quality_event_snapshot_jpeg_quality` to media-cache settings with default `95` and bounds `70-100`.

**Step 2: Expose via settings API**

Include the field in settings response and update handling.

**Step 3: Verify backend tests**

Run targeted tests covering the high-quality snapshot service and settings path.

### Task 3: Add UI slider

**Files:**
- Modify: `apps/ui/src/lib/components/settings/DataSettings.svelte`
- Modify: frontend settings types/locales if required

**Step 1: Add slider UI**

Add a slider for HQ event snapshot JPEG quality near the existing HQ snapshot toggle, defaulting to 95 and bounded to 70-100.

**Step 2: Ensure settings binding**

Hook it into the existing settings state/update flow.

**Step 3: Verify frontend checks**

Run the relevant frontend type/check command if needed.

### Task 4: Verify targeted suite and update changelog

**Files:**
- Modify: `CHANGELOG.md`
- Test: `backend/tests/test_high_quality_snapshot_service.py`
- Test: any touched backend/frontend settings tests

**Step 1: Run verification**

Run the focused backend tests for the snapshot service plus any touched settings tests, and run frontend checks if UI types were touched.

Expected: PASS
