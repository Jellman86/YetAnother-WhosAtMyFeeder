# Small Slot Swap Design

## Summary

Replace the current small-slot candidate backing `hieradet_small_inat21` with the validated `vit_reg4_m16_rms_avg_i-jepa-inat21-256px` artifact while keeping the existing registry slot and internal model ID stable.

## Goals

- Preserve the current backend and frontend small-slot wiring by keeping `hieradet_small_inat21` as the public model ID.
- Replace the artifact, display metadata, and release notes so the slot describes the actual validated model.
- Keep install, activation, and download progress behavior compatible with the existing manager flow.

## Non-Goals

- No frontend structural redesign.
- No additional model slots.
- No CUDA validation claims beyond the existing best-effort caveat.

## Chosen Approach

Use an in-place swap:

- Keep registry/model ID `hieradet_small_inat21`.
- Change its human-facing metadata to the new ViT small model.
- Update export tooling so this model can be reproduced from source with the current `birder` package and newer ONNX export path.
- Publish replacement release assets and point the existing registry slot at them.

This keeps the tiered UX and download flow stable while removing the known Intel GPU incompatibility from the small wildlife recommendation.

## Data and Artifact Model

The replacement export produces:

- `model.onnx`
- `model.onnx.data`
- `labels.txt`

That means the release asset set and manager download path must continue to support ONNX external data artifacts.

## Validation Requirements

The replacement small-slot artifact must be verified on:

- ONNX Runtime CPU
- OpenVINO CPU
- OpenVINO GPU on the Intel GPU host

NVIDIA/CUDA remains unverified in this environment and should continue to be described that way in release notes and model notes.

## Risks

- The current Birder export script assumes an older loader contract and a legacy ONNX exporter path.
- The replacement model requires the newer ONNX exporter path to handle `rms_norm`.
- Replacing release assets in place must not break manager downloads for the small slot.

## Implementation Notes

- Prefer changing only backend/export metadata and tests unless a frontend metadata assertion fails.
- Keep the stable model ID even though the backing architecture changes; rely on display metadata and notes for user-facing clarity.
