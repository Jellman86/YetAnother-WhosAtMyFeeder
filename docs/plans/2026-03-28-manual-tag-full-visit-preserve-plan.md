# Manual Tag Full-Visit Preserve Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve full-visit readiness across manual detection renames so the UI does not offer a redundant fetch for the same Frigate event.

**Architecture:** Add a refresh-capable full-visit availability probe keyed by `frigate_event`, use it after manual tag updates, and lock the behavior in with store-level regression tests. Document the fix in the changelog under `Unreleased`.

**Tech Stack:** Svelte, TypeScript, Vitest

---

### Task 1: Save the design and plan

**Files:**
- Create: `docs/plans/2026-03-28-manual-tag-full-visit-preserve-design.md`
- Create: `docs/plans/2026-03-28-manual-tag-full-visit-preserve-plan.md`

**Step 1: Save the approved design**

Write the short design note describing event-based preservation.

**Step 2: Save the implementation plan**

Write this plan so the execution stays bounded.

### Task 2: Add the failing store test

**Files:**
- Modify: `apps/ui/src/lib/stores/full-visit.test.ts`

**Step 1: Write the failing regression**

Add a test showing that an explicit refresh can promote an event from stale availability to fetched/ready after the backend later reports a persisted full visit.

**Step 2: Run the test to verify it fails**

Run: `npm --prefix apps/ui test -- src/lib/stores/full-visit.test.ts`

Expected: FAIL because the refresh path does not exist yet.

### Task 3: Implement the minimal store change

**Files:**
- Modify: `apps/ui/src/lib/stores/full-visit.svelte.ts`

**Step 1: Add a refresh option**

Allow `ensureAvailability` to bypass stale cached state when the caller explicitly asks to refresh an event.

**Step 2: Preserve event-based fetched state**

When the backend reports the persisted clip as cached, mark the event as fetched without regard to the current detection label.

### Task 4: Use the refresh after manual tag updates

**Files:**
- Modify: `apps/ui/src/lib/pages/Events.svelte`
- Modify: `apps/ui/src/lib/pages/Dashboard.svelte`

**Step 1: Refresh the same Frigate event after manual tag success**

Call the full-visit refresh path after single-event manual tag updates.

**Step 2: Refresh updated events after bulk tag success**

Refresh the affected events so stale unfetched UI state is corrected there too.

### Task 5: Update the changelog and verify

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add Unreleased changelog entries**

Document the derived notification-timeout behavior and the manual-tag full-visit preservation fix.

**Step 2: Run verification**

Run:
- `npm --prefix apps/ui test -- src/lib/stores/full-visit.test.ts`
- `npm --prefix apps/ui run check`

Expected: PASS
