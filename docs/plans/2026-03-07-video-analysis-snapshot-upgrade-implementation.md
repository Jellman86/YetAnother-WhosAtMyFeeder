# Video Analysis Snapshot Upgrade Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the high-quality snapshot feature so manual video reclassification and batch/auto video analysis can also refresh the cached event snapshot when they already have valid clip bytes.

**Architecture:** Reuse the existing high-quality snapshot service as the single owner of clip-frame extraction and cache replacement. Add a direct clip-bytes entry point and call it from the manual video reclassify path and the auto/batch video-analysis worker only after clip validation has succeeded.

**Tech Stack:** FastAPI, Python async services, OpenCV, Frigate clip API, YA-WAMF media cache, pytest

---

### Task 1: Add a clip-bytes entry point to the snapshot upgrade service

**Files:**
- Modify: `backend/app/services/high_quality_snapshot_service.py`
- Test: `backend/tests/test_high_quality_snapshot_service.py`

**Step 1: Write the failing test**
Add tests covering:
- `replace_from_clip_bytes(event_id, clip_bytes)` replaces the cached snapshot when the feature is enabled
- invalid extraction failure leaves the original snapshot in place
- feature flag off returns a no-op result

**Step 2: Run test to verify it fails**
Run: `python -m pytest backend/tests/test_high_quality_snapshot_service.py -k clip_bytes -q`
Expected: FAIL because the method does not exist

**Step 3: Write minimal implementation**
Add a direct service method that:
- checks the feature flag
- extracts a frame from the provided clip bytes
- calls `media_cache.replace_snapshot()`
- records the same outcome codes as the existing async path

**Step 4: Run test to verify it passes**
Run: `python -m pytest backend/tests/test_high_quality_snapshot_service.py -k clip_bytes -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/high_quality_snapshot_service.py backend/tests/test_high_quality_snapshot_service.py
git commit -m "feat: allow snapshot upgrade from clip bytes"
```

### Task 2: Wire manual video reclassify into snapshot upgrade

**Files:**
- Modify: `backend/app/routers/events.py`
- Test: `backend/tests/test_events_reclassify.py` or closest existing reclassify test file

**Step 1: Write the failing test**
Add tests covering:
- `strategy=video` with valid clip bytes triggers the shared snapshot replacement call when enabled
- video request that falls back to snapshot does not trigger replacement
- snapshot replacement failure does not make the reclassify endpoint fail if classification succeeds

**Step 2: Run test to verify it fails**
Run: `python -m pytest backend/tests/test_events_reclassify.py -q`
Expected: FAIL because the endpoint does not call the snapshot upgrade service

**Step 3: Write minimal implementation**
In the valid video path, call the shared snapshot-upgrade method once clip validation has succeeded. Keep it best-effort and do not alter classification or response semantics.

**Step 4: Run test to verify it passes**
Run: `python -m pytest backend/tests/test_events_reclassify.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/routers/events.py backend/tests/test_events_reclassify.py
git commit -m "feat: reuse clip-backed snapshot upgrade in manual reclassify"
```

### Task 3: Wire auto/batch video analysis into snapshot upgrade

**Files:**
- Modify: `backend/app/services/auto_video_classifier_service.py`
- Test: `backend/tests/test_auto_video_classifier_service.py` or closest existing video-classifier test file

**Step 1: Write the failing test**
Add tests covering:
- when `_wait_for_clip(...)` returns valid clip bytes and the feature is enabled, snapshot upgrade is called
- snapshot upgrade failure does not mark the video analysis task failed
- feature flag off skips the call

**Step 2: Run test to verify it fails**
Run: `python -m pytest backend/tests/test_auto_video_classifier_service.py -q`
Expected: FAIL because no snapshot-upgrade call exists in the worker path

**Step 3: Write minimal implementation**
After valid clip bytes are retrieved in the worker path, call the shared clip-bytes snapshot-upgrade method before or after classification. Keep it best-effort and separate from classification success.

**Step 4: Run test to verify it passes**
Run: `python -m pytest backend/tests/test_auto_video_classifier_service.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/auto_video_classifier_service.py backend/tests/test_auto_video_classifier_service.py
git commit -m "feat: reuse clip-backed snapshot upgrade in video analysis"
```

### Task 4: Verify integration behavior

**Files:**
- Modify: none unless defects are found
- Reference: `docs/plans/2026-03-07-video-analysis-snapshot-upgrade-design.md`
- Reference: `docs/plans/2026-03-07-video-analysis-snapshot-upgrade-implementation.md`

**Step 1: Run targeted tests**
Run:
```bash
python -m pytest backend/tests/test_high_quality_snapshot_service.py -q
python -m pytest backend/tests/test_events_reclassify.py -q
python -m pytest backend/tests/test_auto_video_classifier_service.py -q
```
Expected: PASS

**Step 2: Manual verification**
- enable the feature toggle
- run manual video reclassification on an existing detection with a retained clip
- confirm the cached image upgrades after the analysis path uses that clip
- run an `analyze unknowns` / batch path on a retained clip and confirm the same behavior

**Step 3: Record any follow-up defects**
If the replaced image is not visible in an already-open page without refetch, note that as a separate live-refresh enhancement rather than expanding this task.

**Step 4: Commit docs if updated**
```bash
git add docs/plans/2026-03-07-video-analysis-snapshot-upgrade-design.md docs/plans/2026-03-07-video-analysis-snapshot-upgrade-implementation.md
git commit -m "docs: add video analysis snapshot upgrade plan"
```
