# Crop Detector Evaluation Harness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a manifest-driven evaluation harness for crop detectors that compares `fast` and `accurate` tiers on feeder and clean reference bird images, using explicit bird boxes and reusable fixture downloads.

**Architecture:** Build a crop-detector evaluator under `backend/scripts/` that reuses the production `BirdCropService` inference path, loads a dedicated crop-detector fixture manifest, computes localization metrics and overlays, and supports both auto-downloaded reference images and harvested feeder images. Keep the first version CLI-driven and deterministic, with fixtures cached in `backend/tests/fixtures/`.

**Tech Stack:** Python 3.12, ONNX Runtime, Pillow, existing YA-WAMF `BirdCropService`, existing fixture/evaluation script patterns, pytest.

---

### Task 1: Add failing tests for crop-detector manifest loading and IoU metrics

**Files:**
- Create: `backend/tests/test_crop_detector_eval_harness.py`
- Create: `backend/scripts/eval_crop_detector_accuracy.py`

**Step 1: Write the failing tests**

Add tests covering:

- crop manifest entries load and validate required fields
- IoU calculation is correct for overlapping and non-overlapping boxes
- per-image evaluation chooses the best predicted box against ground truth

**Step 2: Run test to verify it fails**

Run:
`/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_crop_detector_eval_harness.py -q`

Expected: fail because the evaluator module does not exist yet.

**Step 3: Write minimal implementation**

Create the evaluator module with:

- manifest loader
- `compute_iou`
- basic image-result summarization

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add backend/tests/test_crop_detector_eval_harness.py backend/scripts/eval_crop_detector_accuracy.py
git commit -m "test: add crop detector evaluation harness core coverage"
```

### Task 2: Add failing tests for bucket aggregation and output summaries

**Files:**
- Modify: `backend/tests/test_crop_detector_eval_harness.py`
- Modify: `backend/scripts/eval_crop_detector_accuracy.py`

**Step 1: Write the failing tests**

Add tests covering:

- bucket aggregation by `feeder_real` and `reference_clean`
- recall at IoU `0.3` and `0.5`
- mean/median best IoU
- selected-crop rate and any-detection rate

**Step 2: Run test to verify it fails**

Run:
`/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_crop_detector_eval_harness.py -q`

Expected: fail because bucket aggregation does not exist yet.

**Step 3: Write minimal implementation**

Add:

- aggregate summary helpers
- thresholded localization metrics
- JSON/CSV-serializable summary structures

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add backend/tests/test_crop_detector_eval_harness.py backend/scripts/eval_crop_detector_accuracy.py
git commit -m "feat: add crop detector evaluation metrics"
```

### Task 3: Add failing tests for production crop-service-backed evaluation

**Files:**
- Modify: `backend/tests/test_crop_detector_eval_harness.py`
- Modify: `backend/scripts/eval_crop_detector_accuracy.py`

**Step 1: Write the failing tests**

Add tests covering:

- evaluator uses `BirdCropService` for `fast` and `accurate`
- evaluation records detector tier and best confidence
- evaluator handles missing/empty candidates cleanly

Use monkeypatched fake detectors so tests do not depend on real ONNX models.

**Step 2: Run test to verify it fails**

Run:
`/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_crop_detector_eval_harness.py -q`

Expected: fail because the evaluator does not yet use production crop-service code.

**Step 3: Write minimal implementation**

Add a detector runner that:

- instantiates `BirdCropService(detector_tier=...)`
- calls `_ensure_model_for_tier`
- calls `_infer_candidates`
- evaluates predicted boxes against ground truth

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add backend/tests/test_crop_detector_eval_harness.py backend/scripts/eval_crop_detector_accuracy.py
git commit -m "feat: evaluate crop detectors through BirdCropService"
```

### Task 4: Add failing tests for overlay rendering

**Files:**
- Modify: `backend/tests/test_crop_detector_eval_harness.py`
- Modify: `backend/scripts/eval_crop_detector_accuracy.py`

**Step 1: Write the failing tests**

Add tests covering:

- overlay image file is written
- overlay includes both GT and predicted boxes
- overlay generation does not crash when there is no prediction

**Step 2: Run test to verify it fails**

Run:
`/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_crop_detector_eval_harness.py -q`

Expected: fail because overlay output does not exist yet.

**Step 3: Write minimal implementation**

Add:

- overlay writer using Pillow drawing primitives
- simple labels for detector, bucket, and confidence

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add backend/tests/test_crop_detector_eval_harness.py backend/scripts/eval_crop_detector_accuracy.py
git commit -m "feat: add crop detector evaluation overlays"
```

### Task 5: Add fixture manifest and reference-image download flow

