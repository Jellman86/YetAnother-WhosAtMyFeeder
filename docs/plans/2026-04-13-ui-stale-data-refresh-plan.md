# UI Stale Data Refresh — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate stale data in the detection modal, dashboard, and other pages by adding a lightweight refresh layer driven by navigation and tab-visibility signals.

**Architecture:** A `StaleTracker` utility tracks `lastFetchedAt` per store; a `RefreshCoordinator` singleton listens to the custom `navigate()` call and `document.visibilitychange`, then sweeps all registered stores calling `refreshIfStale()`. Pages already remount on navigation in this custom SPA router so `onMount` re-fetches already happen — the coordinator catches stores that are shared/long-lived (detections, settings, auth). The detection modal gets a dedicated fix: `ensureAvailability()` is called with `{ refresh: true }` the first time a modal opens for a given event ID so a cached `unavailable` state is re-probed.

**Tech Stack:** Svelte 5 runes (`$state`), TypeScript, custom SPA router in App.svelte, existing `fullVisitStore.ensureAvailability({ refresh })` API

---

## Important Context

- This app is **NOT** SvelteKit routing. It uses a custom `navigate()` function and `currentRoute` state in App.svelte. There is no `afterNavigate` from SvelteKit.
- Pages (`Dashboard`, `Events`, `Species`, `Errors`) **do** mount/unmount on navigation, so their `onMount` hooks already fire fresh on each navigation. The coordinator is mainly needed for shared singleton stores (`detectionsStore`, `settingsStore`, `authStore`).
- `fullVisitStore.ensureAvailability(id, { refresh?: boolean })` already supports forced re-probe — it just isn't being called with `refresh: true` when the modal opens.
- `detectionsStore.loadInitial()` is called once at app startup but **not** on SSE reconnect — events missed during SSE downtime are never backfilled until page reload.

---

## Task 1: StaleTracker utility

**Files:**
- Create: `apps/ui/src/lib/utils/stale_tracker.ts`

**Step 1: Write the file**

```typescript
/**
 * Tracks whether a data source is stale based on elapsed time since last fetch.
 * Compose this into a store class — do not inherit from it.
 */
export class StaleTracker {
    private lastFetchedAt = $state(0);

    constructor(private readonly maxAgeMs: number) {}

    /** Call after every successful fetch to mark data as fresh. */
    touch(): void {
        this.lastFetchedAt = Date.now();
    }

    /** Returns true if the data has never been fetched or was fetched longer ago than maxAgeMs. */
    isStale(): boolean {
        return Date.now() - this.lastFetchedAt > this.maxAgeMs;
    }

    /** Force data to be considered stale on the next sweep (e.g. after logout). */
    reset(): void {
        this.lastFetchedAt = 0;
    }
}
```

**Step 2: Type-check**
```bash
cd apps/ui && npm run check 2>&1 | tail -20
```
Expected: no errors from this new file.

**Step 3: Commit**
```bash
git add apps/ui/src/lib/utils/stale_tracker.ts
git commit -m "feat(ui): add StaleTracker utility for data freshness tracking"
```

---

## Task 2: RefreshCoordinator store

**Files:**
- Create: `apps/ui/src/lib/stores/refresh_coordinator.svelte.ts`

**Step 1: Write the file**

```typescript
/**
 * Central coordinator that triggers background data refreshes when the user
 * navigates or returns to the browser tab.
 *
 * Stores register a `refreshIfStale` callback in their constructor.
 * App.svelte calls `coordinator.onNavigate()` inside navigate() and
 * adds `coordinator.onVisibilityChange()` to the visibilitychange listener.
 */

type RefreshCallback = () => Promise<void> | void;

class RefreshCoordinator {
    private callbacks = new Set<RefreshCallback>();
    private debounceTimer: ReturnType<typeof setTimeout> | null = null;

    /** Register a store's refreshIfStale method. Returns an unregister function. */
    register(cb: RefreshCallback): () => void {
        this.callbacks.add(cb);
        return () => this.callbacks.delete(cb);
    }

    /** Call from navigate() in App.svelte after updating currentRoute. */
    onNavigate(): void {
        this.sweep();
    }

    /** Call from the visibilitychange handler in App.svelte when tab becomes visible. */
    onVisibilityChange(): void {
        if (document.hidden) return;
        this.sweep();
    }

    /** Call after SSE reconnects so stores catch up on any missed events. */
    onSseReconnect(): void {
        this.sweep();
    }

    private sweep(): void {
        // Debounce: navigation + visibilitychange can fire together; one sweep is enough.
        if (this.debounceTimer !== null) return;
        this.debounceTimer = setTimeout(() => {
            this.debounceTimer = null;
            for (const cb of this.callbacks) {
                void Promise.resolve(cb()).catch((err) => {
                    console.warn('[RefreshCoordinator] refreshIfStale error', err);
                });
            }
        }, 150);
    }
}

export const refreshCoordinator = new RefreshCoordinator();
```

