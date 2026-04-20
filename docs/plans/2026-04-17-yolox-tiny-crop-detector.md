# YOLOX-Tiny Crop Detector Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an optional YOLOX-Tiny-based `accurate` bird-crop detector tier while preserving the current fast detector as the default fail-soft crop path.

**Architecture:** Extend the managed crop-detector registry to support two detector tiers, add a new owner setting for tier selection, split detector parsing into adapter-style code in `BirdCropService`, and integrate the accurate tier into the existing HQ crop flow with explicit fallback to the fast detector and then the original image.

**Tech Stack:** FastAPI, Pydantic settings/config, ONNX Runtime, existing YA-WAMF model manager and bird crop service, pytest.

---

### Task 1: Add failing tests for crop-detector tier selection

**Files:**
- Modify: `backend/tests/test_audio_service.py` (do not touch)
- Create: `backend/tests/test_bird_crop_service_tiers.py`
- Modify: `backend/app/services/bird_crop_service.py`

**Step 1: Write the failing test**

Add tests covering:

- default tier is `fast`
- `accurate` requested + unavailable falls back to `fast`
- no healthy detectors returns an empty/fail-soft crop result

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_bird_crop_service_tiers.py -q`

Expected: failing tests because tier selection does not exist yet.

**Step 3: Write minimal implementation**

Add internal tier-selection helpers in `backend/app/services/bird_crop_service.py` without changing detector parsing yet.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add backend/tests/test_bird_crop_service_tiers.py backend/app/services/bird_crop_service.py
git commit -m "test: add bird crop detector tier selection coverage"
```

### Task 2: Add config setting for detector tier

**Files:**
- Modify: `backend/app/config_models.py`
- Modify: `backend/app/routers/settings.py`
- Create: `tests/unit/test_bird_crop_detector_tier_setting.py`

**Step 1: Write the failing test**

Add tests for:

- allowed values: `fast`, `accurate`
- default value is `fast`
- settings GET/PUT include the field

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/tests/unit/test_bird_crop_detector_tier_setting.py -q`

Expected: fail because the setting is missing.

**Step 3: Write minimal implementation**

Add the setting to config models and settings router response/update handling.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add backend/app/config_models.py backend/app/routers/settings.py tests/unit/test_bird_crop_detector_tier_setting.py
git commit -m "feat: add bird crop detector tier setting"
```

### Task 3: Extend model manager registry for accurate crop detector

**Files:**
- Modify: `backend/app/services/model_manager.py`
- Create: `tests/unit/test_crop_detector_registry.py`

**Step 1: Write the failing test**

Add tests asserting:

- fast crop detector remains present
- accurate YOLOX-Tiny detector is present with distinct id/tier metadata
- crop detector status surfaces can resolve both tiers

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/tests/unit/test_crop_detector_registry.py -q`

Expected: fail because only one detector tier exists today.

**Step 3: Write minimal implementation**

Add a new registry entry for the accurate detector and helper methods for crop-detector tier lookup/status.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add backend/app/services/model_manager.py tests/unit/test_crop_detector_registry.py
git commit -m "feat: register accurate YOLOX crop detector tier"
```

### Task 4: Add failing tests for YOLOX output parsing

**Files:**
- Create: `backend/tests/test_bird_crop_yolox_adapter.py`
- Modify: `backend/app/services/bird_crop_service.py`

**Step 1: Write the failing test**

Add tests for:

- YOLOX output shape parsing into normalized boxes
- unknown output shape returns no candidates
- bird-class filtering keeps only bird detections

Use synthetic output tensors, not a real model artifact.

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_bird_crop_yolox_adapter.py -q`

Expected: fail because the YOLOX adapter does not exist yet.

**Step 3: Write minimal implementation**

Add a YOLOX-specific parser/adapter path in `bird_crop_service.py`.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add backend/tests/test_bird_crop_yolox_adapter.py backend/app/services/bird_crop_service.py
git commit -m "feat: add YOLOX bird crop parser"
```

### Task 5: Wire tier-based model loading into bird crop service

