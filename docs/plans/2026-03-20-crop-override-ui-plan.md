# Crop Override UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add per-model and per-variant crop overrides in settings/UI, with shipped manifest defaults and optional high-quality crop source preference.

**Architecture:** Keep `model_config.json` as the shipped default contract. Extend settings with override maps, apply overrides in `ModelManager` during active-spec resolution, and let `ClassifierService` consume one resolved `crop_generator` block. Add a higher-quality crop-source resolver that is only used when crop generation is enabled and the input is not already cropped.

**Tech Stack:** FastAPI, Pydantic, Svelte, Vitest, pytest, existing YA-WAMF model/settings infrastructure.

---

### Task 1: Add failing backend tests for crop override resolution

**Files:**
- Modify: `backend/tests/test_model_manager_download.py`
- Modify: `backend/tests/test_model_registry_metadata.py`

**Step 1: Write the failing tests**

Add tests that assert:

- family crop override beats manifest default
- variant crop override beats family override
- invalid override values normalize back to manifest behavior
- crop source override resolves to `high_quality` or `standard`

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_model_manager_download.py \
  backend/tests/test_model_registry_metadata.py -q
```

Expected: FAIL on missing settings fields / unresolved override behavior.

**Step 3: Write minimal implementation**

Implement only enough settings and model-manager resolution to satisfy these tests.

**Step 4: Run test to verify it passes**

Run the same command and confirm PASS.

**Step 5: Commit**

```bash
git add backend/tests/test_model_manager_download.py backend/tests/test_model_registry_metadata.py backend/app/config_models.py backend/app/services/model_manager.py
git commit -m "feat(settings): add crop override resolution"
```

### Task 2: Add failing settings schema and API tests

**Files:**
- Modify: `backend/tests/test_settings_api.py` or nearest existing settings test file
- Modify: `backend/app/config_models.py`
- Modify: `backend/app/routers/settings.py`

**Step 1: Write the failing tests**

Add tests that assert:

- settings payload accepts and persists `crop_model_overrides`
- settings payload accepts and persists `crop_source_overrides`
- invalid override values normalize to `default`

**Step 2: Run test to verify it fails**

Run the targeted settings test command.

Expected: FAIL because the fields do not exist yet.

**Step 3: Write minimal implementation**

Add:

- Pydantic fields in `ClassificationSettings`
- request/update fields in settings router schema
- normalization validators
- persistence through settings save/load path

**Step 4: Run test to verify it passes**

Re-run the targeted settings tests and confirm PASS.

**Step 5: Commit**

```bash
git add backend/app/config_models.py backend/app/routers/settings.py backend/tests/test_settings_api.py
git commit -m "feat(settings): persist crop override preferences"
```

### Task 3: Add failing classifier tests for resolved override behavior

**Files:**
- Modify: `backend/tests/test_classifier_service.py`
- Modify: `backend/app/services/classifier_service.py`

**Step 1: Write the failing tests**

Add tests that assert:

- resolved override `off` suppresses crop generation even when manifest default is `enabled`
- resolved override `on` enables crop generation even when manifest default is `disabled`
- resolved `source_preference=high_quality` triggers high-quality source resolution first
- failed higher-quality source fetch falls back to the original image

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -q
```

Expected: FAIL due to missing source-resolution path and override handling.

**Step 3: Write minimal implementation**

Add:

- resolved source-preference handling
- helper to obtain a higher-quality crop source
- fail-soft fallback behavior

**Step 4: Run test to verify it passes**

Re-run the same command and confirm PASS.

**Step 5: Commit**

```bash
git add backend/app/services/classifier_service.py backend/tests/test_classifier_service.py
git commit -m "feat(classifier): support crop source overrides"
```

### Task 4: Add higher-quality crop source resolver

**Files:**
- Create: `backend/app/services/crop_source_resolver.py`
- Modify: `backend/app/models/ai_models.py`
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_crop_source_resolver.py`

**Step 1: Write the failing test**

Add tests that assert:

- event-backed uncropped image lookup prefers a high-quality snapshot when available
- resolver falls back to current image when lookup fails
- already-cropped input bypasses the resolver

**Step 2: Run test to verify it fails**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_crop_source_resolver.py -q
```

