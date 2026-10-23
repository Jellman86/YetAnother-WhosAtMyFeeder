# Crop detector validation and loaded device selection

## Problem and behaviour

A crop detector without current host evidence uses CPU even when the species
classifier uses an accelerator. That is intentional. The missing setup path was
an evaluation request scoped only to a crop detector: `model_ids` previously
accepted classifiers only. A second problem was that already loaded crop
sessions watched the chosen model identity but not its provider recommendation.
Updating evidence in the API process did not invalidate a worker's cached CPU
session.

Compatibility requests can now target an installed, ready crop detector using
`compat_only=true`, `sweep_devices=true` and `model_ids`. Explicit scopes filter
both classifier and crop groups. Missing artifacts fail instead of checking
something else. Crop-only compatibility does not activate or reload an
identification model. Accuracy evaluation still requires a classifier. Crop
results appear in the compatibility summary and device matrix.

On their next use, crop sessions compare their loaded model and requested
provider with the current recommendation. A changed recommendation reloads that
tier, including returning to CPU when evidence becomes stale. The remembered
value is the requested provider, rather than the active provider: a runtime
accelerator failure may leave CPU recovery active without retrying the same
failed accelerator on every frame.

## Hardware evidence and limits

One Intel host passed isolated native CPU, Intel CPU, GPU and NPU RF-DETR checks using the
exact installed registry artifact, eight committed bird images and three
deterministic negatives. Both accelerators passed the existing CPU box/presence/
confidence agreement rules and finite-output checks. Requested GPU execution
reported `GPU.0`; NPU reported `NPU`. Median forward times under the same bounded
test service were 3,204 ms ONNX Runtime CPU, 314.3 ms OpenVINO CPU, 70.7 ms GPU
and 89.4 ms NPU.

These measurements cover a model forward pass, not the full tiled crop path,
video throughput, sustained stability or independent bird-counting accuracy.
Initial missing-library test setup failures occurred before accelerator
inference. Native test evidence is not copied into application eligibility: the
running image must produce its own host/runtime/artifact-bound record.

## Second-order effects and boundaries

- Device checks consume CPU, accelerator memory and shared bandwidth. The
  existing evaluation panel is still fetched before the native sweep; narrowing
  the model list does not eliminate those downloads.
- GPU crops can avoid competing with an NPU species classifier, but the existing
  fastest-passing-provider policy decides. No provider is forced or promoted
  globally. CPU fallback and validation/quarantine rules are unchanged.
- Reading the current recommendation adds bounded validation-file reads to a
  crop-session lookup. The device is reloaded only when the recommendation or
  chosen model changes, rather than for every frame.
- An in-flight caller retains its model reference while a later lookup adopts
  another session. No worker is restarted and no real job is cancelled. Separate
  worker processes may transition on different subsequent requests.
- A failed accelerator with an unchanged recommendation retains CPU recovery.
  This change does not introduce automatic periodic accelerator retries or
  release native crash evidence.
- Validation evidence remains owner-controlled and tied to the existing image,
  artifact and runtime checks. Settings, defaults, history, authentication and
  database schemas are unchanged. RF-DETR remains opt-in; YOLOX-Tiny remains the
  default.

## Verification and rollback

Tests reproduce rejected crop-only selection and a loaded CPU session ignoring a
new recommendation. They also cover summaries, missing artifacts, unchanged
fallback, recommendation withdrawal and the absence of classifier activation in
a crop-only run. Full repository gates and CI results belong in the delivering
pull request.

Reverting the change restores classifier-only targeting and the former cache
behaviour. It requires no migration or history repair. The original affected-host
GPU-dropout report and independent two-bird counting qualification remain open.
