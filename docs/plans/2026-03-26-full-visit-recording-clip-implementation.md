# Full-Visit Recording Clip Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a gated full-visit recording clip feature that works across playback, downloads, share links, and public-access paths while only allowing users to enable it when the current Frigate configuration appears compatible.

**Architecture:** Extend YA-WAMF's existing Frigate proxy/media layer with a second clip variant (`recording`) and gate it from Settings using a backend Frigate capability probe derived from `/api/config`. Mirror the auth, cache, and public-access behavior of the existing event clip path instead of inventing a second media subsystem.

**Tech Stack:** FastAPI, Pydantic settings models, httpx, Svelte, TypeScript, Vitest, pytest

---

### Task 1: Add failing backend tests for Frigate recording capability status

**Files:**
- Modify: `backend/tests/test_settings_api.py`
- Modify: `backend/app/routers/settings.py`

**Step 1: Write the failing tests**

Add tests covering:

- supported config with global `record`
- unsupported config with no `record`
- unsupported config with selected cameras lacking recording

Assert the response shape includes:

- `supported`
- `reason`
- `eligible_cameras`
- `retention_days`

**Step 2: Run the targeted tests to verify they fail**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_settings_api.py -q -k recording_capability
```

Expected: FAIL because the endpoint/fields do not exist yet.

**Step 3: Implement the minimal backend capability response**

Add a settings/Frigate capability route that:

- fetches Frigate config
- determines whether recording clips are likely supported
- returns a stable typed payload

Reuse the existing retention parsing helpers in `settings.py` instead of duplicating that logic.

**Step 4: Run the targeted tests again**

Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_settings_api.py backend/app/routers/settings.py
git commit -m "feat(settings): add Frigate recording clip capability probe"
```

### Task 2: Add settings schema for full-visit clip gating and windows

**Files:**
- Modify: `backend/app/config_models.py`
- Modify: `backend/app/config_loader.py`
- Modify: `backend/app/routers/settings.py`
- Modify: `apps/ui/src/lib/api/settings.ts`

**Step 1: Write failing tests for settings round-trip**

Add tests that read/write:

- `recording_clip_enabled`
- `recording_clip_before_seconds`
- `recording_clip_after_seconds`

**Step 2: Run the targeted tests to verify they fail**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_settings_api.py -q -k recording_clip
```

Expected: FAIL because the fields are not yet exposed.

**Step 3: Implement minimal settings support**

Add the three fields to the Frigate settings model, loader defaults, settings API response, and update payload handling.

Also add the fields to the frontend settings type.

**Step 4: Run the tests again**

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/config_models.py backend/app/config_loader.py backend/app/routers/settings.py apps/ui/src/lib/api/settings.ts backend/tests/test_settings_api.py
git commit -m "feat(settings): add full-visit clip settings fields"
```

### Task 3: Add failing backend tests for recording clip proxy routing

**Files:**
- Modify: `backend/tests/test_proxy_api.py`
- Modify: `backend/app/routers/proxy.py`
- Modify: `backend/app/services/frigate_client.py`

**Step 1: Write failing tests**

Add tests for:

- `HEAD /api/frigate/{event_id}/recording-clip.mp4` returns `200` when available
- `GET /api/frigate/{event_id}/recording-clip.mp4` proxies the recording window
- Frigate "No recordings found for the specified time range" becomes `404`
- guest/public-access enforcement matches event clips

Mock the Frigate client instead of depending on live Frigate.

**Step 2: Run the targeted tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_proxy_api.py -q -k recording_clip
```

Expected: FAIL because the route does not exist.

**Step 3: Implement minimal routing**

Add:

- Frigate client helper for camera-level recording clip requests
- route handlers for `HEAD` and `GET`
- DB lookup of `camera_name` and `detection_time`
- normalized `404` for recordings not available

Preserve existing access control behavior from the event clip route.

**Step 4: Re-run the tests**

Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_proxy_api.py backend/app/routers/proxy.py backend/app/services/frigate_client.py
git commit -m "feat(proxy): add full-visit recording clip route"
```

### Task 4: Add separate media-cache support for recording clips

**Files:**
- Modify: `backend/app/services/media_cache.py`
- Modify: `backend/tests/test_media_cache.py`
- Modify: `backend/app/routers/proxy.py`

**Step 1: Write failing cache tests**

Cover:

- separate path/key for recording clips
- no collision with event clips
- cleanup/read behavior still works

