# Video Analysis Film Reel UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current fixed frame-grid video-analysis progress UI with a shared non-interactive film-reel component, and fix `DetectionModal` so active video analysis replaces the media/video slot instead of stacking above it.

**Architecture:** Build a shared `VideoAnalysisFilmReel` component that renders a windowed, progress-driven film strip from `ReclassificationProgress`. Integrate it into `ReclassificationOverlay` first, then add compact/detail variants for `DetectionCard` and `DetectionModal`, with modal-specific logic to swap the left media region while analysis is pending/processing.

**Tech Stack:** Svelte 5, Tailwind CSS, TypeScript, existing `detectionsStore` reclassification progress state, `svelte-i18n`

---

### Task 1: Map Current UI Integration Points and Add State Helpers

**Files:**
- Modify: `apps/ui/src/lib/components/DetectionModal.svelte`
- Modify: `apps/ui/src/lib/components/DetectionCard.svelte`
- Modify: `apps/ui/src/lib/components/ReclassificationOverlay.svelte`

**Step 1: Add/confirm derived booleans for active video-analysis states**

- Define explicit reusable state checks in each surface for:
  - `videoAnalysisActive` (`pending` or `processing`)
  - `videoAnalysisDone`
  - `videoAnalysisFailed`
- Keep logic separate from presentation markup.

**Step 2: Run frontend check to catch type/template issues**

Run: `npm --prefix apps/ui run check`

Expected: passes (or only pre-existing unrelated issues)

**Step 3: Commit**

```bash
git add apps/ui/src/lib/components/DetectionModal.svelte apps/ui/src/lib/components/DetectionCard.svelte apps/ui/src/lib/components/ReclassificationOverlay.svelte
git commit -m "refactor: isolate video analysis UI state flags"
```

### Task 2: Create Shared Film Reel Component (Overlay-First)

**Files:**
- Create: `apps/ui/src/lib/components/VideoAnalysisFilmReel.svelte`
- Modify: `apps/ui/src/lib/components/ReclassificationOverlay.svelte`

**Step 1: Write the component with variant-based rendering**

Implement `VideoAnalysisFilmReel.svelte` props (minimum):
- `progress`
- `variant` (`overlay | detail | compact`)
- `showSummary` (optional, default by variant)

Include:
- safe frame count/index derivations
- progress percent
- windowed visible frames (avoid rendering all frames as full-size tiles)
- current frame highlight
- completed/pending placeholders
- reduced-motion-friendly transitions

**Step 2: Replace the existing frame-grid block in `ReclassificationOverlay`**

- Keep current circular progress, label summary, and done button.
- Remove duplicated frame-grid logic now handled by the shared component.

**Step 3: Run frontend check and build**

Run:
- `npm --prefix apps/ui run check`
- `npm --prefix apps/ui run build`

Expected: both pass

**Step 4: Manual verify overlay behavior**

- Start reclassification
- Confirm reel advances only with real frame progress
- Confirm completed state freezes and shows final result
- Confirm failed state freezes without layout breakage

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/VideoAnalysisFilmReel.svelte apps/ui/src/lib/components/ReclassificationOverlay.svelte
git commit -m "feat: add shared film reel video analysis progress UI"
```

### Task 3: Integrate Compact Film Reel into Detection Cards

**Files:**
- Modify: `apps/ui/src/lib/components/DetectionCard.svelte`
- Modify: `apps/ui/src/lib/components/VideoAnalysisFilmReel.svelte` (if compact polish needed)

**Step 1: Render compact reel when card has active reclassification progress**

- Replace/augment current compact status indication with `variant=\"compact\"`
- Keep card density and tap targets intact
- Avoid heavy blur/backdrop effects in compact mode

**Step 2: Run frontend check**

Run: `npm --prefix apps/ui run check`

Expected: pass

**Step 3: Manual verify card list performance/behavior**

- Multiple active cards should not stutter
- Reel should not overflow card width
- Progress should remain readable at small sizes

**Step 4: Commit**

