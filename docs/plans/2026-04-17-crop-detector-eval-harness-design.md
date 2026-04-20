# Crop Detector Evaluation Harness Design

**Date:** 2026-04-17

## Goal

Add a repeatable evaluation harness for bird crop detectors so YA-WAMF can compare `fast` and `accurate` tiers on both real feeder snapshots and cleaner reference bird images, using explicit ground-truth bird boxes instead of subjective spot checks.

## Why

Current crop-detector testing is ad hoc. That makes it impossible to separate:

- detector integration bugs
- bad threshold choices
- weak detector artifacts
- feeder-scene difficulty

The existing full-model accuracy harness already proved useful for classifier decisions. Crop detectors need the same treatment, but with localization metrics instead of classification accuracy.

## Scope

First version:

- evaluates crop-detector tiers `fast` and `accurate`
- supports two dataset buckets:
  - `feeder_real`
  - `reference_clean`
- uses a manifest with explicit bird boxes
- downloads and caches clean reference images automatically
- can harvest candidate feeder images from local Frigate clips/snapshots
- writes machine-readable metrics plus visual overlays

Out of scope for first version:

- browser-based annotation UI
- multi-reviewer annotation workflows
- model training or fine-tuning
- automatic box labeling from a third-party detector

## Dataset Design

### Layout

Use a dedicated fixture area parallel to the current model-accuracy fixtures:

- `backend/tests/fixtures/crop_detector_manifest.json`
- `backend/tests/fixtures/crop_detector_images/reference_clean/...`
- `backend/tests/fixtures/crop_detector_images/feeder_real/...`
- `backend/tests/fixtures/crop_detector_overlays/...`

### Manifest Shape

Each manifest entry contains:

- `id`
- `bucket`
- `source`
- `image_path`
- `width`
- `height`
- `boxes`
- optional metadata such as:
  - `scientific_name`
  - `common_name`
  - `inat_taxon_id`
  - `frigate_camera`
  - `notes`

`boxes` is a list of bird boxes in absolute `xyxy` pixel coordinates.

This mirrors the existing manifest-driven evaluation style already used by classifier fixtures, but adds localization-specific information instead of acceptable class labels.

## Data Acquisition

### Reference Images

For `reference_clean`, reuse the existing iNaturalist-style fixture download pattern:

- keep a small curated manifest of target species/taxa
- download a limited number of images per species
- cache those images under the crop-detector fixture directory

These images should favor clear, well-framed bird subjects to answer: “Is the detector basically competent on obvious bird images?”

### Feeder Images

For `feeder_real`, add a harvest script that:

- scans local Frigate media paths
- copies a bounded set of candidate images into fixture storage
- writes stub manifest entries if needed

The first version can rely on a small curated list or bounded auto-harvest plus manual box annotation by script. The important part is that the resulting dataset becomes stable and repeatable once written into the fixture cache.

## Annotation Flow

The first version should not require the user to annotate by hand.

Instead, provide a small helper flow:

- image discovery/harvest script
- manifest generation helper
- simple annotation helper script for adding box coordinates

This can be CLI-driven rather than UI-driven. A minimal helper that prints image info and accepts/updates `xyxy` coordinates is enough for the first pass.

The output must remain a normal manifest file in-repo so the evaluator stays deterministic.

## Evaluation Metrics

Per image:

- `best_confidence`
- `best_iou`
- whether any predicted box exists
- whether any predicted box clears IoU threshold(s)
- whether selected crop is “usable”

Per detector and per bucket:

- image count
- any-detection recall
- recall at IoU `0.3`
- recall at IoU `0.5`
- mean best IoU
- median best IoU
- mean best confidence
- selected-crop rate at active threshold

The lower IoU threshold matters because crop usefulness is more forgiving than strict detector benchmarking; a crop can still be practically useful before it is tightly localized.

## Outputs

The evaluator should emit:

- console summary
- JSON results
- optional CSV summary
- overlay images for failures and representative successes

Overlay images should draw:

- ground-truth boxes
- top predicted box
- detector name and confidence
- bucket label

This gives a human-auditable record when numeric metrics look suspicious.

## Implementation Shape

### Scripts

Add under `backend/scripts/`:

- `eval_crop_detector_accuracy.py`
- `download_crop_detector_fixtures.py`
- `harvest_feeder_crop_images.py`
- optional lightweight annotation helper if needed

These should follow the existing evaluator style in `backend/scripts/eval_model_accuracy.py`.

### Runtime Path

The crop evaluator should use the same `BirdCropService` detector loading and parsing logic as production, not a separate inference path. That avoids benchmarking a synthetic code path that can disagree with real runtime behavior.

### Testing

Add focused tests for:

- manifest loading
- IoU computation
- bucket aggregation
- overlay rendering
- crop-service-backed evaluation of fake detectors

## Success Criteria

The first version is successful when:

- it can evaluate both installed crop-detector tiers
- it can run on a mixed dataset without manual intervention from the user
- it produces per-bucket metrics and visual overlays
- it gives enough evidence to decide whether `accurate` is actually better than `fast`

## Recommendation

Build the harness now before trying more detector candidates. Right now the repo has enough evidence to suspect the current accurate detector artifact is poor, but not enough structured evidence to compare alternatives cleanly. The harness is the correct next investment.
