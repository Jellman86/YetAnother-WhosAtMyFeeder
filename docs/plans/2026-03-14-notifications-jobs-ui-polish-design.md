# Notifications Jobs UI Polish Design

## Goal

Turn the Notifications Jobs view and global progress banner into a clearer operational surface that always explains what active jobs are doing, whether progress is determinate, what is limiting throughput, and what real capacity is available.

## Problem

The current Jobs UI has usable raw data but weak presentation.

Today it often shows:

- generic progress bars without clear unit labels
- raw job titles and messages that do not explain the current stage
- aggregate progress that can mix incompatible work units
- limited capacity visibility even when the backend already exposes queue and concurrency telemetry
- stale or blocked jobs without enough explanation of what they are waiting on

That leaves the owner with bars and counters, but not a clear answer to “what is running right now?” or “why is this not moving?”

## Constraints

- Show only truthful telemetry; do not fabricate thread or worker counts
- Prefer frontend-side presentation changes over broad backend refactors
- Reuse existing job progress and analysis status signals where possible
- Keep the diagnostics workspace separate from the main Jobs UI; diagnostics remain a troubleshooting surface, not the primary operational dashboard
- Aggregate percent should only appear when the underlying units are compatible
- Unknown values must remain visibly unknown

## Recommended Approach

Build a UI-facing jobs presentation layer that translates raw `jobProgressStore` items and queue telemetry into explicit operator-facing summaries.

The polished surfaces should answer these questions in order:

1. What work is happening now?
2. How far through that work are we?
3. What resource is limiting it, if any?
4. What capacity is available?
5. How fresh is this status?

This approach keeps the current stores and SSE flow, but changes the presentation model so every visible bar, chip, and label has an explicit meaning.

## Information Model

Each job family shown in the Jobs tab and global banner should expose a presentation model with:

- `activity_label`: plain-English current action such as `Analyzing clips`, `Scanning historical detections`, `Waiting for classifier slots`, or `Paused by circuit breaker`
- `progress_label`: determinate progress like `143 / 800 events` or indeterminate progress like `Total work still expanding`
- `progress_unit`: explicit unit such as `events`, `frames`, or `queue items`
- `capacity_label`: truthful capacity text such as `1 of 2 worker slots busy` or `187 of 200 queue slots free`
- `blocker_label`: optional limiting factor such as `Throttled by live detections` or `Queue depth not reported`
- `freshness_label`: update age with stale state called out clearly
- `percent`: only when `current` and `total` represent a meaningful determinate unit
- `determinate`: whether the progress bar should render as determinate or indeterminate

The UI should derive this model centrally instead of assembling labels ad hoc inside multiple components.

## Telemetry Sources

The main sources remain:

- `jobProgressStore` for active job state, current/total, rate, ETA, stale status, and route
- `fetchAnalysisStatus()` for reclassification queue pressure and capacity
- existing queue telemetry aggregation in `Jobs.svelte`

The TypeScript contract for `AnalysisStatus` should be expanded to match the fields the backend already returns and the UI currently ignores:

- `max_concurrent_configured`
- `max_concurrent_effective`
- `mqtt_pressure_level`
- `throttled_for_mqtt_pressure`
- `mqtt_in_flight`
- `mqtt_in_flight_capacity`

The Jobs UI should not pull worker counts from diagnostics snapshots. Diagnostics remain useful for incident analysis, but the operational Jobs surface should rely on current live status.

## UI Changes

### Global Progress Banner

Refocus the banner into a compact summary strip:

- headline showing active job count
- subline naming the dominant work family and its current throughput or queue state
- aggregate progress bar only when totals are compatible
- indeterminate bar with explicit text when totals are not compatible
- detail rows for the first few active job families showing action, progress, capacity, blocker, and freshness

The banner should stop presenting a generic sum if the underlying jobs mix queue items, detections, and frames.

### Jobs Tab

Reorganize the page into three clearer sections.

#### 1. System Throughput

Show one card per job family with:

- queued count
- running count
- failed/completed counts
- worker slot usage when known
- queue free/capacity when known
- pause or throttle reason when present

#### 2. Active Jobs

Each active job card should show:

- title and job family
- plain-English current activity
- determinate or indeterminate progress label with explicit unit
- rate and ETA only when meaningful
- capacity row
- blocker row when present
- freshness row with stale emphasis

#### 3. Recent Outcomes

Keep this section lighter, but include a better final summary so the user can see what completed or failed without opening the originating route.

## Presentation Rules

- Determinate progress bars only render when `current` and `total` describe the same unit
- Indeterminate bars must include text explaining why total progress is unknown
- Capacity labels must only render when backed by real telemetry
- Unknown queue depth must be labeled as unknown, not treated as zero
- Stale work should switch to warning styling and copy such as `No update for 5m`
- Job titles can remain, but must no longer be the only explanation of what the card is doing

## Testing

Add focused coverage for the new presenter logic and rendering rules.

### Unit tests

- presenter output for queued, running, stale, and blocked states
- determinate versus indeterminate progress selection
- truthful capacity labels from analysis status
- blocker labels for circuit-open and MQTT-throttled states

### Component tests

- `Jobs.svelte` renders explicit action/progress/capacity labels
- `GlobalProgress.svelte` renders determinate and indeterminate states correctly
- stale jobs render warning treatment rather than normal running treatment

## Risks

- Overloading the screen with too many tiny metrics would hurt readability; the design should prefer a few plain-English labels over a dense debug panel
- Mixing diagnostics and operational telemetry would make the Jobs page noisy and inconsistent; keep diagnostics separate
- Aggregate progress must remain conservative to avoid misleading totals

## Success Criteria

The polished Jobs UI is successful if an owner can open Notifications and immediately understand:

- what each active job is doing
- whether the work is making progress
- what capacity is available
- whether a queue or circuit breaker is limiting throughput
- which values are known versus unknown
