# Explorer View Improvements Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update the Explorer page so the desktop filter selects render in a compact three-column layout and the page-level selection toggle reads "Multi Select".

**Architecture:** Keep the change isolated to the existing Explorer page component at `apps/ui/src/lib/pages/Events.svelte`. Add a focused UI test that checks the intended desktop classes and the page-level toggle label, then make the minimal markup changes to satisfy it without changing card-level selection copy.

**Tech Stack:** Svelte 5, Vitest, Testing Library, Tailwind utility classes

---

### Task 1: Explorer filter layout and selection label

**Files:**
- Modify: `apps/ui/src/lib/pages/Events.svelte`
- Create: `apps/ui/src/lib/pages/Events.layout.test.ts`

**Step 1: Write the failing test**

Create a layout-oriented test that reads the Explorer page source and asserts:
- the filter wrapper uses a desktop three-column grid for the first three selects
- the selection toggle uses `Multi Select` when selection mode is off
- card-level `Select` copy is not part of this test scope

**Step 2: Run test to verify it fails**

Run: `npm --prefix apps/ui test -- src/lib/pages/Events.layout.test.ts`
Expected: FAIL because the current page uses a flex wrapper for the filters and the page-level button still says `Select`.

**Step 3: Write minimal implementation**

Update `Events.svelte` so:
- the filter card uses a responsive layout that keeps mobile wrapping but gives the first three selects equal-width columns on large screens
- the page-level button label changes from `Select` to `Multi Select`

**Step 4: Run test to verify it passes**

Run: `npm --prefix apps/ui test -- src/lib/pages/Events.layout.test.ts`
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/pages/Events.svelte apps/ui/src/lib/pages/Events.layout.test.ts docs/plans/2026-03-20-explorer-view-improvements.md
git commit -m "fix(explorer): tighten desktop filters and clarify multi-select"
```