**Step 2: Type-check**
```bash
cd apps/ui && npm run check 2>&1 | tail -20
```

**Step 3: Commit**
```bash
git add apps/ui/src/lib/stores/refresh_coordinator.svelte.ts
git commit -m "feat(ui): add RefreshCoordinator for navigate/visibility-driven store sweeps"
```

---

## Task 3: Wire coordinator into App.svelte

**Files:**
- Modify: `apps/ui/src/App.svelte`

### Step 1: Import the coordinator

At the top of the `<script>` block, alongside the other store imports, add:

```typescript
import { refreshCoordinator } from './lib/stores/refresh_coordinator.svelte';
```

Find the existing import block around line 1-50 in App.svelte. Add the import after the existing store imports.

### Step 2: Call `onNavigate` inside `navigate()`

Find the `navigate()` function (around line 81):
```typescript
function navigate(path: string, opts: { replace?: boolean } = {}) {
    const targetPath = normalizeRouteForCurrentAccess(path);
    const isDashboardRefresh = targetPath === '/' && currentRoute === '/' && !opts.replace;
    if (isDashboardRefresh) {
        dashboardRefreshKey += 1;
    }
    currentRoute = targetPath;
    if (opts.replace) window.history.replaceState(null, '', targetPath);
    else window.history.pushState(null, '', targetPath);
}
```

Add `refreshCoordinator.onNavigate();` at the end:
```typescript
function navigate(path: string, opts: { replace?: boolean } = {}) {
    const targetPath = normalizeRouteForCurrentAccess(path);
    const isDashboardRefresh = targetPath === '/' && currentRoute === '/' && !opts.replace;
    if (isDashboardRefresh) {
        dashboardRefreshKey += 1;
    }
    currentRoute = targetPath;
    if (opts.replace) window.history.replaceState(null, '', targetPath);
    else window.history.pushState(null, '', targetPath);
    refreshCoordinator.onNavigate();
}
```

### Step 3: Extend the visibilitychange handler

Find the existing `handleVisibilityChange` function (around line 320):
```typescript
const handleVisibilityChange = () => {
    if (!document.hidden && !detectionsStore.connected && !isReconnecting) {
        logger.info("Tab became visible, attempting to reconnect SSE");
        reconnectAttempts = 0;
        scheduleReconnect();
    }
    if (!document.hidden) {
        void reclassifyRecovery.reconcile();
        void liveUpdates.syncAnalysisQueueStatus();
    }
};
```

Add `refreshCoordinator.onVisibilityChange();` in the `!document.hidden` block:
```typescript
const handleVisibilityChange = () => {
    if (!document.hidden && !detectionsStore.connected && !isReconnecting) {
        logger.info("Tab became visible, attempting to reconnect SSE");
        reconnectAttempts = 0;
        scheduleReconnect();
    }
    if (!document.hidden) {
        void reclassifyRecovery.reconcile();
        void liveUpdates.syncAnalysisQueueStatus();
        refreshCoordinator.onVisibilityChange();
    }
};
```

### Step 4: Call `onSseReconnect` when SSE connection opens

Find the `evtSource.onopen` handler (around line 456):
```typescript
evtSource.onopen = () => {
    logger.sseEvent("connection_opened");
    notificationCenter.remove('system:sse-disconnected');
};
```

Add coordinator notification AND detections reload so missed events are caught:
```typescript
evtSource.onopen = () => {
    logger.sseEvent("connection_opened");
    notificationCenter.remove('system:sse-disconnected');
    refreshCoordinator.onSseReconnect();
};
```

