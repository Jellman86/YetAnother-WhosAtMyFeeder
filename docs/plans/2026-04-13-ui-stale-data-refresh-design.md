# UI Stale Data Refresh — Design

**Date:** 2026-04-13  
**Status:** Approved

## Problem

Several pages and modals display stale data after navigation or tab-switching:

- **Detection detail modal** opens with a snapshot/full-visit state from when the parent page last loaded, not the current server state.
- **Dashboard summary** (daily count, top species) is loaded once on mount and never refreshed.
- **Errors / Incident Workspace** fetches once on mount; resolved or new incidents aren't reflected without a manual refresh.
- **Species leaderboard** is static after load — new detections don't update counts.
- **Events page** can show an outdated list if the user navigated away and returned.
- **Settings and Auth** are fetched once at app startup; remote changes are invisible.

## Approach — afterNavigate + Page Visibility refresh (Approach B)

Two browser signals drive refreshes:

1. **SvelteKit `afterNavigate`** — fires each time the user arrives at any page.
2. **`document.visibilitychange`** — fires when the browser tab regains focus after being hidden.

Each store tracks a `lastFetchedAt` timestamp and a `maxAgeMs` threshold. When either signal fires, the coordinator sweeps all registered stores and calls `refreshIfStale()` on each. Stale stores re-fetch silently in the background; the UI renders existing (possibly stale) data immediately and updates naturally when the fetch resolves — the same flow SSE updates already use. No loading spinners, no flicker.

The detection detail modal additionally fetches its detection by ID when opened, so it always reflects the current server state regardless of how long the parent page has been loaded.

## Components

### 1. `StaleTracker` (utility class — `lib/utils/stale_tracker.ts`)

```typescript
export class StaleTracker {
    private lastFetchedAt = $state(0);
    constructor(private maxAgeMs: number) {}
    touch(): void { this.lastFetchedAt = Date.now(); }
    isStale(): boolean { return Date.now() - this.lastFetchedAt > this.maxAgeMs; }
    reset(): void { this.lastFetchedAt = 0; }
}
```

Composed into each store — not inherited. Calling `touch()` after a successful fetch marks data fresh. `reset()` is available to force a re-fetch on the next signal (e.g. after logout).

### 2. `RefreshCoordinator` (singleton — `lib/stores/refresh_coordinator.svelte.ts`)

- Singleton instance created at module scope.
- Stores call `coordinator.register(refreshIfStaleFn)` in their constructor and `coordinator.unregister(fn)` on destroy.
- The coordinator exposes a `sweep()` method that calls every registered `refreshIfStale()` in parallel.
- `sweep()` is debounced with a 150 ms trailing edge so a simultaneous navigation + visibilitychange only triggers one sweep.
- The coordinator is initialised from `App.svelte` once the app is ready: it attaches the `visibilitychange` listener and calls `afterNavigate(() => coordinator.sweep())`.

### 3. `refreshIfStale()` on each store

Each store implementing this pattern gets:

```typescript
async refreshIfStale(): Promise<void> {
    if (!this.staleTracker.isStale()) return;
    await this.fetch();          // existing fetch logic
    this.staleTracker.touch();   // mark fresh on success
}
```

Errors during background re-fetch are swallowed silently (same as the current polling pattern). The store's existing error-handling path logs or toasts if needed.

### 4. Detection modal — fetch by ID on open

`DetectionModal.svelte` calls `GET /api/detections/{id}` when the modal opens. The prop passed from the parent provides an instant render (no blank flash); the fresh response merges into local state within a few hundred milliseconds. Full-visit availability is also re-probed on open via the existing `ensureAvailability()` path.

## Per-Store Max-Age Thresholds

| Store / Data | Max-age |
|---|---|
| Detections list (dashboard cards) | 30 s |
| Dashboard daily summary | 60 s |
| Events list | 30 s |
| Species leaderboard | 120 s |
| Incident workspace (Errors page) | 60 s |
| Settings | 300 s |
| Auth / feature flags | 300 s |

Thresholds are constants defined in each store (not the coordinator) so they can be tuned independently.

## Data Flow

```
Tab gains focus  ─┐
                   ├─→ coordinator.sweep()  ─→  store.refreshIfStale()  ─→  fetch (if stale)  ─→  store state updated  ─→  UI re-renders
SvelteKit nav   ─┘

Modal opens  ─→  GET /api/detections/{id}  ─→  merge into modal local state
           ─→  ensureAvailability()         ─→  full-visit probe
```

## What This Does NOT Change

- SSE-driven real-time updates continue unchanged — they are the primary mechanism for live data.
- The ref-counted polling for Analysis Queue and Backfill Status (Jobs page) is left as-is — those stores are fine while Jobs page is mounted and are not visible elsewhere.
- No loading spinners are added — staleness is resolved silently in the background.
- No server-side changes are required.

## Error Handling

Background `refreshIfStale()` calls that fail:
- Do not surface to the user (silent failure is acceptable — the data is slightly stale, not wrong).
- Do not advance `lastFetchedAt`, so the next sweep will retry.
- Existing store error paths (toast notifications for deliberate user actions) are unaffected.

## Files Changed

| File | Change |
|---|---|
| `lib/utils/stale_tracker.ts` | New — `StaleTracker` class |
| `lib/stores/refresh_coordinator.svelte.ts` | New — coordinator singleton |
| `App.svelte` | Wire coordinator: attach `visibilitychange` + `afterNavigate` |
| `lib/stores/detections.svelte.ts` | Add `StaleTracker` + `refreshIfStale` + register |
| `lib/stores/settings.svelte.ts` | Add `StaleTracker` + `refreshIfStale` + register |
| `lib/stores/auth.svelte.ts` | Add `StaleTracker` + `refreshIfStale` + register |
| `lib/pages/Dashboard.svelte` | Add `StaleTracker` + re-fetch summary on coordinator signal |
| `lib/pages/Species.svelte` | Add `StaleTracker` + re-fetch leaderboard on coordinator signal |
| `lib/pages/Errors.svelte` | Add `StaleTracker` + re-fetch workspace on coordinator signal |
| `lib/components/DetectionModal.svelte` | Fetch detection by ID on open; re-probe full-visit |
