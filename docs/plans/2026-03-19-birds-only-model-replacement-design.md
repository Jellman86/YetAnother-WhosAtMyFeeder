# Birds-Only Regional Model Resolver Design

## Goal

Replace YA-WAMF's weak small and medium wildlife-wide ONNX tiers with regional birds-only model families that auto-select by configured location and allow a manual override, while leaving the current large and elite paths unchanged for now.

## Current Problem

YA-WAMF is a bird-feeder product, but its current small and medium ONNX tiers are broad wildlife models. Even if a generic birds-only replacement existed, one global bird model is still a compromise when the actual deployment is geographically constrained.

The better product is:

- regional birds-only models for small and medium
- automatic region selection from configured location
- explicit user override when auto-selection is wrong or undesirable

## Approved Scope

This first pass only regionalizes the small and medium tiers.

- Small family: regional birds-only variants
- Medium family: regional birds-only variants
- Large: keep current global `convnext_large_inat21`
- Elite: keep current global `eva02_large_inat21`

Initial supported regions:

- `eu`
- `na`

## Recommended Architecture

Use model families, not flat top-level model entries.

### Why this is the right shape

1. Clean UI
   - Users should not see a wall of nearly identical `small eu`, `small na`, `medium eu`, `medium na` cards.
2. Better defaults
   - YA-WAMF can choose a sensible regional model automatically when location is known.
3. User control
   - Manual override prevents silent wrong choices and helps debugging.
4. Extensibility
   - Additional regions can be added later without redesigning the settings model.

## Model Resolver Design

Introduce two logical families:

- `small_birds`
- `medium_birds`

Each family has variants, initially:

- `eu`
- `na`

Each variant stores:

- slot family id
- region code
- architecture name
- source checkpoint
- `download_url`
- optional `weights_url`
- `labels_url`
- runtime support notes
- validation notes

The backend resolves the active artifact with this priority:

1. manual override region
2. auto-detected region from configured location
3. family default fallback

## Settings Design

Add a new setting:

- `bird_model_region_override`

Allowed values:

- `auto`
- `eu`
- `na`

Behavior:

- `auto`: backend infers region from configured location
- explicit region: backend uses that region for small and medium birds-only families

## Location Resolver

Use the existing configured location information already present in YA-WAMF settings.

Resolution rules:

- if `country` or coordinates clearly match a supported region, pick that region
- if not enough information exists, fall back to family default
- manual override always wins

This first version should be intentionally simple and deterministic, not a geopolitical inference engine.

## User Experience

The UI should present:

- one small birds family
- one medium birds family
- current effective region
- whether the region came from `Auto` or manual override

The UI should not present every regional variant as a separate top-level downloadable card.

## Candidate Direction

The exact winning checkpoints must be chosen from models that actually exist and can survive validation on this host.

At this stage, the most realistic candidates are birds-only regional checkpoints that already exist, even if they are not the ideal architecture originally preferred.

That means checkpoint availability outranks architecture purity.

## Validation Rules

Required in this environment:

- ONNX Runtime CPU
- OpenVINO CPU
- OpenVINO Intel GPU

Not available here:

- NVIDIA CUDA

CUDA must remain explicitly unvalidated unless a later pass is run on real NVIDIA hardware.

## Artifact Delivery

Each regional family variant must be delivered as release-backed assets:

- `model.onnx`
- `model.onnx.data` when required
- `labels.txt`

Winning assets are uploaded to GitHub Releases and referenced by stable URLs in the resolver metadata.

## Execution Order

1. Add backend support for bird model families and regional variants.
2. Add settings support for `bird_model_region_override`.
3. Add location-to-region resolution.
4. Add UI for `Auto | Europe | North America`.
5. Select actual available regional checkpoints for small and medium.
6. Export, validate, and upload one winning artifact per family/region pair.
7. Switch the small and medium runtime selection to use the family resolver.
8. Leave large and elite unchanged.

## Why This Is Better Than A Single Global Replacement

- Regional bird classes are a better fit for feeder deployments.
- Smaller models can spend capacity on the actual species users see.
- Automatic selection gives good defaults.
- Manual override preserves trust and debuggability.

## Sources

- MobileNetV4 paper: https://arxiv.org/abs/2404.10518
- ConvNeXt V2 paper: https://arxiv.org/abs/2301.00808
- FastViT paper: https://arxiv.org/abs/2303.14189
- EfficientFormerV2 paper: https://arxiv.org/abs/2212.08059
- OpenVINO device/property docs: https://docs.openvino.ai/2024/notebooks/gpu-device-with-output.html
- iNaturalist 2021 dataset summary: https://www.tensorflow.org/datasets/catalog/i_naturalist2021
