# OpenVINO GPU Artifact Forensics Design

## Goal

Make YA-WAMF's OpenVINO GPU failure diagnostics trustworthy enough to isolate whether the current Intel GPU breakage is caused by the model artifact, the exporter path, or the runtime/image stack.

## Current Findings

- The live ConvNeXt artifact at `/data/models/convnext_large_inat21/model.onnx` is already the patched variant with sequence ops removed.
- That patched artifact is byte-for-byte identical to the output of [patch_convnext_openvino_model.py](/config/workspace/YA-WAMF/.worktrees/openvino-gpu-reliability/backend/scripts/patch_convnext_openvino_model.py).
- On the live backend container, the patched ConvNeXt artifact produces:
  - finite logits on OpenVINO CPU
  - all-`NaN` logits on OpenVINO GPU
- The same behavior persists after converting the model to OpenVINO IR, both default FP16-compressed IR and explicit FP32 IR.
- EVA-02 behaves differently on the same GPU path: CPU is finite, GPU fails with `CL_OUT_OF_RESOURCES`.
- The current `/api/classifier/probe` startup self-test does not fully match raw in-container OpenVINO behavior yet. The API currently surfaces an empty output tensor while the raw direct probe returns a full `NaN` tensor.

## Objectives

1. Expose exact artifact/runtime evidence through the API and logs.
2. Preserve the ability to keep testing GPU without silently trusting broken artifacts.
3. Compare the current artifact/export path against the historical known-good ConvNeXt path from git history.
4. Keep the current branch as the primary debugging surface; use history only as a controlled contrast path.

## Approach

### 1. Diagnostic Fidelity

Extend classifier runtime diagnostics so `/api/classifier/status`, `/api/classifier/probe`, and structured logs report:

- artifact fingerprint:
  - model path
  - model format (`onnx` or `ir`)
  - SHA-256 for model file and weight sidecar where applicable
  - ONNX producer/version
  - opset
  - input and output tensor declarations
- requested runtime config:
  - provider/backend
  - requested OpenVINO GPU properties
  - startup self-test settings
- actual runtime config:
  - compiled OpenVINO properties
  - selected execution devices
- inference evidence:
  - exact input summary
  - exact output summary
  - top-k values when finite
  - explicit invalid-output classification (`empty`, `all_nan`, `mixed_non_finite`, `runtime_error`)

The critical rule is that API diagnostics must be derived from the same raw output object used for runtime validation, so the probe endpoint cannot report a different failure shape from direct OpenVINO execution.

### 2. Compatibility State

Introduce a lightweight compatibility record for the currently selected bird artifact:

- per-device last probe result
- artifact fingerprint associated with that probe
- trust state:
  - `unknown`
  - `trusted`
  - `untrusted`

For now this is warning-only. The runtime should continue attempting GPU where configured, but the status API and logs must clearly show when GPU is running against an `untrusted` artifact.

### 3. Historical Artifact Comparison

Use git history to identify the earlier known-good ConvNeXt export/remediation path, then reproduce or recover that artifact in the worktree. Run the exact same probe matrix inside the live-style backend container:

- current patched ONNX
- current IR variants
- reconstructed historical artifact if obtainable

If the historical artifact succeeds on GPU, the remediation path becomes artifact/exporter replacement. If it fails too, the break is more likely in the runtime/image stack.

## Why This Approach

This keeps the current observability work intact and builds on it. A rollback now would reduce the evidence surface and make it harder to distinguish artifact regressions from runtime regressions. Warning-only compatibility state also avoids prematurely blocking experiments while still making the risk explicit.

## Testing Strategy

- Add failing backend unit tests for:
  - artifact metadata/fingerprint extraction
  - probe output fidelity for invalid GPU outputs
  - status payload compatibility state exposure
- Re-run the existing classifier status/probe tests.
- Continue validating against the live backend container with direct API probes and direct in-container OpenVINO probes.

## Expected Outcome

After this change, YA-WAMF should expose enough exact evidence to answer:

- what artifact is actually loaded
- whether it matches a historical known-good artifact
- what OpenVINO was asked to do
- what OpenVINO actually did
- whether the GPU failure is a `NaN` execution fault, empty output, compile issue, or GPU resource issue

That gives us a defensible basis for either replacing the artifact/export path or reverting runtime/image changes.
