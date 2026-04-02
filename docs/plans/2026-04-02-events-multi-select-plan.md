# Events Multi-Select Card Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current text-heavy in-card multi-select pill with an edge-mounted icon-only selector and stronger selected-card cyan styling in the Events explorer.

**Architecture:** Keep selection state and bulk-tagging logic in `Events.svelte`. Restrict the UI change to the card presentation layer so the new affordance is a pure rendering change: selected cards get stronger cyan framing, and selection mode renders a circular icon control positioned on the card edge rather than over the snapshot.

**Tech Stack:** Svelte 5, TypeScript, Tailwind utilities, Vitest, svelte-check.

---

### Task 1: Lock the new selection affordance in source-level tests

**Files:**
- Modify: `apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts`
- Modify: `apps/ui/src/lib/pages/Events.layout.test.ts`
- Verify: `apps/ui/src/lib/components/DetectionCard.svelte`
- Verify: `apps/ui/src/lib/pages/Events.svelte`

**Step 1: Write the failing test**

Add assertions that:

- selected cards use stronger cyan border/ring styling
- the card no longer renders `Select` / `Selected` text inside the selector affordance
- the selector is a compact circular icon treatment rather than a text pill

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-card-full-visit.layout.test.ts src/lib/pages/Events.layout.test.ts
```

Expected: FAIL because the current card still uses the text pill overlay.

**Step 3: Write minimal implementation**

Update the assertions to reflect:

- cyan selected card framing
- icon-only selector markup
- no embedded selection words on the card

**Step 4: Run test to verify it passes**

Run the same command again.
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts apps/ui/src/lib/pages/Events.layout.test.ts
git commit -m "test(ui): lock events multi-select card affordance"
```

### Task 2: Rebuild the in-card selector affordance

**Files:**
- Modify: `apps/ui/src/lib/components/DetectionCard.svelte`

**Step 1: Write the failing test**

Use the source-level tests from Task 1 as the failing guard.

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-card-full-visit.layout.test.ts src/lib/pages/Events.layout.test.ts
```

Expected: FAIL while the old text pill still exists.

**Step 3: Write minimal implementation**

In `DetectionCard.svelte`:

- replace the current in-image text pill with an edge-mounted circular selector
- keep it visible only in `selectionMode`
- render a hollow neutral circle when unselected
- render a filled cyan circle with a checkmark when selected
- strengthen selected card border/ring styling to match the Events selection UI

**Step 4: Run test to verify it passes**

Run the same command again.
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/DetectionCard.svelte
git commit -m "feat(ui): redesign events multi-select card selector"
```

### Task 3: Verify page-level fit and changelog

**Files:**
- Modify: `CHANGELOG.md`
- Verify: `apps/ui/src/lib/pages/Events.svelte`
- Verify: `apps/ui/src/lib/components/DetectionCard.svelte`

**Step 1: Run focused verification**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-card-full-visit.layout.test.ts src/lib/pages/Events.layout.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
```

Expected: PASS

**Step 2: Update changelog**

Add an `Unreleased` note that the Events explorer multi-select UI now uses an icon-only edge selector and stronger cyan selected-card styling.

**Step 3: Manual review checklist**

Verify visually that:

- the selector no longer covers favorite/full-visit badges
- selected cards are obvious in the grid
- unselected cards remain readable and uncluttered
- the bulk action bar still provides the explanatory text

**Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: note events multi-select card refresh"
```
