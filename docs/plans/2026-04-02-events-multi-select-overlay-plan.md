# Events Multi-Select Overlay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Strengthen the Events explorer multi-select state by replacing the weak corner-led selection treatment with a full selected-card cyan-blue veil, a centered checkmark, and a clearly visible selected card border.

**Architecture:** Keep selection behavior unchanged in `Events.svelte`. Refine only the card rendering in `DetectionCard.svelte` and the related source-level UI tests so the selected state is communicated by the card border itself plus a full-card obscuring overlay above existing card content.

**Tech Stack:** Svelte 5, TypeScript, Tailwind utilities, Vitest, svelte-check.

---

### Task 1: Lock the stronger selected-card treatment in tests

**Files:**
- Modify: `apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts`

**Step 1: Write the failing test**

Add assertions that selected cards now include:

- a stronger cyan selected border/ring on the card itself
- a selected-only overlay element above the card content
- a centered checkmark
- no regression back to the old corner selector or text-based selector

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-card-full-visit.layout.test.ts
```

Expected: FAIL because the current card still uses the weaker edge-led treatment.

**Step 3: Write minimal implementation**

Update the test to assert the stronger overlay contract precisely.

**Step 4: Run test to verify it passes**

Run the same command again.
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts
git commit -m "test(ui): lock stronger events selected-card treatment"
```

### Task 2: Implement the stronger selected-card overlay

**Files:**
- Modify: `apps/ui/src/lib/components/DetectionCard.svelte`

**Step 1: Use the failing test from Task 1**

No new test file; use the updated source-level test as the failing guard.

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-card-full-visit.layout.test.ts
```

Expected: FAIL before the card markup is updated.

**Step 3: Write minimal implementation**

In `DetectionCard.svelte`:

- move the strong selected state onto the actual card border
- remove the corner selector entirely
- add a selected-only cyan/blur overlay above the card content
- add a large centered checkmark above the overlay

**Step 4: Run test to verify it passes**

Run the same command again.
Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/DetectionCard.svelte
git commit -m "feat(ui): strengthen events selected-card treatment"
```

### Task 3: Final verification and changelog

**Files:**
- Modify: `CHANGELOG.md`
- Verify: `apps/ui/src/lib/components/DetectionCard.svelte`
- Verify: `apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts`
- Verify: `apps/ui/src/lib/pages/Events.layout.test.ts`

**Step 1: Run focused verification**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-card-full-visit.layout.test.ts src/lib/pages/Events.layout.test.ts
npm --prefix /config/workspace/YA-WAMF/apps/ui run check
```

Expected: PASS

**Step 2: Update changelog**

Adjust the existing Events multi-select note so it describes the card border, centered checkmark, and full-card selected veil, not the previous corner treatment.

**Step 3: Manual review checklist**

Verify that:

- selected cards pop clearly from a grid scan
- the selected card border is clearly visible and aligned to the card shape
- the selected overlay clearly obscures card content
- the centered checkmark remains readable and balanced

**Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: refine events multi-select overlay note"
```
