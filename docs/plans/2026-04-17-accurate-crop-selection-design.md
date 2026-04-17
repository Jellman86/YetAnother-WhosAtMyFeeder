# Accurate Crop Selection Design

## Goal

Improve selected bird crops for the `accurate` crop-detector tier by biasing selection toward bird recall, while keeping `fast` detector behavior unchanged.

## Problem

The new crop-detector evaluation harness shows that corrected YOLOX-Tiny localization is materially better than the legacy fast detector at the raw-candidate level, but YA-WAMF still drops many usable accurate detections during crop selection. The main blockers are the global `confidence_threshold` and `min_crop_size`, which were tuned for the legacy fast detector and are too strict for the accurate tier's candidate distribution.

## Constraints

- Do not change detector inference or model parsing.
- Do not regress the current `fast` tier behavior.
- Keep classifier and high-quality snapshot services aligned with the crop policy they depend on.
- Prefer small, reversible code changes over a large ranking redesign.

## Options Considered

### 1. Tier-aware relaxed selection

Add per-tier effective crop-policy helpers and use softer defaults for `accurate` only.

Pros:
- Smallest, safest change
- Directly targets the measured bottleneck
- Preserves `fast` behavior

Cons:
- Does not address all possible ranking issues

### 2. Global relaxed thresholds

Lower crop thresholds for all tiers.

Pros:
- Minimal implementation

Cons:
- Risks noisier fast-detector crops everywhere
- Unnecessarily changes stable behavior

### 3. Ranking redesign only

Keep thresholds mostly unchanged and re-rank accurate candidates more aggressively.

Pros:
- More targeted if ranking is the only issue

Cons:
- Current evidence shows threshold and minimum-size rejection are already blocking valid detections

## Chosen Design

Use option 1.

Implement tier-aware effective crop-policy helpers in `BirdCropService` so `accurate` can use recall-first selection defaults without mutating the public constructor defaults or changing `fast`.

For `accurate`:
- Use a lower effective confidence floor
- Use a smaller effective minimum crop size
- Keep existing expansion behavior

For `fast`:
- Keep existing threshold and size rules exactly as they are today

Update selection and downstream helper consumers to use the effective per-tier policy rather than reading raw constructor values directly.

## Testing

- Add regression tests for:
  - accurate candidate accepted below the legacy global threshold
  - accurate candidate accepted below the legacy global minimum crop size
  - fast tier remains unchanged under the same candidate shapes
- Re-run focused crop-service tests
- Re-run the crop-detector harness in the live container and compare selected metrics before/after
