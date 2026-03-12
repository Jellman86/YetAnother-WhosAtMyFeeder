# Owner Incident Workspace Design

## Goal

Replace the current owner-only Errors tab with an incident-focused operational workspace that aggregates system failures across YA-WAMF, preserves actionable evidence, and makes it easy to prepare high-quality GitHub issues.

## Problem

The current Errors page is a grouped diagnostics console, not a true troubleshooting surface.

Today the owner has to piece together failures from several partial sources:

- grouped frontend diagnostics in the Errors tab
- backend `error_diagnostics_history`
- `/health` snapshots
- Jobs and Notifications state
- ad hoc model or AI diagnostics elsewhere in the UI

That creates three practical problems:

- the page is centered on grouped records instead of incidents, so it is hard to answer “what is broken right now?”
- exported bundles are useful but incomplete; they do not consistently preserve timeline, environment identity, or newer worker/runtime recovery evidence
- there is no guided issue-reporting flow that turns evidence into something maintainers can actually action quickly

## Constraints

- Owner-only feature; do not optimize for anonymous or non-owner users
- Evidence must be truthful and preserve raw signals; the UI may summarize, but must not replace or invent evidence
- Job progress and incident state must remain authoritative; unknown values stay unknown
- Keep history bounded in memory and local storage
- Preserve offline usefulness: owners must still be able to capture/download bundles without GitHub API integration
- Prefer incremental refactor over a full observability platform or server-side incident database

## Recommended Approach

Build an owner-only incident workspace that correlates existing evidence streams into operator-facing incidents while preserving raw data for export.

The page should answer four questions quickly:

1. What is broken right now?
2. What recently went wrong?
3. What evidence do I have?
4. Can I open an actionable issue from here?

The existing grouped diagnostics model remains useful, but it becomes one evidence source inside the new incident model rather than the primary mental model.

## Incident Model

Represent owner-facing failures as bounded incidents with conservative correlation.

Each incident should include:

- `id`
- `status`: `open`, `recovering`, `resolved`
- `severity`: `info`, `warning`, `error`, `critical`
- `title`
- `summary`
- `started_at`
- `last_seen_at`
- `affected_area`: for example `live_detection`, `backfill`, `video`, `notifications`, `frontend`, `auth`, `storage`
- `primary_reason_code`
- `evidence_refs`
- `reportability`

Evidence flows through three layers:

1. Raw evidence
   - backend diagnostics events
   - health snapshots
   - frontend runtime errors
   - job/progress failures
   - worker/runtime recovery signals
   - version/config identity
2. Correlated incidents
   - owner-facing problem records built from the evidence above
3. Frozen bundles
   - downloadable support evidence that contains both summaries and raw records

The correlation layer must remain traceable. Every incident summary should link back to the evidence records that justified it.

## Evidence Contract

The new bundle format should be explicit and versioned, not just “export current JSON”.

### Bundle sections

1. `environment`
   - app version, git hash, build date
   - frontend version/build identity
   - owner role and client metadata that are safe to expose
   - timezone and locale
   - deployment/runtime flags relevant to troubleshooting
2. `health`
   - current health snapshot
   - recent health transition snapshots
   - event pipeline, DB pool, notification dispatcher, MQTT, classifier, video classifier state
   - worker pool state for `live`, `background`, and `video`
   - last runtime recovery details
3. `incidents`
   - current correlated incidents
   - recent resolved incidents
4. `timeline`
   - ordered evidence timeline combining backend diagnostics, frontend exceptions, health transitions, job transitions, worker restarts, circuit events, and recovery events
5. `jobs`
   - current and recent backfill/batch-analysis/video jobs
   - failures and stale states with authoritative totals only
6. `diagnostic_groups`
   - grouped summaries for readability
7. `raw_evidence`
   - backend diagnostics events
   - frontend/runtime records
   - health snapshots
   - recent worker stderr excerpts when available
   - startup warnings
8. `report`
   - bundle label
   - optional owner notes
   - generation timestamp
   - schema version

