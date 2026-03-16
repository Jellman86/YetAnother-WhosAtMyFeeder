# Issue 23 Strict eBird Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the eBird export route emit only strict importer-safe rows by excluding `Unknown Bird` and non-English fallback rows.

**Architecture:** Keep a single backend export route and harden it into a strict formatter. Frontend export controls stay unchanged; the main work is in backend row filtering plus regression coverage proving the route shape and content are consistent.

**Tech Stack:** FastAPI, SQLite, pytest, Svelte/Vitest for existing frontend coverage

---

### Task 1: Add failing backend export tests

**Files:**
- Modify: `backend/tests/test_ebird_export.py`

1. Add a failing test proving `Unknown Bird` rows are excluded from export.
2. Add a failing test proving localized/common-name fallback rows are excluded when no English taxonomy name is available.
3. Run targeted pytest and confirm those tests fail before implementation.

### Task 2: Harden backend export filtering

**Files:**
- Modify: `backend/app/routers/ebird.py`

1. Add explicit strict row eligibility checks.
2. Exclude unknown-label rows before writing CSV.
3. Remove localized fallback for column 1 so only English taxonomy-backed common names are exported.
4. Run targeted pytest and confirm the new tests pass.

### Task 3: Keep range/export path consistent

**Files:**
- Modify: `backend/tests/test_ebird_export.py`

1. Add/adjust one range-filter test to prove suppression rules still apply under `from` / `to` filtering.
2. Run the focused eBird export test file and confirm all pass.

### Task 4: Verification and changelog

**Files:**
- Modify: `CHANGELOG.md`

1. Add an unreleased note documenting strict exclusion of `Unknown Bird` and non-English fallback rows.
2. Run the eBird export backend tests.
3. Run `git diff --check`.
4. Optionally perform one direct local export request verification against the running backend if available.
