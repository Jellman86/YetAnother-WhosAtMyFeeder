# Blocked Species Picker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add structured blocked-species support, conservative migration of legacy blocked labels, and a manual-tag-style species picker in Detection Settings.

**Architecture:** Extend backend settings and block-matching to support a new structured `blocked_species` list while preserving legacy `blocked_labels`. On the frontend, add a small helper-driven migration layer plus a picker UI in `DetectionSettings.svelte`, keeping unresolved legacy entries visible and round-tripped safely.

**Tech Stack:** FastAPI, Pydantic, Svelte 5, Vitest, pytest.

---

### Task 1: Backend Settings Schema + Round-Trip

**Files:**
- Modify: `backend/app/config_models.py`
- Modify: `backend/app/config_loader.py`
- Modify: `backend/app/routers/settings.py`
- Test: `backend/tests/test_settings_api.py`

**Step 1: Write the failing test**

Add a settings API round-trip test for `blocked_species`.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_settings_api.py -q -k blocked_species`
Expected: FAIL because `blocked_species` is not in the schema/API yet.

**Step 3: Write minimal implementation**

Add the structured model and thread it through config defaults and the settings GET/POST path.

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_settings_api.py -q -k blocked_species`
Expected: PASS

### Task 2: Backend Block Matching

**Files:**
- Create: `backend/app/utils/blocked_species.py`
- Modify: `backend/app/services/detection_service.py`
- Modify: `backend/app/routers/events.py`
- Test: `backend/tests/test_detection_service_filter.py`
- Test: `backend/tests/test_detection_service.py`
- Test: `backend/tests/test_event_manual_update_api.py`

**Step 1: Write the failing tests**

Add:
- filter test proving structured blocked species can suppress a live classification
- save-detection test proving taxonomy-resolved `taxa_id` / scientific names are blocked
- manual-tag test proving structured blocked species returns 422

**Step 2: Run tests to verify they fail**

Run:
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_detection_service_filter.py -q -k blocked`
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_detection_service.py -q -k blocked`
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_event_manual_update_api.py -q -k blocked`

Expected: FAIL before helper integration.

**Step 3: Write minimal implementation**

Create a shared helper for sanitizing structured entries and checking mixed legacy/structured blocklists. Use it in live filtering, post-taxonomy save filtering, video-result promotion, and manual tag guard.

**Step 4: Run tests to verify they pass**

Run the same commands above.

### Task 3: Frontend Migration Helper

**Files:**
- Create: `apps/ui/src/lib/settings/blocked-species.ts`
- Create: `apps/ui/src/lib/settings/blocked-species.test.ts`
- Modify: `apps/ui/src/lib/api/settings.ts`

**Step 1: Write the failing test**

Add tests for:
- converting a selected species result into a structured blocked-species entry
- conservative migration of legacy blocked labels with unresolved leftovers preserved

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- blocked-species.test.ts`
Expected: FAIL because the helper does not exist yet.

**Step 3: Write minimal implementation**

Implement helper functions for normalization, chip formatting, and conservative legacy migration.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- blocked-species.test.ts`
Expected: PASS

### Task 4: Settings Page + Detection Settings UI

**Files:**
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`
- Create: `apps/ui/src/lib/components/settings/blocked-species.layout.test.ts`

**Step 1: Write the failing wiring test**

Add a source-based layout test proving `blockedSpecies` is threaded through Settings into Detection Settings.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- blocked-species.layout.test.ts`
Expected: FAIL because bindings/UI do not exist yet.

**Step 3: Write minimal implementation**

Add local `blockedSpecies` state plus baseline state to `Settings.svelte`, run conservative migration during settings load, include `blocked_species` in save payload and dirty tracking, and replace the Detection Settings add flow with a picker/search result list plus structured/legacy chips.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- blocked-species.layout.test.ts`
Expected: PASS

### Task 5: Docs + Verification

**Files:**
- Modify: `ROADMAP.md`
- Modify: `CHANGELOG.md`

**Step 1: Update docs**

Mark roadmap item 1 complete if the structured picker and reliable mixed matching ship together. Add a changelog note under `Unreleased`.

**Step 2: Run verification**

Run:
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_settings_api.py -q -k blocked_species`
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_detection_service_filter.py -q -k blocked`
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_detection_service.py -q -k blocked`
- `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_event_manual_update_api.py -q -k blocked`
- `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- blocked-species.test.ts blocked-species.layout.test.ts`
- `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`
- `npm --prefix /config/workspace/YA-WAMF/apps/ui test`