### Correctness rules

- summaries are additive; they do not replace raw evidence
- inferred statements must be marked as inferred
- unknown values remain unknown
- bounded retention must be explicit and visible

## Page Structure

Refactor the owner-only Errors tab into an incident workspace with four panels.

### 1. Current Issues

Shows open incidents only, with:

- severity
- affected area
- first seen / last seen
- short summary
- current status
- quick actions: inspect, capture evidence, copy issue summary, open issue

### 2. Incident Detail

Shows the selected incident with:

- human-readable summary
- evidence quality / readiness
- timeline
- affected jobs
- related diagnostic groups
- raw evidence preview

### 3. Evidence Bundles

Shows saved bundles with:

- label
- generated time
- app version
- incident count
- evidence coverage indicators
- actions: download, delete, copy issue body

### 4. Report Issue

Generates issue-ready content:

- suggested title
- short summary
- environment block
- incident summary
- reproduction / notes area
- GitHub issue URL shortcut with prefilled text

The UI should not directly mutate GitHub state. A prefilled issue flow plus bundle download is enough and keeps the feature robust.

## Touchpoints And Producers

To make this page comprehensive, standardize the evidence producers rather than adding more ad hoc UI logic.

### Backend producers

- event processor / event pipeline
- backfill service and backfill router
- classifier supervisor and worker failures
- worker runtime recovery / fallback state
- notification dispatcher
- video classification
- DB/storage failures
- startup/config/auth warnings that materially affect operation

### Frontend producers

- uncaught runtime exceptions
- owner-surface API failures
- job reconciliation anomalies
- bundle/report actions

### Shared evidence schema

Extend the current diagnostics schema to support:

- `source`
- `component`
- `reason_code`
- `severity`
- `stage`
- `message`
- `event_id`
- `timestamp`
- `context`
- optional `correlation_key`
- optional `job_id`
- optional `worker_pool`
- optional `runtime_recovery`
- optional `snapshot_ref`

The backend remains the authoritative recent event source. The frontend adds owner-session evidence and correlation, then exports both together.

## Backend API Shape

Keep the current lightweight `/api/diagnostics/errors` route, but add a richer bounded diagnostics payload for the owner incident workspace.

That payload should provide, in one request:

- recent backend diagnostics events
- latest health snapshot
- recent health snapshots if available
- worker/runtime pool summaries
- startup warnings
- bounded metadata needed for issue bundles

This avoids the UI stitching critical evidence from too many unrelated endpoints.

## Second- And Third-Order Effects

### Reliability

- The page must not become another synthetic state machine that diverges from backend truth.
- Correlation should be conservative so one bad heuristic does not create noisy false incidents.

### Supportability

- Bundles become a compatibility contract; once introduced, schema changes should be versioned.
- Preserving stderr/runtime recovery details prevents “worker exited” style dead ends in future debugging.

### Performance

- Diagnostics fetching must remain bounded and owner-only.
- Status polling should reuse existing health/diagnostics snapshots where possible instead of adding expensive new probes.

### Product behavior

- Resolved incidents should remain visible in a recent-history section for intermittent faults.
- Capturing a bundle must not clear or mutate live evidence.

## Testing Strategy

Backend tests:

- diagnostics payload shape and bounds
- richer event schema normalization
- worker/runtime recovery evidence inclusion
- issue-bundle export payload stability

Frontend tests:

- incident correlation from mixed evidence sources
- no fabricated progress or false “resolved” states
- refresh persistence
- bundle capture/download behavior
- issue-body generation
- current vs recent incident separation

Integration tests:

- live classifier failure becomes a current incident with actionable evidence
- backfill failure appears with related job state and backend diagnostics
- frontend exception creates a frontend-scoped incident without hiding backend truth
- resolved incidents move out of Current Issues but remain in Recent Incidents

## Out Of Scope

- automatic GitHub issue creation via API
- a durable server-side incident database
- exposing the page to non-owner users
- replacing all existing diagnostics endpoints in one pass
