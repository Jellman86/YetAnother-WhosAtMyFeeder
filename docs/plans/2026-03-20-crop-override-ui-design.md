# Crop Override UI Design

## Goal

Allow YA-WAMF to ship per-model crop behavior defaults in `model_config.json`, while letting the user override crop behavior in the UI at both the logical model/family level and the specific variant level.

This should also support preferring a higher-quality uncropped source image for crop generation when a model opts into that behavior.

## Problem

The current crop-generator behavior is static:

- model manifests can enable or disable crop generation
- runtime reads the resolved `crop_generator` block from the active model spec
- there is no user-visible way to override crop behavior
- higher-quality crop source selection is not modeled as a per-model policy

That is too rigid for the current evidence. Crop generation appears to help some models or cases more than others, and detector quality is not strong enough to justify a universal policy.

## Requirements

### Functional

- Keep shipped crop defaults in each model manifest or registry-backed spec.
- Allow UI overrides per logical model or family:
  - examples: `small_birds`, `medium_birds`, `convnext_large_inat21`
- Allow UI overrides per specific resolved variant:
  - examples: `small_birds.eu`, `small_birds.na`
- Support tri-state crop enablement:
  - `default`
  - `on`
  - `off`
- Support tri-state crop source preference:
  - `default`
  - `standard`
  - `high_quality`
- Prefer higher-quality uncropped input for crop generation when configured and available.
- Skip crop generation entirely when the input is already cropped.
- Fail soft when the crop detector or higher-quality source is unavailable.

### Non-functional

- Preserve current manifest-driven runtime behavior when there are no overrides.
- Keep the classifier pipeline consuming one resolved `crop_generator` block.
- Avoid spreading override logic across multiple runtime layers.
- Keep the default UI simple and push variant controls into an advanced section.

## Recommended Approach

Use model-default plus layered overrides:

1. shipped model/variant default from `model_config.json` or registry-backed spec
2. logical model/family override from settings
3. specific variant override from settings

Precedence:

1. variant override
2. model/family override
3. shipped manifest default

This keeps shipped behavior self-describing while allowing targeted user control.

## Data Model

Add two settings maps under classification:

- `crop_model_overrides: dict[str, str]`
  - keys are logical model ids or specific variant ids
  - values are `default | on | off`
- `crop_source_overrides: dict[str, str]`
  - keys are logical model ids or specific variant ids
  - values are `default | standard | high_quality`

Examples:

```json
{
  "classification": {
    "crop_model_overrides": {
      "small_birds": "off",
      "small_birds.na": "on"
    },
    "crop_source_overrides": {
      "small_birds.na": "high_quality",
      "convnext_large_inat21": "standard"
    }
  }
}
```

Resolved runtime crop block:

- `enabled`
- `source_preference`
- existing crop fields such as threshold, expand ratio, min crop size, fallback behavior, input context hints

## Resolution Flow

`ModelManager` remains the place that resolves active specs.

Flow:

1. resolve active model or family variant as today
2. load shipped crop defaults from installed `model_config.json` or registry metadata
3. apply logical model/family override if present
4. apply specific variant override if present
5. return one resolved `crop_generator` block to `ClassifierService`

`ClassifierService` should not know whether the final crop policy came from the manifest or the user override.

## Crop Source Preference

Add `source_preference` to the resolved crop block:

- `standard`
  - use the currently supplied image
- `high_quality`
  - try to fetch a higher-quality uncropped source for the same event before crop generation
- `default`
  - not used at runtime; only a persisted override state before resolution

Runtime rules:

- if the input context says `is_cropped=true`, skip higher-quality fetch and skip crop generation
- if `high_quality` is requested and a higher-quality uncropped image exists, run crop generation on that image
- if higher-quality fetch fails, fall back to the current image
- if the crop detector fails, fall back to the image selected for classification

## UI Design

### Default Layer

Expose per-model controls in Detection Settings and/or the model manager UI:

- crop behavior:
  - `Use model default`
  - `Force on`
  - `Force off`
- crop source:
  - `Use model default`
  - `Use current image`
  - `Prefer high-quality snapshot`

For families like `small_birds` and `medium_birds`, the default controls apply at the family level.

### Advanced Layer

Expose a collapsible advanced section for variant-specific overrides:

- `small_birds.eu`
- `small_birds.na`
- `medium_birds.eu`
- `medium_birds.na`

Each gets the same tri-state controls.

UI should make inheritance visible:

- show when a variant is inheriting from the family
- show when a model is inheriting from the shipped default

## Higher-Quality Source Strategy

Higher-quality crop sourcing should be runtime-driven and model-config-aware.

Recommended first pass:

- only attempt higher-quality fetch when:
  - crop generation is enabled after resolution
  - input is not already cropped
  - input context includes an event id or equivalent lookup handle
- source from YA-WAMF/Frigate snapshot services, not from arbitrary re-fetch logic inside the detector

This keeps image-fetching concerns out of the detector itself.

## Error Handling

- Invalid override keys are ignored.
- Invalid override values are normalized back to `default`.
- If a user forces crop `on` for a model with no available detector, runtime logs and falls back to original image.
- If higher-quality fetch fails, runtime uses the current image.
- If the current image is already cropped, no second-stage crop attempt is made.

## Testing Strategy

### Settings and Resolution

- family override beats shipped manifest default
- variant override beats family override
- invalid override values normalize to `default`
- unknown override keys do not break resolution

### Classifier Runtime

- forced `off` disables crop even when manifest default is `enabled`
- forced `on` enables crop even when manifest default is `disabled`
- already-cropped input still bypasses crop generation
- unavailable crop detector still fails soft

### Higher-Quality Source

- high-quality source is used when available
- fetch failure falls back to current image
- already-cropped input skips high-quality fetch

### UI

- detection settings can save family overrides
- advanced variant overrides persist correctly
- inherited/default/overridden state is displayed correctly

## Recommendation

Implement:

- model/family crop override
- variant crop override
- source-preference override
- high-quality-source fetch only for crop-enabled, uncropped flows

Do not implement user-facing numeric tuning for crop detector thresholds in this pass. The data does not justify expanding the surface area yet.
