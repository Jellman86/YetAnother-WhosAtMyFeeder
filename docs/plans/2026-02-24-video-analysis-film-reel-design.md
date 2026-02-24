# Video Analysis Film Reel UI Design

**Date:** 2026-02-24

**Problem**

The number of video-analysis frames is now configurable, but the current UI still assumes a small fixed "frame grid" presentation. This creates two issues:

- The progress visualization does not scale well as frame counts increase.
- In detection details, video-analysis status can appear as a separate banner above the media area instead of replacing the media/video player region during analysis, which feels broken and confusing.

**Goal**

Create a consistent, non-interactive, automatically updating "film reel" progress UI that gives an accurate visual assessment of video-analysis progress across list/detail/overlay contexts, and correctly replaces the media/video area during active analysis where appropriate.

## Approved Direction

**Approach:** Windowed Film Reel (non-interactive, progress-driven)

- The reel advances only when real backend analysis progress advances.
- Motion reflects actual frame completion (`currentFrame`, `frameResults`) rather than a fake timer/marquee.
- Compact and detailed variants share one component to prevent UI drift.

## UX Requirements

### 1. Accurate Progress (No Fake Motion)

- Reel position updates are tied to analysis progress events only.
- The "current frame" marker reflects the actual frame index being processed.
- Pending frames remain placeholders until real results arrive.
- If analysis stalls or fails, the reel visibly stops/freeze-frames at the real position.

### 2. Non-Interactive Presentation

- Users cannot scrub/click/step through frames in this UI.
- The reel is purely informational and automatic.
- Interaction remains in existing actions (reclassify, play video, close modal, etc.).

### 3. Modal/Details Media-Slot Replacement (Critical)

When a detection is in video-analysis `pending` or `processing` state:

- The film-reel analysis UI must replace the media/video presentation region in `DetectionModal` (left column media slot), not render as an additional status card above metadata.
- This prevents visual stacking conflicts with the newer video-player behavior and makes the analysis experience coherent.

When analysis is `completed` or `failed`:

- Normal media/video presentation resumes.
- A compact result/failure summary may still appear in the details panel as status context.

## Component Architecture

### Shared Component

Create a reusable component (proposed):

- `apps/ui/src/lib/components/VideoAnalysisFilmReel.svelte`

Props (proposed):

- `progress` (reclassification progress object)
- `variant` (`compact | detail | overlay`)
- `status` (`pending | processing | completed | failed`) if needed independently
- `showSummary` / `showFrameLabels` / `showBackdrop` flags (or variant-driven defaults)

### Reuse Targets

- `ReclassificationOverlay.svelte` (replace current frame-grid block)
- `DetectionCard.svelte` (compact status/progress strip when reclassification is active)
- `DetectionModal.svelte` (media-slot replacement while analysis is active)

## Visual Design

### Film Reel Structure

- Horizontal strip with "sprocket" styling to communicate frame sequence.
- Windowed viewport shows only a subset of frames (prevents layout blowups at high frame counts).
- Auto-shift keeps the active frame centered where possible.
- Completed frames display thumbnails when available.
- Pending frames use placeholders (no layout shift).

### State Styling

- `current` frame: ring highlight + subtle pulse (disabled in reduced motion)
- `completed` frame: confidence tint + thumbnail
- `pending` frame: neutral placeholder
- `failed` run: frozen reel + error label
- `completed` run: stop pulse/animation and show final result label

### Confidence Colors

Retain and standardize current semantics used in the overlay:

- high confidence -> emerald
- medium confidence -> teal/amber (pick one threshold mapping and use consistently)
- low confidence -> amber/rose

## Layout Behavior by Surface

### `overlay` (ReclassificationOverlay)

- Largest reel variant
- Replaces current grid block
- Keeps existing circular progress and final result controls
- Supports backdrop thumbnail for visual continuity (with reduced-motion/perf safeguards)

### `detail` (DetectionModal media slot)

- Uses the left media area (`aspect-video` region) during `pending/processing`
- Shows reel + progress percent + "AI analysis in progress" + current frame info
- Hides the video-play affordance while active analysis UI is shown
- Restores thumbnail/video affordances when analysis completes/fails

### `compact` (DetectionCard)

- Minimal reel (5-7 visible cells)
- No per-frame percentages
- Small progress percent/status chip only
- No heavy blur/backdrop effects

## Data/State Mapping

Use existing `ReclassificationProgress` fields:

- `currentFrame`, `totalFrames`
- `frameIndex`, `clipTotal`
- `frameResults[]` (label/score/thumb)
- `status`
- `results[]` (final top result when completed)
- `modelName`

Derived values (shared helper or component-local):

- safe counts/indexes
- percent complete
- visible window start/end
- current frame display index
- final summary label/score

## Robustness / 2nd and 3rd Order Effects

### Performance

- Do not render an unbounded full-width thumbnail grid for high frame counts.
- Use a windowed reel viewport and transform-based motion.
- In compact variant, avoid expensive blur/backdrop layers.
- Missing thumbnails must not cause layout shifts or exceptions.

### Motion & Accessibility

- Respect `prefers-reduced-motion`:
  - disable animated shifts/pulses
  - still update state instantly
- Keep status text readable without relying on color alone.
- Preserve focus/order for modal controls when media-slot content switches.

### State Transition Correctness

- `pending -> processing`: show reel with placeholders, then fill frames as results arrive
- `processing -> completed`: freeze reel, show final result
- `processing -> failed`: freeze reel and show failure state without leaving stale spinner banner elsewhere
- dismissal/overlay cleanup should not leak timers or stale animation state

## Testing & Verification Strategy

Because the UI package currently has no component test runner:

- `npm --prefix apps/ui run check`
- `npm --prefix apps/ui run build`
- Manual verification:
  - Reclassification overlay (small + large)
  - Detection card active reclassification state
  - Detection modal during `pending/processing` (media slot replacement)
  - Completed/failed transitions
  - Reduced-motion mode

## Out of Scope (This Iteration)

- Interactive frame scrubbing/selection
- Reusing timeline-preview sprites from video playback
- New backend progress/event payload schema
