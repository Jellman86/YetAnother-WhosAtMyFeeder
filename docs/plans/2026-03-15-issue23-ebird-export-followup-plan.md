# Issue 23 eBird Export Follow-up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reopen and complete issue `#23` by aligning eBird export behavior with the latest GitHub comment and adding the missing single-day export date picker in the UI.

**Architecture:** Tighten the backend export route with explicit per-date duration and submission-comment formatting, preserving the strict 19-column CSV contract. Then wire the existing UI export flow to expose the optional `date` parameter directly with a small date input, and verify both backend and frontend with focused regression coverage.

**Tech Stack:** FastAPI, SQLite, pytest, Svelte 5, TypeScript, Vitest

---

### Task 1: Reopen the issue and red-test the new export contract

**Files:**
- Modify: `backend/tests/test_ebird_export.py`
- Reference: `backend/app/routers/ebird.py`

**Step 1: Reopen issue 23**

Run:

```bash
gh issue reopen 23 --repo Jellman86/YetAnother-WhosAtMyFeeder
```

Expected: issue state becomes `OPEN`

**Step 2: Write the failing tests**

Extend `backend/tests/test_ebird_export.py` with focused tests for:

- protocol column is `Stationary`
- duration column reflects first-to-last detection minutes for a date
- multi-date exports compute duration per date bucket
- submission comments include model and confidence when available

Example shape:

```python
@pytest.mark.asyncio
async def test_ebird_export_uses_stationary_protocol_and_daily_duration(client):
    ...
    assert row[12] == "Stationary"
    assert row[17] == "42"
```

**Step 3: Run tests to verify they fail**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_ebird_export.py -q
```

Expected: FAIL because the route still emits `Incidental`, blank duration, and older submission-comment formatting

**Step 4: Write minimal implementation**

Update `backend/app/routers/ebird.py` to:

- compute per-date observation windows before streaming rows
- emit `Stationary`
- populate duration column
- include model/confidence in submission comments when available
- keep strict date/time field formatting and English-name forcing

**Step 5: Run tests to verify they pass**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_ebird_export.py -q
```

Expected: PASS

**Step 6: Commit**

```bash
git add backend/tests/test_ebird_export.py backend/app/routers/ebird.py
git commit -m "fix: align ebird export with issue23 follow-up"
```

### Task 2: Add the UI export date-picker workflow

**Files:**
- Modify: `apps/ui/src/lib/api/species.ts`
- Modify: `apps/ui/src/lib/api/species.test.ts`
- Modify the eBird export UI component/page discovered in repo search
- Modify relevant locale file(s) for export-date copy

**Step 1: Write the failing tests**

Add/extend frontend tests so they prove:

- blank date calls `/api/ebird/export`
- selected date calls `/api/ebird/export?date=YYYY-MM-DD`

If a UI test already exists for the export surface, extend it; otherwise keep the red/green coverage at the API helper and use `svelte-check`/build for UI integration.

**Step 2: Run tests to verify they fail**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/api/species.test.ts
```

Expected: FAIL if the current helper or UI still ignores the selected date

**Step 3: Write minimal implementation**

Update the UI export surface to:

- add a date input next to the eBird export action
- call the existing export helper with optional date
- keep empty date behavior as export-all

**Step 4: Run tests to verify they pass**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/api/species.test.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/api/species.ts apps/ui/src/lib/api/species.test.ts <ui-export-surface> <locale-files>
git commit -m "feat: add ebird export date picker"
```

### Task 3: Harden country/state behavior and keep output deterministic

**Files:**
- Modify: `backend/app/routers/ebird.py`
- Modify: `backend/tests/test_ebird_export.py`
- Reference config/settings files if reliable location fields exist

**Step 1: Write the failing tests**

Add tests proving:

- reliable local/configured country/state values are used when present
- otherwise those columns remain blank rather than guessed

**Step 2: Run tests to verify they fail**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_ebird_export.py -q
```

Expected: FAIL until route behavior matches the new deterministic rule

**Step 3: Write minimal implementation**

Add a small local resolver in the export route/helper that only uses reliable in-app values and otherwise leaves columns blank.

**Step 4: Run tests to verify they pass**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_ebird_export.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/routers/ebird.py backend/tests/test_ebird_export.py
git commit -m "fix: keep ebird location fields deterministic"
```

### Task 4: Update changelog and full verification

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Update changelog**

Add an unreleased note that eBird export now:

- follows the issue-23 follow-up semantics
- uses `Stationary`
- fills duration
- includes model/confidence in submission comments when available
- exposes the UI export date picker

**Step 2: Run backend verification**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_ebird_export.py backend/tests/test_ebird_api.py backend/tests/test_ebird_service.py -q
```

Expected: PASS

**Step 3: Run frontend verification**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/api/species.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
npm --prefix /config/workspace/YA-WAMF/apps/ui run build
git -C /config/workspace/YA-WAMF diff --check
```

Expected: PASS

**Step 4: Final commit**

```bash
git add CHANGELOG.md
git commit -m "chore: document issue23 export follow-up"
```
