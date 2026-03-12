# Issue 23 eBird Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make YA-WAMF's eBird CSV export a strict, importer-safe eBird Record Format export with English-stable names and optional single-day filtering.

**Architecture:** Tighten the existing `/api/ebird/export` route into a strict formatter instead of a best-effort dump. Add a small backend export helper for deterministic row formatting and English-name resolution, plus a minimal UI date filter and regression coverage for exact output shape.

**Tech Stack:** FastAPI, Python CSV streaming, existing SQLite detections data, Svelte UI, pytest

---

### Task 1: Lock the export contract with failing backend tests

**Files:**
- Create: `backend/tests/test_ebird_export.py`
- Modify: `backend/app/routers/ebird.py`

**Step 1: Write the failing test**

Add tests for:
- no header row
- exact 19 columns
- `MM/DD/YYYY` date formatting
- `HH:MM` start-time formatting
- provenance text in submission comments
- export allowed even when eBird API is disabled

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_ebird_export.py -q`
Expected: FAIL because the strict contract is not fully implemented and the test file is new.

**Step 3: Write minimal implementation**

In `backend/app/routers/ebird.py`:
- extract row building into small helpers
- remove the eBird API-key/config requirement from export
- preserve streaming behavior
- emit strict 19-column rows only

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_ebird_export.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_ebird_export.py backend/app/routers/ebird.py
git commit -m "fix(ebird): enforce strict export format"
```

### Task 2: Add English-stable name resolution and date filtering

**Files:**
- Modify: `backend/app/routers/ebird.py`
- Test: `backend/tests/test_ebird_export.py`

**Step 1: Write the failing test**

Add tests for:
- `date=YYYY-MM-DD` filters rows correctly
- export common name remains English-stable even when `settings.ebird.locale` is non-English
- export does not depend on UI display name

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_ebird_export.py -q`
Expected: FAIL because filtering and English pinning are not fully implemented.

**Step 3: Write minimal implementation**

In `backend/app/routers/ebird.py`:
- add optional `date` query parsing
- constrain the SQL query by detection-day when a date is supplied
- add deterministic English-name resolution for export rows
- keep fail-open local behavior; do not add remote eBird dependency

**Step 4: Run test to verify it passes**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_ebird_export.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/routers/ebird.py backend/tests/test_ebird_export.py
git commit -m "feat(ebird): add strict day-scoped export filtering"
```

### Task 3: Add minimal UI date filter and request plumbing

**Files:**
- Modify: `apps/ui/src/lib/api/species.ts`
- Modify: `apps/ui/src/lib/components/settings/IntegrationSettings.svelte`
- Test: `apps/ui/src/lib/api/species.ts` (existing test location if present) or create a small UI/unit test only if repo patterns support it cleanly

**Step 1: Write the failing test**

If there is an existing test pattern for the API helper or integration settings export flow, add a test asserting that an optional date is appended to the export request. If no clean local pattern exists, document this and keep verification manual for the UI helper.

**Step 2: Run test to verify it fails**

Run the relevant Vitest command if a test is added.

**Step 3: Write minimal implementation**

- extend `exportEbirdCsv()` to accept an optional date
- add a simple date picker next to the export action
- keep blank as “all detections”

**Step 4: Run test to verify it passes**

Run the relevant Vitest command if applicable.

**Step 5: Commit**

```bash
git add apps/ui/src/lib/api/species.ts apps/ui/src/lib/components/settings/IntegrationSettings.svelte
git commit -m "feat(ebird): add export date filter control"
```

### Task 4: Update changelog and run widened verification

**Files:**
- Modify: `CHANGELOG.md`
- Test: `backend/tests/test_ebird_export.py`
- Test: any touched backend/UI tests

**Step 1: Update changelog**

Add an unreleased entry stating that eBird export now emits strict Record Format CSV, uses English-stable names, supports date filtering, and no longer depends on eBird API credentials.

**Step 2: Run focused backend verification**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_ebird_export.py \
  backend/tests/test_ebird_service.py \
  -q
```

Expected: PASS

**Step 3: Run widened verification**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_ebird_export.py \
  backend/tests/test_ebird_service.py \
  backend/tests/test_settings_api.py \
  -q
```

And if a UI test/helper was added, run the relevant Vitest command for that file.

**Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(ebird): document strict export compatibility"
```