```bash
git add apps/ui/src/lib/components/DetectionCard.svelte apps/ui/src/lib/components/VideoAnalysisFilmReel.svelte
git commit -m "feat: show compact film reel progress on detection cards"
```

### Task 4: Fix Detection Modal Media-Slot Replacement (Critical UX Bug)

**Files:**
- Modify: `apps/ui/src/lib/components/DetectionModal.svelte`
- Modify: `apps/ui/src/lib/components/VideoAnalysisFilmReel.svelte` (detail variant)

**Step 1: Write the failing manual reproduction checklist**

Reproduce current bug:
- Open detection details
- Trigger video analysis / reclassification
- Observe status banner renders in details panel while media/video player area remains visible (stacked/conflicting UI)

Expected desired behavior:
- During `pending/processing`, the left media slot shows the film reel analysis UI instead of the normal thumbnail/video surface.

**Step 2: Implement modal media-slot swap**

- In the left media region (`aspect-video` / media container), conditionally render `VideoAnalysisFilmReel variant=\"detail\"` for active analysis
- Hide video-play button and conflicting overlays in this state
- Restore normal thumbnail/video surface for completed/failed/idle states

**Step 3: Keep details-panel status copy minimal and non-duplicative**

- Prevent duplicate progress messaging above metadata when the reel is already occupying the media slot
- Retain compact completion/failure summaries as appropriate

**Step 4: Run frontend check and build**

Run:
- `npm --prefix apps/ui run check`
- `npm --prefix apps/ui run build`

Expected: both pass

**Step 5: Manual verify transitions**

- `pending -> processing`: reel appears in media slot immediately
- `processing -> completed`: media slot restores normal media UI; result shown correctly
- `processing -> failed`: media slot restores, failure summary remains readable
- modal close/open cycles do not retain stale reel state

**Step 6: Commit**

```bash
git add apps/ui/src/lib/components/DetectionModal.svelte apps/ui/src/lib/components/VideoAnalysisFilmReel.svelte
git commit -m "fix: replace modal media slot with film reel during video analysis"
```

### Task 5: i18n, Accessibility, and Reduced-Motion Polish

**Files:**
- Modify: `apps/ui/src/lib/i18n/locales/en.json`
- Modify: `apps/ui/src/lib/i18n/locales/de.json`
- Modify: `apps/ui/src/lib/i18n/locales/es.json`
- Modify: `apps/ui/src/lib/i18n/locales/fr.json`
- Modify: `apps/ui/src/lib/i18n/locales/it.json`
- Modify: `apps/ui/src/lib/i18n/locales/ja.json`
- Modify: `apps/ui/src/lib/i18n/locales/pt.json`
- Modify: `apps/ui/src/lib/i18n/locales/ru.json`
- Modify: `apps/ui/src/lib/i18n/locales/zh.json`
- Modify: `apps/ui/src/lib/components/VideoAnalysisFilmReel.svelte`

**Step 1: Add any new strings required by the film reel UI**

Examples (if needed):
- film reel / frame sequence label
- analyzing frames status text
- pending/completed/failed chips

**Step 2: Add reduced-motion handling**

- Use media-query aware class/logic so reel updates remain accurate without animated movement
- Ensure no pulse/transition dependence for readability

**Step 3: Run frontend check and build**

Run:
- `npm --prefix apps/ui run check`
- `npm --prefix apps/ui run build`

Expected: both pass

**Step 4: Manual accessibility verification**

- `prefers-reduced-motion`
- focus order in modal unchanged
- status remains understandable without color

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/VideoAnalysisFilmReel.svelte apps/ui/src/lib/i18n/locales/*.json
git commit -m "fix: polish film reel analysis UI accessibility and i18n"
```

### Task 6: Final Verification and Changelog

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Update changelog entry**

- Document film-reel progress UI
- Document modal media-slot replacement fix for active video analysis

**Step 2: Run final verification**

Run:
- `npm --prefix apps/ui run check`
- `npm --prefix apps/ui run build`

Expected: pass

**Step 3: Commit final summary**

```bash
git add CHANGELOG.md
git commit -m "docs: note film reel video analysis UI improvements"
```

