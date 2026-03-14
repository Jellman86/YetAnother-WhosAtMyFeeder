# Notifications Jobs UI Polish Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the Notifications Jobs tab and global progress banner clearly explain what active jobs are doing, whether progress is determinate, what capacity is available, and what is blocking throughput.

**Architecture:** Add a small UI-side presenter layer that converts `jobProgressStore` items plus reclassification queue telemetry into explicit display models. Update `Jobs.svelte` and `GlobalProgress.svelte` to render those models, and extend the frontend `AnalysisStatus` contract to consume backend fields that already exist but are currently ignored.

**Tech Stack:** Svelte 5, TypeScript, Vitest, svelte-check, Vite

---

### Task 1: Expand The Queue Telemetry Contract

**Files:**
- Modify: `apps/ui/src/lib/api/maintenance.ts`
- Test: `apps/ui/src/lib/jobs/pipeline.test.ts`

**Step 1: Write the failing test**

Extend `apps/ui/src/lib/jobs/pipeline.test.ts` with a case proving the frontend queue telemetry model preserves:

- configured concurrency
- effective concurrency
- MQTT pressure state
- MQTT in-flight load

Example assertion target:

```ts
expect(queueTelemetry.reclassify).toMatchObject({
    queued: 12,
    running: 2,
    maxConcurrentConfigured: 4,
    maxConcurrentEffective: 2,
    mqttPressureLevel: 'high',
    throttledForMqttPressure: true,
    mqttInFlight: 9,
    mqttInFlightCapacity: 10
});
```

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run test -- src/lib/jobs/pipeline.test.ts
```

Expected: FAIL because the telemetry shape does not include the added fields yet.

**Step 3: Write minimal implementation**

Update `apps/ui/src/lib/api/maintenance.ts` so `AnalysisStatus` includes:

```ts
max_concurrent_configured?: number;
max_concurrent_effective?: number;
mqtt_pressure_level?: string;
throttled_for_mqtt_pressure?: boolean;
mqtt_in_flight?: number;
mqtt_in_flight_capacity?: number;
```

Update the queue telemetry types used by the jobs pipeline so those values can be carried into the presenter layer.

**Step 4: Run test to verify it passes**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run test -- src/lib/jobs/pipeline.test.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission add apps/ui/src/lib/api/maintenance.ts apps/ui/src/lib/jobs/pipeline.test.ts
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission commit -m "test: expand jobs queue telemetry contract"
```

### Task 2: Add A Jobs Presentation Layer

**Files:**
- Create: `apps/ui/src/lib/jobs/presenter.ts`
- Create: `apps/ui/src/lib/jobs/presenter.test.ts`
- Modify: `apps/ui/src/lib/jobs/pipeline.ts`

**Step 1: Write the failing test**

Create `apps/ui/src/lib/jobs/presenter.test.ts` with cases for:

- determinate progress labels for known totals
- indeterminate progress labels when totals are missing or mixed
- capacity labels such as `1 of 2 worker slots busy`
- blocker labels such as `Paused by circuit breaker` and `Throttled by live detections`
- stale job labeling

Example shape:

```ts
expect(model.activityLabel).toBe('Waiting for classifier slots');
expect(model.capacityLabel).toBe('1 of 2 worker slots busy');
expect(model.blockerLabel).toBe('MQTT pressure reduced background capacity');
expect(model.determinate).toBe(false);
```

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run test -- src/lib/jobs/presenter.test.ts
```

Expected: FAIL because `presenter.ts` does not exist yet.

**Step 3: Write minimal implementation**

Create `apps/ui/src/lib/jobs/presenter.ts` with pure functions that:

- normalize queue telemetry into job-family capacity signals
- derive `activityLabel`, `progressLabel`, `capacityLabel`, `blockerLabel`, `freshnessLabel`, `percent`, and `determinate`
- avoid returning misleading percentages when units are not compatible

Keep `apps/ui/src/lib/jobs/pipeline.ts` focused on counts and family-level aggregation, then layer presentation logic on top.

**Step 4: Run test to verify it passes**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run test -- src/lib/jobs/presenter.test.ts src/lib/jobs/pipeline.test.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission add apps/ui/src/lib/jobs/presenter.ts apps/ui/src/lib/jobs/presenter.test.ts apps/ui/src/lib/jobs/pipeline.ts
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission commit -m "feat: add jobs presentation model"
```

### Task 3: Rebuild The Jobs Tab Around Explicit Status Labels

**Files:**
- Modify: `apps/ui/src/lib/pages/Jobs.svelte`
- Modify: `apps/ui/src/lib/i18n/locales/en.json`
- Test: `apps/ui/src/lib/jobs/presenter.test.ts`
- Test: `apps/ui/src/lib/i18n/locales.jobs-errors.test.ts`

**Step 1: Write the failing test**

Add presenter expectations covering the exact copy and fallback logic the Jobs tab depends on, such as:

