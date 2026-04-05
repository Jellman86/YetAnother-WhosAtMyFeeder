# Jobs Recent Stability Design

## Goal

Make the Jobs page behave truthfully and predictably by:
- showing active lanes that match the configured concurrent-job capacity
- sorting recent jobs by newest terminal event first
- adding lightweight job-type icons to recent/history rows

## Current Problem

The current Jobs UI has two mismatches with user expectations:

1. Active lanes are hard-clamped to a minimum of three slots even when the configured effective concurrency is lower. This makes a system configured for `2` concurrent jobs appear to have `3` worker threads.
2. Recent/history items can appear to bounce because their ordering is not explicitly tied to terminal recency.

## Recommended Approach

Use the configured effective concurrency as the exact active slot count and treat that number as a UI truth source. Remove the current hard minimum of three slots. Sort recent/history jobs by newest terminal timestamp first, falling back to the latest update timestamp when no terminal timestamp exists. Add a small icon keyed off job kind for faster scanning.

## Tradeoffs

### Exact slot count

Pros:
- The UI matches the actual configured capacity.
- Thread/lane labels become trustworthy.
- The page no longer implies hidden capacity that does not exist.

Cons:
- If the backend ever temporarily reports more active jobs than configured capacity, the active lane grid cannot show one job per lane.

Mitigation:
- Keep the lane count exact.
- If active jobs exceed visible lanes, prefer deterministic placement of the newest/highest-priority jobs in the visible lanes and let the rest appear in recent/history rather than inventing extra fake lanes.

### Recent ordering by terminal time

Pros:
- History becomes stable and intuitive.
- Finished jobs stay anchored by when they actually finished.

Cons:
- Jobs without a terminal timestamp need a fallback ordering rule.

Mitigation:
- Use `finishedAt`/terminal timestamp when available.
- Fall back to `updatedAt`.
- Fall back to original list order only as a last resort.

### Job-type icons

Pros:
- Faster scanning with minimal text.
- Reinforces type distinctions without adding noise.

Cons:
- Too many icon styles could make the history section visually busy.

Mitigation:
- Reuse a small, consistent icon set.
- Keep the icon secondary to the job title.

## UI Contract

### Active

- The active section shows exactly the configured effective concurrency lanes.
- If configured concurrency is unavailable or invalid, fall back to configured concurrency, then to `1`.
- Lane labels remain `Thread 1`, `Thread 2`, etc.

### Recent

- Recent jobs are sorted descending by terminal timestamp, newest first.
- Rows include a compact job-type icon before the title.

### Overflow

- If active jobs exceed lane count, the page does not fabricate extra threads.
- Overflow jobs remain represented in recent/history rather than expanding the active grid beyond configured capacity.

## Files Likely Affected

- `apps/ui/src/lib/pages/Jobs.svelte`
- `apps/ui/src/lib/jobs/active-slots.ts`
- `apps/ui/src/lib/jobs/presenter.ts`
- `apps/ui/src/lib/pages/Jobs.layout.test.ts`
- `apps/ui/src/lib/jobs/active-slots.test.ts`
- `apps/ui/src/lib/jobs/presenter.test.ts`
- `apps/ui/src/lib/i18n/locales/*.json` if new copy is needed
- `CHANGELOG.md`
