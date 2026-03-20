# Bird Crop Generator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a model-config-driven bird crop-generator stage that only runs for opted-in models and skips itself when the source image is already cropped.

**Architecture:** Extend the manifest/runtime contract with a `crop_generator` block, thread lightweight image-source context through YA-WAMF classification entrypoints, and add a shared bird-crop service that can fail soft back to the original image. Keep the crop stage inside the existing classifier execution path so it does not create a second unmanaged concurrency system.

**Tech Stack:** FastAPI, Pydantic, Pillow, ONNX/OpenVINO/TFLite classifier stack, pytest

---

### Task 1: Add Manifest and Input-Context Schema

**Files:**
- Modify: `backend/app/models/ai_models.py`
- Modify: `backend/app/services/model_manager.py`
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_model_registry_metadata.py`
- Test: `backend/tests/test_model_manager_download.py`
- Test: `backend/tests/test_classifier_service.py`

**Step 1: Write the failing tests**

Add tests that assert:
- installed or registry model specs preserve a `crop_generator` block
- classification entrypoints accept an input-context object with `is_cropped`
- missing or invalid `crop_generator` fields degrade safely to disabled behavior

**Step 2: Run tests to verify they fail**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_model_registry_metadata.py \
  backend/tests/test_model_manager_download.py \
  backend/tests/test_classifier_service.py -q
```

Expected: failures for missing `crop_generator` schema and missing classification input-context handling.

**Step 3: Write minimal implementation**

Implement:
- a manifest schema path for `crop_generator`
- a small classification input-context model or dict-normalization helper
- defensive merging/parsing in `ModelManager`

**Step 4: Run tests to verify they pass**

Run the same pytest command and confirm the new schema/context tests pass.

**Step 5: Commit**

```bash
git add backend/app/models/ai_models.py backend/app/services/model_manager.py backend/app/services/classifier_service.py backend/tests/test_model_registry_metadata.py backend/tests/test_model_manager_download.py backend/tests/test_classifier_service.py
git commit -m "feat(classifier): add crop generator manifest contract"
```

### Task 2: Add the Bird Crop Service

**Files:**
- Create: `backend/app/services/bird_crop_service.py`
- Test: `backend/tests/test_bird_crop_service.py`
- Modify: `backend/app/services/classifier_service.py`

**Step 1: Write the failing tests**

Add tests for:
- valid crop box selection and expansion
- clamping to image bounds
- rejecting tiny or degenerate boxes
- soft failure when crop model load/inference fails

**Step 2: Run test to verify it fails**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_bird_crop_service.py -q
```

Expected: FAIL because the new crop service does not exist yet.

**Step 3: Write minimal implementation**

Implement a crop service that:
- lazily initializes its model/runtime
- exposes a method returning `crop_image`, `box`, `confidence`, and `reason`
- never raises fatal errors back into the classifier path

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm the service tests pass.

**Step 5: Commit**

```bash
git add backend/app/services/bird_crop_service.py backend/tests/test_bird_crop_service.py backend/app/services/classifier_service.py
git commit -m "feat(classifier): add shared bird crop service"
```

### Task 3: Apply Crop Generation in ClassifierService

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_classifier_service.py`

**Step 1: Write the failing tests**

Add tests for:
- crop generation applied when model manifest enables it and `is_cropped=false`
- crop generation skipped when `is_cropped=true`
- crop generation skipped when manifest disables it
- fallback to original image when crop service returns no crop

