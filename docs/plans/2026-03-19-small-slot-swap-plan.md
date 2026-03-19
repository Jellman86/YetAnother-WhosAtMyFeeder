# Small Slot Swap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current small-slot model artifact behind `hieradet_small_inat21` with the validated ViT small export while keeping the existing slot ID and download flow stable.

**Architecture:** Keep the registry slot and sort order unchanged, but swap its metadata and artifact source to the new Birder ViT model. Update the Birder export script to support the current loader contract and the newer ONNX exporter path required by this model, then publish replacement release assets and reverify manager download and activation.

**Tech Stack:** Python, pytest, Pydantic, ONNX, OpenVINO, ONNX Runtime, GitHub Releases, Svelte metadata consumer

---

### Task 1: Lock Down the In-Place Swap in Tests

**Files:**
- Modify: `backend/tests/test_model_registry_metadata.py`
- Modify: `backend/tests/test_model_manager_download.py`
- Test: `backend/tests/test_export_birder_model.py`

**Step 1: Write the failing tests**

```python
assert by_id["hieradet_small_inat21"].architecture == "ViT Reg4 M16 RMS Avg (I-JEPA)"
assert "Intel GPU validated" in by_id["hieradet_small_inat21"].notes
assert "HieraDet" not in by_id["hieradet_small_inat21"].name
```

Add an exporter test that proves external-data ONNX exports are reported correctly.

**Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=/tmp/yawamf-testshim:/config/workspace/YA-WAMF/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/backend/tests/test_model_registry_metadata.py /config/workspace/YA-WAMF/backend/tests/test_export_birder_model.py -q`
Expected: FAIL because the registry and exporter still describe the old small model behavior.

**Step 3: Write the minimal implementation**

Update registry metadata and exporter return data only enough to satisfy the new expectations.

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=/tmp/yawamf-testshim:/config/workspace/YA-WAMF/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/backend/tests/test_model_registry_metadata.py /config/workspace/YA-WAMF/backend/tests/test_export_birder_model.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_model_registry_metadata.py backend/tests/test_model_manager_download.py backend/tests/test_export_birder_model.py backend/app/services/model_manager.py backend/scripts/export_birder_model.py
git commit -m "feat: swap small model registry metadata"
```

### Task 2: Make the Birder Exporter Reproducible for the New Small Model

**Files:**
- Modify: `backend/scripts/export_birder_model.py`
- Test: `backend/tests/test_export_birder_model.py`

**Step 1: Write the failing test**

```python
assert report["external_data_path"] == str(output_dir / "model.onnx.data")
```

Add a test that injects a fake exporter callback which writes `model.onnx.data` and proves the report captures it.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/tmp/yawamf-testshim:/config/workspace/YA-WAMF/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/backend/tests/test_export_birder_model.py -q`
Expected: FAIL because the report does not expose external-data output.

**Step 3: Write minimal implementation**

Update the exporter to:
- resolve a file path for the Birder weights cache
- support an injected ONNX export function
- detect and report `model.onnx.data`

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=/tmp/yawamf-testshim:/config/workspace/YA-WAMF/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/backend/tests/test_export_birder_model.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/scripts/export_birder_model.py backend/tests/test_export_birder_model.py
git commit -m "feat: support external-data birder exports"
```

### Task 3: Export and Publish the Replacement Small Artifact

**Files:**
- Modify: `backend/app/services/model_manager.py`
- External: GitHub release `models`

**Step 1: Export the new artifact locally**

Run:

```bash
/config/workspace/tmp/birder-validate-venv/bin/python /config/workspace/YA-WAMF/backend/scripts/export_birder_model.py --model birder-project/vit_reg4_m16_rms_avg_i-jepa-inat21-256px --output_dir /config/workspace/tmp/hieradet_small_inat21_replacement --size 256
```

**Step 2: Validate locally**

Run ONNX Runtime CPU, OpenVINO CPU, and OpenVINO GPU checks against the export.

**Step 3: Publish replacement assets**

Upload:
- replacement `hieradet_small_inat21.onnx`
- replacement `hieradet_small_inat21.onnx.data`
- replacement `hieradet_small_inat21_labels.txt`

**Step 4: Update registry metadata**

Point the existing small slot at the new artifact set and update display metadata and notes to describe the actual model.

**Step 5: Commit**

```bash
git add backend/app/services/model_manager.py
git commit -m "feat: replace small wildlife model artifact"
```

### Task 4: Reverify Manager Download and Activation End to End

**Files:**
- Modify: `backend/tests/test_model_manager_download.py`

**Step 1: Write the failing test**

Add or extend a download-manager assertion that the swapped small slot still exposes the required sidecar download metadata for external-data ONNX.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/tmp/yawamf-testshim:/config/workspace/YA-WAMF/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/backend/tests/test_model_manager_download.py -q`
Expected: FAIL because the manager metadata has not yet been updated.

**Step 3: Write minimal implementation**

Adjust the registry entry or tests only as needed to reflect the replacement artifact.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=/tmp/yawamf-testshim:/config/workspace/YA-WAMF/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/backend/tests/test_model_manager_download.py /config/workspace/YA-WAMF/backend/tests/test_model_registry_metadata.py /config/workspace/YA-WAMF/backend/tests/test_export_birder_model.py -q`
Expected: PASS

Then run real download and activation verification for `hieradet_small_inat21`.

**Step 5: Commit**

```bash
git add backend/tests/test_model_manager_download.py
git commit -m "test: verify swapped small model download flow"
```
