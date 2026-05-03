# Issue 33 Live Classification Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore live detection ingestion when Frigate MQTT is healthy but live snapshot classification repeatedly times out or overloads.

**Architecture:** Treat the April 23 diagnostics as a live image-classifier resilience failure, not an MQTT, video-classifier, or DB-pool failure. Add tests and diagnostics around the live classification admission/lease path, then make live inference degrade to a safer backend/provider or subprocess mode when repeated lease expiries show the current in-process OpenVINO GPU path is not returning in time.

**Tech Stack:** Python async services, pytest, OpenVINO/ONNX classifier runtime, YA-WAMF diagnostics bundle, Frigate MQTT event pipeline.

---

## Evidence From Latest Issue #33 Bundle

- Issue #33 was reopened on 2026-04-23.
- Latest attachment inspected: `tmp/issue33-latest/yawamf-job-diagnostics-2026-04-23-12-15-14.json`.
- App/build in bundle: `2.9.13-dev+7a07ab7`; health payload backend version: `2.9.13-dev+76b9243`.
- MQTT is connected and normal: Frigate messages are still arriving, no stall reconnects, no stall warning.
- Video classifier is idle and circuit is closed.
- DB pool is healthy.
- Pipeline is degraded because live event classification is failing:
  - `started_events: 903`
  - `completed_events: 534`
  - `dropped_events: 369`
  - `classify_snapshot_timeout: 230`
  - `classify_snapshot_overloaded: 138`
- Live classifier health:
  - `runtime: openvino`
  - `active_provider: intel_gpu`
  - `image_execution_mode: in_process`
  - `live_image_max_concurrent: 2`
  - `live_image_admission_timeout_seconds: 0.25`
  - `live_image_abandoned: 230`
  - `recovery_active: true`
  - `recovery_reason: stale_work_reclaim`

Working hypothesis: in-process live image inference can stall long enough on OpenVINO Intel GPU that both live worker slots are reclaimed by the coordinator lease. While those slots are stuck or being reclaimed, new live events hit the short admission budget and are dropped. Since the in-process thread cannot be killed, capacity is reclaimed logically but the underlying inference can still consume runtime resources. The existing diagnostics show abandonment counts, but not enough per-provider/per-work evidence to make the runtime fallback automatic or obvious.

## Review Findings

1. `backend/app/services/event_processor.py` wraps `_classify_snapshot()` in `_run_stage(..., timeout_seconds=EVENT_STAGE_TIMEOUT_CLASSIFY_SECONDS)`. The production bundle shows a 30s stage timeout. The live admission coordinator also defaults to a 30s live lease. These two deadlines can fire at roughly the same time, which makes it hard to distinguish outer-stage timeout from classifier lease expiry.

2. `backend/app/services/classifier_service.py` uses `ThreadPoolExecutor` for `image_execution_mode == "in_process"`. If OpenVINO GPU inference stalls in that thread, the coordinator can reclaim logical capacity, but it cannot stop the underlying Python/native worker thread.

3. `backend/app/services/classification_admission.py` correctly records abandoned work and frees coordinator capacity, but it only has generic `abandoned`/`late_completion_ignored` counters. It does not preserve enough context for the diagnostics bundle to answer which provider/model/work item repeatedly expired.

4. `backend/app/services/event_processor.py` uses a very short live admission timeout derived from `CLASSIFIER_LIVE_IMAGE_ADMISSION_TIMEOUT_SECONDS` and capped by live event freshness. That protects freshness, but under repeated abandoned work it turns a slow classifier into broad live event loss.

5. Existing tests cover lease reclaim and admission timeout mechanics, but not an issue-33-shaped sequence: repeated live lease expiries under in-process OpenVINO GPU followed by automatic runtime degradation or better diagnostics.

## Fix Strategy

Prefer a conservative two-layer fix:

1. Make the failure mode observable in diagnostics and tests.
2. Add automatic runtime/provider degradation for repeated live lease expiry on in-process OpenVINO GPU.

The first implementation should not rewrite the whole classifier architecture. It should add a targeted guardrail: if live in-process GPU inference repeatedly exceeds the lease, temporarily disable the unstable live GPU path and use a safer provider/path for live snapshots. Background/video classification should keep their existing behavior unless the same failure evidence appears there.

