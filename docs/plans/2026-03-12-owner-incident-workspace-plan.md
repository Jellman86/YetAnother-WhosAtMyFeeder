# Owner Incident Workspace Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the owner-only Errors tab with an incident-focused diagnostics workspace that aggregates backend/frontend failures, preserves actionable evidence, and generates issue-ready bundles.

**Architecture:** Keep the current bounded diagnostics systems, but add a richer backend diagnostics snapshot API, extend the frontend diagnostics store into an incident/evidence store, and refactor the Errors page into an owner-only incident workspace. Correlation stays conservative and traceable back to raw evidence so the UI summarizes without inventing state.

**Tech Stack:** FastAPI, Python diagnostics services, Svelte 5, TypeScript stores, Vitest, pytest

---

### Task 1: Expand the backend diagnostics contract

**Files:**
- Modify: `backend/app/services/error_diagnostics.py`
- Modify: `backend/app/routers/diagnostics.py`
- Test: `backend/tests/test_error_diagnostics_service.py`
- Test: `backend/tests/test_error_diagnostics_api.py`

**Step 1: Write the failing service test**

Add a test in `backend/tests/test_error_diagnostics_service.py` that records a diagnostics event with richer fields and asserts the snapshot preserves bounded metadata needed by the incident workspace:

```python
def test_snapshot_preserves_extended_event_fields():
    history = ErrorDiagnosticsHistory(max_events=5)
    history.record(
        source="worker",
        component="classifier_supervisor",
        reason_code="startup_timeout",
        message="Background worker timed out during startup",
        severity="error",
        stage="startup",
        event_id="evt-1",
        context={"worker_pool": "background"},
        correlation_key="background:startup_timeout",
        job_id="job-123",
        worker_pool="background",
        runtime_recovery={"failed_provider": "GPU"},
        snapshot_ref="health-1",
    )

    snapshot = history.snapshot(limit=10)
    event = snapshot["events"][0]
    assert event["correlation_key"] == "background:startup_timeout"
    assert event["job_id"] == "job-123"
    assert event["worker_pool"] == "background"
    assert event["snapshot_ref"] == "health-1"
```

**Step 2: Run the service test to verify it fails**

Run: `python -m pytest backend/tests/test_error_diagnostics_service.py -q`

Expected: FAIL because the new fields are not yet accepted or returned.

**Step 3: Implement the richer diagnostics event schema**

Extend `ErrorDiagnosticsHistory.record()` and `snapshot()` in `backend/app/services/error_diagnostics.py` to normalize and preserve:

- `correlation_key`
- `job_id`
- `worker_pool`
- `runtime_recovery`
- `snapshot_ref`

Keep the history bounded and backward-compatible for existing producers.

**Step 4: Write the failing API test**

Add a test in `backend/tests/test_error_diagnostics_api.py` for a new owner-only workspace payload route, for example `/api/diagnostics/workspace`, and assert it returns bounded diagnostics plus current health metadata:

```python
def test_workspace_payload_includes_error_history_and_health(client, owner_headers):
    response = client.get("/api/diagnostics/workspace", headers=owner_headers)
    assert response.status_code == 200
    payload = response.json()
    assert "backend_diagnostics" in payload
    assert "health" in payload
    assert "workspace_schema_version" in payload
```

**Step 5: Run the API test to verify it fails**

Run: `python -m pytest backend/tests/test_error_diagnostics_api.py -q`

Expected: FAIL with missing route or missing keys.

**Step 6: Implement the workspace diagnostics payload**

Update `backend/app/routers/diagnostics.py` to expose one bounded owner-only payload that includes:

- recent backend diagnostics events
- current `/health` payload
- bounded startup warnings / worker pool summaries
- a schema version for exported bundles

Do not add expensive new probing inside the route.

**Step 7: Run both backend tests**

Run: `python -m pytest backend/tests/test_error_diagnostics_service.py backend/tests/test_error_diagnostics_api.py -q`

Expected: PASS

**Step 8: Commit**

```bash
git add backend/app/services/error_diagnostics.py backend/app/routers/diagnostics.py backend/tests/test_error_diagnostics_service.py backend/tests/test_error_diagnostics_api.py
git commit -m "feat: expand diagnostics workspace payload"
```

### Task 2: Extend the frontend evidence store for incidents and richer bundles

**Files:**
- Modify: `apps/ui/src/lib/stores/job_diagnostics.svelte.ts`
- Test: `apps/ui/src/lib/stores/job_diagnostics.test.ts`

**Step 1: Write the failing store tests**

Add tests in `apps/ui/src/lib/stores/job_diagnostics.test.ts` that assert:

- worker stderr/runtime recovery fields survive health snapshot sanitization
- video worker pool state is preserved
- bundle export contains environment, health, incidents placeholder, timeline, and raw evidence sections

Example:

