# Global Progress Sticky Spawn Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the global progress banner mount in flow with a small content gap, then become sticky only after scrolling begins.

**Architecture:** Keep the shared app chrome height variable as the single offset contract, add a small scroll-state gate in `App.svelte`, and use a layout test to lock the markup contract. This avoids introducing extra stores or component-level measurement complexity for a narrow UI regression.

**Tech Stack:** Svelte 5, Vitest, Tailwind utility classes

---

### Task 1: Lock the layout contract with a failing test

**Files:**
- Modify: `apps/ui/src/lib/components/GlobalProgress.layout.test.ts`
- Test: `apps/ui/src/lib/components/GlobalProgress.layout.test.ts`

**Step 1: Write the failing test**

Assert that `App.svelte` contains:
- the shared `--app-chrome-height: 4rem;` contract
- a `window.scrollY > 0` sticky gate
- a sticky wrapper class for scrolled state
- a relative wrapper class with a bottom gap for spawn state

**Step 2: Run test to verify it fails**

Run: `npm test -- src/lib/components/GlobalProgress.layout.test.ts`
Expected: FAIL because the app shell still uses an always-sticky wrapper.

### Task 2: Implement the minimal shell behavior change

**Files:**
- Modify: `apps/ui/src/App.svelte`

**Step 1: Add scroll state**

Create a local Svelte state flag and a small helper that sets it from `window.scrollY > 0`.

**Step 2: Register and clean up the scroll listener**

Wire the helper into the existing `onMount` lifecycle and remove the listener in the existing cleanup path.

**Step 3: Update the banner wrapper**

Use the relative wrapper with a small bottom margin before scroll, and switch to `sticky top-[var(--app-chrome-height)]` after scroll begins.

### Task 3: Verify the change

**Files:**
- Test: `apps/ui/src/lib/components/GlobalProgress.layout.test.ts`
- Test: `apps/ui/src/lib/stores/job_progress.test.ts`

**Step 1: Re-run the focused layout test**

Run: `npm test -- src/lib/components/GlobalProgress.layout.test.ts`
Expected: PASS.

**Step 2: Re-run adjacent progress coverage**

Run: `npm test -- src/lib/stores/job_progress.test.ts src/lib/components/GlobalProgress.layout.test.ts`
Expected: PASS.
