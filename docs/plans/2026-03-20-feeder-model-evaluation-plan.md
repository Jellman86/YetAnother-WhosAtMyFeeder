# Feeder Model Evaluation Harness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an offline labeled-feeder evaluation harness that compares YA-WAMF models and crop modes using the real classifier pipeline and writes detailed plus aggregate outputs.

**Architecture:** Add a backend script that reads a manifest CSV, temporarily applies evaluation-only model and crop overrides in memory, runs classification through the existing classifier service, and writes detailed CSV plus summary JSON reports. Keep the harness read-only with explicit state restoration so it never persists setting changes.

**Tech Stack:** Python, existing YA-WAMF backend services, pytest, CSV/JSON stdlib, Pillow.

---

### Task 1: Add manifest and summary helper tests

**Files:**
- Create: `backend/tests/test_feeder_model_evaluation.py`
- Create: `backend/scripts/evaluate_feeder_models.py`

**Step 1: Write the failing tests**

Add tests for:
- parsing a valid manifest row
- rejecting rows missing `truth_species`
- computing top-1 and top-3 summary metrics from row results
- building per-row output with crop/source diagnostics

**Step 2: Run test to verify it fails**

Run: `backend/venv/bin/python -m pytest backend/tests/test_feeder_model_evaluation.py -q`
Expected: FAIL because `evaluate_feeder_models.py` and helper functions do not exist yet.

**Step 3: Write minimal implementation**

Implement minimal pure helpers in `backend/scripts/evaluate_feeder_models.py`:
- manifest row normalization
- summary aggregation
- row output shaping

**Step 4: Run test to verify it passes**

Run: `backend/venv/bin/python -m pytest backend/tests/test_feeder_model_evaluation.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/scripts/evaluate_feeder_models.py backend/tests/test_feeder_model_evaluation.py
git commit -m "test(eval): add feeder harness manifest helpers"
```

### Task 2: Add failing tests for temporary override isolation

**Files:**
- Modify: `backend/tests/test_feeder_model_evaluation.py`
- Modify: `backend/scripts/evaluate_feeder_models.py`

**Step 1: Write the failing tests**

Add tests that verify:
- temporary crop model override is applied for a run
- temporary crop source override is applied for a run
- original `settings.classification.crop_model_overrides` and `crop_source_overrides` are restored afterward
- original `model_manager.active_model_id` is restored afterward

**Step 2: Run test to verify it fails**

Run: `backend/venv/bin/python -m pytest backend/tests/test_feeder_model_evaluation.py -q`
Expected: FAIL because override isolation context is not implemented yet.

**Step 3: Write minimal implementation**

Implement a small context manager or helper in `backend/scripts/evaluate_feeder_models.py` that snapshots and restores in-memory model/settings state.

**Step 4: Run test to verify it passes**

Run: `backend/venv/bin/python -m pytest backend/tests/test_feeder_model_evaluation.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/scripts/evaluate_feeder_models.py backend/tests/test_feeder_model_evaluation.py
git commit -m "feat(eval): isolate temporary model and crop overrides"
```

### Task 3: Add failing tests for classifier row execution

**Files:**
- Modify: `backend/tests/test_feeder_model_evaluation.py`
- Modify: `backend/scripts/evaluate_feeder_models.py`

**Step 1: Write the failing tests**

Add tests that verify one manifest row evaluation:
- loads image path
- passes `ClassificationInputContext` with `is_cropped` and optional `event_id`
- captures top-1/top-3 species
- records crop diagnostics from the classifier result path
- records per-row exceptions without aborting the run

Use a fake classifier callable returning deterministic predictions and diagnostics.

**Step 2: Run test to verify it fails**

Run: `backend/venv/bin/python -m pytest backend/tests/test_feeder_model_evaluation.py -q`
Expected: FAIL because row execution is not implemented yet.

**Step 3: Write minimal implementation**

Implement row evaluation helpers that:
- open the image
- build the input context
- call the classifier
- shape a result row
- catch row-level failures into an `error` field

**Step 4: Run test to verify it passes**

Run: `backend/venv/bin/python -m pytest backend/tests/test_feeder_model_evaluation.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/scripts/evaluate_feeder_models.py backend/tests/test_feeder_model_evaluation.py
git commit -m "feat(eval): execute feeder evaluation rows through classifier"
```

### Task 4: Build the CLI entrypoint and output writers

**Files:**
- Modify: `backend/scripts/evaluate_feeder_models.py`
- Modify: `backend/tests/test_feeder_model_evaluation.py`

**Step 1: Write the failing tests**

Add tests for:
- parsing CLI arguments for manifest, model ids, output prefix, crop override, source override
- writing detailed CSV rows
- writing summary JSON

**Step 2: Run test to verify it fails**

Run: `backend/venv/bin/python -m pytest backend/tests/test_feeder_model_evaluation.py -q`
Expected: FAIL because CLI and writers are incomplete.

**Step 3: Write minimal implementation**

Implement:
- `argparse` CLI
- detailed CSV writer
- summary JSON writer
- script `main()` orchestration

**Step 4: Run test to verify it passes**

Run: `backend/venv/bin/python -m pytest backend/tests/test_feeder_model_evaluation.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/scripts/evaluate_feeder_models.py backend/tests/test_feeder_model_evaluation.py
git commit -m "feat(eval): add feeder evaluation CLI outputs"
```

### Task 5: Add a small real-world sample fixture and smoke path

**Files:**
- Modify: `backend/tests/test_feeder_model_evaluation.py`
- Optionally create: `backend/tests/fixtures/` small generated images only if needed

**Step 1: Write the failing test**

Add one integration-style smoke test that runs a tiny manifest with a fake classifier across multiple rows and verifies:
- summary totals are correct
- a failed row does not stop later rows
- crop/source reasons are preserved in output rows

**Step 2: Run test to verify it fails**

Run: `backend/venv/bin/python -m pytest backend/tests/test_feeder_model_evaluation.py -q`
Expected: FAIL because orchestration still misses one smoke-path behavior.

**Step 3: Write minimal implementation**

Fill any missing orchestration behavior with the smallest change required.

**Step 4: Run test to verify it passes**

Run: `backend/venv/bin/python -m pytest backend/tests/test_feeder_model_evaluation.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/scripts/evaluate_feeder_models.py backend/tests/test_feeder_model_evaluation.py
git commit -m "test(eval): add feeder harness smoke coverage"
```

### Task 6: Document usage and verify targeted suites

**Files:**
- Modify: `CHANGELOG.md`
- Optionally modify: `docs/plans/2026-03-20-feeder-model-evaluation-design.md`

**Step 1: Update docs**

Add a changelog entry describing the new offline feeder evaluation harness and what outputs it writes.

**Step 2: Run targeted verification**

Run:
```bash
backend/venv/bin/python -m pytest backend/tests/test_feeder_model_evaluation.py -q
backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py backend/tests/test_model_manager_download.py -q
```
Expected: PASS

**Step 3: Optional manual smoke run**

Run the script against a tiny local manifest if available:
```bash
backend/venv/bin/python backend/scripts/evaluate_feeder_models.py --manifest /tmp/sample_manifest.csv --model small_birds --output-prefix /tmp/eval
```
Expected: writes `/tmp/eval_detailed.csv` and `/tmp/eval_summary.json`

**Step 4: Commit**

```bash
git add CHANGELOG.md backend/scripts/evaluate_feeder_models.py backend/tests/test_feeder_model_evaluation.py
git commit -m "feat(eval): add feeder model evaluation harness"
```
