# Notifications Jobs UI Simplification Design

## Goal

Simplify the Notifications global progress bar and Jobs view so they communicate truthful background-work status with less prose and fewer always-visible operational details.

## Problem

The current Jobs polish pass made the UI more accurate, but it now over-explains normal background work:

- The global banner uses a long subline and verbose progress text.
- Expanded banner rows repeat activity, message, freshness, capacity, and blocker detail even when the job is healthy.
- The Jobs page opens with an operational throughput section that is useful for debugging but too heavy for routine use.
- Active job cards surface internal mechanics by default instead of leading with the user-visible state.

This makes the page harder to scan and causes simple states like "running" or "waiting" to feel noisy.

## Non-Goals

- Do not remove truthful blocker/capacity telemetry entirely.
- Do not redesign the backend jobs model.
- Do not invent worker/thread counts for job kinds that do not expose them.
- Do not change the meaning of progress calculation or queue telemetry.

## Approved Approach

Use a headline-first design that keeps the default surfaces minimal and only shows extra operational detail when it explains an actual limitation.

### Global Progress Banner

Collapsed banner:

- Headline: short aggregate label such as `3 jobs running`
- Status line: one concise sentence naming the dominant work, for example `Reclassification analyzing clips`
- Progress line: one direct label such as `143 / 800 items` or `Working...`

Expanded banner:

- One compact row per visible job
- Show only job title, short activity, and progress/freshness
- Show a muted extra detail line only when the job is blocked, stale, or capacity-limited

Remove verbose explanatory copy like "Mixed work units; showing live status instead of a combined percent." Replace with direct text like `Multiple jobs in progress`.

### Jobs View

Replace the current heavy "System Throughput" section with a compact summary strip:

- `Queued`
- `Running`
- `Done`
- `Failed`

Each active job card should default to:

- Title
- One short activity line
- One progress line with a determinate or indeterminate bar

Optional detail should appear only when useful:

- Blocked by circuit breaker
- Throttled / capacity-limited
- Stale / not updated recently

Do not show capacity, queue-depth, or blocker panels by default for healthy jobs.

## Data and Presentation Rules

- Preserve existing presenter-derived truth for determinate vs indeterminate progress.
- Preserve reclassification-only queue/circuit telemetry scoping.
- Keep the shared `analysisQueueStatusStore`; no return to duplicate polling.
- Continue using real queue/capacity numbers where available, but surface them only when they clarify a limitation.
- If multiple jobs have incompatible units, use a short fallback like `Multiple jobs in progress`.

## Files Expected To Change

- `apps/ui/src/lib/jobs/presenter.ts`
- `apps/ui/src/lib/pages/Jobs.svelte`
- `apps/ui/src/lib/components/GlobalProgress.svelte`
- UI tests covering presenter output and rendered job/banner states
- `CHANGELOG.md`

## Testing Strategy

- Update presenter tests to assert shorter banner summary strings and conditional detail behavior.
- Update Jobs/global progress UI tests so healthy jobs render minimal metadata and blocked/stale jobs still surface the needed explanation.
- Run `npm --prefix apps/ui test ...` for the touched suites.
- Run `npm --prefix apps/ui run check`
- Run `npm --prefix apps/ui run build`

## Risks and Mitigations

- Risk: oversimplifying and hiding meaningful state.
  - Mitigation: only suppress detail when the job is healthy; preserve blocker/stale/capacity text when it explains behavior.
- Risk: regressions in i18n coverage for new shorter copy.
  - Mitigation: update locale coverage tests alongside presenter changes.
- Risk: banner and Jobs page diverge again.
  - Mitigation: keep simplification centered in the shared presenter layer where possible.