## Task 1: Add Focused Admission Diagnostics

**Files:**
- Modify: `backend/app/services/classification_admission.py`
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_classifier_service.py`

**Step 1: Write failing test**

Add a test that forces a live inference lease expiry and asserts classifier status includes recent admission outcomes with enough context to diagnose the failure.

Expected fields:
- `priority`
- `kind`
- `outcome`
- `work_id`
- `timestamp`
- `lease_timeout_seconds` for `abandoned`
- optional `provider`, `backend`, `model_id` when supplied by classifier service

**Step 2: Run test to verify failure**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -q -k "live_reclaims_stale_capacity or live_admission"
```

Expected: new diagnostic assertions fail because abandoned outcomes do not include enough context.

**Step 3: Implement minimal diagnostics**

Extend `_WorkItem` in `classification_admission.py` with a `context: dict[str, Any]` field.

Add optional `context` parameter to `ClassificationAdmissionCoordinator.submit()` and `_run_coordinated_inference()`.

Include `context` fields in `_record_recent_outcome_locked()`, especially for `abandoned` and `failed` outcomes.

Pass classifier context from `classifier_service.py`:

```python
context={
    "backend": self._inference_backend,
    "provider": self._active_inference_provider,
    "model_id": model_id or self._resolve_active_model_id(),
    "execution_mode": self._image_execution_mode,
}
```

**Step 4: Run focused tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -q -k "live_reclaims_stale_capacity or live_admission"
```

Expected: PASS.

## Task 2: Add Live Lease Expiry Runtime Guard

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_classifier_service.py`

**Step 1: Write failing test**

Add a test for repeated live lease expiry while:
- `image_execution_mode == "in_process"`
- `_inference_backend == "openvino"`
- `_active_inference_provider == "intel_gpu"`

Expected behavior after threshold:
- live health reports a specific recovery reason such as `live_gpu_lease_expiry_fallback`
- subsequent live classification uses a safer provider/path or refuses GPU until cooldown
- diagnostics expose threshold count and fallback cooldown

**Step 2: Run test to verify failure**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -q -k "lease_expiry"
```

Expected: FAIL because repeated live lease expiry only increments abandoned counts.

**Step 3: Implement guard**

Add live lease expiry tracking in `ClassifierService`:

- rolling window counter for live `ClassificationLeaseExpiredError`
- threshold default: 3 expiries in 10 minutes
- cooldown default: 10 minutes

When threshold trips for `openvino + intel_gpu + in_process`, temporarily route live image classification away from Intel GPU.

Preferred minimal fallback order:

1. If `intel_cpu` is available, use OpenVINO CPU for live image requests during cooldown.
2. Else if ONNX CPU is available, use CPU runtime for live image requests during cooldown.
3. Else keep current behavior but expose a clear degraded status.

Do not change background/video provider selection in this task.

**Step 4: Preserve normal success path**

Add/keep a test showing one isolated lease expiry does not immediately degrade GPU.

**Step 5: Run focused tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -q -k "lease_expiry or live_reclaims_stale_capacity"
```

Expected: PASS.

## Task 3: Decouple Stage Timeout From Live Lease Timeout

**Files:**
- Modify: `backend/app/services/event_processor.py`
- Test: `backend/tests/test_event_processor.py`

**Step 1: Write failing test**

Add a test that simulates `ClassificationLeaseExpiredError` from `_classify_snapshot()` and asserts the event pipeline records it as a live classifier lease expiry with context, not only a generic `stage_timeout`.

**Step 2: Run test to verify failure**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_event_processor.py -q -k "lease_expired or classify_snapshot"
```

Expected: FAIL because current event diagnostics collapse it into `classify_snapshot_timeout`.

**Step 3: Implement event-pipeline reason separation**

Keep the user-facing drop reason compatible (`classify_snapshot_timeout`) if needed, but add a distinct diagnostic reason code:

- `classify_snapshot_lease_expired`
- include `timeout_seconds`
- include provider/backend/model context when present on the exception or classifier status

This lets future bundles distinguish:

- snapshot fetch timeout
- admission overload
- inference lease expiry
- outer stage timeout

**Step 4: Run focused tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_event_processor.py -q -k "lease_expired or classify_snapshot"
```

