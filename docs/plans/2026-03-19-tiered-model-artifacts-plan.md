# Tiered Model Artifacts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add one small and one medium wildlife model artifact alongside the existing CPU-only, large, and advanced models, with local download/export steps that can produce ONNX artifacts suitable for CUDA and OpenVINO validation.

**Architecture:** Keep the existing runtime contract centered on ONNX/TFLite artifacts and registry metadata. Add a new backend export path for Birder-hosted iNat21 checkpoints, validate those artifacts locally, then register only the candidates that survive download and conversion. Do not disturb the current install/activate flow or existing models while the new artifacts are being proven out.

**Tech Stack:** Python, PyTorch, ONNX, ONNX Runtime GPU, OpenVINO, Hugging Face model hosting, backend pytest

---

### Task 1: Lock candidate models and validation surface

**Files:**
- Modify: `backend/tests/test_model_registry_metadata.py`
- Modify: `backend/tests/test_model_manager_download.py`
- Modify: `backend/app/services/model_manager.py`

**Step 1: Write the failing tests**

```python
async def test_available_models_include_small_and_medium_wildlife_candidates():
    models = await ModelManager().list_available_models()
    by_id = {model.id: model for model in models}

    assert by_id["hieradet_small_inat21"].tier == "small"
    assert by_id["hieradet_small_inat21"].taxonomy_scope == "wildlife_wide"
    assert by_id["rope_vit_b14_inat21"].tier == "medium"
    assert by_id["rope_vit_b14_inat21"].advanced_only is False
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/tmp/yawamf-testshim:/config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend/tests/test_model_registry_metadata.py -q`
Expected: FAIL because the new model IDs are not present.

**Step 3: Write minimal implementation**

```python
REMOTE_REGISTRY.extend([
    {
        "id": "hieradet_small_inat21",
        "tier": "small",
        ...
    },
    {
        "id": "rope_vit_b14_inat21",
        "tier": "medium",
        ...
    },
])
```

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=/tmp/yawamf-testshim:/config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend/tests/test_model_registry_metadata.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_model_registry_metadata.py backend/tests/test_model_manager_download.py backend/app/services/model_manager.py
git commit -m "feat: add small and medium model registry entries"
```

### Task 2: Add Birder export tooling for local artifact generation

**Files:**
- Create: `backend/scripts/export_birder_model.py`
- Create: `backend/tests/test_export_birder_model.py`
- Modify: `backend/scripts/export_model.py`

**Step 1: Write the failing test**

```python
def test_export_birder_model_writes_labels_and_onnx_paths(tmp_path):
    report = export_birder_model(
        model_id="birder-project/hieradet_d_small_dino-v2-inat21-256px",
        output_dir=tmp_path,
        input_size=256,
        loader=fake_loader,
    )

    assert report["model_path"] == str(tmp_path / "model.onnx")
    assert report["labels_path"] == str(tmp_path / "labels.txt")
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=/config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend/tests/test_export_birder_model.py -q`
Expected: FAIL because the exporter does not exist.

**Step 3: Write minimal implementation**

```python
def export_birder_model(model_id: str, output_dir: str, input_size: int, loader=load_birder_model):
    model, labels = loader(model_id)
    ...
    return {"model_path": str(model_path), "labels_path": str(labels_path)}
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=/config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend/tests/test_export_birder_model.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/scripts/export_birder_model.py backend/tests/test_export_birder_model.py backend/scripts/export_model.py
git commit -m "feat: add birder onnx export tooling"
```

### Task 3: Download and convert candidate artifacts locally

**Files:**
- Create: `backend/data/models/hieradet_small_inat21/`
- Create: `backend/data/models/rope_vit_b14_inat21/`
- Modify: `backend/app/services/model_manager.py`

**Step 1: Run the local export commands**

```bash
python3 backend/scripts/export_birder_model.py   --model birder-project/hieradet_d_small_dino-v2-inat21-256px   --output_dir backend/data/models/hieradet_small_inat21   --size 256

python3 backend/scripts/export_birder_model.py   --model birder-project/rope_vit_reg4_b14_capi-inat21-224px   --output_dir backend/data/models/rope_vit_b14_inat21   --size 224
```

Expected: local `model.onnx` and `labels.txt` artifacts are created for both candidates.

**Step 2: Validate ONNX load with runtime backends**

Run: `python3 backend/scripts/test_onnx.py`
Expected: ONNX Runtime can load the artifacts; record any OpenVINO compile failures for follow-up patching or rejection.

**Step 3: Add minimal implementation updates**

```python
REMOTE_REGISTRY[...] = {
    "download_url": local_or_release_artifact_url,
    ...
}
```

**Step 4: Run backend tests to verify registry and download behavior**

Run: `PYTHONPATH=/tmp/yawamf-testshim:/config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend/tests/test_model_registry_metadata.py /config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend/tests/test_model_manager_download.py -q`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/data/models/hieradet_small_inat21 backend/data/models/rope_vit_b14_inat21 backend/app/services/model_manager.py
git commit -m "feat: add small and medium wildlife model artifacts"
```

### Task 4: Verify artifact viability and document follow-ups

**Files:**
- Modify: `CHANGELOG.md`
- Create: `docs/plans/2026-03-19-tiered-model-artifacts-validation.md`

**Step 1: Write the validation note**

```md
- candidate
- source
- artifact size
- onnxruntime cpu/cuda result
- openvino result
- any patching required
```

**Step 2: Run final verification**

Run: `npm --prefix /config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/apps/ui run check`
Run: `PYTHONPATH=/tmp/yawamf-testshim:/config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend python3 -m pytest --noconftest /config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend/tests/test_model_registry_metadata.py /config/workspace/YA-WAMF/.worktrees/tiered-model-lineup/backend/tests/test_model_manager_download.py -q`
Expected: PASS

**Step 3: Commit**

```bash
git add CHANGELOG.md docs/plans/2026-03-19-tiered-model-artifacts-validation.md
git commit -m "docs: record tiered model artifact validation"
```