**Step 2: Run the tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_media_cache.py -q -k recording
```

Expected: FAIL because recording cache helpers do not exist.

**Step 3: Implement minimal cache support**

Add recording-specific:

- path/key helper
- cache write/read helper
- delete/cleanup coverage if needed

Then wire the recording clip proxy to use the new cache path.

**Step 4: Re-run the tests**

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/media_cache.py backend/tests/test_media_cache.py backend/app/routers/proxy.py
git commit -m "feat(cache): isolate recording clip media cache keys"
```

### Task 5: Add failing frontend tests for settings gate UX

**Files:**
- Create: `apps/ui/src/lib/components/settings/full-visit-gate.layout.test.ts`
- Modify: `apps/ui/src/lib/components/settings/ConnectionSettings.svelte`
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Modify: `apps/ui/src/lib/api/system.ts`

**Step 1: Write failing tests**

Cover:

- capability status panel is rendered
- toggle is bound and disabled when unsupported
- before/after inputs are shown only when enabled

Use source-layout or lightweight component tests consistent with the repo.

**Step 2: Run the tests**

Run:

```bash
npm --prefix apps/ui test -- full-visit-gate.layout.test.ts
```

Expected: FAIL because the UI does not yet expose this.

**Step 3: Implement minimal UI wiring**

Add a typed capability fetch helper and thread state through `Settings.svelte` into `ConnectionSettings.svelte`.

Render:

- capability summary
- gated toggle
- before/after fields

**Step 4: Re-run the tests**

Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/settings/full-visit-gate.layout.test.ts apps/ui/src/lib/components/settings/ConnectionSettings.svelte apps/ui/src/lib/pages/Settings.svelte apps/ui/src/lib/api/system.ts
git commit -m "feat(ui): gate full-visit clips in Frigate settings"
```

### Task 6: Add failing frontend tests for clip variant support in VideoPlayer

**Files:**
- Modify: `apps/ui/src/lib/components/VideoPlayer.svelte`
- Create: `apps/ui/src/lib/components/video-player-recording-clip.layout.test.ts`
- Modify: `apps/ui/src/lib/api/media.ts`

**Step 1: Write failing tests**

Cover:

- recording-clip URL helpers exist
- player can reference both event and recording clip variants
- variant toggle only appears when recording clip probe passes

**Step 2: Run the tests**

Run:

```bash
npm --prefix apps/ui test -- video-player-recording-clip.layout.test.ts
```

Expected: FAIL because variant state and helpers do not exist.

**Step 3: Implement minimal variant support**

Add:

- recording clip URL helper
- availability check helper
- variant state in `VideoPlayer.svelte`
- source switching for playback/download/share URLs

Do not add recording-preview thumbnails in this task.

**Step 4: Re-run the tests**

Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/VideoPlayer.svelte apps/ui/src/lib/components/video-player-recording-clip.layout.test.ts apps/ui/src/lib/api/media.ts
git commit -m "feat(video): add full-visit recording clip variant"
```

### Task 7: Add targeted share/public-access tests for recording clip parity

**Files:**
- Modify: `backend/tests/test_proxy_api.py`
- Modify: `apps/ui/src/lib/components/VideoPlayer.svelte`

**Step 1: Write failing tests**

Add coverage showing recording clips honor:

- owner access
- share token access
- public access restrictions
- clip download restriction rules

**Step 2: Run the targeted tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_proxy_api.py -q -k share
```

Expected: FAIL for the new recording-clip cases.

**Step 3: Implement minimal parity fixes**

Reuse the existing event-clip auth/download logic exactly instead of inventing new rules.

**Step 4: Re-run the tests**

Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_proxy_api.py backend/app/routers/proxy.py apps/ui/src/lib/components/VideoPlayer.svelte
git commit -m "test(proxy): cover recording clip auth and share parity"
```

### Task 8: Update docs and run final verification

**Files:**
- Modify: `README.md`
- Modify: `docs/api.md`
- Modify: `docs/troubleshooting/diagnostics.md`
- Modify: `CHANGELOG.md`
- Modify: `ROADMAP.md`

**Step 1: Update docs**

Document:

- full-visit clip settings and gating
- capability diagnostics
- new proxy endpoint
- roadmap status change if the implementation is complete

**Step 2: Run backend verification**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_settings_api.py -q -k recording
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_proxy_api.py -q -k recording
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_media_cache.py -q -k recording
```

Expected: PASS

**Step 3: Run frontend verification**

Run:

```bash
npm --prefix apps/ui run check
npm --prefix apps/ui test
```

Expected: PASS

**Step 4: Run docs-quality verification**

Run:

```bash
python3 backend/scripts/docs_consistency_check.py
```

Expected: PASS

**Step 5: Commit**

```bash
git add README.md docs/api.md docs/troubleshooting/diagnostics.md CHANGELOG.md ROADMAP.md
git commit -m "docs: document full-visit recording clip support"
```
