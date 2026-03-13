# OpenVINO GPU Artifact Forensics Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make OpenVINO GPU diagnostics faithfully expose artifact and runtime evidence, then compare the current ConvNeXt artifact path with historical known-good behavior.

**Architecture:** Extend the existing classifier runtime snapshot and probe machinery so it emits exact artifact fingerprints and exact invalid-output summaries from the raw OpenVINO outputs. Add a warning-only compatibility record keyed by artifact fingerprint, then use the enhanced tooling to compare the current artifact against historical export/remediation paths.

**Tech Stack:** FastAPI, Python 3.12, OpenVINO, ONNX metadata inspection, pytest

---

### Task 1: Add failing tests for artifact metadata and compatibility state

**Files:**
- Modify: `backend/tests/test_classifier_service.py`
- Modify: `backend/tests/test_classifier_status_api.py`

**Step 1: Write the failing tests**

Add tests that expect:

- `openvino_runtime.model` includes artifact fingerprint fields:
  - `model_sha256`
  - `weights_sha256`
  - `producer_name`
  - `producer_version`
  - `opset`
- `openvino_runtime.compatibility` exists and exposes:
  - `artifact_trust_state`
  - `last_probe_device`
  - `last_probe_status`

**Step 2: Run tests to verify they fail**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_classifier_service.py \
  backend/tests/test_classifier_status_api.py -q
```

Expected: FAIL because the new artifact and compatibility fields are not exposed yet.

**Step 3: Write minimal implementation**

Implement only the metadata/compatibility snapshot code required to satisfy these tests.

**Step 4: Run tests to verify they pass**

Run the same command and confirm green.

**Step 5: Commit**

```bash
git add backend/tests/test_classifier_service.py backend/tests/test_classifier_status_api.py backend/app/services/classifier_service.py
git commit -m "feat(gpu): expose artifact fingerprint and compatibility state"
```

### Task 2: Add failing tests for probe fidelity on invalid GPU outputs

**Files:**
- Modify: `backend/tests/test_classifier_service.py`
- Modify: `backend/tests/test_error_diagnostics_api.py`

**Step 1: Write the failing tests**

Add tests that expect the probe/startup-self-test diagnostics to preserve the exact invalid output classification:

- if the raw output is a `[1, 10000]` all-`NaN` tensor, the API diagnostics must report:
  - `shape == [1, 10000]`
  - `nan_count == 10000`
  - `invalid_output_kind == "all_nan"`
- if the raw output is empty, the diagnostics must explicitly report:
  - `shape == [0]`
  - `invalid_output_kind == "empty"`

**Step 2: Run tests to verify they fail**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_classifier_service.py \
  backend/tests/test_error_diagnostics_api.py -q
```

Expected: FAIL because the current diagnostics do not preserve the exact invalid-output classification consistently.

**Step 3: Write minimal implementation**

Refactor the OpenVINO output summarization path so both runtime validation and API diagnostics consume the same raw-summary helper and return `invalid_output_kind`.

**Step 4: Run tests to verify they pass**

Run the same command and confirm green.

**Step 5: Commit**

```bash
git add backend/tests/test_classifier_service.py backend/tests/test_error_diagnostics_api.py backend/app/services/classifier_service.py
git commit -m "fix(gpu): preserve exact invalid output diagnostics"
```

### Task 3: Add artifact metadata extraction helpers

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Test: `backend/tests/test_classifier_service.py`

**Step 1: Write the failing test**

Add a focused unit test for the helper that extracts model metadata from ONNX/IR artifacts and sidecars.

**Step 2: Run test to verify it fails**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_classifier_service.py -q
```

Expected: FAIL because the helper does not exist yet.

**Step 3: Write minimal implementation**

Implement:

- artifact hash helper
- ONNX metadata extraction helper
- safe fallback behavior for non-ONNX or missing files

**Step 4: Run test to verify it passes**

Run the same command and confirm green.

**Step 5: Commit**

```bash
git add backend/app/services/classifier_service.py backend/tests/test_classifier_service.py
git commit -m "feat(gpu): add model artifact metadata extraction"
```

### Task 4: Surface compatibility and artifact state in API payloads

**Files:**
- Modify: `backend/app/services/classifier_service.py`
- Modify: `backend/app/routers/diagnostics.py`
- Test: `backend/tests/test_classifier_status_api.py`
- Test: `backend/tests/test_error_diagnostics_api.py`

**Step 1: Write the failing tests**

Extend API tests so:

- `GET /api/classifier/status` returns the new artifact metadata and compatibility state
- `GET /api/diagnostics/workspace` includes the same classifier compatibility snapshot

**Step 2: Run tests to verify they fail**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_classifier_status_api.py \
  backend/tests/test_error_diagnostics_api.py -q
```

Expected: FAIL until the payloads are updated.

**Step 3: Write minimal implementation**

Wire the new snapshot data into the existing payload builders.

**Step 4: Run tests to verify they pass**

Run the same command and confirm green.

**Step 5: Commit**

```bash
git add backend/app/services/classifier_service.py backend/app/routers/diagnostics.py backend/tests/test_classifier_status_api.py backend/tests/test_error_diagnostics_api.py
git commit -m "feat(gpu): expose compatibility diagnostics in status APIs"
```

### Task 5: Historical artifact comparison procedure

**Files:**
- Create: `backend/tests/test_openvino_model_compatibility.py`
- Create: `backend/scripts/compare_openvino_artifacts.py`

**Step 1: Write the failing test**

Add a narrow test for the comparison script helper functions that:

- fingerprint artifacts
- label artifact source (`current_patched`, `historical_export`, `ir_fp16`, `ir_fp32`)

**Step 2: Run test to verify it fails**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_openvino_model_compatibility.py -q
```

Expected: FAIL because the script/helpers do not exist yet.

**Step 3: Write minimal implementation**

Implement a local comparison script that records artifact metadata and emits a consistent JSON report for container-side probe runs.

**Step 4: Run test to verify it passes**

Run the same command and confirm green.

**Step 5: Commit**

```bash
git add backend/tests/test_openvino_model_compatibility.py backend/scripts/compare_openvino_artifacts.py
git commit -m "test(gpu): add openvino artifact comparison tooling"
```

### Task 6: Full verification

**Files:**
- Verify only

**Step 1: Run focused backend tests**

Run:
```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest \
  backend/tests/test_classifier_service.py \
  backend/tests/test_classifier_status_api.py \
  backend/tests/test_error_diagnostics_api.py \
  backend/tests/test_openvino_bird_probe.py \
  backend/tests/test_openvino_model_compatibility.py -q
```

Expected: PASS

**Step 2: Run live container probes**

Run:
```bash
docker exec yawamf-backend env PYTHONUNBUFFERED=1 python /tmp/ov_probe.py
docker exec yawamf-backend env PYTHONUNBUFFERED=1 OV_MODEL_PATH=/tmp/convnext_ir/model.xml python /tmp/ov_probe.py
docker exec yawamf-backend env PYTHONUNBUFFERED=1 OV_MODEL_PATH=/data/models/eva02_large_inat21/model.onnx OV_ONLY_DEVICES=GPU python /tmp/ov_probe.py
```

Expected:
- ConvNeXt current/IR results remain reproducible
- API diagnostics now match raw output classification
- EVA-02 resource failure remains explicitly classified

**Step 3: Commit final verification-ready state**

```bash
git add .
git commit -m "fix(gpu): improve artifact diagnostics and comparison workflow"
```
