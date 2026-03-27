# Automatic Full-Visit Replacement Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically generate persisted full-visit clips for eligible finished detections and make YA-WAMF's normal `/clip.mp4` route serve that persisted full-visit file whenever it exists.

**Architecture:** Extend the Frigate MQTT/event pipeline with a narrow `end`-event full-visit trigger, back it with a small retryable background generation service plus a bounded reconciler, and change the existing clip proxy to prefer the persisted recording-clip cache key before falling back to the normal event clip path. Keep the dedicated recording-clip route and manual fetch path as compatibility and recovery affordances.

**Tech Stack:** FastAPI, asyncio, httpx, Pydantic settings, pytest, Svelte, TypeScript, Vitest

---

### Task 1: Add failing tests for automatic full-visit trigger on Frigate `end`

**Files:**
- Modify: `backend/tests/test_event_processor.py`
- Modify: `backend/app/services/event_processor.py`

**Step 1: Write the failing tests**

Add tests showing:

- a `bird` MQTT payload with `type="end"` schedules automatic full-visit generation when recording clips are enabled
- a `bird` MQTT payload with `type="new"` still does not schedule the automatic full-visit path
- false-positive events do not schedule automatic full-visit generation

Patch the eventual background trigger dependency rather than running the real fetch logic.

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_event_processor.py -q -k full_visit
```

Expected: FAIL because `end` events are currently ignored.

**Step 3: Write minimal implementation**

Update `backend/app/services/event_processor.py` so eligible `bird` `end` events are no longer discarded outright. Route them into a narrow automatic full-visit trigger path that:

- validates `clips_enabled` and `recording_clip_enabled`
- avoids the main snapshot classification/save flow
- delegates to a dedicated async trigger helper

Keep `new` event behavior unchanged.

**Step 4: Run test to verify it passes**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_event_processor.py -q -k full_visit
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_event_processor.py backend/app/services/event_processor.py
git commit -m "feat(video): trigger auto full-visit generation on end events"
```

### Task 2: Add failing tests for a reusable automatic full-visit generation service

**Files:**
- Create: `backend/tests/test_full_visit_clip_service.py`
- Create: `backend/app/services/full_visit_clip_service.py`

**Step 1: Write the failing tests**

Add tests covering:

- no-op when recording clips are disabled
- no-op when `{event_id}_recording.mp4` already exists
- successful fetch persists the recording clip through the existing media-cache service
- temporary recording unavailability is retried before failing
- duplicate triggers for the same event reuse a per-event lock instead of downloading twice

Mock:

- `_get_recording_clip_context`-equivalent context lookup
- Frigate HTTP responses
- media-cache writes

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_full_visit_clip_service.py -q
```

Expected: FAIL because the service does not exist yet.

**Step 3: Write minimal implementation**

Create `backend/app/services/full_visit_clip_service.py` with a small service that:

- exposes `trigger_for_event(event_id, camera, *, source="mqtt_end")`
- reuses existing recording-clip context logic
- fetches and persists the full-visit clip to `{event_id}_recording.mp4`
- retries transient failures a small bounded number of times
- uses per-event locking for idempotency

Keep this service focused on orchestration, not UI or proxy behavior.

**Step 4: Run test to verify it passes**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_full_visit_clip_service.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_full_visit_clip_service.py backend/app/services/full_visit_clip_service.py
git commit -m "feat(video): add automatic full-visit generation service"
```

### Task 3: Add failing tests for `/clip.mp4` preferring the persisted full-visit file

**Files:**
- Modify: `backend/tests/test_proxy.py`
- Modify: `backend/app/routers/proxy.py`

**Step 1: Write the failing tests**

Add tests showing:

- `GET /api/frigate/{event_id}/clip.mp4` serves `{event_id}_recording.mp4` when it exists
- `GET /api/frigate/{event_id}/clip.mp4` falls back to the normal cached or proxied event clip when the recording file does not exist
- `HEAD /api/frigate/{event_id}/clip.mp4` still behaves sensibly for normal clip availability checks

