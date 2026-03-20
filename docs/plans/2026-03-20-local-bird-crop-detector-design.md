# Local Bird Crop Detector Design

## Goal

Wire the existing crop-generator stage to a real locally managed detector so crop-enabled classifier models can receive a tighter bird crop when the input image is not already cropped.

## Decision

Use one global local detector path for the backend, and keep crop application controlled per classifier model via `model_config.json`.

That splits responsibility cleanly:

- backend runtime decides whether a local detector is available
- classifier model config decides whether that model should attempt bird cropping

## Why This Shape

This is better than putting detector paths into every model manifest:

- one detector is loaded once instead of duplicating config
- fewer opportunities for inconsistent local paths
- simpler debugging when crop generation is unavailable
- still flexible enough because per-model manifests already control opt-in

## Runtime Contract

### Global Detector Configuration

Add one backend-level local detector path, sourced from environment/settings.

Recommended contract:

- `BIRD_CROP_MODEL_PATH`
- `BIRD_CROP_BOX_FORMAT` with default `xyxy` and optional `cxcywh`

Optional future settings can be added later, but the first implementation should stay minimal.

Current implementation target:

- local ONNX detector loaded with ONNX Runtime CPU
- no release-backed download flow
- no per-model detector paths

### Per-Model Policy

Keep using `crop_generator.enabled` in `model_config.json`.

- `true`: attempt crop generation when the detector exists and the input is not already cropped
- `false`: bypass crop generation entirely

Current intended policy:

- North America birds-only models: enabled
- Europe birds-only models: disabled
- wildlife-wide models: disabled
- bundled TFLite default model: disabled

## Detector Integration

### BirdCropService

`BirdCropService` should move from placeholder logic to a real ONNX detector integration.

Responsibilities:

- load the detector from the configured local path
- preprocess the image for detector inference
- run inference through ONNX Runtime
- extract bird bounding boxes from the detector output
- choose the best valid candidate
- return a crop image plus diagnostics

The service must remain fail-soft. If loading or inference fails, classification continues with the original image.

### Detector Scope

First implementation should support one detector format:

- local ONNX file

This keeps the scope controlled. OpenVINO execution for the detector can be added later if CPU-only ORT is too slow.

The supported output contract should stay intentionally narrow:

- single tensor with rows shaped like `x1, y1, x2, y2, score[, class]`
- or split outputs that can be interpreted as `boxes` and `scores`

Incompatible detector outputs should fail soft and yield no crop instead of trying to guess.

In particular:

- multi-class row layouts with extra class-probability columns should be treated as unsupported by default
- `cxcywh` coordinates should only be interpreted when explicitly configured

## Failure Policy

The detector is an enhancement, not a dependency.

Rules:

- if `BIRD_CROP_MODEL_PATH` is unset, crop generation returns `load_failed`
- if the file does not exist or is unreadable, crop generation returns `load_failed`
- if ONNX Runtime cannot create a session, crop generation returns `load_failed`
- if inference errors, crop generation returns `inference_failed`
- if detector output is malformed or yields no valid bird box, classification uses the original image
- if the caller marks the image as already cropped, crop generation is skipped before any detector work

## Detector Assumptions

To avoid over-designing the first pass, support one narrow detection output contract:

- detector input is standard image tensor input
- detector output is a set of candidate boxes with confidence scores
- only `bird` detections are relevant

Implementation should isolate output parsing behind helper methods so the output adapter can be changed later without rewriting classifier integration.

## Testing Strategy

Add tests for:

- loading from a configured local model path
- soft failure when the env/path is missing
- ORT session creation failure
- candidate extraction/parsing from detector outputs
- crop application through `ClassifierService` with a real service seam
- regression that already-cropped Frigate inputs still skip detector work

## Rollout

1. Add failing tests for detector-path loading and ONNX candidate parsing.
2. Implement minimal ONNX Runtime integration in `BirdCropService`.
3. Verify crop-enabled NA models still fail soft when the detector is absent.
4. Verify classifier behavior still skips the detector for `is_cropped=true`.
