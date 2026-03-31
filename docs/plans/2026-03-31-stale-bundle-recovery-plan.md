# Stale Bundle Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Recover stale tabs after deploys by detecting chunk-load/runtime stale-bundle failures and backend/frontend version drift, then performing a guarded one-shot reload with a toast fallback instead of leaving the tab broken.

**Architecture:** Add a pure deploy-recovery helper that classifies deploy-like runtime failures and tracks one-shot reload attempts in session storage. Wire that helper into the app shell's runtime error handlers and health checks so stale-bundle recovery is isolated, testable, and does not interfere with normal runtime errors.

**Tech Stack:** Svelte 5, TypeScript, Vitest, svelte-check

---

### Task 1: Add the failing deploy-recovery tests

**Files:**
- Create: `apps/ui/src/lib/app/deploy-recovery.test.ts`
- Reference: `apps/ui/src/App.svelte`

**Step 1: Write the failing tests**

Cover:
- dynamic-import / chunk-load style errors trigger a reload on the first sighting
- the same signature after a recorded reload does not trigger another reload and instead triggers a warning
- generic runtime errors are ignored
- backend/frontend version mismatch triggers the same one-shot reload guard

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/app/deploy-recovery.test.ts`

Expected: FAIL because `deploy-recovery.ts` does not exist yet.

**Step 3: Commit**

Do not commit yet.

### Task 2: Implement the minimal helper

**Files:**
- Create: `apps/ui/src/lib/app/deploy-recovery.ts`
- Test: `apps/ui/src/lib/app/deploy-recovery.test.ts`

**Step 1: Write the minimal implementation**

Add:
- deploy-like runtime error classifier
- guarded session-storage-backed reload attempt tracking
- backend/frontend version drift handling
- toast callback path after a guarded reload has already been attempted

**Step 2: Run test to verify it passes**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/app/deploy-recovery.test.ts`

Expected: PASS

### Task 3: Wire the helper into the app shell

**Files:**
- Modify: `apps/ui/src/App.svelte`
- Reference: `apps/ui/src/main.ts`

**Step 1: Write the failing integration-facing tests if needed**

Prefer keeping integration coverage in the helper test and rely on compile checks for the Svelte wiring unless a new pure behavior needs extraction.

**Step 2: Implement the minimal wiring**

Add:
- helper creation in `App.svelte`
- runtime error/unhandled rejection forwarding
- health-check wrapping so backend version drift can trigger the same guarded recovery path
- localized warning toast fallback after a reload has already been attempted

**Step 3: Run focused verification**

Run:
- `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/app/deploy-recovery.test.ts src/lib/app/live-updates.test.ts`
- `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`

Expected: PASS

### Task 4: Update changelog and finalize

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Document the behavior**

Describe the stale-bundle recovery path, the one-shot reload guard, and the toast fallback after a repeated stale-bundle failure.

**Step 2: Run final targeted verification**

Run:
- `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/app/deploy-recovery.test.ts src/lib/app/live-updates.test.ts src/lib/stores/analysis_queue_status.test.ts`
- `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`

Expected: PASS

**Step 3: Commit**

```bash
git add docs/plans/2026-03-31-stale-bundle-recovery-design.md docs/plans/2026-03-31-stale-bundle-recovery-plan.md apps/ui/src/lib/app/deploy-recovery.ts apps/ui/src/lib/app/deploy-recovery.test.ts apps/ui/src/App.svelte CHANGELOG.md
git commit -m "fix(ui): recover stale tabs after deploys"
```
