# Detection Card Analysis Overlay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make automatic video analysis fully take over a detection card so other card chrome never renders above it.

**Architecture:** Add an explicit `analysisActive` state to `DetectionCard.svelte`, use it to drive a temporary analysis border and suppress normal image/action chrome, and wrap the existing overlay in a top-priority layer. Lock the behavior in with a focused layout regression test and changelog note.

**Tech Stack:** Svelte 5, Vitest source-layout tests, Tailwind utility classes

---

### Task 1: Define the takeover contract in the card test

**Files:**
- Modify: `apps/ui/src/lib/components/detection-card-full-visit.layout.test.ts`

**Step 1: Write the failing test**

Add assertions for:
- `let analysisActive = $derived(!!reclassifyProgress);`
- analysis border classes on the card wrapper
- analysis overlay wrapper with a higher `z-*`
- chrome gated behind `!analysisActive`
- selection overlay gated behind `!analysisActive`

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-card-full-visit.layout.test.ts`
Expected: FAIL because the source does not yet implement the takeover contract

### Task 2: Implement the analysis takeover state

**Files:**
- Modify: `apps/ui/src/lib/components/DetectionCard.svelte`

**Step 1: Add explicit derived state**

Introduce:

```ts
let analysisActive = $derived(!!reclassifyProgress);
```

**Step 2: Promote analysis to highest visual layer**

Wrap the existing `ReclassificationOverlay` in a dedicated top-level absolute layer with a higher `z-index`.

**Step 3: Suppress competing chrome while active**

Gate the top badges, timestamp, play/full-visit controls, hover action buttons, and selection overlay behind `!analysisActive`.

**Step 4: Add temporary analysis border**

Apply an indigo/cyan analysis border/ring class on the card wrapper while `analysisActive` is true, ensuring it wins over normal/selected border treatment.

### Task 3: Verify and document

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Update changelog**

Add an unreleased note describing the new analysis-overlay takeover behavior.

**Step 2: Run focused verification**

Run:
- `npm --prefix /config/workspace/YA-WAMF/apps/ui test -- src/lib/components/detection-card-full-visit.layout.test.ts`
- `npm --prefix /config/workspace/YA-WAMF/apps/ui run check`

Expected: PASS
