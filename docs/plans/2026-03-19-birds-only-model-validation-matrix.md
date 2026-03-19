# Birds-Only Model Validation Matrix

Use this document to track the exact evidence for each in-place slot replacement before release assets are published.

## Validation Rules

- Required on this host:
  - ONNX Runtime CPU
  - OpenVINO CPU
  - OpenVINO Intel GPU
- Not available on this host:
  - NVIDIA CUDA
- CUDA must be recorded as `not validated in this environment` unless a later pass is run on real NVIDIA hardware.

## Candidate Matrix

| Slot ID | Candidate Architecture | Source Checkpoint | ONNX Runtime CPU | CUDA Status | OpenVINO CPU | OpenVINO Intel GPU | RAM / Startup Notes | Verdict | Release Asset URLs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `small_birds` (`eu`) | `MobileNetV4 Large` | `birder-project/mobilenet_v4_l_eu-common` | pass (`1x3x384x384 -> 1x707`, finite) | not validated in this environment | pass (`1x707`, finite) | pass in `yawamf-backend` container (`CPU`,`GPU` available; `1x707`, finite) | export succeeds without external data | uploaded candidate; clears current CPU + OpenVINO gates | `small_birds_eu_mobilenet_v4_l_candidate.onnx`, `small_birds_eu_mobilenet_v4_l_candidate_labels.txt` |
| `medium_birds` (`eu`) | `ConvNeXt V2 Tiny 256px` | `birder-project/convnext_v2_tiny_eu-common256px` | pass (`1x3x256x256 -> 1x707`, finite) | not validated in this environment | pass (`1x707`, finite) | pass in `yawamf-backend` container (`CPU`,`GPU` available; `1x707`, finite) | export succeeds without external data | uploaded candidate; clears current CPU + OpenVINO gates | `medium_birds_eu_convnext_v2_tiny_256_candidate.onnx`, `medium_birds_eu_convnext_v2_tiny_256_candidate_labels.txt` |
| `medium_birds` (`na`) | `DINOv2 ViT-B/14 linear probe` | `jiujiuche/binocular` (`artifacts/dinov2_vitb14_nabirds.pth`) | pass (`1x3x224x224 -> 1x555`, finite) | not validated in this environment | pass (`1x555`, finite) | compile succeeds in `yawamf-backend`, but inference returns all-`NaN` logits on GPU even with `INFERENCE_PRECISION_HINT=f32` | export succeeds via repo-owned `export_binocular_model.py`; requires ONNX external data sidecar; runtime now needs grouped-label collapse to surface `404` species instead of raw `555` visual categories | uploaded candidate; GPU blocked, now restricted to `cpu` + `intel_cpu` in registry metadata | `medium_birds_na_binocular_candidate.onnx`, `medium_birds_na_binocular_candidate.onnx.data`, `medium_birds_na_binocular_candidate_labels.txt` |
| `small_birds` (`na`) | `EfficientNet-B0 NABirds` | `n2b8/birdwatcher` (`ai/model/efficientnet_b0_nabirds.onnx`) | pass (`1x3x224x224 -> 1x555`, finite) | not validated in this environment | pass (`1x555`, finite) | default GPU path returns all-`NaN`; forcing `INFERENCE_PRECISION_HINT=f32` produces finite but catastrophically divergent logits vs CPU (synthetic-image max abs diff `~1.8e21`) | direct RGB ONNX artifact; requires grouped-label collapse to surface `404` species instead of raw `555` visual categories | uploaded candidate; GPU blocked, now restricted to `cpu` + `intel_cpu` in registry metadata | `n2b8_efficientnet_b0_nabirds.onnx`, `n2b8_class_labels.txt` |
| `convnext_large_inat21` | `ConvNeXt V2 Base` | deferred | not started | not validated in this environment | not started | not started | deferred until small/medium land | deferred | pending |
| `eva02_large_inat21` | `EVA-02 Large` birds-only successor | deferred | not started | not validated in this environment | not started | not started | deferred until large lands | deferred | pending |

## Notes

- The host Python environment currently exposes only `['CPU']` to OpenVINO, but the real `yawamf-backend` container exposes `['CPU', 'GPU']`. The decisive validation gate is therefore the in-container result, not the host-only probe.
- Europe small and medium candidates are now exported and uploaded as release candidates, but registry metadata still points at placeholder URLs and should not be updated until the lineup decision is complete.
- North America medium has a viable exported candidate, but it is a DINOv2 linear probe rather than the earlier convolution-first target.
- North America small now has a viable RGB ONNX candidate via `n2b8/birdwatcher`, but it still needs release packaging and the same grouped-label collapse path used by the medium NABirds model.
- The current North America NABirds candidates emit `555` visual categories. YA-WAMF now needs grouped-label collapse at inference time so those categories resolve to `404` species labels cleanly.
- Both North America candidates currently fail the OpenVINO GPU correctness gate in the running backend container even though model compilation succeeds.
- `small_birds.na` is especially deceptive: with explicit GPU `f32` it can return finite logits, but they diverge wildly from ORT/OpenVINO CPU and therefore are still not trustworthy.
- YA-WAMF now constrains both North America variants to `cpu` and `intel_cpu` so `auto` and `intel_gpu` requests cannot activate OpenVINO GPU for those artifacts.