**Step 5: Type-check**
```bash
cd apps/ui && npm run check 2>&1 | tail -20
```

**Step 6: Commit**
```bash
git add apps/ui/src/App.svelte
git commit -m "feat(ui): wire RefreshCoordinator into navigate(), visibilitychange, and SSE onopen"
```

---

## Task 4: Add refreshIfStale to DetectionsStore

**Files:**
- Modify: `apps/ui/src/lib/stores/detections.svelte.ts`

The detections store is loaded once at app startup. Missed events during SSE downtime are never backfilled. This task adds a 30-second stale threshold so that navigation and tab-focus trigger a catch-up reload when needed.

### Step 1: Import dependencies

At the top of `detections.svelte.ts`, add:
```typescript
import { StaleTracker } from '../utils/stale_tracker';
import { refreshCoordinator } from './refresh_coordinator.svelte';
```

### Step 2: Add StaleTracker and register with coordinator

Inside the `DetectionsStore` class, add after the existing `private` constants:

```typescript
private readonly staleTracker = new StaleTracker(30_000); // 30 seconds
private unregister: (() => void) | null = null;
```

Add a `constructor` that registers with the coordinator:
```typescript
constructor() {
    this.unregister = refreshCoordinator.register(() => this.refreshIfStale());
}
```

### Step 3: Add refreshIfStale method

Add after `loadInitial()`:
```typescript
async refreshIfStale(): Promise<void> {
    if (!this.staleTracker.isStale()) return;
    await this.loadInitial();
}
```

### Step 4: Mark fresh after loadInitial succeeds

Inside `loadInitial()`, add `this.staleTracker.touch()` after the assignments on the success path:
```typescript
async loadInitial() {
    this.isLoading = true;
    try {
        const d = new Date();
        d.setDate(d.getDate() - 3);
        const startDate = toLocalYMD(d);

        const [recent, countResult] = await Promise.all([
            fetchEvents({ limit: this.MAX_ITEMS, startDate }),
            fetchEventsCount({ startDate: toLocalYMD(), endDate: toLocalYMD() })
        ]);
        this.detections = recent;
        this.totalToday = countResult.count;
        this.markMutated();
        this.staleTracker.touch(); // ← add this line
    } catch (e) {
        // existing error handling unchanged
        ...
    } finally {
        this.isLoading = false;
    }
}
```

**Step 5: Type-check**
```bash
cd apps/ui && npm run check 2>&1 | tail -20
```

**Step 6: Commit**
```bash
git add apps/ui/src/lib/stores/detections.svelte.ts
git commit -m "feat(ui): add refreshIfStale to DetectionsStore (30s threshold)"
```

---

## Task 5: Add refreshIfStale to SettingsStore

**Files:**
- Modify: `apps/ui/src/lib/stores/settings.svelte.ts`

Settings are loaded once at app startup. This adds a 5-minute threshold.

### Step 1: Import dependencies

```typescript
import { StaleTracker } from '../utils/stale_tracker';
import { refreshCoordinator } from './refresh_coordinator.svelte';
```

### Step 2: Add StaleTracker, constructor, and refreshIfStale

Inside `SettingsStore`, add:
```typescript
private readonly staleTracker = new StaleTracker(300_000); // 5 minutes
private unregister: (() => void) | null = null;

constructor() {
    this.unregister = refreshCoordinator.register(() => this.refreshIfStale());
}

async refreshIfStale(): Promise<void> {
    if (!this.staleTracker.isStale()) return;
    if (!this._loadPromise) {
        // Reset the dedup guard so load() fetches fresh data.
        // We only do this when we've decided the data is stale.
        await this.load();
    }
}
```

### Step 3: Touch after successful load

In the existing `load()` method, add `this.staleTracker.touch()` after `this.settings = await fetchSettings()`:
```typescript
this.settings = await fetchSettings();
this.staleTracker.touch(); // ← add this line
```

**Important:** `_loadPromise` is set to null in the `finally` block already, so `refreshIfStale` doesn't need to clear it — the next call to `load()` after reset will fetch fresh data.

Actually the current `load()` uses `_loadPromise` as a dedup guard:
```typescript
async load() {
    if (this._loadPromise) return this._loadPromise;
    this._loadPromise = (async () => { ... })();
    return this._loadPromise;
}
```