Expected: FAIL because resolver does not exist yet.

**Step 3: Write minimal implementation**

Create a small service that:

- reads `ClassificationInputContext`
- tries to locate a higher-quality uncropped source for the event
- returns either that image or the original image

Keep the first pass narrow and fail-soft.

**Step 4: Run test to verify it passes**

Re-run the same command and confirm PASS.

**Step 5: Commit**

```bash
git add backend/app/services/crop_source_resolver.py backend/app/models/ai_models.py backend/app/services/classifier_service.py backend/tests/test_crop_source_resolver.py
git commit -m "feat(classifier): add high-quality crop source resolver"
```

### Task 5: Add failing UI tests for crop override controls

**Files:**
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`
- Create or modify: `apps/ui/src/lib/settings/crop-overrides.ts`
- Create or modify: `apps/ui/src/lib/settings/*.test.ts`

**Step 1: Write the failing tests**

Add tests that assert:

- family crop override controls round-trip correctly
- variant override controls round-trip correctly
- crop source override controls round-trip correctly

**Step 2: Run test to verify it fails**

Run the targeted Vitest command for the new/updated settings tests.

Expected: FAIL because the controls and payload helpers do not exist yet.

**Step 3: Write minimal implementation**

Add:

- settings helpers for override payloads
- default-layer controls for model/family overrides
- advanced-layer controls for variant overrides

Keep the initial UI scoped to Detection Settings.

**Step 4: Run test to verify it passes**

Re-run the targeted Vitest command and confirm PASS.

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/settings/DetectionSettings.svelte apps/ui/src/lib/settings/crop-overrides.ts apps/ui/src/lib/settings/*.test.ts
git commit -m "feat(ui): add crop override controls"
```

### Task 6: Add integration coverage for settings -> model resolution -> classifier behavior

**Files:**
- Modify: `backend/tests/test_model_family_resolution_api.py`
- Modify: `backend/tests/test_events_reclassify_api.py`
- Modify: `backend/tests/test_backfill_service.py`

**Step 1: Write the failing tests**

Add coverage proving:

- a saved override changes the effective crop policy in resolved family metadata
- reclassification and backfill still pass cropped/full-frame input context correctly with overrides present
- overrides do not break fail-soft behavior when the crop detector is unavailable

**Step 2: Run test to verify it fails**

Run the targeted backend integration tests.

Expected: FAIL until the override plumbing is complete.

**Step 3: Write minimal implementation**

Patch only the missing glue needed to make the end-to-end behavior consistent.

**Step 4: Run test to verify it passes**

Re-run the targeted tests and confirm PASS.

**Step 5: Commit**

```bash
git add backend/tests/test_model_family_resolution_api.py backend/tests/test_events_reclassify_api.py backend/tests/test_backfill_service.py
git commit -m "test(classifier): cover crop override integration paths"
```

### Task 7: Verify the full targeted suite and update docs/changelog

**Files:**
- Modify: `CHANGELOG.md`
- Optionally modify: `docs/plans/2026-03-20-crop-override-ui-design.md`

**Step 1: Update user-facing notes**

Document:

- per-model crop override support
- per-variant crop override support
- higher-quality crop source preference

**Step 2: Run full targeted verification**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_bird_crop_service.py \
  backend/tests/test_classifier_service.py \
  backend/tests/test_crop_source_resolver.py \
  backend/tests/test_model_manager_download.py \
  backend/tests/test_model_registry_metadata.py \
  backend/tests/test_model_family_resolution_api.py \
  backend/tests/test_events_reclassify_api.py \
  backend/tests/test_backfill_service.py -q
```

Run UI verification:

```bash
npm --prefix apps/ui test -- --run
```

Expected: PASS.

**Step 3: Commit**

```bash
git add CHANGELOG.md docs/plans/2026-03-20-crop-override-ui-design.md docs/plans/2026-03-20-crop-override-ui-plan.md
git commit -m "docs: record crop override and high-quality crop source design"
```
