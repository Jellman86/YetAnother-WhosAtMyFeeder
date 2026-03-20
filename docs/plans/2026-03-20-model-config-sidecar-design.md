# Model Config Sidecar Design

## Goal

Standardize YA-WAMF model preprocessing and runtime metadata by shipping a per-model `model_config.json` sidecar with every downloadable artifact and making runtime consume that manifest as the primary source of truth.

## Problem

Today the model registry in `backend/app/services/model_manager.py` mixes catalog metadata with runtime-critical preprocessing details. That works only when the registry is manually kept in sync with the upstream model card and export path. It is not currently in sync for several ONNX models. The downloader also only installs the model file, optional external weights, and labels, so there is no artifact-local manifest that can survive registry drift.

## Decision

Use a sidecar manifest named `model_config.json` for every model artifact and family variant.

The runtime will prefer the installed sidecar manifest over registry defaults. The registry remains the distribution catalog for:

- display metadata in the API/UI
- release URLs
- fallback compatibility for older installs without a sidecar

## Artifact Contract

Each installed model directory must contain:

- `model.onnx` or `model.tflite`
- optional `model.onnx.data`
- `labels.txt`
- `model_config.json`

For family models, each region directory will contain its own copy of those files.

## Manifest Schema

The sidecar must carry all runtime-critical metadata:

- `model_id`
- `runtime`
- `input_size`
- `color_space`
- `resize_mode`
- `interpolation`
- `crop_pct`
- `padding_color`
- `mean`
- `std`
- `label_grouping`
- `supported_inference_providers`
- optional `notes`

The important new distinction is `resize_mode`, which must support:

- `letterbox`
- `center_crop`
- `direct_resize`

## Runtime Behavior

`ModelManager.get_active_model_spec()` will load installed `model_config.json` when present and merge it over the registry entry. `ClassifierService` will then consume the resolved manifest fields rather than guessing from generic runtime defaults.

This gives each model an explicit preprocessing contract:

- Birder models can use crop-based transforms with their actual RGB stats
- timm models can use crop-based eval transforms with source `crop_pct`
- models like Binocular can use direct resize without letterboxing

## Downloader Behavior

The downloader must fetch `model_config_url` together with the model artifact, optional weights, and labels. Install validation must require `model_config.json` for new payloads.

Backward compatibility remains:

- if a downloaded model does not have a sidecar, runtime falls back to the registry entry
- older installs continue to work during transition

## Export Behavior

Export scripts will emit `model_config.json` next to `model.onnx` and `labels.txt`.

For timm exports, the exporter should capture available source metadata from `pretrained_cfg`, especially:

- `input_size`
- `mean`
- `std`
- `crop_pct`
- `interpolation`

For non-timm or custom artifacts, the sidecar may still be assembled explicitly, but once emitted it becomes the runtime contract.

## Files

Expected primary changes:

- `backend/app/models/ai_models.py`
- `backend/app/services/model_manager.py`
- `backend/app/services/classifier_service.py`
- `backend/scripts/export_birds_only_model.py`
- backend tests covering downloader, registry metadata, and classifier preprocessing

## Testing Strategy

Add regression tests for:

- manifest download/install validation
- active model resolution preferring installed `model_config.json`
- ONNX/OpenVINO preprocessing modes `letterbox`, `center_crop`, and `direct_resize`
- registry fallback behavior when sidecar is absent
- exporter emission of `model_config.json`

## Rollout

1. Add manifest support and compatibility fallback.
2. Start emitting and downloading sidecars for the corrected models first.
3. Repoint the known-wrong models to explicit manifests.
4. Retest accuracy/runtime after preprocessing is corrected.
