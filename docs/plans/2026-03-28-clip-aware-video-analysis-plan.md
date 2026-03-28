# Clip-Aware Video Analysis Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prefer the persisted full-visit clip for manual video reclassification and use deterministic clip-aware frame sampling for event vs recording clips.

**Architecture:** Add a clip-variant-aware frame-index helper in the classifier, thread `clip_variant` through existing `input_context`, and update manual reclassification to prefer the cached recording clip when it exists.

**Tech Stack:** Python, FastAPI backend, pytest, NumPy

---

### Task 1: Save the design and plan

**Files:**
- Create: `docs/plans/2026-03-28-clip-aware-video-analysis-design.md`
- Create: `docs/plans/2026-03-28-clip-aware-video-analysis-plan.md`

### Task 2: Add failing tests

**Files:**
- Modify: `backend/tests/test_events_reclassify_api.py`
- Modify: `backend/tests/test_classifier_service.py`

**Step 1: Write the failing API regression**

Prove that manual video reclassification prefers the persisted recording clip and passes `clip_variant="recording"` into classifier input context.

**Step 2: Write the failing sampling regression**

Prove that event clips are more center-weighted than recording clips while both preserve edge coverage.

**Step 3: Run tests to verify they fail**

Run:
- `pytest backend/tests/test_events_reclassify_api.py -q`
- `pytest backend/tests/test_classifier_service.py -q -k "video_frame_indices"`

### Task 3: Implement minimal backend changes

**Files:**
- Modify: `backend/app/routers/events.py`
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/services/auto_video_classifier_service.py`

**Step 1: Add clip-aware frame-index helper**

Implement a deterministic helper that builds frame indices for `event` vs `recording`.

**Step 2: Thread clip variant through input context**

Use `clip_variant` in the video-classification input context so the sampler can switch policy.

**Step 3: Prefer cached recording clips for manual reclassification**

If a persisted recording clip exists, analyze it before falling back to the normal event clip.

### Task 4: Verify and commit

**Step 1: Run targeted verification**

Run:
- `pytest backend/tests/test_events_reclassify_api.py -q`
- `pytest backend/tests/test_classifier_service.py -q -k "video_frame_indices or reclassify_video"`

**Step 2: Commit**

Commit the clip-aware video analysis change and docs.
