# Jobs Stable Slots Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make active jobs stay in stable visual slots in the Jobs view and ensure weather-backfill counters populate consistently.

**Architecture:** Add a UI-only slot allocator for active jobs so card positions remain stable while jobs are active, and normalize weather-backfill totals through the existing scoped-progress flow so running counters stop showing empty denominators.

**Tech Stack:** Svelte 5, TypeScript, Vitest

---

### Task 1: Add stable active-job slot allocation helper

**Files:**
- Create: `apps/ui/src/lib/jobs/active-slots.ts`
- Test: `apps/ui/src/lib/jobs/active-slots.test.ts`

**Step 1: Write the failing test**

Cover:
- two jobs get slots `0` and `1`
- timestamp updates do not move them
- removing one frees its slot
- the next new job reuses the free slot

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/jobs/active-slots.test.ts`

**Step 3: Write minimal implementation**

Implement a pure helper that:
- accepts active jobs and a previous slot map
- returns ordered slots plus next slot map
- never reassigns a live job if its slot is still valid

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/jobs/active-slots.test.ts`

**Step 5: Commit**

```bash
git add apps/ui/src/lib/jobs/active-slots.ts apps/ui/src/lib/jobs/active-slots.test.ts
git commit -m "test(ui): add stable active job slot helper"
```

### Task 2: Render stable active-job slots in Jobs view

**Files:**
- Modify: `apps/ui/src/lib/pages/Jobs.svelte`
- Test: `apps/ui/src/lib/pages/Jobs.layout.test.ts` or the nearest existing Jobs test file

**Step 1: Write the failing test**

Assert that Jobs renders from a slot-model path instead of directly iterating `activeJobs`, and that placeholder slots are supported.

**Step 2: Run test to verify it fails**

Run the targeted Jobs test file.

**Step 3: Write minimal implementation**

- derive slot count from configured concurrency with a sensible minimum
- build stable slot presentation from the helper
- render empty placeholder cards for unused slots
- keep recent/history rendering unchanged

**Step 4: Run tests to verify they pass**

Run the targeted Jobs test file and the slot-helper test.

**Step 5: Commit**

```bash
git add apps/ui/src/lib/pages/Jobs.svelte apps/ui/src/lib/pages/Jobs.layout.test.ts apps/ui/src/lib/jobs/active-slots.ts apps/ui/src/lib/jobs/active-slots.test.ts
git commit -m "feat(ui): stabilize active job slots"
```

### Task 3: Fix weather-backfill total normalization

**Files:**
- Modify: `apps/ui/src/lib/backfill/progress.ts`
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Test: nearest backfill progress/unit test file, or add `apps/ui/src/lib/backfill/progress.test.ts`

**Step 1: Write the failing test**

Cover weather status where:
- `total` starts at `0`
- `processed` / `updated` increase
- the derived summary total becomes non-empty and stable for the current job id

**Step 2: Run test to verify it fails**

Run the targeted backfill progress test.

**Step 3: Write minimal implementation**

- extend scoped progress normalization so running jobs can adopt a stable observed total when explicit total is absent
- ensure this behavior remains job-id scoped
- keep completed/failed terminal behavior unchanged

**Step 4: Run tests to verify they pass**

Run the targeted backfill progress test plus any Settings/source-layout test that covers weather backfill UI.

**Step 5: Commit**

```bash
git add apps/ui/src/lib/backfill/progress.ts apps/ui/src/lib/pages/Settings.svelte apps/ui/src/lib/backfill/progress.test.ts
git commit -m "fix(ui): populate weather backfill counters"
```

### Task 4: Final verification and docs

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Update changelog**

Add a brief unreleased note for:
- stable active job slots
- weather-backfill counter fix

**Step 2: Run focused verification**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/jobs/active-slots.test.ts src/lib/backfill/progress.test.ts src/lib/pages/Jobs.layout.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
```

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(ui): note jobs slot stabilization"
```
