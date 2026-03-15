# Errors Tab Backend-Only Design

## Goal

Make the live Notifications `Errors` tab show backend-recorded operational failures only, while keeping frontend/client diagnostics available in captured support bundles.

## Problem

The current Errors tab mixes two different categories:

- backend diagnostics from `/api/diagnostics/workspace`
- frontend/local runtime diagnostics recorded into `jobDiagnosticsStore`

That makes the live surface noisy and can elevate client polling failures like cache-status fetch issues to the same prominence as actual backend faults.

## Decision

The live Errors tab will become backend-only by default.

- `currentIssues` and `recentIncidents` will continue to come from backend diagnostics correlation in `incidentWorkspaceStore`
- grouped diagnostics rendered in `Errors.svelte` will be filtered to backend-backed groups only
- frontend/local diagnostics will no longer appear in the live grouped error UI
- captured/downloadable bundles will still include frontend/local diagnostics so support evidence is preserved

## Data Flow

### Live tab

- `incidentWorkspaceStore.currentIssues`
- `incidentWorkspaceStore.recentIncidents`
- backend-only diagnostic groups derived from `selectedIncident`

### Bundles

- existing `jobDiagnosticsStore.captureBundle()` payload stays intact
- local runtime diagnostics remain included there

## Implementation Shape

1. Add an explicit backend-only diagnostic-group accessor to `incidentWorkspaceStore`.
2. Update `Errors.svelte` to use backend-only groups for the live tab instead of `jobDiagnosticsStore.groups`.
3. Update counts and empty-state behavior so they reflect backend-visible issues only.
4. Leave bundle export and bundle capture behavior unchanged.

## Risks

- Some currently visible frontend fetch problems will disappear from the live tab. That is intentional.
- If any operationally important issue currently exists only as a frontend-local diagnostic, it should eventually be recorded server-side instead of relying on the client tab.

## Verification

- incident workspace tests prove backend-only incidents still render
- new regression test proves local-only diagnostics are excluded from live groups
- bundle tests prove local diagnostics remain in captured bundles
- `svelte-check` stays clean