For `refreshIfStale`, we want to force a fresh load. The cleanest approach: call `this.load()` normally since `_loadPromise` is always cleared in the `finally` block. The dedup guard prevents overlapping calls but not sequential refreshes. So:

```typescript
async refreshIfStale(): Promise<void> {
    if (!this.staleTracker.isStale()) return;
    await this.load();
}
```

This works because `_loadPromise` is null after previous load completes, so `load()` will run fresh.

**Step 4: Type-check**
```bash
cd apps/ui && npm run check 2>&1 | tail -20
```

**Step 5: Commit**
```bash
git add apps/ui/src/lib/stores/settings.svelte.ts
git commit -m "feat(ui): add refreshIfStale to SettingsStore (5 min threshold)"
```

---

## Task 6: Add refreshIfStale to AuthStore

**Files:**
- Modify: `apps/ui/src/lib/stores/auth.svelte.ts`

Auth/feature flags refreshed at 5-minute threshold.

### Step 1: Import dependencies

```typescript
import { StaleTracker } from '../utils/stale_tracker';
import { refreshCoordinator } from './refresh_coordinator.svelte';
```

### Step 2: Add StaleTracker and refreshIfStale

Inside `AuthStore`, add:
```typescript
private readonly staleTracker = new StaleTracker(300_000); // 5 minutes
private unregister: (() => void) | null = null;
```

Update the existing `constructor()`:
```typescript
constructor() {
    // Status is loaded via loadStatus()
    this.unregister = refreshCoordinator.register(() => this.refreshIfStale());
}
```

Add:
```typescript
async refreshIfStale(): Promise<void> {
    if (!this.staleTracker.isStale()) return;
    await this.loadStatus();
}
```

### Step 3: Touch after successful loadStatus

In `loadStatus()`, add `this.staleTracker.touch()` at the end of the `try` block, after `this.statusHealthy = true`:
```typescript
this.statusHealthy = true;
this.staleTracker.touch(); // ← add this line
```

**Step 4: Also reset StaleTracker on logout so next action fetches fresh auth**

In the `logout()` method, add `this.staleTracker.reset()` after `await apiLogout()`:
```typescript
async logout() {
    await apiLogout();
    this.staleTracker.reset(); // ← add this line
    this.token = null;
    await this.loadStatus();
}
```

**Step 5: Type-check**
```bash
cd apps/ui && npm run check 2>&1 | tail -20
```

**Step 6: Commit**
```bash
git add apps/ui/src/lib/stores/auth.svelte.ts
git commit -m "feat(ui): add refreshIfStale to AuthStore (5 min threshold); reset on logout"
```

---

## Task 7: Fix detection modal — force full-visit re-probe on open

**Files:**
- Modify: `apps/ui/src/lib/pages/Dashboard.svelte`

**Problem:** When you open the detection modal for an event whose full-visit availability was previously cached as `unavailable`, the modal shows stale availability state. `fullVisitStore.ensureAvailability()` skips re-probing unless `{ refresh: true }` is passed.

**Fix:** Track the last event ID for which we probed on modal-open. When `selectedEvent` changes to a new event ID (modal opens for a different detection), call `ensureAvailability` with `{ refresh: true }` so the cache is bypassed.

### Step 1: Add lastModalEventId tracking

After the existing state declarations (around line 36-40 of Dashboard.svelte), add:
```typescript
let lastModalEventId = $state<string | null>(null);
```

### Step 2: Update the modal full-visit effect

Find the existing effect (around line 114-117):
```typescript
$effect(() => {
    if (!recordingClipFetchEnabled || !selectedEvent) return;
    void fullVisitStore.ensureAvailability(selectedEvent.frigate_event);
});
```

Replace with:
```typescript
$effect(() => {
    if (!recordingClipFetchEnabled || !selectedEvent) {
        // Modal closed — do not reset lastModalEventId so re-opening same
        // detection doesn't re-probe unnecessarily within a short window.
        return;
    }
    const eventId = selectedEvent.frigate_event;
    const isNewOpen = eventId !== lastModalEventId;
    if (isNewOpen) {
        lastModalEventId = eventId;
        // Force fresh probe so a cached 'unavailable' state is re-checked.
        void fullVisitStore.ensureAvailability(eventId, { refresh: true });
    } else {
        // Same event, modal already open (SSE update to selectedEvent).
        // Non-refresh probe respects existing cache — no extra round-trips.
        void fullVisitStore.ensureAvailability(eventId);
    }
});
```

