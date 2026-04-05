# Jobs Stable Slots Design

## Goal

Stop active job cards in the Jobs view from visually reordering as progress updates arrive, and fix weather-backfill progress counters so they populate consistently.

## Problem

The current Jobs page renders active jobs directly from a list sorted by `updatedAt`. That makes cards jump around whenever different jobs emit progress at slightly different times. During backfills this reads as flicker, even when the underlying work is healthy.

Weather backfill has a second issue: the UI progress summary often shows no meaningful denominator because weather jobs do not always report a stable `total`, so the summary never settles into a proper counter.

## Recommended Approach

Use a UI-only stable slot assignment model for active jobs.

- Keep the existing job data model and backend APIs unchanged.
- Derive a fixed list of active-job slots from the current active jobs plus a small amount of persistent UI state.
- Assign the first available slot to a job when it appears.
- Keep that slot reserved for the job until it leaves the active set.
- Render empty placeholder slots when capacity exceeds current active jobs.

This gives the user stable “thread-like” positions without changing actual job execution semantics.

For weather backfill counters:

- Keep the existing polling/status flow.
- Normalize weather totals through the same scoped-progress rules used elsewhere, but allow the running summary to adopt a stable denominator from the first non-zero total or the observed processed count once work is underway.
- This keeps the progress label populated even when the backend job status is sparse.

## Why This Approach

- It fixes the UX problem at the right layer: presentation, not backend scheduling.
- It works for all job kinds in one combined active section.
- It avoids inventing fake backend “thread” ids.
- It preserves all existing job semantics, routes, and history behavior.

## Rejected Alternatives

### Sort-only stabilization

Keeping a stronger sort key would reduce motion slightly, but jobs would still reshuffle as their timestamps diverge. It does not solve the core problem.

### Per-kind slot groups

This would be more complex and visually fragmented. The current page already presents one active-jobs area, and the user wants a combined model.

### Backend thread ids

This would overfit the presentation requirement and couple UI layout to backend worker internals. The issue is visual stability, not job identity.

## Affected Files

- `apps/ui/src/lib/pages/Jobs.svelte`
- `apps/ui/src/lib/stores/job_progress.svelte.ts`
- `apps/ui/src/lib/backfill/progress.ts`
- likely new helper file under `apps/ui/src/lib/jobs/` for slot assignment
- Jobs/UI tests covering active jobs and backfill progress

## Testing Strategy

- Add a unit test for the slot allocator:
  - active jobs keep their slot when progress timestamps change
  - finished jobs release their slot
  - new jobs take the lowest free slot
- Add/update Jobs layout/source tests so the active section renders a fixed slot list rather than directly iterating `activeJobs`.
- Add/update backfill progress tests so weather totals become non-empty when work progresses.