Expected: PASS.

## Task 4: Tune Live Admission Under Recovery

**Files:**
- Modify: `backend/app/services/event_processor.py`
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_event_processor.py`
- Test: `backend/tests/test_classifier_service.py`

**Step 1: Write failing test**

Simulate classifier health with recent live abandoned work and a healthy MQTT pipeline. Assert `_live_classification_queue_timeout_seconds()` gives live work enough admission budget to use reclaimed capacity, without exceeding event freshness.

**Step 2: Run test to verify failure**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_event_processor.py -q -k "live_classification_queue_timeout"
```

Expected: FAIL if the timeout remains too small for recovery scenarios.

**Step 3: Implement conservative recovery timeout**

When live classifier health shows `recovery_active == true` and MQTT pressure is normal, allow queue timeout up to `LIVE_EVENT_QUEUE_TIMEOUT_CAP_SECONDS` instead of falling back to the raw 0.25s default.

Do not allow stale events to wait past `LIVE_EVENT_STALE_SECONDS`.

**Step 4: Run tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_event_processor.py backend/tests/test_classifier_service.py -q -k "live_classification_queue_timeout or live_admission or lease_expiry"
```

Expected: PASS.

## Task 5: Harness/Bundle Regression Check

**Files:**
- Modify only if needed: `scripts/run_issue33_harness.py`
- Test: existing issue-33 harness docs and focused backend tests

**Step 1: Check harness coverage**

Inspect whether `scripts/run_issue33_harness.py` can assert:

- live image `abandoned` delta stays at 0
- `classify_snapshot_timeout` delta stays at 0
- `classify_snapshot_overloaded` delta stays at 0
- runtime fallback event is recorded if forced

**Step 2: Add summary fields only if missing**

If the harness cannot observe these values, add them to the summary. Do not change traffic generation yet.

**Step 3: Run targeted tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py backend/tests/test_event_processor.py -q
```

Expected: PASS.

If a local monolith is already running and suitable, run a short issue-33 harness. Otherwise leave harness execution for CI/live validation because repo guidance says not to build main images locally.

## Task 6: Changelog And Retest Note

**Files:**
- Modify: `CHANGELOG.md`
- Optional issue comment draft: `/tmp/issue33-retest.md`

**Step 1: Update changelog**

Add an Unreleased fixed entry:

```markdown
- **Classification (#33):** Live snapshot classification now detects repeated live classifier lease expiry on the in-process OpenVINO Intel GPU path, records provider/model context in diagnostics, and temporarily routes live snapshots through a safer fallback during cooldown so healthy Frigate MQTT traffic does not collapse into `classify_snapshot_timeout` / `classify_snapshot_overloaded` drops.
```

**Step 2: Verify focused tests**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py backend/tests/test_event_processor.py -q
```

Expected: PASS.

**Step 3: Prepare issue comment after code lands**

Use `agents/GITHUB_API_WORKFLOW.md`. Draft in `/tmp/issue33-retest.md`, then post with `gh issue comment --body-file` only after the fix is pushed to `dev` and CI has built the dev image.

Recommended ask:

```markdown
We pushed a new #33 live-classification hardening fix to dev.

This one targets the latest April 23 bundle specifically: MQTT was healthy, but live snapshot classification was dropping events via `classify_snapshot_timeout` and `classify_snapshot_overloaded` after repeated live classifier lease expiry on the OpenVINO Intel GPU path.

Please retest with `ghcr.io/jellman86/yawamf-monalithic:dev`. If it still reproduces, attach one fresh diagnostics bundle and note whether the Errors page still shows Pipeline critical while MQTT remains normal.
```

## Out Of Scope

- Do not reopen the old video circuit breaker work unless a fresh bundle shows `video_classifier.circuit_open == true`.
- Do not patch MQTT stall recovery based on this April 23 bundle; MQTT is healthy in the evidence.
- Do not make split-image behavior the primary validation path; current agent guidance prefers monolithic `dev`.
- Do not locally build the main YA-WAMF images.
