# Issue 33 Video Breaker Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Isolate maintenance video-classification failures from the live auto-video breaker and enrich timeout diagnostics so `#33` bundles identify the failing path clearly.

**Architecture:** Keep one shared work queue, but attach a source to each queued job and maintain separate breaker state for `live` and `maintenance`. Extend diagnostics and status payloads so maintenance failures remain visible without suppressing live auto-video classification.

**Tech Stack:** FastAPI, asyncio, Python service layer, pytest

---

### Task 1: Lock the source-aware breaker contract with tests

**Files:**
- Modify: `backend/tests/test_auto_video_classifier_queueing.py`
- Modify: `backend/tests/test_auto_video_classifier_snapshot_upgrade.py`

**Step 1: Write failing queueing tests**

Add tests for:
- queued maintenance jobs storing their source in the pending queue
- maintenance `video_timeout` opening only the maintenance breaker
- live breaker remaining closed after maintenance failures

**Step 2: Write failing timeout diagnostic test**

Add a `_process_event()` timeout test that asserts the diagnostic context includes the job source and timeout metadata.

**Step 3: Run focused tests and confirm failure**

Run:
`/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_auto_video_classifier_queueing.py /config/workspace/YA-WAMF/backend/tests/test_auto_video_classifier_snapshot_upgrade.py -q`

### Task 2: Implement source-aware queueing and isolated breakers

**Files:**
- Modify: `backend/app/services/auto_video_classifier_service.py`
- Modify: `backend/app/routers/settings.py`

**Step 1: Carry job source through the queue**

Add a source field to queued jobs and set:
- `live` from `trigger_classification()`
- `maintenance` from `/maintenance/analyze-unknowns`

**Step 2: Split breaker state**

Track separate failure events and open-until timestamps for:
- live
- maintenance

**Step 3: Use source-aware failure accounting**

Ensure `_record_failure()` and breaker-open diagnostics are keyed by source, and only the live breaker blocks live auto-video.

### Task 3: Enrich timeout diagnostics and status

**Files:**
- Modify: `backend/app/services/auto_video_classifier_service.py`
- Modify: `backend/app/routers/settings.py`
- Modify: `CHANGELOG.md`

**Step 1: Add timeout context**

Include source, timeout seconds, camera, clip byte size, and classifier runtime/provider status where available.

**Step 2: Expose both circuit states**

Extend status output so maintenance breaker health is visible beside the live breaker.

**Step 3: Verify and document**

Run the focused backend suite, update the changelog, and keep the scope limited to `#33`.
