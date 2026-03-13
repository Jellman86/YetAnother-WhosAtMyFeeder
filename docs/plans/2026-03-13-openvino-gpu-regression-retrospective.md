# OpenVINO GPU Regression Retrospective

## Summary

This incident was not caused by a single missing code flag. The important finding is that YA-WAMF's Intel GPU reliability depended heavily on the OpenVINO runtime line, not just on application-side compile properties.

The final stable combination we verified on the live Intel iGPU host was:

- `openvino==2024.6.0`
- `CACHE_DIR=/tmp/openvino_cache`
- `PERFORMANCE_HINT=LATENCY`
- `INFERENCE_PRECISION_HINT=f32` for GPU
- the existing patched `convnext_large_inat21` ONNX artifact already present in `/data/models`

Under that combination, both backfill and unknown-video analysis produced finite GPU scores and completed successfully on the live container.

## What We Thought Was Broken

At the start of the investigation, the user-reported symptom was simple:

- latest batch runs were not using the GPU

Initial suspicion focused on application-level hardening gaps such as:

- missing FP32 precision hint
- missing compile cache
- missing single-stream GPU limit
- incomplete diagnostics about actual runtime state

Those were real concerns, but they were not the whole story.

## What Actually Happened

### 1. There were multiple distinct failure modes across runtime lines

We saw three separate OpenVINO-era behaviors:

1. `openvino 2026.0.0`
   - Intel GPU enumeration failed entirely
   - OpenVINO only exposed `["CPU"]`
   - GPU plugin/device discovery was broken on this host/container combination

2. `openvino 2025.4.1`
   - Intel GPU enumerated correctly
   - model compiled on GPU
   - inference on the live ConvNeXt artifact returned non-finite output (`NaN` logits / `NaN` probabilities)
   - workers or backfill then fell back, demoted, or silently dropped writes depending on branch behavior

3. `openvino 2024.6.0`
   - Intel GPU enumerated correctly
   - model compiled on GPU
   - inference returned finite scores on the same live ConvNeXt artifact
   - backfill and unknown analysis completed successfully on GPU

This means the root issue was not "GPU support missing" in general. It was "the later OpenVINO runtime line is unstable for this model/hardware path on this host."

### 2. The model artifact was not the primary late-stage culprit

We verified that the deployed bird model was:

- ONNX
- opset `18`
- producer `pytorch 2.9.1+cu128`
- initializer types:
  - `FLOAT: 350`
  - `INT64: 9`

That means the deployed model artifact is FP32, not FP16.

We also verified earlier that the live artifact already reflected the historical ConvNeXt compatibility patching step from the repo's issue-21 era. In other words:

- the old "patch/convert the ConvNeXt model for OpenVINO compatibility" step had already been applied to the deployed artifact
- the remaining failures were runtime/numerical-stability failures, not a fresh missing-sequence-op problem

### 3. Some of our instrumentation initially lied by omission

During the middle of the investigation, the system showed several misleading symptoms:

- top-level classifier status sometimes reported `tflite` or otherwise non-authoritative process state while subprocess workers had already recovered/fallen back
- raw container probes showed all-`NaN` GPU outputs while some API surfaces summarized that as `empty`
- backfill reported `already_exists` when the true cause was a non-finite classifier score

The worst hidden bug was in the older backfill path:

- `DetectionRepository.upsert_if_higher_score()` used `INSERT OR IGNORE`
- SQLite treats `NaN` in a `NOT NULL` float column as an ignored insert with `changes() == 0`
- backfill then logged `Event already exists and score not improved, skipped`
- this was false; the row did **not** exist
- the real cause was a non-finite score being silently discarded by SQLite

We fixed that branch so non-finite scores are surfaced explicitly as `non_finite_score`.

## Investigation Timeline

### Phase A: Modern branch forensics

We first investigated the newer supervised/subprocess branch and added diagnostics:

- worker-authoritative runtime status
- direct probe endpoints / runtime probe APIs
- artifact fingerprinting and compile-property reporting
- startup self-tests and bounded invalid-output diagnostics

Those changes were useful because they established the real behavior:

- GPU passthrough worked
- OpenVINO saw `GPU.0`
- the ConvNeXt artifact compiled
- `2025.4.1` still produced invalid GPU outputs for this model on this host

### Phase B: Historical rollback

We then rolled `dev` back toward the issue-21 / ConvNeXt-conversion era to test the user's memory that "it worked just after we converted the model."

That exposed another important fact:

- older code alone was not enough
- old branches could fail on current DB migration graphs
- old container/runtime combinations could fail to enumerate Intel GPU at all

So "restore the old code" was not by itself the answer.

### Phase C: Controlled runtime archaeology

We combined:

