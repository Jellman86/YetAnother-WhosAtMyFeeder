# Error Bundles UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the `Error Bundles` section on the owner `Errors` page clearly communicate when a bundle is available and make saved bundles easier to scan and act on.

**Architecture:** Keep the existing diagnostics store and local bundle persistence model. Derive a `latest bundle` presentation in the page layer, redesign the saved bundles list as distinct cards, and preserve all current capture/download/delete behavior while improving visual hierarchy.

**Tech Stack:** Svelte 5, TypeScript, existing YA-WAMF UI utility classes, Vitest, Svelte type-check.

---

### Task 1: Identify reusable bundle view data

**Files:**
- Modify: `apps/ui/src/lib/pages/Errors.svelte`
- Test: `apps/ui/src/lib/stores/job_diagnostics.test.ts`

**Step 1: Write the failing test**

Add a test case that captures multiple bundles and asserts the newest bundle metadata needed by the UI remains accessible, including report notes when present.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/job_diagnostics.test.ts`
Expected: FAIL because the new expectations for latest-bundle-friendly data are not yet satisfied or exposed.

**Step 3: Write minimal implementation**

If needed, add a tiny helper or use existing payload structure so the page can safely read:

- newest bundle
- bundle report notes
- bundle summary counts

Avoid changing bundle storage shape unless the test proves it is necessary.

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/job_diagnostics.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/stores/job_diagnostics.test.ts apps/ui/src/lib/pages/Errors.svelte
git commit -m "test(ui): lock bundle presentation data"
```

### Task 2: Add latest-bundle availability card

**Files:**
- Modify: `apps/ui/src/lib/pages/Errors.svelte`

**Step 1: Write the failing test**

If there is existing page-level coverage, add a render expectation for a `Latest Bundle Ready` section when at least one bundle exists. If not, document this as a manual UI verification target and keep automated coverage at the store level.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/job_diagnostics.test.ts`
Expected: FAIL for the new expectation, or no page test coverage available and manual verification retained.

**Step 3: Write minimal implementation**

In `Errors.svelte`:

- derive `latestBundle` from the first saved bundle
- render a prominent availability card when bundles exist
- show:
  - bundle label
  - captured time
  - groups/events/snapshots summary
  - optional notes preview
- add a primary `Download Latest` action
- add explicit copy that the bundle is saved locally

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/job_diagnostics.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/pages/Errors.svelte apps/ui/src/lib/stores/job_diagnostics.test.ts
git commit -m "feat(ui): highlight latest captured error bundle"
```

### Task 3: Redesign saved bundles as bundle cards

**Files:**
- Modify: `apps/ui/src/lib/pages/Errors.svelte`

**Step 1: Write the failing test**

Add or extend a test expectation for bundle metadata visibility if practical. Otherwise capture this as a manual verification point.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/job_diagnostics.test.ts`
Expected: FAIL for new expectation or rely on manual verification if page rendering is not currently test-covered.

**Step 3: Write minimal implementation**

Replace the divided row list with a card/grid presentation:

- each bundle gets its own bordered card
- newest bundle gets a `Newest` badge
- metadata is grouped into compact stat pills
- buttons remain `Download` and `Delete`
- actions wrap cleanly on narrow screens

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/job_diagnostics.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/pages/Errors.svelte apps/ui/src/lib/stores/job_diagnostics.test.ts
git commit -m "feat(ui): redesign saved error bundle library"
```

### Task 4: Tighten copy and empty states

**Files:**
- Modify: `apps/ui/src/lib/pages/Errors.svelte`

**Step 1: Write the failing test**

If text assertions exist nearby, add an expectation for the new empty-state wording. Otherwise document manual verification.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/job_diagnostics.test.ts`
Expected: FAIL for text expectation or retain as manual verification.

**Step 3: Write minimal implementation**

Update copy to emphasize availability:

- latest card text explicitly says the bundle is saved and downloadable
- empty state explains no captured bundles are currently available
- capture controls remain simple and not overly wordy

**Step 4: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/job_diagnostics.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/pages/Errors.svelte
git commit -m "copy(ui): clarify error bundle availability states"
```

### Task 5: Final verification and cleanup

**Files:**
- Modify: `CHANGELOG.md`
- Verify: `apps/ui/src/lib/pages/Errors.svelte`
- Verify: `apps/ui/src/lib/stores/job_diagnostics.test.ts`

**Step 1: Write the failing test**

No new failing test here. This task is verification and documentation only.

**Step 2: Run relevant checks**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/stores/job_diagnostics.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
```

Expected: PASS

**Step 3: Update changelog**

Add a concise `Unreleased` entry describing the improved bundle capture clarity and redesigned saved-bundle library.

**Step 4: Manual verification**

Check the `Errors` page in desktop and mobile layouts:

- capture a bundle and confirm the latest card becomes obvious
- confirm the newest badge is visible
- confirm `Download Latest` and per-card `Download` both work
- confirm notes preview only appears when notes exist
- confirm empty state is clear after clearing bundles

**Step 5: Commit**

```bash
git add CHANGELOG.md apps/ui/src/lib/pages/Errors.svelte apps/ui/src/lib/stores/job_diagnostics.test.ts
git commit -m "feat(ui): improve diagnostics bundle capture clarity"
```