**Files:**
- Create: `backend/tests/fixtures/crop_detector_manifest.json`
- Create: `backend/scripts/download_crop_detector_fixtures.py`
- Modify: `backend/tests/test_crop_detector_eval_harness.py`

**Step 1: Write the failing tests**

Add tests covering:

- reference fixture downloader can read the crop manifest
- target download paths resolve under `backend/tests/fixtures/crop_detector_images/reference_clean`
- downloader ignores already-cached images cleanly

**Step 2: Run test to verify it fails**

Run:
`/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_crop_detector_eval_harness.py -q`

Expected: fail because the crop fixture downloader and manifest do not exist yet.

**Step 3: Write minimal implementation**

Add:

- initial manifest with a small mixed set of curated clean-reference entries
- downloader following the current model-accuracy harness style
- local cache layout under `backend/tests/fixtures/crop_detector_images/reference_clean`

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add backend/tests/fixtures/crop_detector_manifest.json backend/scripts/download_crop_detector_fixtures.py backend/tests/test_crop_detector_eval_harness.py
git commit -m "feat: add crop detector reference fixture download flow"
```

### Task 6: Add feeder-image harvest flow

**Files:**
- Create: `backend/scripts/harvest_feeder_crop_images.py`
- Modify: `backend/tests/test_crop_detector_eval_harness.py`
- Modify: `backend/tests/fixtures/crop_detector_manifest.json`

**Step 1: Write the failing tests**

Add tests covering:

- feeder harvest script discovers local images from configured directories
- harvested paths are normalized into the feeder fixture cache
- manifest entries can be created or updated for `feeder_real`

**Step 2: Run test to verify it fails**

Run:
`/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_crop_detector_eval_harness.py -q`

Expected: fail because the harvest script does not exist yet.

**Step 3: Write minimal implementation**

Add:

- bounded image discovery from local Frigate or supplied directories
- copy-to-cache behavior under `backend/tests/fixtures/crop_detector_images/feeder_real`
- manifest update helpers for feeder entries

**Step 4: Run test to verify it passes**

Run the same pytest command and confirm pass.

**Step 5: Commit**

```bash
git add backend/scripts/harvest_feeder_crop_images.py backend/tests/test_crop_detector_eval_harness.py backend/tests/fixtures/crop_detector_manifest.json
git commit -m "feat: add feeder crop fixture harvest flow"
```

### Task 7: Add initial dataset generation and evaluation CLI flow

**Files:**
- Modify: `backend/scripts/eval_crop_detector_accuracy.py`
- Modify: `backend/scripts/download_crop_detector_fixtures.py`
- Modify: `backend/scripts/harvest_feeder_crop_images.py`
- Modify: `docs/features/model-accuracy.md`
- Create: `docs/features/crop-detector-accuracy.md`

**Step 1: Wire the CLI**

Add CLI options for:

- manifest path
- fixture download
- feeder harvest
- detector selection (`fast`, `accurate`, `all`)
- overlay output directory
- JSON/CSV output paths

**Step 2: Verify terminology and docs**

Run:
`cd /config/workspace/YA-WAMF && rg -n "crop detector evaluation|crop-detector-accuracy|eval_crop_detector_accuracy" backend docs`

Expected: consistent terminology.

**Step 3: Document usage**

Document:

- fixture download
- feeder harvest
- evaluator invocation
- output meanings

**Step 4: Commit**

```bash
git add backend/scripts/eval_crop_detector_accuracy.py backend/scripts/download_crop_detector_fixtures.py backend/scripts/harvest_feeder_crop_images.py docs/features/model-accuracy.md docs/features/crop-detector-accuracy.md
git commit -m "docs: add crop detector evaluation harness usage"
```

### Task 8: Run full verification

**Files:**
- No code changes required unless a failure is found

**Step 1: Run targeted backend tests**

Run:
`/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest /config/workspace/YA-WAMF/backend/tests/test_crop_detector_eval_harness.py /config/workspace/YA-WAMF/backend/tests/test_bird_crop_service.py /config/workspace/YA-WAMF/tests/unit/test_crop_detector_registry.py -q`

Expected: all pass.

**Step 2: Run the evaluator on a small sample**

Run:
`cd /config/workspace/YA-WAMF/backend && /config/workspace/YA-WAMF/backend/venv/bin/python scripts/eval_crop_detector_accuracy.py --manifest tests/fixtures/crop_detector_manifest.json --detectors all --max_samples 10 --output_json /tmp/crop_eval.json`

Expected: successful run with JSON output.

**Step 3: Run frontend checks if docs/UI references changed**

Run:
`npm --prefix /config/workspace/YA-WAMF/apps/ui run check`

Expected: `0 errors, 0 warnings`.

**Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "feat: add crop detector evaluation harness"
```