- issue-21-era application behavior
- newer Intel GPU runtime packages
- progressively narrowed runtime settings

Key outcomes:

- adding `f32` alone was not enough on `2025.4.1`
- adding `NUM_STREAMS=1` alone was not enough on `2025.4.1`
- switching the runtime line to `2024.6.0` changed the outcome decisively

### Phase D: Live confirmation

On the live container with `openvino==2024.6.0` we observed:

- `openvino_devices=["CPU","GPU"]`
- `active_provider="intel_gpu"`
- `inference_backend="openvino"`
- backfill produced finite scores and persisted detections successfully
- unknown video analysis produced finite top-k scores and completed successfully

Examples from live logs:

- Backfill:
  - `Low confidence detection, saving as Unknown ... score=0.21704019606113434`
  - `Backfilled detection ... species=Unknown Bird`
- Unknown analysis:
  - `Video classification complete (Top-K) ... top_score=0.156`
  - `Auto video classification completed ... score=0.1556200087070465`

The previous `score=nan` signatures disappeared under the verified `2024.6.0` runtime line.

## What Changed That Broke GPU

The best-supported explanation is:

- YA-WAMF drifted across OpenVINO/runtime lines over time
- `2026.x` was bad for GPU enumeration on this host
- `2025.4.1` enumerated GPU but was numerically unstable for this ConvNeXt/iGPU path
- earlier success likely happened because the system had landed on a more stable runtime combination, not because the app logic was radically better

This is why the issue felt confusing:

- several code-level hardening changes were correct and necessary
- but they did not eliminate the runtime-line regression

## Final Technical Findings

### Proven-good live combination

- App/runtime line: modern or restored code can work if the runtime line is correct
- OpenVINO: `2024.6.0`
- Model artifact: existing patched FP32 ConvNeXt ONNX
- GPU compile properties:
  - `CACHE_DIR=/tmp/openvino_cache`
  - `PERFORMANCE_HINT=LATENCY`
  - `INFERENCE_PRECISION_HINT=f32`

### Proven-bad combinations on this host

- `openvino 2026.0.0`
  - no usable GPU enumeration

- `openvino 2025.4.1`
  - GPU visible
  - GPU compile succeeds
  - live ConvNeXt inference produced non-finite outputs in our observed paths

### Important non-findings

- The deployed model is not an FP16 artifact.
- The live model had already undergone the historical ConvNeXt compatibility patching step.
- The final successful fix was not simply "add FP32" or "add single stream."

## Why the Modern Branch Should Use This Knowledge

Once `2024.6.0` was proven stable on the restored branch, the right next step was not to keep the old issue-21 code forever.

The better strategy is:

- keep the newer modern branch behavior and diagnostics
- replace only the unstable runtime assumption

That led to a new modern branch base (`4223251`) with a narrow fix:

- change the OpenVINO pin from `2025.4.1` to `2024.6.0`
- keep the newer supervisor, diagnostics, probe/status, cache, and self-test logic

That modern branch work was prepared in worktree:

- `/config/workspace/YA-WAMF/.worktrees/modern-openvino-2024`

and pushed as:

- `90cf0e4` `fix(gpu): pin modern openvino runtime to 2024.6`

## Operational Lessons

1. OpenVINO version drift is a high-risk change on Intel GPU hosts.
   - Do not treat `openvino>=...` as safe.

2. Device enumeration success is not enough.
   - GPU compile succeeding does not mean GPU inference is numerically trustworthy.

3. Backfill and batch flows need explicit non-finite handling.
   - otherwise SQLite and upsert semantics can hide the real failure mode

4. Worker-authoritative status matters.
   - top-level process status is not enough in supervised/subprocess mode

5. Runtime archaeology was necessary.
   - the regression was not recoverable from app-code reasoning alone

## Recommended Durable Repo State

For future maintainers:

- treat `openvino==2024.6.0` as the last known-good Intel iGPU runtime line for this host/model combination
- keep the newer diagnostics/probe/self-test/reporting from the modern branch
- only upgrade OpenVINO behind explicit live GPU validation on this ConvNeXt artifact

Before changing the OpenVINO pin again:

1. build a dev image
2. verify `/api/classifier/status`
3. run the live ConvNeXt probe on GPU and CPU
4. run backfill on known feeder events
5. run unknown-video analysis and confirm finite persisted scores

## References

- `docs/plans/2026-03-13-openvino-gpu-reliability-design.md`
- `docs/plans/2026-03-13-openvino-gpu-reliability-plan.md`
- closed GitHub issue `#21 OpenVino load fails`
- archived forensic branch:
  - `origin/archive/dev-openvino-forensics-2026-03-13`
- modern rebase target:
  - `4223251`
- modern runtime fix:
  - `90cf0e4`

