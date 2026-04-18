# Crop Source Priority Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a global crop source priority setting and polished UI controls so users can choose whether Frigate hints or the configured crop model are preferred.

**Architecture:** Extend classification settings with a new `bird_crop_source_priority` enum, then centralize crop-source ordering in both classification and HQ snapshot flows. Keep crop tier selection separate and unchanged in meaning. Update Detection Settings to use matching styled dropdowns for both crop controls.

**Tech Stack:** Python, pytest, Svelte, existing settings API

---

### Task 1: Add failing tests for the new settings field and crop order

**Files:**
- Modify: `tests/unit/test_bird_crop_detector_tier_setting.py`
- Modify: `backend/tests/test_classifier_service.py`
- Modify: `backend/tests/test_high_quality_snapshot_service.py`
- Modify: `apps/ui/src/lib/components/settings/detection-crop-overrides.layout.test.ts`

**Step 1: Write the failing tests**

Add tests that cover:
- settings model accepts supported `bird_crop_source_priority` values
- settings route exposes the field
- classification uses model first when configured
- classification skips model when `frigate_hints_only`
- HQ snapshot flow uses model first when configured
- UI source contains the new setting control and matching styled dropdown markup

**Step 2: Run tests to verify they fail**

Run:
`cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/unit/test_bird_crop_detector_tier_setting.py backend/tests/test_classifier_service.py backend/tests/test_high_quality_snapshot_service.py -q`

Run:
`cd /config/workspace/YA-WAMF && npm --prefix apps/ui test -- detection-crop-overrides.layout.test.ts`

Expected: failures for the missing field and missing alternate crop ordering.

### Task 2: Implement backend setting and crop source ordering

**Files:**
- Modify: `backend/app/config_models.py`
- Modify: `backend/app/config_loader.py`
- Modify: `backend/app/routers/settings.py`
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/services/high_quality_snapshot_service.py`

**Step 1: Add the new setting**

Implement `bird_crop_source_priority` with supported values:
- `frigate_hints_first`
- `crop_model_first`
- `crop_model_only`
- `frigate_hints_only`

Default to `frigate_hints_first`.

**Step 2: Implement shared source-order behavior**

Update classification and HQ snapshot crop logic so both use the same configured source ordering while preserving model tier behavior.

**Step 3: Run tests to verify they pass**

Run:
`cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/unit/test_bird_crop_detector_tier_setting.py backend/tests/test_classifier_service.py backend/tests/test_high_quality_snapshot_service.py -q`

Expected: PASS

### Task 3: Polish the settings UI

**Files:**
- Modify: `apps/ui/src/lib/api/settings.ts`
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`
- Modify: `apps/ui/src/lib/pages/Settings.svelte`
- Modify: `apps/ui/src/lib/components/settings/detection-crop-overrides.layout.test.ts`

**Step 1: Add UI state and API binding**

Wire the new setting through the settings page state, dirty-checking, load, and save paths.

**Step 2: Replace the plain crop selector presentation**

Keep the crop settings grouped together and use the same polished dropdown style used by the main model selector for:
- crop detector tier
- crop source priority

**Step 3: Run UI tests**

Run:
`cd /config/workspace/YA-WAMF && npm --prefix apps/ui test -- detection-crop-overrides.layout.test.ts`

Run:
`cd /config/workspace/YA-WAMF && npm --prefix apps/ui run check`

Expected: PASS

### Task 4: Final verification and commit

**Files:**
- Modify only the files above, plus these docs:
  - `docs/plans/2026-04-18-crop-source-priority-design.md`
  - `docs/plans/2026-04-18-crop-source-priority.md`

**Step 1: Run final focused verification**

Run:
`cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest tests/unit/test_bird_crop_detector_tier_setting.py backend/tests/test_classifier_service.py backend/tests/test_high_quality_snapshot_service.py -q`

Run:
`cd /config/workspace/YA-WAMF && npm --prefix apps/ui test -- detection-crop-overrides.layout.test.ts`

Run:
`cd /config/workspace/YA-WAMF && npm --prefix apps/ui run check`

**Step 2: Commit**

```bash
git -C /config/workspace/YA-WAMF add \
  backend/app/config_models.py \
  backend/app/config_loader.py \
  backend/app/routers/settings.py \
  backend/app/services/classifier_service.py \
  backend/app/services/high_quality_snapshot_service.py \
  tests/unit/test_bird_crop_detector_tier_setting.py \
  backend/tests/test_classifier_service.py \
  backend/tests/test_high_quality_snapshot_service.py \
  apps/ui/src/lib/api/settings.ts \
  apps/ui/src/lib/components/settings/DetectionSettings.svelte \
  apps/ui/src/lib/pages/Settings.svelte \
  apps/ui/src/lib/components/settings/detection-crop-overrides.layout.test.ts \
  docs/plans/2026-04-18-crop-source-priority-design.md \
  docs/plans/2026-04-18-crop-source-priority.md
git -C /config/workspace/YA-WAMF commit -m "Add crop source priority configuration"
```
