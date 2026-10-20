# RF-DETR Nano CUDA candidate validation

Date: 20 October 2026. Baseline: `ca160ae74de041bd597b3ebfe5f9aaf3aab283ba`.
Related work: [#734](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/734).

## Problem and requirements

RF-DETR Nano already runs through the production crop service, including its
full-frame and overlapping-tile scan. Its registry excludes CUDA, so a normal
compatibility check skips that route even on a capable CUDA installation.

The change adds CUDA to the reviewed candidate list. The supported-provider
list retains CPU and Intel CPU/GPU/NPU; this is not blanket NVIDIA support.
The candidate list also includes all those existing routes, because the normal
sweep uses the candidate list in preference to the supported list.

Acceptance requires the ordinary image/host intersection to offer CUDA only
where packaged and available. Eligibility still needs a finite, CPU-agreeing
crop sweep on that installation. The existing persisted records must match the
artifact, image and provider runtime/driver before crop generation can select
CUDA. Missing, failed, disagreeing or stale results retain CPU. The existing
CPU retry after accelerated loading or inference failure remains in place.

RF-DETR remains opt-in. YOLOX-Tiny stays the default. No thresholds, counting
rules, settings, inference implementation, quarantine policy, schema or API
contract change. The older installed model sidecar cannot suppress the new
registry candidate: exact crop validation reads current registry metadata.
Generated release sidecars carry the same candidate policy for new downloads.

## Hardware evidence

The published CUDA image from the baseline passed its complete build, smoke,
persistent-state flavor-switch and tag-promotion workflow before the test.
The registry and running test image both identify that exact revision.

- CUDA amd64 manifest: `sha256:cb13b39f3a7970c8d4eebd1729d8211b58f2a2f7b276a707493a08f9559b7e05`.
- RF-DETR ONNX: `889453865bc1a776b93c6ec3292d2e06833f3907db99187e37cd01476fb47620`.
- Labels: `4896d9e76fff04240339eedf66b220f4fdf8196b2597726116adbedbbcd60fd8`.
- Model config: `2ece390066e1169163e76205839a4fb95106f3819acdf4ebc86a44179ba42d29`.
- Reference device: RTX 4070, 12 GB, driver 617.42, Ubuntu under WSL.
- Packaged runtime: ONNX Runtime GPU 1.26.0, NumPy 2.5.4, Pillow 13.0.0.

Two CPU and two CUDA disposable subprocesses completed with exit zero. Each
unmodified packaged crop-provider probe evaluated the eight committed images in
`backend/tests/fixtures/crop_detector_images` plus three deterministic synthetic
negatives. All outputs were finite; all 11 comparison rows agreed with CPU.
CUDA was the primary provider and the existing service disabled runtime-wide
automatic CPU retry during the strict probe.

A separate observer enabled ONNX Runtime profiling and limited CPU threads while
using the packaged crop loader, preprocessing, parser and duplicate merge. It
tested the same panel plus one derived 3840×2160 image. The derived image forced
one full-frame and four tile forwards. Each run evaluated 12 rows with 16 native
calls and 456,000 finite output elements. Candidate counts agreed, with eight
box matches, minimum IoU 0.999373 and maximum confidence difference 0.002345.
The limits were frozen before execution at IoU 0.95 and confidence delta 0.02.

Each profiled CUDA repeat recorded 11,472 CUDA kernel events, including Conv,
Gemm, MatMul, Softmax and GridSample, with no CPU-provider kernel events.
A provider appearing in an installed-runtime list was not counted as execution.

The unmodified probe measured warmed median forwards of 108.5/107.9 ms on CPU
and 8.3/8.2 ms on CUDA. The separate profiled session had different thread limits;
its latency is not mixed into those figures. Maximum observed child RSS was
589 MiB on CPU and 1,309 MiB on CUDA. One-second whole-host GPU samples rose from
939 MiB to a peak of 1,368 MiB; they include other clients and may miss short
peaks, so they are not exact task VRAM measurements.

The test container had a 6 GiB memory cap, four-CPU cap, no network, no application
entrypoint or ports, read-only fixture/model inputs and private writable scratch.
Each native child had a 240-second deadline. All children exited and the owned
container was removed. No production data or saved settings were mounted.

## Second-order effects and rollback

| Effect | Boundary |
| --- | --- |
| Crop inference can compete with species classification for GPU time and memory | CUDA remains opt-in and host-validated; the short reference run does not qualify concurrent or sustained workloads. |
| A compatibility run now performs an additional native compile/forward on CUDA hosts | Existing isolated-child deadlines, finite-output and CPU-comparison checks apply; CPU and Intel-only images do not add a CUDA probe. |
| A faster reference result could be mistaken for a guaranteed speedup | The recorded medians are short warmed forwards on one device, not visit throughput or startup latency. |
| Existing downloads retain older sidecars | Exact crop sweeps use the running registry; no forced download, model replacement or eligibility rewrite occurs on upgrade. |
| Old validation could silently authorize new hardware or weights | Existing image/artifact/provider signatures remain authoritative; regressions cover replacement artifacts and changed driver/runtime or image evidence. |
| Failure handling or crash evidence could be bypassed | This metadata change does not clear quarantine or alter native recovery; failed CUDA validation cannot authorize its activation. |
| Counting success could be inferred from hardware agreement | The 4K probe is derived; fresh independent two-bird, fixture and duplicate-part counting validation is still required for #734. |

Withdrawing CUDA from the candidate list stops new ordinary sweeps from offering
it. Existing persisted recommendations and loaded crop sessions can outlive that
metadata edit; reverting the candidate alone is not an immediate live rollback.
To return an affected installation to CPU, rerun compatibility with the withdrawn
route and let the existing crop-session reset apply the new recommendation.
Do not delete history, hand-edit validation files or discard crash evidence.

## Regression coverage and limits

The new tests use an installed-model fixture with an older sidecar and the real
registry, sweep, evaluation persistence and crop recommendation code. Only the
native inference boundary is substituted. They cover CUDA/full/Intel/CPU/Pi
image boundaries; passing, failed, nonfinite, disagreeing and negative-only CUDA
errors; missing and stale evidence; and generated candidate-only sidecars.
The original registry failed the CUDA cases before the metadata change.

The hardware panel is a consistency check, not independently labelled accuracy
or counting evidence. It does not certify other NVIDIA devices, native Windows,
cold driver caches, sustained load, live/backfill concurrency or the underlying
Intel GPU failure in #490. No application default or broader support claim follows
from this reference pass.

## Local verification

- Full bounded backend gate: 6,107 passed, 54 skipped, 80% branch coverage;
  process exited zero within the eight-minute limit. Hardware skips are not passes.
- Focused crop/validation/sidecar suite: 139 passed.
- Frontend: 1,667 passed; Svelte check reported zero errors and warnings.
- Repository-wide Ruff and format checks passed (900 Python files); documentation
  consistency passed with 224 routes; whitespace checks passed.
