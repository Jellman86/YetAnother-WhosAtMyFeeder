# eBird Export Date Range Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the single eBird export date with inclusive `from`/`to` date filters in the backend API and settings UI.

**Architecture:** Extend `/api/ebird/export` to accept optional inclusive `from` and `to` query params while preserving current CSV generation rules. Update the frontend export helper and settings card to use two date inputs, validate the range client-side, and keep empty inputs meaning "export all detections."

**Tech Stack:** FastAPI, SQLite, Svelte, Vitest, pytest

---

### Task 1: Range API tests

**Files:**
- Modify: `backend/tests/test_ebird_export.py`

1. Add a failing test for inclusive `from`/`to` filtering across multiple days.
2. Add a failing test for `from`-only and `to`-only behavior.
3. Run the targeted pytest command and confirm the new tests fail for the expected missing query support.

### Task 2: Range API implementation

**Files:**
- Modify: `backend/app/routers/ebird.py`

1. Replace the single `date` query param with optional `from` and `to`.
2. Apply inclusive date filtering using start-of-day and next-day upper bounds.
3. Keep existing CSV semantics unchanged for protocol, duration buckets, English names, and comments.
4. Run the targeted pytest command and confirm the new tests pass.

### Task 3: Frontend API tests

**Files:**
- Modify: `apps/ui/src/lib/api/species.test.ts`

1. Add failing tests for `from`/`to`, `from`-only, `to`-only, and empty export requests.
2. Run the targeted Vitest command and confirm the new tests fail for the expected signature mismatch.

### Task 4: Frontend range UI

**Files:**
- Modify: `apps/ui/src/lib/api/species.ts`
- Modify: `apps/ui/src/lib/components/settings/IntegrationSettings.svelte`
- Modify: `apps/ui/src/lib/i18n/locales/en.json`
- Modify: other locale JSON files under `apps/ui/src/lib/i18n/locales/`

1. Change the export helper to accept optional `from` and `to`.
2. Replace the single export date input with `From` and `To` inputs.
3. Disable export and show a concise inline error when `from > to`.
4. Update locale strings for the new labels/help text.
5. Run the targeted UI tests and confirm they pass.

### Task 5: Verification and docs

**Files:**
- Modify: `CHANGELOG.md`

1. Update the changelog entry to describe inclusive date-range export.
2. Run backend pytest, frontend Vitest, `npm run check`, and `npm run build`.
3. Run `git diff --check`.
