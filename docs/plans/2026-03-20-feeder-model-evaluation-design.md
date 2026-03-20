# Feeder Model Evaluation Harness Design

## Goal
Build a repeatable offline evaluation harness for real feeder snapshots so YA-WAMF can compare full-frame vs crop-assisted classification across candidate models using ground-truth labels instead of plausibility guesses.

## Context
Recent crop and regional-model work established the following:
- crop behavior is now model-config-driven and can be overridden per model family and per variant
- high-quality crop source preference now exists and fails soft
- crop gains were inconsistent on a tiny manual sample, especially for North America models
- the next product decision should be evidence-based: which models should keep crop enabled by default, and whether high-quality crop sourcing is worth using

The repo does not currently have a durable labeled-feeder evaluation harness. There are export scripts and runtime probes, but no tool that reads a manifest of ground-truth feeder images and compares multiple models and crop modes through the real classifier stack.

## Requirements
- Use a manifest CSV as the canonical dataset input.
- Reuse YA-WAMF’s real classifier pipeline, including crop source resolution and crop diagnostics.
- Evaluate one or more requested models on the same manifest.
- Support temporary evaluation-only overrides for crop behavior and source preference.
- Never persist those overrides or mutate the live app settings on disk.
- Produce both per-image detailed outputs and aggregate summary metrics.
- Continue past per-row failures and record them explicitly.

## Recommended Approach
Add an offline backend script under `backend/scripts/` that:
- reads a CSV manifest
- temporarily resolves a requested model and crop policy
- runs classification through `ClassifierService.classify(...)`
- records top-1/top-3 outcomes and crop/source diagnostics
- writes detailed CSV and summary JSON outputs

This is the best first step because it reuses the same runtime path the product uses, gives repeatable evidence, and avoids adding new API surface area.

## Manifest Format
Canonical input: CSV.

Required columns:
- `image_path`
- `truth_species`

Optional columns:
- `event_id`
- `is_cropped`
- `notes`

Rules:
- `image_path` must point to a readable local image file.
- `truth_species` is the canonical expected species string used for top-1/top-3 comparison.
- `is_cropped` defaults to `false` if omitted.
- `event_id` is used only when the runtime needs to look up higher-quality cached snapshots.

A future convenience importer could convert `dataset/<species>/*.jpg` into the same CSV shape, but the harness itself should standardize on CSV.

## Evaluation Modes
The harness should support evaluating a model under several explicit modes without changing global settings:
- manifest default
  - use model-config defaults as currently resolved
- crop forced on
  - temporarily override crop behavior to `on`
- crop forced off
  - temporarily override crop behavior to `off`
- source forced high_quality
  - temporarily override crop source to `high_quality`
- source forced standard
  - temporarily override crop source to `standard`

The implementation should allow combining a crop override and a source override for the run.

## Data Flow
1. Read the manifest CSV.
2. Validate rows before running inference.
3. Snapshot the current in-memory classifier/model settings needed for safe restoration.
4. For each requested model and evaluation mode:
   - temporarily point model resolution at that model
   - temporarily apply evaluation-only crop/source overrides in memory
5. For each manifest row:
   - load the image from `image_path`
   - build `ClassificationInputContext` using `is_cropped` and optional `event_id`
   - classify using the real classifier service
   - capture top-1 and top-3 predictions
   - capture crop/source diagnostics from the runtime
6. Restore original in-memory state even on failure.
7. Write results.

## Outputs
Detailed CSV rows should include at least:
- `model_id`
- `evaluation_mode`
- `image_path`
- `truth_species`
- `top1_species`
- `top1_score`
- `top3_species`
- `hit_top1`
- `hit_top3`
- `crop_attempted`
- `crop_applied`
- `crop_reason`
- `source_reason`
- `error`
- `notes`

Summary JSON should include per model/mode:
- total rows
- evaluated rows
- failed rows
- top-1 accuracy
- top-3 hit rate
- average top-1 confidence
- crop-attempt rate
- crop-applied rate
- source-reason counts
- crop-reason counts

## Runtime Isolation
The harness must not leave the live application mutated.

Safe approach:
- capture original `model_manager.active_model_id`
- capture original in-memory `settings.classification.crop_model_overrides`
- capture original in-memory `settings.classification.crop_source_overrides`
- restore them in `finally`
- do not call settings-save APIs
- do not write any app config files

This is acceptable for an offline owner-only script because it runs in a standalone process and should leave runtime memory as it found it.

## Error Handling
Per-row failures should not abort the whole run.

Rules:
- unreadable image path: record failed row, continue
- invalid/missing `truth_species`: reject manifest before evaluation starts
- model resolution/load failure: fail that model/mode block clearly
- crop detector failure: preserve classifier fail-soft behavior and record diagnostics
- high-quality source lookup failure: preserve classifier fail-soft behavior and record diagnostics
- output write failure: fail loudly after preserving any completed in-memory summary

## Testing Strategy
Add focused automated coverage for:
- manifest parsing and validation
- top-1/top-3 aggregation logic
- row-result building from classifier outputs plus crop diagnostics
- temporary override application and restoration
- per-row error recording without aborting the whole run

Where possible, use lightweight fake classifier/model manager behavior rather than requiring real ONNX artifacts.

## Non-Goals
This pass should not:
- add a public HTTP API for evaluation
- add UI for launching evaluations
- add automatic folder-to-manifest import
- add detector-threshold tuning controls
- promise direct Frigate HQ retrieval if cached snapshots are the only synchronous safe source today

## Success Criteria
The harness is successful when:
- a user can point it at a labeled feeder manifest and a set of models
- it writes reproducible detailed and summary outputs
- it reports real crop/source diagnostics from the actual runtime path
- it lets YA-WAMF choose sensible crop defaults per model based on evidence
