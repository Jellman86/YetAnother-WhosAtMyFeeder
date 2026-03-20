# Bird Crop Generator Design

## Goal

Improve classification quality for models that need a tighter bird crop by adding a dedicated crop-generator stage that is enabled per model via `model_config.json`.

## Problem

YA-WAMF currently classifies whatever image it is given. That works reasonably well for Frigate `crop=True` snapshots, but some bird models, especially the North America models, appear to expect a tighter crop around the bird than YA-WAMF can currently guarantee.

The new manifest work already standardized resize, normalization, and provider constraints. Cropping now needs the same treatment:

- explicit per-model configuration
- one shared runtime path
- safe fallback to the original image if crop generation fails

The design must also avoid double-cropping. Most YA-WAMF classification entrypoints already use Frigate `crop=True` snapshots, so a crop generator should skip itself when the input is already cropped.

## Decision

Add a dedicated bird-localization stage in the classifier pipeline, but make it opt-in per model through `model_config.json`.

The crop generator will:

- run only when the active model config enables it
- skip itself when the caller marks the input as already cropped
- produce one best crop box and expand it using configurable margins
- fall back to the original image on any failure or low-confidence result

This keeps crop-sensitive models explicit without changing behavior for the rest of the catalog.

## Architecture

### Classification Input Context

Image classification entrypoints need lightweight source metadata in addition to the `PIL.Image`.

The minimum useful field is:

- `is_cropped: bool`

Additional useful fields:

- `source: str`
- `event_id: str | None`
- `camera_name: str | None`

This context lets the classifier make a deterministic decision about whether crop generation should be attempted.

### Crop Generator Service

Add a dedicated backend service, for example `backend/app/services/bird_crop_service.py`.

Responsibilities:

- lazily load the crop-generator model
- preprocess the source image for the crop model
- run inference and choose the best bird bounding box
- expand and clamp the box to image bounds
- return the cropped `PIL.Image` plus diagnostics

The crop service is an enhancement, not a dependency. Failure must never block downstream classification.

### Model Manifest Contract

The first implementation extends `model_config.json` with a minimal `crop_generator` block:

- `enabled`
- `input_context.is_cropped`

This is enough to activate crop generation per model and skip it when the caller already knows the image is cropped. Richer per-model fields like crop-model selection or thresholds can be added later once the baseline behavior is proven.

Example:

```json
{
  "model_id": "small_birds.na",
  "runtime": "onnx",
  "input_size": 224,
  "preprocessing": {
    "color_space": "RGB",
    "resize_mode": "direct_resize",
    "interpolation": "bilinear",
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225]
  },
  "crop_generator": {
    "enabled": true,
    "input_context": {
      "is_cropped": true
    }
  }
}
```

## Runtime Flow

1. Caller fetches image and passes classification context.
2. `ClassifierService` resolves the active model spec and installed manifest.
3. If `crop_generator.enabled` is false, classification proceeds normally.
4. If `crop_generator.enabled` is true and `is_cropped` is true, classification proceeds normally.
5. Otherwise, `ClassifierService` asks the crop service for a candidate crop.
6. If the crop service returns a valid crop, classification uses that crop.
7. If the crop service fails, returns no box, or returns an invalid box, classification uses the original image.
8. Existing model-specific resize/normalize from `model_config.json` runs after crop selection.

## Scope

First release:

- enable crop generation only for the North America birds-only models
- leave EU birds-only models unchanged
- leave wildlife and TFLite models unchanged

This keeps risk contained and matches the models that currently benefit most from tighter bird framing.

## Error Handling

The crop-generator stage must fail soft.

Rules:

- if the crop model is missing or unloadable, disable crop generation for that runtime window and use the original image
- if crop inference returns no bird box, use the original image
- if the chosen box is too small, out of bounds, or degenerate, use the original image
- if the image is already cropped and config says skip, do not attempt crop generation
- if runtime pressure is high, crop generation must run inside the existing classification worker path rather than creating a new uncontrolled executor

## Diagnostics

Record internal diagnostics per classification:

- `crop_attempted`
- `crop_applied`
- `crop_reason`
- optional crop box coordinates
- optional crop confidence
- crop model id

These should be available for logs and tests. They do not need to become a user-facing feature in the first pass.

## Call-Site Changes

Current YA-WAMF behavior matters here:

- reclassification uses Frigate `crop=True`
- backfill uses Frigate `crop=True`
- live event processing uses Frigate `crop=True`
- video fallback uses Frigate `crop=True`

Those paths should pass `is_cropped=true`.

Paths that classify full-frame or uploaded images should pass `is_cropped=false`.

## Reclassification and Steering

Crop generation should happen before result scoring and before personalized reranking. That means:

- classification feedback and reclassification steering continue to operate on the final classifier output
- the new crop stage only changes the input image chosen for inference
- no schema changes are needed for the personalization or feedback tables in the first pass

## Testing Strategy

Add regression coverage for:

- manifest parsing of `crop_generator`
- skip behavior when `is_cropped=true`
- fallback behavior when crop generation fails
- crop application for models with `crop_generator.enabled=true`
- no crop application for models without it
- live/background/reclassify paths preserving `is_cropped=true` for Frigate crops
- rerank/reclassification paths still working with the new input context

## Rollout

1. Add classification input context and manifest schema support.
2. Add the crop-generator service with safe fallback behavior.
3. Wire `ClassifierService` to apply crop generation before model preprocessing.
4. Mark the NA models as crop-enabled in their manifests.
5. Retest classifier quality and verify existing cropped Frigate paths skip the extra crop stage.
