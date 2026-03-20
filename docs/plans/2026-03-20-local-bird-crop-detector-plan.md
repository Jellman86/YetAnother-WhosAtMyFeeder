# Local Bird Crop Detector Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the existing crop-generator stage to a real locally configured ONNX bird detector without making classification depend on that detector being present.

**Architecture:** Keep crop policy model-driven via `model_config.json`, but load one global local detector inside `BirdCropService` by autodiscovering standard model paths first and honoring `BIRD_CROP_MODEL_PATH` as an explicit override. The service should use ONNX Runtime, parse detector candidates into bounding boxes, and fail soft back to the original image whenever the detector is missing, unloadable, or returns unusable results.

**Tech Stack:** Python, ONNX Runtime, Pillow, FastAPI backend services, pytest

---

### Task 1: Add Detector Loading and Output Parsing Tests

**Files:**
- Modify: `backend/tests/test_bird_crop_service.py`

**Step 1: Write the failing tests**

Add tests that assert:
- the service attempts to load a detector from `BIRD_CROP_MODEL_PATH`
- missing env/path degrades to `load_failed`
- parsed detector outputs can produce candidate boxes and confidences
- malformed detector outputs degrade safely

**Step 2: Run test to verify it fails**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_bird_crop_service.py -q
```

Expected: FAIL because the current crop service has no real detector loading or output parsing.

**Step 3: Write minimal implementation**

Implement just enough test seam coverage to describe the desired detector contract.

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm the new tests pass.

**Step 5: Commit**

```bash
git add backend/tests/test_bird_crop_service.py
git commit -m "test(classifier): define local bird detector contract"
```

### Task 2: Implement ONNX Detector Loading in BirdCropService

**Files:**
- Modify: `backend/app/services/bird_crop_service.py`
- Test: `backend/tests/test_bird_crop_service.py`

**Step 1: Write the failing test**

Add a test that asserts:
- `_load_model()` creates an ONNX Runtime session when `BIRD_CROP_MODEL_PATH` is set
- session creation errors degrade to `load_failed`

**Step 2: Run test to verify it fails**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_bird_crop_service.py -q
```

Expected: FAIL because `_load_model()` is still a placeholder.

**Step 3: Write minimal implementation**

Implement:
- local-path lookup via `BIRD_CROP_MODEL_PATH`
- lazy ONNX Runtime session creation
- defensive session metadata capture needed for inference

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm the loader tests pass.

**Step 5: Commit**

```bash
git add backend/app/services/bird_crop_service.py backend/tests/test_bird_crop_service.py
git commit -m "feat(classifier): load local bird crop detector"
```

### Task 3: Implement Detector Inference and Candidate Extraction

**Files:**
- Modify: `backend/app/services/bird_crop_service.py`
- Test: `backend/tests/test_bird_crop_service.py`

**Step 1: Write the failing test**

Add tests for:
- image preprocessing into detector input tensor
- extracting box/confidence pairs from detector output
- ignoring malformed output tensors

**Step 2: Run test to verify it fails**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_bird_crop_service.py -q
```

Expected: FAIL because `_infer_candidates()` still expects a fake `infer()` method.

**Step 3: Write minimal implementation**

Implement:
- detector preprocessing helper
- ORT inference call
- output parsing helper that returns normalized candidate dicts

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm the parsing tests pass.

**Step 5: Commit**

```bash
git add backend/app/services/bird_crop_service.py backend/tests/test_bird_crop_service.py
git commit -m "feat(classifier): run local bird crop detector inference"
```

### Task 4: Verify Classifier Fallback and Skip Behavior

**Files:**
- Modify: `backend/tests/test_classifier_service.py`

**Step 1: Write the failing tests**

Add tests that assert:
- crop-enabled NA models still classify normally when the detector path is missing
- `is_cropped=true` bypasses detector loading/inference entirely

**Step 2: Run tests to verify they fail**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -q
```

Expected: FAIL if the live service path is not correctly using the real detector-backed crop service.

**Step 3: Write minimal implementation**

Adjust only what is necessary so `ClassifierService` preserves current fail-soft and skip semantics with the real detector implementation.

**Step 4: Run tests to verify they pass**

Run the same pytest command and confirm the new classifier tests pass.

**Step 5: Commit**

```bash
git add backend/tests/test_classifier_service.py backend/app/services/bird_crop_service.py backend/app/services/classifier_service.py
git commit -m "test(classifier): verify detector crop fallback behavior"
```

### Task 5: Regression Verification and Documentation

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/plans/2026-03-20-local-bird-crop-detector-design.md`
- Test: `backend/tests/test_bird_crop_service.py`
- Test: `backend/tests/test_classifier_service.py`
- Test: `backend/tests/test_events_reclassify_api.py`
- Test: `backend/tests/test_backfill_service.py`

**Step 1: Update docs**

Document:
- that the crop detector is now locally discoverable from the standard models directory and still overrideable via `BIRD_CROP_MODEL_PATH`
- that crop-enabled models still fail soft when the detector is unavailable

**Step 2: Run regression verification**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_bird_crop_service.py \
  backend/tests/test_classifier_service.py \
  backend/tests/test_events_reclassify_api.py \
  backend/tests/test_backfill_service.py -q
```

Expected: PASS.

**Step 3: Commit**

```bash
git add CHANGELOG.md docs/plans/2026-03-20-local-bird-crop-detector-design.md backend/tests/test_bird_crop_service.py backend/tests/test_classifier_service.py
git commit -m "docs: document local bird crop detector runtime"
```
