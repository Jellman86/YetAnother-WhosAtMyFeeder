# High-Quality Event Snapshots Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a default-off YA-WAMF feature that asynchronously replaces Frigate-provided event snapshots with a higher-quality still extracted from the event clip recorded on the main stream.

**Architecture:** Keep the existing event pipeline unchanged for first paint and fallback safety. Cache the Frigate snapshot immediately, then if enabled schedule a background replacement job that waits for the clip, extracts one representative frame, and atomically overwrites the cached snapshot while leaving the original snapshot in place on failure.

**Tech Stack:** FastAPI, Python async services, OpenCV/ffmpeg-backed clip handling, Frigate HTTP API, YA-WAMF media cache, pytest

---

### Task 1: Add feature flag configuration

**Files:**
- Modify: `backend/app/config_models.py`
- Modify: `backend/app/config_loader.py`
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_config_loader.py` or the closest config test file already covering media/classification settings

**Step 1: Write the failing test**
Add tests covering:
- the new setting defaults to `False`
- env/config values can enable it
- timeout value loads correctly if included in v1

**Step 2: Run test to verify it fails**
Run: `python -m pytest backend/tests/test_config_loader.py -q`
Expected: FAIL because the setting is missing

**Step 3: Write minimal implementation**
Add a minimal config model section for the feature, default-off.
Keep the setting surface small. Recommended shape:
- `enabled: bool = False`
- `timeout_seconds: int = 20`

**Step 4: Run test to verify it passes**
Run: `python -m pytest backend/tests/test_config_loader.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/config_models.py backend/app/config_loader.py backend/app/config.py backend/tests/test_config_loader.py
git commit -m "feat: add high-quality event snapshot config"
```

### Task 2: Add atomic snapshot replacement support in media cache

**Files:**
- Modify: `backend/app/services/media_cache.py`
- Test: `backend/tests/test_media_cache.py`

**Step 1: Write the failing test**
Add tests for a method that atomically replaces an existing cached snapshot without deleting the original on failure.
Cover:
- replacement succeeds and bytes change
- replacement failure leaves original file intact

**Step 2: Run test to verify it fails**
Run: `python -m pytest backend/tests/test_media_cache.py -q`
Expected: FAIL because replacement method does not exist

**Step 3: Write minimal implementation**
Add a focused method such as `replace_snapshot(event_id, image_bytes)` using temp file + atomic rename/replace.
Reuse the existing snapshot cache path.

**Step 4: Run test to verify it passes**
Run: `python -m pytest backend/tests/test_media_cache.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/media_cache.py backend/tests/test_media_cache.py
git commit -m "feat: add atomic cached snapshot replacement"
```

### Task 3: Create clip-frame extraction service

**Files:**
- Create: `backend/app/services/high_quality_snapshot_service.py`
- Test: `backend/tests/test_high_quality_snapshot_service.py`

**Step 1: Write the failing test**
Add unit tests covering:
- feature flag off: no work performed
- clip bytes available: extracted frame replaces cached snapshot
- invalid clip or no frame: replacement skipped, original snapshot preserved
- duplicate job for same event is deduplicated

Use real small MP4 fixture bytes if available; otherwise use a minimal generated fixture or isolate the extraction helper for testability.

**Step 2: Run test to verify it fails**
Run: `python -m pytest backend/tests/test_high_quality_snapshot_service.py -q`
Expected: FAIL because the service does not exist

**Step 3: Write minimal implementation**
Implement a service that:
- checks the feature flag
- deduplicates one in-flight job per event
- reuses `frigate_client.get_clip_with_error()` and/or the existing `_wait_for_clip` retry pattern concept
- extracts one representative frame from clip bytes
- writes the derived JPEG via `media_cache.replace_snapshot()`
- logs explicit reason codes on failure

Keep v1 frame selection simple: representative frame near the middle or first good frame after a fixed offset.
Do not add hardware acceleration in v1.

**Step 4: Run test to verify it passes**
Run: `python -m pytest backend/tests/test_high_quality_snapshot_service.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/high_quality_snapshot_service.py backend/tests/test_high_quality_snapshot_service.py
git commit -m "feat: add async high-quality snapshot replacement service"
```

### Task 4: Hook background replacement into event processing

**Files:**
- Modify: `backend/app/services/event_processor.py`
- Modify: `backend/app/services/notification_orchestrator.py` only if current sequencing requires it
- Test: `backend/tests/test_event_processor.py`

**Step 1: Write the failing test**
Add tests covering:
- when the feature is enabled and snapshot caching succeeds, the replacement job is scheduled
- when the feature is disabled, no replacement job is scheduled
- scheduling happens after the original snapshot path is available

**Step 2: Run test to verify it fails**
Run: `python -m pytest backend/tests/test_event_processor.py -q`
Expected: FAIL because no replacement scheduling exists

**Step 3: Write minimal implementation**
Trigger the background replacement task after the normal snapshot is cached and the detection is saved.
Avoid blocking the event pipeline.
If the original snapshot is unavailable, skip scheduling.

**Step 4: Run test to verify it passes**
Run: `python -m pytest backend/tests/test_event_processor.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/event_processor.py backend/tests/test_event_processor.py
git commit -m "feat: schedule high-quality snapshot replacement after event save"
```

### Task 5: Ensure served snapshot paths automatically benefit

**Files:**
- Modify: `backend/app/routers/proxy.py`
- Modify: `backend/app/routers/events.py` if needed
- Test: `backend/tests/test_proxy_router.py` or closest existing proxy/events media test file

**Step 1: Write the failing test**
Add or update tests proving the snapshot-serving endpoints continue to prefer the cached snapshot, so replacement automatically changes what clients receive.
If this behavior is already covered, add only the minimum test extension needed to lock it in.

**Step 2: Run test to verify it fails**
Run: `python -m pytest backend/tests/test_proxy_router.py -q`
Expected: FAIL only if behavior needs tightening

**Step 3: Write minimal implementation**
Only change production code if the current router does not already serve the updated cache path transparently.
Avoid new endpoints.

**Step 4: Run test to verify it passes**
Run: `python -m pytest backend/tests/test_proxy_router.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/routers/proxy.py backend/app/routers/events.py backend/tests/test_proxy_router.py
git commit -m "test: lock in cached snapshot replacement serving path"
```

### Task 6: Add observability and failure accounting

**Files:**
- Modify: `backend/app/services/high_quality_snapshot_service.py`
- Modify: `backend/app/routers/diagnostics.py` only if necessary
- Test: `backend/tests/test_high_quality_snapshot_service.py`

**Step 1: Write the failing test**
Add tests for explicit logging/failure-state handling if exposed via counters or structured return values.
At minimum ensure failure reasons are surfaced deterministically by the service.

**Step 2: Run test to verify it fails**
Run: `python -m pytest backend/tests/test_high_quality_snapshot_service.py -q`
Expected: FAIL for missing failure accounting behavior

**Step 3: Write minimal implementation**
Add lightweight structured outcome reporting:
- success
- clip_not_found
- clip_timeout
- clip_invalid
- frame_extract_failed
- snapshot_replace_failed
Do not overbuild a new diagnostics subsystem unless needed.

**Step 4: Run test to verify it passes**
Run: `python -m pytest backend/tests/test_high_quality_snapshot_service.py -q`
Expected: PASS

**Step 5: Commit**
```bash
git add backend/app/services/high_quality_snapshot_service.py backend/tests/test_high_quality_snapshot_service.py
git commit -m "chore: add observability for snapshot replacement outcomes"
```

### Task 7: Verify end-to-end behavior

**Files:**
- Modify: none unless defects are found
- Reference: `docs/plans/2026-03-07-high-quality-event-snapshots-design.md`
- Reference: `docs/plans/2026-03-07-high-quality-event-snapshots-implementation-plan.md`

**Step 1: Run targeted tests**
Run:
```bash
python -m pytest backend/tests/test_config_loader.py -q
python -m pytest backend/tests/test_media_cache.py -q
python -m pytest backend/tests/test_high_quality_snapshot_service.py -q
python -m pytest backend/tests/test_event_processor.py -q
python -m pytest backend/tests/test_proxy_router.py -q
```
Expected: PASS

**Step 2: Run a focused manual backend verification**
Using a real or mocked event with an available clip:
- confirm the original Frigate snapshot appears quickly
- confirm the cached snapshot is later replaced
- confirm the served snapshot endpoint returns the replaced image

**Step 3: Capture timing observations**
Record CPU-only extraction latency and note whether hwaccel is unnecessary for v1.

**Step 4: Commit final verification/docs updates**
```bash
git add docs/plans/2026-03-07-high-quality-event-snapshots-design.md docs/plans/2026-03-07-high-quality-event-snapshots-implementation-plan.md
git commit -m "docs: record high-quality event snapshot design and plan"
```
