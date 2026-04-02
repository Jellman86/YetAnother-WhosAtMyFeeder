# Canonical Full-Visit Clip Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current clip-vs-full-visit player choice with one canonical `/clip.mp4` playback contract that automatically promotes persisted full visits for both authenticated and guest/public users, while showing a visible “full visit” indicator in the UI.

**Architecture:** Keep the backend promotion behavior centered on the canonical `/api/frigate/{event_id}/clip.mp4` route. Remove playback-variant choice from the UI and reduce the full-visit store to readiness/indicator state only. Treat `/recording-clip.mp4` as an internal fetch/probe path rather than a user-facing playback variant.

**Tech Stack:** FastAPI, Python, Svelte 5, TypeScript, Vitest, pytest.

---

### Task 1: Lock the canonical backend clip contract with tests

**Files:**
- Modify: `backend/tests/test_proxy.py`
- Verify: `backend/app/routers/proxy.py`

**Step 1: Write the failing test**

Add or extend tests that assert:

- `/api/frigate/{event_id}/clip.mp4` returns the short event clip when no promoted full visit exists
- `/api/frigate/{event_id}/clip.mp4` returns the persisted recording clip when one exists
- guest/public share-token access sees the same promoted canonical clip behavior

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_proxy.py -k 'clip and recording' -q`
Expected: FAIL if any legacy direct-recording assumptions remain exposed in the canonical route behavior.

**Step 3: Write minimal implementation**

In `backend/app/routers/proxy.py`, tighten any remaining route logic so:

- `/clip.mp4` is always the best-available canonical clip
- auth/public access paths share the same variant-selection behavior
- `/recording-clip.mp4` remains non-canonical

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_proxy.py -k 'clip and recording' -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_proxy.py backend/app/routers/proxy.py
git commit -m "test(proxy): lock canonical full-visit clip promotion"
```

### Task 2: Remove playback-variant switching from the full-visit store

**Files:**
- Modify: `apps/ui/src/lib/stores/full-visit.svelte`
- Modify: `apps/ui/src/lib/stores/full-visit.test.ts`

**Step 1: Write the failing test**

Add store tests that assert:

- the store tracks readiness/promotion state, not clip preference
- promotion clears any need for a user playback choice
- restored state does not attempt to force a separate recording-clip playback route

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/full-visit.test.ts`
Expected: FAIL because the current store still models user-facing full-visit preference.

**Step 3: Write minimal implementation**

Simplify the store to expose only:

- whether full-visit fetching is available
- whether the event has a promoted full visit
- fetch lifecycle status

Remove client-side playback-variant preference and any local-storage behavior that exists only to remember the toggle.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/full-visit.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/stores/full-visit.svelte apps/ui/src/lib/stores/full-visit.test.ts
git commit -m "refactor(ui): collapse full-visit store to readiness state"
```

### Task 3: Collapse the player to one canonical clip URL

**Files:**
- Modify: `apps/ui/src/lib/api/media.ts`
- Modify: `apps/ui/src/lib/components/DetectionCard.svelte`
- Modify: `apps/ui/src/lib/components/DetectionModal.svelte`
- Modify: `apps/ui/src/lib/pages/Dashboard.svelte`
- Modify: `apps/ui/src/lib/pages/Events.svelte`
- Test: `apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts`
- Test: `apps/ui/src/lib/components/detection-modal-full-visit.layout.test.ts`
- Test: `apps/ui/src/lib/components/video-player-recording-clip.layout.test.ts`

**Step 1: Write the failing test**

Update layout/source tests so they assert:

- playback uses canonical `/clip.mp4`
- the UI no longer offers a short/full toggle
- the fetch action remains only before promotion

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-card-full-visit.layout.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-modal-full-visit.layout.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/video-player-recording-clip.layout.test.ts
```

Expected: FAIL because the current UI still references recording-clip playback and toggle wiring.

**Step 3: Write minimal implementation**

Update the media API and consuming components so:

- the player always uses canonical `/clip.mp4`
- fetch controls still call the full-visit fetch endpoint when appropriate
- recording-clip playback URLs are removed from user-facing selection logic
- old toggle UI/state is deleted

**Step 4: Run test to verify it passes**

Run the same three commands again.
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/api/media.ts apps/ui/src/lib/components/DetectionCard.svelte apps/ui/src/lib/components/DetectionModal.svelte apps/ui/src/lib/pages/Dashboard.svelte apps/ui/src/lib/pages/Events.svelte apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts apps/ui/src/lib/components/detection-modal-full-visit.layout.test.ts apps/ui/src/lib/components/video-player-recording-clip.layout.test.ts
git commit -m "feat(ui): use canonical clip route for full visits"
```

### Task 4: Add a visible promoted full-visit indicator

**Files:**
- Modify: `apps/ui/src/lib/components/DetectionCard.svelte`
- Modify: `apps/ui/src/lib/components/DetectionModal.svelte`
- Modify: `apps/ui/src/lib/i18n/locales/en.json`
- Test: `apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts`
- Test: `apps/ui/src/lib/components/detection-modal-full-visit.layout.test.ts`

**Step 1: Write the failing test**

Add assertions that the UI renders a visible indicator when the canonical clip is a promoted full visit, for both card and modal surfaces.

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-card-full-visit.layout.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-modal-full-visit.layout.test.ts
```

Expected: FAIL because the new indicator is not yet rendered.

**Step 3: Write minimal implementation**

Render a compact passive indicator such as `Full visit` when promotion is active:

- visible near the video controls or metadata
- not interactive
- consistent across authenticated and guest/public rendering paths

**Step 4: Run test to verify it passes**

Run the same two commands again.
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/DetectionCard.svelte apps/ui/src/lib/components/DetectionModal.svelte apps/ui/src/lib/i18n/locales/en.json apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts apps/ui/src/lib/components/detection-modal-full-visit.layout.test.ts
git commit -m "feat(ui): indicate promoted full-visit clips"
```

### Task 5: Final verification and changelog

**Files:**
- Modify: `CHANGELOG.md`
- Verify: `backend/tests/test_proxy.py`
- Verify: `apps/ui/src/lib/stores/full-visit.test.ts`
- Verify: `apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts`
- Verify: `apps/ui/src/lib/components/detection-modal-full-visit.layout.test.ts`
- Verify: `apps/ui/src/lib/components/video-player-recording-clip.layout.test.ts`

**Step 1: Write the failing test**

No new failing test here. This task is verification and documentation only.

**Step 2: Run relevant checks**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_proxy.py -q
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/full-visit.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-card-full-visit.layout.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-modal-full-visit.layout.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/video-player-recording-clip.layout.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
```

Expected: PASS

**Step 3: Update changelog**

Add an `Unreleased` note explaining that YA-WAMF now promotes full visits into the canonical clip route and shows a visible full-visit indicator instead of exposing a clip-selection toggle.

**Step 4: Manual verification**

Verify on authenticated and guest/public views:

- before promotion, the player shows the short clip and optional `Fetch full clip`
- after manual fetch, the same `/clip.mp4` playback becomes the full visit
- after automatic generation, the player directly shows the full visit
- the `Full visit` indicator is visible whenever promotion is active
- no clip/full toggle remains anywhere in the UI

**Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: note canonical full-visit clip behavior"
```
