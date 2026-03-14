# Notifications Jobs UI Simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simplify the Notifications global progress banner and Jobs tab so they show direct, truthful status with far less always-visible prose.

**Architecture:** Keep the existing job pipeline and shared analysis queue polling, but tighten the shared presenter output so healthy jobs render a minimal default surface. Then simplify `GlobalProgress.svelte` and `Jobs.svelte` to use that leaner presentation model and only surface operational detail when a job is blocked, stale, or capacity-limited.

**Tech Stack:** Svelte 5, TypeScript, Vitest, `svelte-i18n`

---

### Task 1: Red test the shorter presenter language

**Files:**
- Modify: `apps/ui/src/lib/jobs/presenter.test.ts`
- Modify: `apps/ui/src/lib/jobs/presenter.ts`

**Step 1: Write the failing test**

Extend `apps/ui/src/lib/jobs/presenter.test.ts` with assertions that the simplified presenter output is shorter and conditional:

```ts
it('uses short mixed-work banner copy', () => {
    const summary = buildGlobalProgressSummary(/* mixed-unit jobs */);
    expect(summary.progressLabel).toBe('Multiple jobs in progress');
});

it('keeps healthy job detail optional', () => {
    const presented = presentActiveJob(makeJob(), makeRow(), null, 125_000, t);
    expect(presented.detailLabel).toBeNull();
});

it('surfaces detail only when blocked or stale', () => {
    const blocked = presentActiveJob(makeJob({ current: 0, total: 0 }), throttledRow, null, 125_000, t);
    expect(blocked.detailLabel).toBe('MQTT pressure reduced background capacity');
});
```

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui test -- src/lib/jobs/presenter.test.ts`

Expected: FAIL because the presenter still returns the verbose labels and does not expose the simplified conditional detail shape.

**Step 3: Write minimal implementation**

Update `apps/ui/src/lib/jobs/presenter.ts` to:

- add a single optional `detailLabel` on presented active jobs
- shorten mixed-unit banner copy to `Multiple jobs in progress`
- shorten the banner subline so it names the dominant work without always appending capacity/queue prose
- preserve blocker/capacity detail only when it explains a limitation

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui test -- src/lib/jobs/presenter.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/jobs/presenter.ts apps/ui/src/lib/jobs/presenter.test.ts
git commit -m "refactor: simplify jobs presenter copy"
```

### Task 2: Red test the compact global banner

**Files:**
- Create or Modify test: `apps/ui/src/lib/components/GlobalProgress.test.ts`
- Modify: `apps/ui/src/lib/components/GlobalProgress.svelte`

**Step 1: Write the failing test**

Add a focused component test that renders the banner with healthy and blocked jobs and asserts:

- collapsed banner shows one short headline, one short status line, and one progress line
- expanded healthy rows do not show capacity/blocker text
- expanded blocked or stale rows do show the muted detail line

Example shape:

```ts
it('renders minimal details for healthy jobs and keeps blocker detail conditional', async () => {
    render(GlobalProgress, { props: { onNavigate: vi.fn() } });
    expect(screen.getByText('2 jobs running')).toBeInTheDocument();
    expect(screen.getByText('Reclassification analyzing clips')).toBeInTheDocument();
    expect(screen.queryByText(/worker slots busy/i)).not.toBeInTheDocument();
});
```

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui test -- src/lib/components/GlobalProgress.test.ts`

Expected: FAIL because the banner still renders the verbose summary/detail text.

**Step 3: Write minimal implementation**

Update `apps/ui/src/lib/components/GlobalProgress.svelte` to:

- keep the existing bar and expand/collapse behavior
- collapse the summary to headline + short status + one progress line
- remove always-visible capacity/blocker prose from healthy expanded rows
- render the optional detail line only when the presenter says it matters

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui test -- src/lib/components/GlobalProgress.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/GlobalProgress.svelte apps/ui/src/lib/components/GlobalProgress.test.ts
git commit -m "refactor: simplify global jobs banner"
```

### Task 3: Red test the compact Jobs page

**Files:**
- Create or Modify test: `apps/ui/src/lib/pages/Jobs.test.ts`
- Modify: `apps/ui/src/lib/pages/Jobs.svelte`

**Step 1: Write the failing test**

Add a page test that asserts:

- the summary area is a compact `Queued / Running / Done / Failed` strip
- the large explanatory throughput cards are gone
- healthy active job cards show only title, short activity, and progress by default
- blocked/stale job cards still show a small detail line

Example shape:

```ts
it('shows compact active job cards by default', async () => {
    render(Jobs, { props: { embedded: true } });
    expect(screen.getByText('Queued')).toBeInTheDocument();
    expect(screen.queryByText(/See which queues are active/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Capacity/i)).not.toBeInTheDocument();
});
```

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui test -- src/lib/pages/Jobs.test.ts`

Expected: FAIL because the current page still renders the verbose throughput section and default detail panels.

**Step 3: Write minimal implementation**

Update `apps/ui/src/lib/pages/Jobs.svelte` to:

- replace the current throughput card stack with a compact four-metric summary strip
- simplify active cards to title + short activity + progress + optional detail
- keep blocked/stale/capacity-limited truth visible only when relevant

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui test -- src/lib/pages/Jobs.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/pages/Jobs.svelte apps/ui/src/lib/pages/Jobs.test.ts
git commit -m "refactor: simplify jobs page layout"
```

### Task 4: Update i18n coverage and changelog

**Files:**
- Modify locale files under: `apps/ui/src/lib/i18n/locales/`
- Modify: `apps/ui/src/lib/i18n/locales.jobs-errors.test.ts`
- Modify: `CHANGELOG.md`

**Step 1: Write the failing test**

Update `apps/ui/src/lib/i18n/locales.jobs-errors.test.ts` so the new shorter keys are required across shipped locales.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui test -- src/lib/i18n/locales.jobs-errors.test.ts`

Expected: FAIL until the shorter strings are added everywhere.

**Step 3: Write minimal implementation**

- add/update the shorter jobs/banner strings in locale files
- add a short unreleased note to `CHANGELOG.md`

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui test -- src/lib/i18n/locales.jobs-errors.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/i18n/locales.jobs-errors.test.ts apps/ui/src/lib/i18n/locales CHANGELOG.md
git commit -m "chore: update jobs ui copy coverage"
```

### Task 5: Final verification

**Files:**
- Verify modified files only

**Step 1: Run focused UI tests**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui test -- \
  src/lib/jobs/presenter.test.ts \
  src/lib/components/GlobalProgress.test.ts \
  src/lib/pages/Jobs.test.ts \
  src/lib/i18n/locales.jobs-errors.test.ts \
  src/lib/app/live-updates.test.ts \
  src/lib/stores/job_progress.test.ts
```

Expected: PASS

**Step 2: Run type and build verification**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run check
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run build
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission diff --check
```

Expected: all pass cleanly

**Step 3: Final commit**

```bash
git add CHANGELOG.md apps/ui/src/lib/jobs/presenter.ts apps/ui/src/lib/jobs/presenter.test.ts apps/ui/src/lib/components/GlobalProgress.svelte apps/ui/src/lib/components/GlobalProgress.test.ts apps/ui/src/lib/pages/Jobs.svelte apps/ui/src/lib/pages/Jobs.test.ts apps/ui/src/lib/i18n/locales.jobs-errors.test.ts apps/ui/src/lib/i18n/locales
git commit -m "refactor: simplify jobs status surfaces"
```
