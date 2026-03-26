# Manual Tag Picker Common Name Resolution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refresh stale issue-tracking docs and fix the manual-tag species picker so typed searches hydrate missing taxonomy/common names and parenthetical labels resolve cleanly.

**Architecture:** Extend the existing species search hydration API test coverage for parenthetical labels, add a tiny frontend helper that defines the manual-tag search request policy, then wire `DetectionModal` to use it. Update roadmap and issue-tracker docs to reflect the now-closed GitHub issue state and the completion of this roadmap item.

**Tech Stack:** FastAPI, pytest, Svelte 5, Vitest, markdown docs.

---

### Task 1: Backend Hydration Regression Test

**Files:**
- Modify: `backend/tests/test_species_search_api.py`
- Modify: `backend/app/routers/species.py`

**Step 1: Write the failing test**

Add a test proving `hydrate_missing=true` strips a trailing classifier parenthetical before calling `taxonomy_service.get_names()`.

**Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_species_search_api.py -q -k parenthetical`
Expected: FAIL because the router still sends the raw parenthetical label.

**Step 3: Write minimal implementation**

Use `collapse_classifier_label(..., strategy="strip_trailing_parenthetical")` inside `_hydrate_one`.

**Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_species_search_api.py -q -k parenthetical`
Expected: PASS

### Task 2: Frontend Manual-Tag Search Policy

**Files:**
- Create: `apps/ui/src/lib/search/manual-tag-search.ts`
- Create: `apps/ui/src/lib/search/manual-tag-search.test.ts`
- Modify: `apps/ui/src/lib/components/DetectionModal.svelte`

**Step 1: Write the failing test**

Add a unit test proving manual-tag typed searches longer than 2 characters request `hydrateMissing=true`, while short/blank queries do not.

**Step 2: Run test to verify it fails**

Run: `npm --prefix apps/ui test -- manual-tag-search.test.ts`
Expected: FAIL because the helper does not exist yet.

**Step 3: Write minimal implementation**

Create a helper that returns `{ limit: 50, hydrateMissing: query.trim().length > 2 }` and wire `DetectionModal` to use it for typed queries.

**Step 4: Run test to verify it passes**

Run: `npm --prefix apps/ui test -- manual-tag-search.test.ts`
Expected: PASS

### Task 3: Docs Refresh

**Files:**
- Modify: `ROADMAP.md`
- Modify: `ISSUES.md`

**Step 1: Update stale tracker references**

Mark the issue-triage section as cleared of open GitHub issues and remove outdated “awaiting reporter confirmation” language for closed issues.

**Step 2: Update roadmap item status**

Mark the manual-tag picker common-name resolution item as completed and note the shipped behavior at a high level.

### Task 4: Verification

**Files:**
- Test: `backend/tests/test_species_search_api.py`
- Test: `apps/ui/src/lib/search/manual-tag-search.test.ts`

**Step 1: Run focused backend test file**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_species_search_api.py -q`

**Step 2: Run focused frontend tests**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- manual-tag-search.test.ts`

**Step 3: Run frontend typecheck**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`

**Step 4: Run full frontend unit suite**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test`