```ts
it('preserves worker recovery evidence in health snapshots', () => {
  const snapshot = sanitizeHealthSnapshotPayload({
    ml: {
      execution_mode: 'subprocess',
      worker_pools: {
        live: {
          workers: 2,
          restarts: 3,
          last_exit_reason: 'startup_timeout',
          circuit_open: false,
          last_runtime_recovery: { failed_provider: 'GPU', recovered_provider: 'intel_cpu' },
          last_stderr_excerpt: 'OpenVINO compile failed'
        },
        video: { workers: 1, restarts: 0, circuit_open: false }
      }
    }
  });

  expect(snapshot.ml.worker_pools.live.last_runtime_recovery.failed_provider).toBe('GPU');
  expect(snapshot.ml.worker_pools.video.workers).toBe(1);
});
```

**Step 2: Run the store tests to verify they fail**

Run: `npm --prefix apps/ui test -- src/lib/stores/job_diagnostics.test.ts`

Expected: FAIL because the current sanitizer drops the new evidence.

**Step 3: Implement richer evidence preservation**

Update `apps/ui/src/lib/stores/job_diagnostics.svelte.ts` to:

- preserve worker runtime recovery details and stderr excerpts in sanitized health snapshots
- preserve `video` worker pool state
- add bundle schema version and top-level sections matching the design
- keep bounded retention and avoid unbounded raw payload growth

**Step 4: Re-run the store tests**

Run: `npm --prefix apps/ui test -- src/lib/stores/job_diagnostics.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/stores/job_diagnostics.svelte.ts apps/ui/src/lib/stores/job_diagnostics.test.ts
git commit -m "feat: preserve incident evidence in diagnostics store"
```

### Task 3: Build incident correlation and diagnostics workspace APIs in the UI

**Files:**
- Create: `apps/ui/src/lib/api/diagnostics.ts`
- Create: `apps/ui/src/lib/stores/incident_workspace.svelte.ts`
- Test: `apps/ui/src/lib/stores/incident_workspace.test.ts`
- Modify: `apps/ui/src/lib/app/live-updates.ts`
- Test: `apps/ui/src/lib/app/live-updates.test.ts`

**Step 1: Write the failing incident-store tests**

Create `apps/ui/src/lib/stores/incident_workspace.test.ts` with tests for conservative correlation:

- related backend diagnostics + job failures become one incident
- resolved incidents leave `Current Issues` and remain in recent history
- unknown progress totals stay unknown
- summaries retain references back to raw evidence IDs

Example:

```ts
it('correlates backfill worker startup failures into one open incident', () => {
  const store = createIncidentWorkspaceStore();
  store.ingestBackendDiagnostics([
    {
      id: 'diag-1',
      component: 'classifier_supervisor',
      reason_code: 'background_image_worker_unavailable',
      severity: 'error',
      timestamp: '2026-03-12T10:00:00Z',
      job_id: 'job-1'
    }
  ]);
  store.ingestJobState({ id: 'job-1', kind: 'backfill_detection', status: 'failed' });

  const incident = store.currentIssues[0];
  expect(incident.affected_area).toBe('backfill');
  expect(incident.evidence_refs).toContain('diag-1');
});
```

**Step 2: Run the failing tests**

Run: `npm --prefix apps/ui test -- src/lib/stores/incident_workspace.test.ts src/lib/app/live-updates.test.ts`

Expected: FAIL because the API/store do not exist yet.

**Step 3: Implement the diagnostics API client and incident store**

Create `apps/ui/src/lib/api/diagnostics.ts` to fetch the new owner workspace payload.

Create `apps/ui/src/lib/stores/incident_workspace.svelte.ts` to:

- ingest backend diagnostics workspace payload
- ingest local frontend evidence from `jobDiagnosticsStore`
- correlate conservative incidents
- expose `currentIssues`, `recentIncidents`, `evidenceBundles`, and issue-report helpers

Update `apps/ui/src/lib/app/live-updates.ts` so owner polling/reconciliation also refreshes diagnostics workspace state without inventing progress.

**Step 4: Re-run the UI tests**

Run: `npm --prefix apps/ui test -- src/lib/stores/incident_workspace.test.ts src/lib/app/live-updates.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/api/diagnostics.ts apps/ui/src/lib/stores/incident_workspace.svelte.ts apps/ui/src/lib/stores/incident_workspace.test.ts apps/ui/src/lib/app/live-updates.ts apps/ui/src/lib/app/live-updates.test.ts
git commit -m "feat: add owner incident correlation store"
```

### Task 4: Refactor the owner Errors page into the incident workspace

**Files:**
- Modify: `apps/ui/src/lib/pages/Errors.svelte`
- Modify: `apps/ui/src/lib/pages/Notifications.svelte`
- Test: `apps/ui/src/lib/i18n/locales.jobs-errors.test.ts`

