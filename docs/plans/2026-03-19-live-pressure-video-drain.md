# Live-Pressure Video Drain Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make background video classification yield to any live image activity while draining in-flight video work and reporting throttle causes accurately.

**Architecture:** The auto video classifier computes an effective concurrency cap from two independent signals: MQTT ingest pressure and live-image pressure. Live pressure comes from classifier admission metrics, blocks only new video starts, and is surfaced as a distinct status/UI cause.

**Tech Stack:** Python, FastAPI service layer, pytest, TypeScript, Svelte, Vitest

---

### Task 1: Add failing backend tests for live-pressure throttling

**Files:**
- Modify: `backend/tests/test_auto_video_classifier_pressure.py`

**Step 1: Write the failing test**

Add tests asserting:
- live queued work sets effective concurrency to `0`
- live running work sets effective concurrency to `0`
- MQTT-only throttling and live-pressure throttling report separate flags

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/tmp/yawamf-testshim:/config/workspace/YA-WAMF/backend python3 -m pytest /config/workspace/YA-WAMF/backend/tests/test_auto_video_classifier_pressure.py -q`
Expected: FAIL because live-pressure flags/behavior do not exist yet

**Step 3: Write minimal implementation**

Update the service throttle-state logic to use classifier admission metrics and explicit cause fields.

**Step 4: Run test to verify it passes**

Run the same pytest command.
Expected: PASS

### Task 2: Add failing frontend tests for live-pressure messaging

**Files:**
- Modify: `apps/ui/src/lib/jobs/presenter.test.ts`

**Step 1: Write the failing test**

Add a test asserting a reclassification row blocked by live pressure shows live-priority text rather than MQTT-pressure text.

**Step 2: Run test to verify it fails**

Run: `npm --prefix /config/workspace/YA-WAMF/apps/ui run test -- --run apps/ui/src/lib/jobs/presenter.test.ts`
Expected: FAIL because presenter only knows MQTT throttling

**Step 3: Write minimal implementation**

Update queue-status types and presenter logic to surface dedicated live-pressure messaging.

**Step 4: Run test to verify it passes**

Run the same frontend test command.
Expected: PASS

### Task 3: Implement backend live-pressure draining semantics

**Files:**
- Modify: `backend/app/services/auto_video_classifier_service.py`

**Step 1: Use admission metrics**

Read classifier admission status and derive live pressure from `live.running > 0` or `live.queued > 0`.

**Step 2: Preserve drain semantics**

Keep existing active video tasks untouched; only prevent new task starts by forcing effective concurrency to `0`.

**Step 3: Separate throttle causes**

Return distinct booleans/telemetry for live pressure vs MQTT pressure and keep MQTT fields truthful.

**Step 4: Run backend tests**

Run the targeted pytest command and confirm the new tests pass.

### Task 4: Implement UI/status consistency changes

**Files:**
- Modify: `apps/ui/src/lib/api/maintenance.ts`
- Modify: `apps/ui/src/lib/stores/analysis_queue_status.svelte.ts`
- Modify: `apps/ui/src/lib/jobs/pipeline.ts`
- Modify: `apps/ui/src/lib/jobs/presenter.ts`

**Step 1: Extend status contract**

Add dedicated live-pressure fields to the analysis queue status interface and store mapping.

**Step 2: Update presenter semantics**

Use live-pressure-specific activity/blocker labels and keep MQTT messaging only for MQTT throttling.

**Step 3: Run frontend tests**

Run the targeted Vitest command and confirm the presenter test passes.

### Task 5: Correct the changelog

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Tighten wording**

Describe the implemented behavior accurately:
- new video starts pause under live pressure
- in-flight work drains
- worker client change hardens large stdout protocol messages

**Step 2: Review for consistency**

Ensure the changelog matches the code and avoids over-claiming full cancellation/preemption.