**Step 3: Verify Events page has the same pattern**

Check if Events.svelte has a similar full-visit `ensureAvailability` call for its modal. If so, apply the same `lastModalEventId` pattern there too.

```bash
grep -n "ensureAvailability\|selectedEvent" /config/workspace/YA-WAMF/apps/ui/src/lib/pages/Events.svelte | head -20
```

Apply the same fix to Events.svelte if it has a modal open pattern.

**Step 4: Type-check**
```bash
cd apps/ui && npm run check 2>&1 | tail -20
```

**Step 5: Commit**
```bash
git add apps/ui/src/lib/pages/Dashboard.svelte
# Include Events.svelte if modified in step 3
git commit -m "fix(ui): re-probe full-visit availability when detection modal opens"
```

---

## Task 8: Reload detections on SSE reconnect

**Files:**
- Modify: `apps/ui/src/App.svelte`

When SSE reconnects after a gap, events that arrived during the downtime are missing from the detections store. The `onopen` handler fires after every reconnect. We should trigger a `refreshIfStale` on the detections store there. Since Task 3 already calls `refreshCoordinator.onSseReconnect()` in `onopen`, and Task 4 registered the detections store with a 30-second threshold, this is already handled by the coordinator.

However, SSE `onopen` fires for the initial connection too (where detections were just loaded at startup). The 30-second threshold prevents an unnecessary double-fetch on first connect (startup fetch → SSE opens < 30s later → stale check → not stale).

**Verification:** Confirm the flow works:
1. App starts → `detectionsStore.loadInitial()` → `staleTracker.touch()` at t=0
2. SSE opens at t=1s → coordinator sweeps → `refreshIfStale()` → not stale (1s < 30s) → skip ✓
3. SSE drops at t=120s, reconnects at t=180s → coordinator sweeps → `refreshIfStale()` → stale (180s > 30s) → reloads ✓

No additional code needed. This task is validation only.

**Step 1: Confirm the flow**
Read through the changes from Tasks 3 and 4 and trace the SSE reconnect flow. Verify the 30-second threshold prevents double-fetch on startup.

**Step 2: Commit note**
No file changes — this task confirmed the coordinator + threshold design handles SSE reconnect backfill correctly.

---

## Task 9: Final type-check and push

**Step 1: Full type-check**
```bash
cd apps/ui && npm run check 2>&1
```
Expected: 0 errors (or same pre-existing errors as before this change set).

**Step 2: Verify no regressions with a quick build**
```bash
cd apps/ui && npm run build 2>&1 | tail -30
```
Expected: build succeeds.

**Step 3: Commit changelog and version bump**

Add an entry to CHANGELOG.md under `[Unreleased]`:
```markdown
### Fixed
- Detection modal now re-probes full-visit clip availability when opened, clearing stale 'unavailable' cache from a previous check.
- Detections list, settings, and auth feature flags are now refreshed automatically when navigating between pages or returning to a backgrounded tab, preventing stale data after long sessions or SSE reconnects.
```

**Step 4: Push to dev**
```bash
git push origin dev
```

---

## Summary of Changes

| File | Change |
|---|---|
| `lib/utils/stale_tracker.ts` | New — StaleTracker class |
| `lib/stores/refresh_coordinator.svelte.ts` | New — coordinator singleton |
| `App.svelte` | Wire coordinator: navigate, visibilitychange, SSE onopen |
| `lib/stores/detections.svelte.ts` | StaleTracker (30s) + refreshIfStale + register |
| `lib/stores/settings.svelte.ts` | StaleTracker (5min) + refreshIfStale + register |
| `lib/stores/auth.svelte.ts` | StaleTracker (5min) + refreshIfStale + register + reset on logout |
| `lib/pages/Dashboard.svelte` | Force full-visit re-probe on modal open |
| `lib/pages/Events.svelte` | Same full-visit fix if modal pattern present |
