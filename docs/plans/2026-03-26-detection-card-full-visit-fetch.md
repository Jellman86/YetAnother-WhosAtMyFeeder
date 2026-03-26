# Detection Card Full-Visit Fetch Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `Fetch full clip` action to detection cards that appears only when a full-visit recording span is available, warms the recording clip defensively, and marks that event to prefer the full-visit variant afterward.

**Architecture:** Add a dedicated backend warm endpoint for the recording clip variant, reusing the existing recording-clip context and media-cache flow with per-event locking. In the UI, track per-event recording availability, fetch state, and preferred clip variant so the detection card can render an explicit action and badge without changing the normal clip path for unrelated events.

**Tech Stack:** FastAPI, httpx, Svelte 5, Vitest, pytest

---

### Task 1: Backend recording fetch endpoint

**Files:**
- Modify: `backend/app/routers/proxy.py`
- Test: `backend/tests/test_proxy.py`

**Step 1: Write the failing test**

Add tests for a new `POST /api/frigate/{event_id}/recording-clip/fetch` route that:
- returns `200` with a ready payload when the recording clip can be fetched
- reuses cached recording clips when present
- returns `404` when the recording span is unavailable

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_proxy.py -q -k recording_clip_fetch`

**Step 3: Write minimal implementation**

Add the endpoint, a per-event lock, and shared helpers so the route can warm the recording clip cache when enabled and otherwise validate availability without breaking the normal playback route.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_proxy.py -q -k recording_clip_fetch`

### Task 2: Detection-card fetch state and badge

**Files:**
- Modify: `apps/ui/src/lib/api/media.ts`
- Modify: `apps/ui/src/lib/components/DetectionCard.svelte`
- Modify: `apps/ui/src/lib/pages/Events.svelte`
- Modify: `apps/ui/src/lib/pages/Dashboard.svelte`
- Test: `apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts`

**Step 1: Write the failing test**

Add a layout test asserting the detection card exposes:
- a `Fetch full clip` action hook
- a `Full visit` badge/icon hook
- the new props needed to thread fetch state through the card

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- detection-card-full-visit.layout.test.ts`

**Step 3: Write minimal implementation**

Thread per-event fetch state from page components into `DetectionCard`, add the explicit fetch button, and show the badge when the event has a ready full-visit clip. After a successful fetch, set that event’s preferred clip variant to `recording`.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- detection-card-full-visit.layout.test.ts`

### Task 3: Verify full flow

**Files:**
- Modify: `README.md` if behavior text changes materially

**Step 1: Run focused backend and frontend tests**

Run:
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_proxy.py -q`
- `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`
- `npm --prefix /config/workspace/YA-WAMF/apps/ui test`

**Step 2: Run docs consistency if API docs change**

Run: `python3 /config/workspace/YA-WAMF/backend/scripts/docs_consistency_check.py`
