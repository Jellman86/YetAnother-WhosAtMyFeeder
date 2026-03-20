# Model Config Sidecar Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Standardize YA-WAMF model preprocessing by shipping and consuming a `model_config.json` sidecar for each downloadable model artifact and family variant.

**Architecture:** Keep the registry as the distribution catalog, but make installed `model_config.json` the runtime source of truth for preprocessing and provider metadata. Extend the downloader to fetch and validate the sidecar, then teach classifier preprocessing to honor explicit resize modes instead of using one generic ONNX/OpenVINO path.

**Tech Stack:** Python, Pydantic, FastAPI service layer, Pillow, NumPy, pytest

---

### Task 1: Add model-config schema coverage

**Files:**
- Modify: `backend/app/models/ai_models.py`
- Test: `backend/tests/test_model_registry_metadata.py`

**Step 1: Write the failing test**

Add assertions that `ModelMetadata` accepts and exposes:

- `model_config_url`
- `preprocessing`

Also add assertions that corrected registry entries surface explicit preprocessing metadata for the affected models and family variants.

**Step 2: Run test to verify it fails**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_model_registry_metadata.py -q`

Expected: FAIL because the schema and/or registry entries do not yet expose the new fields correctly.

**Step 3: Write minimal implementation**

Update `ModelMetadata` to include:

- `model_config_url: Optional[str] = None`
- `preprocessing: Optional[Dict[str, Any]] = None`

Update the affected registry entries in `backend/app/services/model_manager.py`.

**Step 4: Run test to verify it passes**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_model_registry_metadata.py -q`

Expected: PASS

### Task 2: Add failing downloader tests for sidecar manifests

**Files:**
- Modify: `backend/tests/test_model_manager_download.py`
- Modify: `backend/app/services/model_manager.py`

**Step 1: Write the failing test**

Add tests that:

- `_validate_download_payload()` requires `model_config.json`
- `_download_payload_to_dir()` writes `model_config.json`
- `get_active_model_spec()` prefers installed `model_config.json` over registry defaults

**Step 2: Run test to verify it fails**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_model_manager_download.py -q`

Expected: FAIL because the downloader and active-model resolver do not yet handle the manifest.

**Step 3: Write minimal implementation**

Patch `backend/app/services/model_manager.py` to:

- carry `model_config_url`
- download `model_config.json`
- require it in payload validation for new-style artifacts
- load installed `model_config.json` into the resolved active model spec

**Step 4: Run test to verify it passes**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_model_manager_download.py -q`

Expected: PASS

### Task 3: Add failing preprocessing-mode tests

**Files:**
- Modify: `backend/tests/test_classifier_service.py`
- Modify: `backend/app/services/classifier_service.py`

**Step 1: Write the failing test**

Add targeted tests for ONNX/OpenVINO preprocessing behavior:

- `letterbox` preserves aspect ratio with padding
- `center_crop` uses crop-based inference preprocessing
- `direct_resize` resizes full frame without padding

Use synthetic images with distinct colored borders/centers so the transformed output can be inspected numerically.

**Step 2: Run test to verify it fails**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -q`

Expected: FAIL because the runtime only supports letterbox-style ONNX/OpenVINO preprocessing.

**Step 3: Write minimal implementation**

Patch `backend/app/services/classifier_service.py` to:

- add shared preprocessing helpers
- read `resize_mode`, `interpolation`, `crop_pct`, and `padding_color`
- apply explicit preprocessing behavior for ONNX and OpenVINO
- preserve compatibility defaults when the manifest omits a field

**Step 4: Run test to verify it passes**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_classifier_service.py -q`

Expected: PASS

### Task 4: Emit sidecar manifests from export tooling

**Files:**
- Modify: `backend/scripts/export_birds_only_model.py`
- Modify: `backend/tests/test_export_birds_only_model.py`

**Step 1: Write the failing test**

Add tests asserting the exporter writes `model_config.json` and includes:

- `runtime`
- `input_size`
- `mean`
- `std`
- `resize_mode`
- `interpolation`

**Step 2: Run test to verify it fails**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_export_birds_only_model.py -q`

Expected: FAIL because the exporter currently emits only `model.onnx` and `labels.txt`.

**Step 3: Write minimal implementation**

Patch `backend/scripts/export_birds_only_model.py` to derive preprocessing metadata from the source model where possible and write `model_config.json`.

**Step 4: Run test to verify it passes**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_export_birds_only_model.py -q`

Expected: PASS

### Task 5: Correct registry metadata for known-wrong models

**Files:**
- Modify: `backend/app/services/model_manager.py`
- Test: `backend/tests/test_model_registry_metadata.py`

**Step 1: Write the failing test**

Add assertions for the corrected preprocessing contract:

- `convnext_large_inat21` uses CLIP/EVA mean/std and crop-based resize metadata
- `rope_vit_b14_inat21` uses Birder RGB stats and crop-based resize metadata
- `small_birds.eu` and `medium_birds.eu` carry Birder RGB stats and crop-based metadata
- `medium_birds.na` carries `direct_resize`
- `eva02_large_inat21` carries crop-based metadata

**Step 2: Run test to verify it fails**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_model_registry_metadata.py -q`

Expected: FAIL because the registry still contains incomplete or incorrect preprocessing metadata.

**Step 3: Write minimal implementation**

Update the registry entries and family variants with explicit preprocessing manifests and sidecar URLs.

**Step 4: Run test to verify it passes**

Run: `cd /config/workspace/YA-WAMF && /config/workspace/YA-WAMF/backend/venv/bin/python -m pytest backend/tests/test_model_registry_metadata.py -q`

Expected: PASS

### Task 6: Run focused verification and update docs

**Files:**
- Modify: `CHANGELOG.md`
- Optional: `docs/plans/2026-03-19-birds-only-model-validation-matrix.md`

**Step 1: Run focused backend verification**

Run:

```bash
cd /config/workspace/YA-WAMF
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_model_registry_metadata.py \
  backend/tests/test_model_manager_download.py \
  backend/tests/test_classifier_service.py \
  backend/tests/test_export_birds_only_model.py -q
```

Expected: PASS

**Step 2: Update docs**

Record that model installs now carry `model_config.json` and that preprocessing is manifest-driven.

**Step 3: Commit**

```bash
cd /config/workspace/YA-WAMF
git add \
  docs/plans/2026-03-20-model-config-sidecar-design.md \
  docs/plans/2026-03-20-model-config-sidecar-plan.md \
  backend/app/models/ai_models.py \
  backend/app/services/model_manager.py \
  backend/app/services/classifier_service.py \
  backend/scripts/export_birds_only_model.py \
  backend/tests/test_model_registry_metadata.py \
  backend/tests/test_model_manager_download.py \
  backend/tests/test_classifier_service.py \
  backend/tests/test_export_birds_only_model.py \
  CHANGELOG.md
git commit -m "feat(models): standardize sidecar preprocessing manifests"
```
