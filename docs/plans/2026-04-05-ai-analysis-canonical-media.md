# AI Analysis Canonical Media Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make detection AI analysis prefer persisted full-visit clips, otherwise event clips, otherwise snapshots, with source-aware center-biased frame sampling.

**Architecture:** Keep the change narrow. Resolve media source in the AI router, pass source-aware metadata into `AIService`, and update frame extraction so `event` and `recording` clips are sampled differently while both remain middle-biased.

**Tech Stack:** FastAPI, existing media-cache/proxy helpers, PIL/OpenCV, pytest/httpx.

---

### Task 1: Add failing router tests for AI media selection

**Files:**
- Create: `backend/tests/test_ai_analysis_media_api.py`

**Step 1:** Add a failing test proving AI analysis prefers cached recording clips over Frigate event clips.

**Step 2:** Add a failing test proving AI analysis falls back to the event clip when no recording clip is available.

**Step 3:** Add a failing test proving AI analysis falls back to a snapshot when no usable clip frames are available.

### Task 2: Add failing service tests for source-aware AI prompt/frame behavior

**Files:**
- Modify: `backend/tests/test_ai_service.py`

**Step 1:** Add a failing test for the prompt note when `frame_source="recording"`.

**Step 2:** Add a failing test that `extract_frames_from_clip(..., clip_variant="recording")` accepts the new argument.

### Task 3: Implement canonical media resolution in the AI router

**Files:**
- Modify: `backend/app/routers/ai.py`

**Step 1:** Add a helper that tries validated cached recording clip first.

**Step 2:** Fall back to Frigate event clip second.

**Step 3:** Fall back to snapshot last.

**Step 4:** Include `frame_source` in AI metadata.

### Task 4: Implement source-aware frame extraction and prompt notes

**Files:**
- Modify: `backend/app/services/ai_service.py`

**Step 1:** Extend `extract_frames_from_clip` with `clip_variant`.

**Step 2:** Keep both variants center-biased but widen the recording window.

**Step 3:** Update `_build_prompt` to describe whether the AI saw a full-visit clip, an event clip, or a snapshot.

### Task 5: Verify and document

**Files:**
- Modify: `CHANGELOG.md`

**Step 1:** Run the targeted AI router and AI service tests.

**Step 2:** Update the changelog.

**Step 3:** Push to `dev`.