- `Queue depth not reported`
- `Total work still expanding`
- `No update for 5m`
- `187 of 200 queue slots free`

Add locale assertions in `apps/ui/src/lib/i18n/locales.jobs-errors.test.ts` for any new `jobs.*` keys.

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run test -- src/lib/jobs/presenter.test.ts src/lib/i18n/locales.jobs-errors.test.ts
```

Expected: FAIL because the new strings and presenter outputs are not implemented yet.

**Step 3: Write minimal implementation**

Update `apps/ui/src/lib/pages/Jobs.svelte` to:

- use the presenter output instead of raw `job.title` and `job.message` as the primary explanation
- add a `System Throughput` section for queue/capacity cards
- render explicit action, progress, capacity, blocker, and freshness labels on active job cards
- only render determinate bars when the presenter says the value is determinate
- render stale jobs with warning treatment

Add only the i18n keys required by the new copy in `apps/ui/src/lib/i18n/locales/en.json`.

**Step 4: Run test to verify it passes**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run test -- src/lib/jobs/presenter.test.ts src/lib/i18n/locales.jobs-errors.test.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission add apps/ui/src/lib/pages/Jobs.svelte apps/ui/src/lib/i18n/locales/en.json apps/ui/src/lib/jobs/presenter.test.ts apps/ui/src/lib/i18n/locales.jobs-errors.test.ts
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission commit -m "feat: clarify notifications jobs status ui"
```

### Task 4: Rebuild The Global Progress Banner

**Files:**
- Modify: `apps/ui/src/lib/components/GlobalProgress.svelte`
- Modify: `apps/ui/src/lib/jobs/presenter.ts`
- Test: `apps/ui/src/lib/jobs/presenter.test.ts`

**Step 1: Write the failing test**

Add presenter-level tests for banner summaries that prove:

- compatible totals yield a determinate aggregate percent
- mixed units yield an indeterminate summary
- dominant work-family summary prefers real queue/capacity signals over raw job titles

Example:

```ts
expect(summary.headline).toBe('3 background jobs active');
expect(summary.subline).toBe('Reclassification using 1 of 2 worker slots, 12 queued');
expect(summary.determinate).toBe(false);
```

**Step 2: Run test to verify it fails**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run test -- src/lib/jobs/presenter.test.ts
```

Expected: FAIL because the banner summary model is not implemented yet.

**Step 3: Write minimal implementation**

Update `apps/ui/src/lib/components/GlobalProgress.svelte` to consume banner summary and per-family detail rows from the presenter layer. Remove the existing generic aggregate logic that can mix incompatible units, and replace it with:

- determinate aggregate output when safe
- indeterminate bar and explanatory copy when unsafe
- detail rows that show action, capacity, blocker, and freshness

**Step 4: Run test to verify it passes**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run test -- src/lib/jobs/presenter.test.ts
```

Expected: PASS

**Step 5: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission add apps/ui/src/lib/components/GlobalProgress.svelte apps/ui/src/lib/jobs/presenter.ts apps/ui/src/lib/jobs/presenter.test.ts
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission commit -m "feat: polish global jobs progress banner"
```

### Task 5: Final Verification And User-Facing Notes

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Write the failing test**

No new failing unit test here. This task is for verification and release notes.

**Step 2: Run focused verification before changelog edit**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run test -- src/lib/jobs/presenter.test.ts src/lib/jobs/pipeline.test.ts src/lib/i18n/locales.jobs-errors.test.ts
```

Expected: PASS

**Step 3: Write minimal implementation**

Add a short unreleased changelog note in `CHANGELOG.md` describing:

- clearer Jobs tab progress/capacity labels
- explicit queue and throttling visibility
- improved global progress banner summaries

**Step 4: Run full verification**

Run:

```bash
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run check
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run build
npm --prefix /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission/apps/ui run test -- src/lib/jobs/presenter.test.ts src/lib/jobs/pipeline.test.ts src/lib/i18n/locales.jobs-errors.test.ts src/lib/app/live-updates.test.ts src/lib/stores/job_progress.test.ts
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission diff --check
```

Expected:

- `svelte-check` passes with `0 errors`
- build succeeds
- targeted Vitest suites pass
- `git diff --check` is clean

**Step 5: Commit**

```bash
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission add CHANGELOG.md apps/ui/src/lib/pages/Jobs.svelte apps/ui/src/lib/components/GlobalProgress.svelte apps/ui/src/lib/jobs/presenter.ts apps/ui/src/lib/jobs/presenter.test.ts apps/ui/src/lib/jobs/pipeline.ts apps/ui/src/lib/jobs/pipeline.test.ts apps/ui/src/lib/api/maintenance.ts apps/ui/src/lib/i18n/locales/en.json apps/ui/src/lib/i18n/locales.jobs-errors.test.ts
git -C /config/workspace/YA-WAMF/.worktrees/issue22-subprocess-admission commit -m "feat: polish notifications jobs ui"
```