**Step 1: Write the failing UI/i18n tests**

Extend `apps/ui/src/lib/i18n/locales.jobs-errors.test.ts` to cover the new owner-facing strings:

- `Current Issues`
- `Recent Incidents`
- `Evidence Bundles`
- `Report Issue`
- issue summary / copy helpers

Also add a focused component-oriented assertion if an Errors page test file already exists during implementation; otherwise keep the locale coverage plus store tests as the first failing protection.

**Step 2: Run the i18n test to verify it fails**

Run: `npm --prefix apps/ui test -- src/lib/i18n/locales.jobs-errors.test.ts`

Expected: FAIL because the strings are missing.

**Step 3: Implement the page refactor**

Update `apps/ui/src/lib/pages/Errors.svelte` to render:

- current issue cards
- incident detail panel
- saved evidence bundles
- report-issue helpers

Update `apps/ui/src/lib/pages/Notifications.svelte` only as needed to keep the owner-only tab shell and badge behavior aligned with the new incident counts.

Add i18n strings required by the refactor.

**Step 4: Re-run the UI tests**

Run: `npm --prefix apps/ui test -- src/lib/i18n/locales.jobs-errors.test.ts src/lib/stores/incident_workspace.test.ts src/lib/stores/job_diagnostics.test.ts`

Expected: PASS

**Step 5: Commit**

```bash
git add apps/ui/src/lib/pages/Errors.svelte apps/ui/src/lib/pages/Notifications.svelte apps/ui/src/lib/i18n/locales.jobs-errors.test.ts
git commit -m "feat: replace errors tab with owner incident workspace"
```

### Task 5: Add issue-ready bundle/report generation and verify the full flow

**Files:**
- Modify: `apps/ui/src/lib/stores/incident_workspace.svelte.ts`
- Modify: `apps/ui/src/lib/stores/job_diagnostics.svelte.ts`
- Modify: `apps/ui/src/lib/pages/Errors.svelte`
- Test: `apps/ui/src/lib/stores/incident_workspace.test.ts`
- Test: `apps/ui/src/lib/stores/job_diagnostics.test.ts`
- Modify: `CHANGELOG.md`

**Step 1: Write the failing reporting tests**

Add tests asserting:

- generated issue body includes title, summary, environment, incident summary, and bundle reference
- bundle capture does not clear live incidents
- bundle schema version is present
- raw evidence is still included even when a human summary exists

Example:

```ts
it('builds an issue-ready summary without dropping raw evidence', () => {
  const store = createIncidentWorkspaceStore();
  store.captureBundle({ label: 'backfill failure', notes: 'repro after DB reset' });
  const report = store.buildIssueDraft();

  expect(report.title).toMatch(/backfill/i);
  expect(report.body).toContain('Environment');
  expect(report.body).toContain('Incident Summary');
  expect(report.bundleSchemaVersion).toBeTruthy();
});
```

**Step 2: Run the failing tests**

Run: `npm --prefix apps/ui test -- src/lib/stores/incident_workspace.test.ts src/lib/stores/job_diagnostics.test.ts`

Expected: FAIL because issue-draft generation and final bundle schema are incomplete.

**Step 3: Implement the report helpers**

Update the stores/page so the owner can:

- capture a labeled evidence bundle with optional notes
- copy a generated issue title/body
- open a prefilled GitHub issue URL
- download the bundle without mutating current incident state

Update `CHANGELOG.md` with the new owner incident workspace feature.

**Step 4: Run the targeted UI verification**

Run: `npm --prefix apps/ui test -- src/lib/stores/incident_workspace.test.ts src/lib/stores/job_diagnostics.test.ts src/lib/app/live-updates.test.ts src/lib/i18n/locales.jobs-errors.test.ts`

Expected: PASS

**Step 5: Run the final mixed verification**

Run: `python -m pytest backend/tests/test_error_diagnostics_service.py backend/tests/test_error_diagnostics_api.py -q`

Run: `npm --prefix apps/ui test -- src/lib/stores/job_diagnostics.test.ts src/lib/stores/incident_workspace.test.ts src/lib/app/live-updates.test.ts src/lib/i18n/locales.jobs-errors.test.ts`

Run: `npm --prefix apps/ui exec svelte-check --tsconfig ./tsconfig.json`

Expected:

- backend tests PASS
- UI tests PASS
- `svelte-check` reports `0 errors, 0 warnings`

**Step 6: Commit**

```bash
git add apps/ui/src/lib/stores/incident_workspace.svelte.ts apps/ui/src/lib/stores/job_diagnostics.svelte.ts apps/ui/src/lib/pages/Errors.svelte apps/ui/src/lib/stores/incident_workspace.test.ts apps/ui/src/lib/stores/job_diagnostics.test.ts CHANGELOG.md
git commit -m "feat: add issue-ready owner incident workspace"
```
