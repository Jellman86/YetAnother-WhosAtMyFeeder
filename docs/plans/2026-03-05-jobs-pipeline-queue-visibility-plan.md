# Jobs Pipeline Queue Visibility Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a top-of-page pipeline view on Jobs that communicates queued -> running -> completed/failed flow for all background job kinds, using real queue counts where available and explicit unknown queue state elsewhere.

**Architecture:** Keep `jobProgressStore` as the canonical source for running/history job items. Add a small Jobs-page-only queue snapshot poll for the existing auto-video queue endpoint (`/api/maintenance/analysis/status`) and combine it with active/history counts into a derived pipeline model. Render a compact 3-lane “flow” card above the existing active/recent lists without removing current progress bars.

**Tech Stack:** Svelte 5, TypeScript, existing UI stores (`job_progress.svelte.ts`), existing maintenance API client (`api/maintenance.ts`), Vitest for logic tests, svelte-check.

---

### Task 1: Add pipeline data model + test coverage

**Files:**
- Create: `apps/ui/src/lib/jobs/pipeline.ts`
- Create: `apps/ui/src/lib/jobs/pipeline.test.ts`

**Step 1: Write the failing tests**
- Add tests for:
  - Aggregating running/completed/failed counts by `kind` from `JobProgressItem[]`.
  - Overlaying queued counts from queue telemetry when available.
  - Marking queue as unknown for kinds without telemetry.
  - Producing total stage counts (`queued`, `running`, `completed`, `failed`).

**Step 2: Run test to verify it fails**
- Run: `npm run --silent test -- src/lib/jobs/pipeline.test.ts`
- Expected: FAIL (module/functions not implemented).

**Step 3: Write minimal implementation**
- Implement pure helpers that transform:
  - `activeJobs`
  - `historyJobs`
  - optional queue snapshots by kind
  into lane cards and per-kind rows.

**Step 4: Run test to verify it passes**
- Run: `npm run --silent test -- src/lib/jobs/pipeline.test.ts`
- Expected: PASS.

### Task 2: Extend maintenance API type for queue telemetry

**Files:**
- Modify: `apps/ui/src/lib/api/maintenance.ts`

**Step 1: Write failing type usage in Jobs page update (Task 3) that needs queue metadata**
- Add typed fields for known queue telemetry (`pending`, `active`, `pending_capacity`, etc.) and kind tag in Jobs page integration.

**Step 2: Implement minimal API typing support**
- Ensure `AnalysisStatus` typing supports fields required by pipeline card.

**Step 3: Validate typecheck**
- Run: `npm run --silent check`
- Expected: PASS for API typing.

### Task 3: Implement Jobs top pipeline card

**Files:**
- Modify: `apps/ui/src/lib/pages/Jobs.svelte`

**Step 1: Write failing integration expectations**
- Add small view-model assertions in `pipeline.test.ts` to cover what Jobs will render (lane totals + per-kind queue-known markers).

**Step 2: Implement UI card**
- Add a new top card with three lanes:
  - Queued
  - Running
  - Completed/Failed
- Add per-kind chips/rows below lane totals.
- For unknown queue telemetry, show `—` with “not reported” copy.
- Keep existing Active and Recent sections unchanged below the card.

**Step 3: Poll existing analysis queue status for known queue telemetry**
- In `Jobs.svelte`, poll `fetchAnalysisStatus()` on mount (owner page) every ~5s.
- Map this endpoint to a queue snapshot for the video-analysis kind(s).
- Clear interval on unmount.

**Step 4: Run check and targeted tests**
- Run: `npm run --silent test -- src/lib/jobs/pipeline.test.ts`
- Run: `npm run --silent check`
- Expected: PASS.

### Task 4: Localization keys for new labels

**Files:**
- Modify: `apps/ui/src/lib/i18n/locales/en.json`

**Step 1: Add new copy keys**
- Add keys for pipeline title/subtitle, lane labels, queue unknown label, and stage legends.

**Step 2: Use defaults/fallbacks in UI to avoid breaking other locales now**
- Access via `$_('...',{ default: '...' })` so non-English locales continue to function.

**Step 3: Run check**
- Run: `npm run --silent check`
- Expected: PASS.

### Task 5: Final verification

**Files:**
- Modify if needed: `CHANGELOG.md`

**Step 1: Verify tests/checks**
- Run:
  - `npm run --silent test -- src/lib/jobs/pipeline.test.ts`
  - `npm run --silent check`

**Step 2: Update changelog (if user-facing behavior changed)**
- Add an Unreleased bullet for Jobs pipeline queue visibility.

**Step 3: Summarize outcomes**
- Report what queue telemetry is real today and where queue remains explicitly unknown.