**Step 2: Run test to verify it fails**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -q
```

Expected: FAIL because `ClassifierService` does not yet consult crop-generator config or input context.

**Step 3: Write minimal implementation**

Implement:
- an internal crop-resolution step ahead of model preprocessing
- safe logging/diagnostics for `crop_attempted`, `crop_applied`, and `crop_reason`
- preservation of existing classification behavior when the crop path is inactive

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm the new crop-application tests pass.

**Step 5: Commit**

```bash
git add backend/app/services/classifier_service.py backend/tests/test_classifier_service.py
git commit -m "feat(classifier): apply model-config bird crops"
```

### Task 4: Thread Image-Source Context Through Call Sites

**Files:**
- Modify: `backend/app/services/event_processor.py`
- Modify: `backend/app/services/backfill_service.py`
- Modify: `backend/app/services/auto_video_classifier_service.py`
- Modify: `backend/app/routers/events.py`
- Modify: `backend/app/routers/classifier.py`
- Test: `backend/tests/test_events_reclassify_api.py`
- Test: `backend/tests/test_backfill_service.py`
- Test: `backend/tests/test_event_processor.py`

**Step 1: Write the failing tests**

Add tests that assert Frigate `crop=True` paths pass `is_cropped=true`, and any full-frame/manual-upload classification paths pass `is_cropped=false`.

**Step 2: Run tests to verify they fail**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_events_reclassify_api.py \
  backend/tests/test_backfill_service.py \
  backend/tests/test_event_processor.py -q
```

Expected: FAIL because the call sites do not yet pass classification input context.

**Step 3: Write minimal implementation**

Update all image-classification call sites to pass source context, with special attention to:
- Frigate `crop=True` snapshot callers
- uploaded/manual image callers
- preserving existing rerank/reclassification behavior

**Step 4: Run tests to verify they pass**

Run the same pytest command and confirm the context-threading tests pass.

**Step 5: Commit**

```bash
git add backend/app/services/event_processor.py backend/app/services/backfill_service.py backend/app/services/auto_video_classifier_service.py backend/app/routers/events.py backend/app/routers/classifier.py backend/tests/test_events_reclassify_api.py backend/tests/test_backfill_service.py backend/tests/test_event_processor.py
git commit -m "feat(classifier): pass crop state through image classification paths"
```

### Task 5: Enable Crop Generation for NA Models

**Files:**
- Modify: `backend/app/services/model_manager.py`
- Modify: `backend/scripts/export_birds_only_model.py`
- Modify: release-side `model_config.json` generation paths if applicable
- Test: `backend/tests/test_model_registry_metadata.py`
- Test: `backend/tests/test_export_birds_only_model.py`

**Step 1: Write the failing tests**

Add tests that assert:
- NA model manifests include `crop_generator.enabled=true`
- EU and other models remain disabled by default
- exporter output preserves the configured crop-generator block

**Step 2: Run tests to verify they fail**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_model_registry_metadata.py \
  backend/tests/test_export_birds_only_model.py -q
```

Expected: FAIL because current NA manifests do not yet advertise crop-generator settings.

**Step 3: Write minimal implementation**

Update the NA model metadata and exporter-side manifest generation to include crop-generator configuration.

**Step 4: Run tests to verify it passes**

Run the same pytest command and confirm the manifest/export tests pass.

**Step 5: Commit**

```bash
git add backend/app/services/model_manager.py backend/scripts/export_birds_only_model.py backend/tests/test_model_registry_metadata.py backend/tests/test_export_birds_only_model.py
git commit -m "feat(models): enable crop generator for NA bird models"
```

### Task 6: Regression Verification and Documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/plans/2026-03-20-bird-crop-generator-design.md`
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_model_manager_download.py`
- Test: `backend/tests/test_events_reclassify_api.py`
- Test: `backend/tests/test_backfill_service.py`
- Test: `backend/tests/test_bird_crop_service.py`

**Step 1: Run the focused regression suite**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_model_registry_metadata.py \
  backend/tests/test_model_manager_download.py \
  backend/tests/test_classifier_service.py \
  backend/tests/test_bird_crop_service.py \
  backend/tests/test_events_reclassify_api.py \
  backend/tests/test_backfill_service.py \
  backend/tests/test_event_processor.py \
  backend/tests/test_export_birds_only_model.py -q
```

Expected: PASS.

**Step 2: Update docs**

Document:
- crop-generator manifest fields
- skip-if-already-cropped behavior
- NA-only initial rollout

**Step 3: Commit**

```bash
git add CHANGELOG.md docs/plans/2026-03-20-bird-crop-generator-design.md
git commit -m "docs(classifier): document crop generator rollout"
```