**Files:**
- Modify: `backend/app/services/bird_crop_service.py`
- Modify: `backend/app/services/high_quality_snapshot_service.py`
- Create: `backend/tests/test_high_quality_snapshot_crop_tiers.py`

**Step 1: Write the failing test**

Add tests covering:

- HQ crop flow uses the selected tier when healthy
- requested accurate tier falls back to fast
- diagnostics/fallback reason is retained

**Step 2: Run test to verify it fails**

Run: `/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_high_quality_snapshot_crop_tiers.py -q`

Expected: fail because HQ crop flow does not yet know about detector tiers.

**Step 3: Write minimal implementation**

Teach the crop service to resolve the selected detector tier and let the HQ snapshot path record which detector was used or why it fell back.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add backend/app/services/bird_crop_service.py backend/app/services/high_quality_snapshot_service.py backend/tests/test_high_quality_snapshot_crop_tiers.py
git commit -m "feat: use selected bird crop detector tier in HQ snapshots"
```

### Task 6: Expose tier selection in settings UI

**Files:**
- Modify: `apps/ui/src/lib/components/settings/DetectionSettings.svelte`
- Modify: `apps/ui/src/lib/api/types.ts`
- Create: `apps/ui/src/lib/components/settings/DetectionSettings.test.ts` or existing UI test file if that pattern exists

**Step 1: Write the failing test**

Add a UI/state test that verifies:

- `fast`/`accurate` options render
- `fast` is the default value
- explanatory help text appears

**Step 2: Run test to verify it fails**

Run the relevant frontend test command for the chosen file.

Expected: fail because the UI field does not exist.

**Step 3: Write minimal implementation**

Add the owner-only selector and wire it to the existing settings payload.

**Step 4: Run test to verify it passes**

Run the same frontend test plus:

`npm --prefix /config/workspace/YA-WAMF/apps/ui run check`

Expected: pass, `0 errors, 0 warnings`.

**Step 5: Commit**

```bash
git add apps/ui/src/lib/components/settings/DetectionSettings.svelte apps/ui/src/lib/api/types.ts
git commit -m "feat: add accurate bird crop detector tier setting to UI"
```

### Task 7: Add docs for the new detector tier

**Files:**
- Modify: `docs/features/ai-models.md`
- Modify: `docs/features/model-accuracy.md`
- Modify: `ROADMAP.md` only if status wording needs adjustment

**Step 1: Write the docs change**

Document:

- fast vs accurate crop detector tiers
- YOLOX-Tiny as the accurate tier
- CPU-first support
- fail-soft fallback behavior
- experimental/optional positioning until benchmarked

**Step 2: Verify docs references**

Run:

`cd /config/workspace/YA-WAMF && rg -n "Bird Crop Detector|accurate" docs backend/app`

Expected: consistent terminology.

**Step 3: Commit**

```bash
git add docs/features/ai-models.md docs/features/model-accuracy.md ROADMAP.md
git commit -m "docs: describe YOLOX accurate bird crop tier"
```

### Task 8: Run full verification

**Files:**
- No code changes required unless a failure is found

**Step 1: Run backend targeted tests**

Run:

`/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_bird_crop_service_tiers.py /config/workspace/YA-WAMF/backend/tests/test_bird_crop_yolox_adapter.py /config/workspace/YA-WAMF/backend/tests/test_high_quality_snapshot_crop_tiers.py /config/workspace/YA-WAMF/tests/unit/test_bird_crop_detector_tier_setting.py /config/workspace/YA-WAMF/tests/unit/test_crop_detector_registry.py -q`

Expected: all pass.

**Step 2: Run backend unit suite**

Run:

`/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/tests/unit -q`

Expected: all pass.

**Step 3: Run frontend checks**

Run:

`npm --prefix /config/workspace/YA-WAMF/apps/ui run check`

Expected: `0 errors, 0 warnings`.

**Step 4: If available, run a representative runtime smoke**

At minimum inspect crop-detector status and ensure the app starts without regression.

**Step 5: Commit any final fixes**

```bash
git add -A
git commit -m "feat: add YOLOX-Tiny accurate bird crop detector tier"
```