Mock the cache methods directly.

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_proxy.py -q -k "recording_clip or clip_prefers_recording"
```

Expected: FAIL because `/clip.mp4` currently checks only the normal event clip cache key.

**Step 3: Write minimal implementation**

Update `backend/app/routers/proxy.py` so the normal `/clip.mp4` route prefers `media_cache.get_recording_clip_path(event_id)` before checking `media_cache.get_clip_path(event_id)`.

Preserve:

- auth behavior
- guest/public-access rules
- filename/content-disposition behavior
- existing fallback to the normal Frigate event clip path

**Step 4: Run test to verify it passes**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_proxy.py -q -k "recording_clip or clip_prefers_recording"
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_proxy.py backend/app/routers/proxy.py
git commit -m "feat(proxy): prefer persisted full-visit clips on clip route"
```

### Task 4: Add failing tests for recent-detection reconciliation

**Files:**
- Modify: `backend/tests/test_full_visit_clip_service.py`
- Modify: `backend/app/services/full_visit_clip_service.py`
- Modify: `backend/app/repositories/detection_repository.py`

**Step 1: Write the failing tests**

Add tests covering:

- a reconciler scan picks recent detections old enough to have a complete recording window
- detections with an existing persisted recording clip are skipped
- detections too recent to have a complete window are skipped
- reconciliation reuses the same generation trigger path as MQTT `end`

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_full_visit_clip_service.py -q -k reconcile
```

Expected: FAIL because no reconciler exists yet.

**Step 3: Write minimal implementation**

Add:

- a repository query for recent eligible detections
- a bounded reconciliation method in `full_visit_clip_service.py`
- startup/task wiring only if needed to run the reconciler on an interval

Keep the initial scan small and bounded by age/time window so it cannot grow unbounded.

**Step 4: Run test to verify it passes**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_full_visit_clip_service.py -q -k reconcile
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_full_visit_clip_service.py backend/app/services/full_visit_clip_service.py backend/app/repositories/detection_repository.py
git commit -m "feat(video): reconcile missing automatic full-visit clips"
```

### Task 5: Add failing tests for retained frontend replacement cues

**Files:**
- Modify: `apps/ui/src/lib/stores/full-visit.test.ts`
- Modify: `apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts`
- Modify: `apps/ui/src/lib/api/media.ts`

**Step 1: Write the failing tests**

Add tests showing:

- the primary clip URL remains `/clip.mp4`
- persisted full-visit state still marks the event as fetched/ready
- layout cues for the existing `Full visit` badge remain intact

Do not redesign the player in this task.

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- full-visit.test.ts detection-card-full-visit.layout.test.ts
```

Expected: FAIL for any assumptions that still require manual-only full-visit replacement.

**Step 3: Write minimal implementation**

Adjust frontend helpers only as needed so existing full-visit state remains compatible with the new backend replacement model. Keep `/clip.mp4` as the main playback URL and preserve the badge/store semantics.

**Step 4: Run test to verify it passes**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- full-visit.test.ts detection-card-full-visit.layout.test.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/stores/full-visit.test.ts apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts apps/ui/src/lib/api/media.ts
git commit -m "test(ui): retain full-visit cues with automatic replacement"
```

### Task 6: Run focused regression coverage and update docs

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `ROADMAP.md`
- Modify: `README.md`
- Modify: `docs/api.md`
- Modify: `docs/setup/frigate-config.md`

**Step 1: Write/update the docs**

Document that:

- enabling recording clips now implies automatic generation for eligible completed detections
- YA-WAMF's normal clip route prefers the persisted full-visit clip once generated
- Frigate itself is not modified
- manual fetch remains as a fallback/recovery path

**Step 2: Run focused backend tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_event_processor.py /config/workspace/YA-WAMF/backend/tests/test_full_visit_clip_service.py /config/workspace/YA-WAMF/backend/tests/test_proxy.py -q
```

Expected: PASS

**Step 3: Run focused frontend tests**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- full-visit.test.ts detection-card-full-visit.layout.test.ts video-player-recording-clip.layout.test.ts
```

Expected: PASS

**Step 4: Run static validation**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_media_cache.py -q -k recording
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
```

Expected: PASS

**Step 5: Commit**

```bash
git add CHANGELOG.md ROADMAP.md README.md docs/api.md docs/setup/frigate-config.md
git commit -m "docs: describe automatic full-visit replacement"
```
