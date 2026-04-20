# YOLOX-Tiny Accurate Crop Detector Design

## Summary

Add an optional `accurate` bird-crop detector tier powered by a permissively licensed YOLOX-Tiny ONNX model, while keeping the current SSD MobileNet crop detector as the default `fast` tier.

The goal is to improve bird localization for high-quality crop generation in difficult feeder scenes without destabilizing the current fail-soft crop pipeline.

## Goals

- Keep the current `fast` crop detector as the default for all existing installs.
- Add a managed `accurate` crop detector artifact using YOLOX-Tiny ONNX.
- Preserve fail-soft behavior:
  - `accurate` falls back to `fast` if unavailable or unhealthy
  - crop generation falls back to the original image if no healthy detector is available
- Keep CPU-first inference as the primary supported path.
- Keep the implementation compatible with future OpenVINO/CUDA runtime selection work.

## Non-Goals

- Do not replace the default fast detector.
- Do not require GPU support for the accurate detector.
- Do not bundle Ultralytics YOLO models.
- Do not redesign the HQ snapshot pipeline beyond detector selection and adapter support.
- Do not make feeder-specific fine-tuning a prerequisite for the first rollout.

## Candidate Choice

Chosen first candidate: `YOLOX-Tiny`

Why:

- Apache-2.0 licensed in the official YOLOX project.
- Explicit ONNX/OpenVINO deployment path exists upstream.
- Already named in the roadmap as the first realistic accurate-tier candidate.
- Small enough to remain practical on general CPU while still being materially stronger than the current SSD-MobileNet-style fast detector.

Deferred candidates:

- `YOLOX-S`: possible follow-up benchmark candidate if Tiny is still too weak.
- `PicoDet` / `PP-YOLOE`: viable permissive-license alternatives, but worse fit for the current roadmap and likely higher adapter/export churn.
- `RF-DETR`: too heavy for the first CPU-first pass.

## Architecture

### 1. Model Registry

Extend the crop-detector model metadata in `backend/app/services/model_manager.py` to represent two managed crop-detector artifacts:

- `bird_crop_detector`
  - tier: `fast`
  - existing SSD MobileNet detector
- `bird_crop_detector_accurate_yolox_tiny`
  - tier: `accurate`
  - YOLOX-Tiny ONNX detector

Each detector should expose:

- installation status
- health status
- runtime
- supported inference providers
- tier label
- notes/description

The registry should remain the source of truth. The crop service should not hard-code file paths for the accurate model.

### 2. Runtime Selection

Add a new owner-only setting in backend config and settings API:

- `bird_crop_detector_tier`
  - allowed values: `fast`, `accurate`
  - default: `fast`

Selection order:

1. use selected tier if installed and healthy
2. if selected tier is `accurate` but unavailable, fall back to `fast`
3. if no detector is healthy, return the original/full frame

This preserves behavior for current installs and keeps the accurate tier optional.

### 3. Detector Adapter Split

The current `BirdCropService` mixes model loading, preprocessing, and output parsing under an SSD-style assumption.

Refactor it into a narrow adapter-based structure:

- common orchestration in `BirdCropService`
- parser/adapter for `fast` SSD detector
- parser/adapter for `accurate` YOLOX detector

The adapter contract should cover:

- model loading
- input preparation
- inference
- normalized candidate extraction
- confidence/class filtering

This avoids ambiguous output parsing and makes future detector additions manageable.

### 4. YOLOX-Specific Parsing

Add a YOLOX adapter that:

- loads the managed ONNX model
- prepares a letterboxed input tensor
- parses YOLOX outputs into normalized bounding boxes
- filters to bird-class detections only
- returns candidate boxes in the same internal structure used by the existing crop selector

Fail-soft rule:

- unknown or unexpected output shapes must return no candidates, not guessed boxes

### 5. Crop Selection

Keep the existing crop result contract, but let the accurate tier participate in the same crop scoring/expansion flow.

Scoring should continue to prioritize:

- confidence
- reasonable crop size
- minimal edge clipping
- bounded expansion margin

The first pass should not introduce major new heuristics beyond what is needed to support the second detector family.

### 6. UI / Settings

Expose the tier selection in the owner detection settings near the existing bird crop options.

Recommended labels:

- `Fast`: lightweight default, lower CPU/RAM, may miss difficult crops
- `Accurate`: better localization, higher CPU/RAM, optional install

The model manager / status surfaces should make it clear whether the accurate detector is installed and healthy.

## Data and Diagnostics

Diagnostics should include:

- selected tier
- actual detector used after fallback
- model id
- detector health state
- fallback reason when accurate was requested but not used

This keeps runtime behavior understandable for support/debugging.

## Testing Strategy

### Unit

- tier selection defaults to `fast`
- `accurate` falls back to `fast` when not installed
- missing all detectors returns original image
- YOLOX parser rejects unknown output shapes fail-soft
- settings validation only allows `fast|accurate`

### Integration

- settings API exposes the new detector tier setting
- model manager reports both crop detector tiers
- high-quality crop path uses the selected healthy detector
- diagnostics include selected tier and fallback reason

### Fixture Evaluation

Add a small labeled crop fixture set comparing:

- current fast detector
- YOLOX-Tiny accurate detector

Track:

- miss rate
- clipped-bird rate
- average crop coverage
- runtime

The accurate tier should show a measurable quality gain before it is documented as better.

## Risks

- The biggest risk is parser drift from the exported YOLOX ONNX shape. Mitigation: explicit shape checks and isolated adapter tests.
- CPU latency may be higher than expected. Mitigation: keep it optional and default-off.
- A generic COCO-trained detector may still underperform on feeder-specific occlusion/background cases. Mitigation: benchmark first and keep fine-tuning as a later phase.

## Rollout

Phase 1:

- land registry, adapter split, runtime selection, UI, tests
- keep accurate tier optional and experimental

Phase 2:

- add fixture benchmark evidence
- refine docs wording based on actual benchmark results

Phase 3:

- consider YOLOX-S or feeder-specific fine-tuning if YOLOX-Tiny is still not strong enough
