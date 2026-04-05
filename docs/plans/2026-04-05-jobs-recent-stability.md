# Jobs Recent Stability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Jobs page use exact configured active-lane capacity, keep recent jobs sorted by newest terminal event first, and add compact job-type icons.

**Architecture:** Keep the active-slot allocator deterministic but remove the fake three-slot minimum. Add a stable recent-job ordering rule in the Jobs page or presenter layer using terminal timestamps first. Introduce a small job-kind icon helper in the presenter path so both active and recent rows can reuse the same mapping without ad hoc SVG duplication.

**Tech Stack:** Svelte 5, TypeScript, Vitest, Svelte source-layout tests.

---

### Task 1: Lock in exact active slot capacity

**Files:**
- Modify: `apps/ui/src/lib/pages/Jobs.svelte`
- Test: `apps/ui/src/lib/pages/Jobs.layout.test.ts`

**Step 1: Write the failing test**

Add a source-level assertion that the active slot count logic no longer uses a hard minimum of `3` and instead falls back through effective/configured/`1`.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/pages/Jobs.layout.test.ts`

Expected: FAIL because the source still contains `Math.max(3, ...)`.

**Step 3: Write minimal implementation**

Update `activeSlotCount` in `Jobs.svelte` so it resolves to:
- effective configured concurrency if valid
- otherwise configured concurrency if valid
- otherwise `1`

Do not inflate the count to match `activeJobs.length`.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/pages/Jobs.layout.test.ts`

Expected: PASS

### Task 2: Stabilize recent/history ordering

**Files:**
- Modify: `apps/ui/src/lib/pages/Jobs.svelte`
- Test: `apps/ui/src/lib/pages/Jobs.layout.test.ts`

**Step 1: Write the failing test**

Add assertions that the recent/history list derives a sorted copy ordered by terminal timestamp descending, with `updatedAt` fallback.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/pages/Jobs.layout.test.ts`

Expected: FAIL because the page currently uses raw history order.

**Step 3: Write minimal implementation**

Add a derived `recentJobs` list in `Jobs.svelte` that sorts by:
1. terminal timestamp / finished timestamp if available
2. `updatedAt`
3. stable original order fallback

Use that list for the Recent section.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/pages/Jobs.layout.test.ts`

Expected: PASS

### Task 3: Add reusable job-type icons

**Files:**
- Modify: `apps/ui/src/lib/jobs/presenter.ts`
- Modify: `apps/ui/src/lib/pages/Jobs.svelte`
- Test: `apps/ui/src/lib/jobs/presenter.test.ts`
- Test: `apps/ui/src/lib/pages/Jobs.layout.test.ts`

**Step 1: Write the failing test**

Add tests asserting that presenter output includes a job-kind icon key or metadata and that the Jobs page consumes it in the recent/history row.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/jobs/presenter.test.ts src/lib/pages/Jobs.layout.test.ts`

Expected: FAIL because no icon metadata exists yet.

**Step 3: Write minimal implementation**

Add a small kind-to-icon mapping in `presenter.ts` and return icon metadata for job rows. Render a compact icon in the Recent/history list and, where useful, reuse it for active jobs without changing existing semantics.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/jobs/presenter.test.ts src/lib/pages/Jobs.layout.test.ts`

Expected: PASS

### Task 4: Verify overflow behavior stays safe

**Files:**
- Modify: `apps/ui/src/lib/jobs/active-slots.test.ts`
- Possibly modify: `apps/ui/src/lib/jobs/active-slots.ts`

**Step 1: Write the failing test**

Add or update a test proving the slot allocator behaves deterministically when more active jobs exist than visible slots.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/jobs/active-slots.test.ts`

Expected: FAIL if current assumptions depend on lane inflation.

**Step 3: Write minimal implementation**

Adjust `active-slots.ts` only if necessary so the allocator remains deterministic with a smaller explicit slot count.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/jobs/active-slots.test.ts`

Expected: PASS

### Task 5: Final verification and changelog

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Update changelog**

Add a concise unreleased note covering:
- exact configured active-lane count
- recent-job newest-first sorting
- job-type icons in recent/history rows

**Step 2: Run targeted verification**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/pages/Jobs.layout.test.ts src/lib/jobs/active-slots.test.ts src/lib/jobs/presenter.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
```

Expected: all pass, no Svelte warnings/errors.

**Step 3: Commit**

```bash
git add CHANGELOG.md \
  apps/ui/src/lib/pages/Jobs.svelte \
  apps/ui/src/lib/jobs/active-slots.ts \
  apps/ui/src/lib/jobs/presenter.ts \
  apps/ui/src/lib/pages/Jobs.layout.test.ts \
  apps/ui/src/lib/jobs/active-slots.test.ts \
  apps/ui/src/lib/jobs/presenter.test.ts \
  docs/plans/2026-04-05-jobs-recent-stability-design.md \
  docs/plans/2026-04-05-jobs-recent-stability.md
git commit -m "fix(ui): stabilize recent job ordering"
```
