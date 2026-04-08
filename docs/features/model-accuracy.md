# Model Accuracy & Benchmark Results

This document describes how to run the model accuracy benchmark, explains the methodology, and documents the current results for all installed models on this hardware.

---

## Benchmark Results

Results are measured against 60 labeled bird images drawn from iNaturalist (15 species × 4 images each). Images cover both North American and European feeder birds, plus common rejection cases (out-of-scope birds that should still be classified but at lower confidence).

Each run tests two preprocessing modes — **raw** (image sent as-is) and **letterbox** (padded to a square with gray borders) — to identify whether padding helps or hurts each model.

> **Note on scope mismatch:** The birds-only models are not directly comparable to the wildlife-wide models on this mixed fixture set. `Small Birds` and `Medium Birds` resolve to regional variants, the published benchmark rows here use the EU variants, `EU FocalNet-B` is European-only, and `FlexiViT Global` covers a smaller 550-species global bird label space. Lower scores here often reflect out-of-scope input in the fixture set, not a real-world failure on their intended deployment.

### Accuracy Table (22 March 2026)

| Model | Tier | Scope | Top-1 (raw) | Top-1 (lbx) | Top-5 (raw) | Top-5 (lbx) | Mean Inference | Provider |
|-------|------|-------|-------------|-------------|-------------|-------------|---------------|----------|
| **EVA-02 Large** | advanced | wildlife_wide | **68.3%** | 66.7% | **81.7%** | 78.3% | 1595ms | intel_cpu |
| **RoPE ViT-B14** | medium | wildlife_wide | 63.3% | **65.0%** | **80.0%** | 75.0% | 493ms | intel_cpu |
| **ConvNeXt Large** | large | wildlife_wide | 63.3% | 60.0% | **80.0%** | 78.3% | 976ms | intel_cpu |
| **MobileNet V2** (legacy TFLite) | cpu_only | birds_only | 61.7% | 63.3% | 68.3% | 70.0% | 13ms | tflite |
| **Small Birds** (EU variant) | small | birds_only (EU) | 41.7% | 38.3% | 48.3% | 50.0% | 55ms | intel_cpu |
| **EU FocalNet-B** | medium | birds_only (EU) | 41.7% | 36.7% | 53.3% | 48.3% | 266ms | intel_gpu |
| **Medium Birds** (EU variant) | medium | birds_only (EU) | 40.0% | 33.3% | 50.0% | 48.3% | 62ms | intel_cpu |
| **FlexiViT Global** | small | birds_only (global) | 33.3% | 31.7% | 40.0% | 38.3% | 199ms | intel_cpu |
| **Bird Crop Detector** | dependency | system | n/a | n/a | n/a | n/a | 5ms | cpu |

> **Birds-only model note:** `Small Birds` and `Medium Birds` are region-resolved family entries, `EU FocalNet-B` is Europe-specific, and `FlexiViT Global` trades coverage and size for speed. The shared fixture set is still weighted toward North American species, so these rows should be read as scope-mismatch diagnostics rather than direct leaderboard entries against the wildlife-wide models.

> **Intel GPU support:** EU FocalNet-B, Small Birds EU, and Medium Birds EU are validated on Intel integrated GPU. All other ONNX models run on Intel CPU (OpenVINO). See the Intel GPU Support table below.

### Key Takeaways

- **EVA-02 Large** achieves the highest top-1 accuracy (68.3% raw) but is slow (~1.6s) and requires ~3GB RAM.
- **RoPE ViT-B14** is the recommended default: 63.3% top-1 / 80.0% top-5 at 493ms — the best speed/accuracy balance for wildlife-wide classification. Letterboxing gives a marginal top-1 gain (+1.7%) at the cost of top-5 (−5.0%).
- **ConvNeXt Large** matches RoPE top-1 but is twice as slow (976ms) with no accuracy advantage.
- **Letterboxing** makes no meaningful difference across any model (±1–7% top-1). Raw preprocessing is recommended as the default.
- **Legacy TFLite MobileNet V2** is fast (13ms) but has fewer labels and lower top-5 accuracy. Hidden in the UI by default and labelled as legacy.

> **Note on score changes from previous run (15 March 2026):** Accuracy is 5–7% lower than the March 15 results. This is due to iNaturalist serving different photos on re-download — the fixture set is the same 15 species but the 4 images per species changed. Scores will vary slightly between runs for this reason.

---

## Intel GPU Support

Models were tested on OpenVINO 2025.4.1 with an Intel integrated GPU:

| Model | Intel GPU Status | Notes |
|-------|-----------------|-------|
| EU FocalNet-B | ✅ Validated | Correct finite output. Static-batch reshape required (applied automatically). |
| Small Birds EU (MobileNetV4-L) | ✅ Validated | ratio=1.03, Spearman=0.996, top5∩=5. Excellent GPU match. Probed 22 March 2026. |
| Medium Birds EU (ConvNeXt-V2-Tiny) | ✅ Validated | ratio=0.98, Spearman=0.959, top5∩=3. Smaller kernel avoids ConvNeXt Large's precision issue. Probed 22 March 2026. |
| ConvNeXt Large | ❌ Not supported | Wrong predictions — GPU logit spread ~3–7 vs ~18 on CPU; top-1 is entirely wrong species. Seven compilation strategies tested exhaustively (f16, ACCURACY hint, no-Winograd, HETERO): f16 → NaN; ACCURACY → compile crash; HETERO → range recovers but ranking still wrong (Spearman 0.16). Not fixable on this iGPU generation with OV 2025.4. |
| RoPE ViT-B14 | ❌ Not supported | NaN in both f32 and f16. RoPE attention ops are not finite on this iGPU. |
| FlexiViT Global | ❌ Not supported | NaN in both f32 and f16. FlexiViT DINOv2 RMSNorm produces non-finite values. |
| Small Birds NA (EfficientNet-B0) | ❌ Not supported | Non-deterministic crash — first inference after clean state may pass (f32: ratio=0.83, Spearman=0.821), but subsequent GPU compilations crash with `CL_OUT_OF_RESOURCES`. f16 → NaN. Too unreliable for production use. |
| Medium Birds NA (Binocular) | ❌ Not supported | NaN in both f32 and f16. |
| EVA-02 Large | ❌ Fatal crash | Non-deterministic: first attempt may return NaN, second attempt crashes the process with `clWaitForEvents -14` / `CL_OUT_OF_RESOURCES`. Not a RAM issue — iGPU can address 28.7 GB with 4 GB max allocation; the 1.2 GB model fits easily. Root cause is an EVA-CLIP attention op incompatibility on this iGPU generation. Confirmed on OV 2024.6.0, 2026.0.0, and 2025.4.1. Do not use with Intel GPU. |

**Intel CPU (OpenVINO)** works correctly for all ONNX models and provides a meaningful speedup over plain ONNX Runtime CPU. Set the provider to `Intel CPU (OpenVINO)` for best performance without a GPU.

The `auto` provider setting will try GPU first, run the startup self-test, detect failures, and fall back to `Intel CPU (OpenVINO)` or `CPU` automatically.

---

## Running the Accuracy Benchmark

### Prerequisites

1. **Docker container running**: `docker compose up -d`
2. **Models installed**: Download at least one model from Settings > Models
3. **Fixture images**: Download iNaturalist test images (one-time setup):

```bash
python3 backend/scripts/download_test_fixtures.py
# Downloads 60 images (15 species × 4 each) to backend/tests/fixtures/bird_images/
```

Alternatively, pass `--auto_download` and the script will fetch them automatically if not already present.

### Run against the active model

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:8946 \
  --username YOUR_USERNAME --password YOUR_PASSWORD
```

If auth is disabled:
```bash
python3 backend/scripts/pipeline_api_test.py --base_url http://localhost:8946
```

### Run against all installed models

This cycles through every installed model in turn, activates it, tests it, then restores the original:

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:8946 \
  --username YOUR_USERNAME --password YOUR_PASSWORD \
  --all_models
```

With auto-download and preprocessing comparison (letterbox vs center-crop):

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:8946 \
  --username YOUR_USERNAME --password YOUR_PASSWORD \
  --all_models --preprocess compare --auto_download
```

### Save a JSON report

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:8946 \
  --all_models \
  --output report.json
```

### Test specific species only

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:8946 \
  --cases house_sparrow,blue_jay,european_robin
```

### Show per-image predictions

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:8946 \
  --verbose
```

---

## Running the Automated Model Tests

### Smoke tests (no images required, fast)

Verifies every installed model loads, has correct I/O shape, and produces finite output:

```bash
cd backend
source venv/bin/activate
pytest tests/test_model_smoke.py -v
```

### Integration tests (requires downloaded fixture images)

Tests each model with real bird images to verify label matching and confidence:

```bash
cd backend
source venv/bin/activate
pytest tests/test_model_integration.py -v
# Filter to a specific model:
pytest tests/test_model_integration.py -v --model rope_vit_b14_inat21
```

### OpenVINO GPU validation tests

Validates which models compile and produce correct output on Intel GPU:

```bash
cd backend
source venv/bin/activate
pytest tests/test_model_openvino_gpu.py -v
```

These tests skip automatically if no Intel GPU is detected.

#### Running inside Docker (required for GPU access)

In this environment the Intel GPU is only accessible inside the running backend container, not from the host shell. Run the tests there:

```bash
docker exec yawamf-backend python -m pytest tests/test_model_openvino_gpu.py -v
```

#### Diagnostic probes (no pass/fail — print a results table)

Two additional probes help investigate GPU failures. They never fail; use `-s` to see the output table.

**NaN / wrong-prediction fix probe** — tries HETERO, SDPA-off, and combined strategies on every model currently failing on GPU:

```bash
docker exec yawamf-backend python -m pytest \
  tests/test_model_openvino_gpu.py::test_gpu_nan_fix_probe -v -s
```

**ConvNeXt Large precision probe** — tries seven compilation strategies specifically for ConvNeXt's precision-degradation failure (f16, ACCURACY hint, no-Winograd, HETERO, combinations):

```bash
docker exec yawamf-backend python -m pytest \
  tests/test_model_openvino_gpu.py::test_convnext_gpu_precision_probe -v -s
```

The table columns are: `GPU range`, `ratio` (GPU/CPU), `spearman` (rank correlation vs CPU), `top5 ∩` (top-5 overlap with CPU), and `result`. A strategy is considered fixed when ratio ≥ 0.5, Spearman ≥ 0.50, and top-5 ∩ ≥ 1.

Results from OV 2025.4.1 on an Intel integrated GPU are documented in the Intel GPU Support table above and in the `GPU_NOT_SUPPORTED` dict in `tests/test_model_openvino_gpu.py`.

---

### NVIDIA GPU diagnostic probes

Contributors with NVIDIA GPUs can run a separate diagnostic suite that tests every installed model through ONNX Runtime's `CUDAExecutionProvider` and `TensorrtExecutionProvider`. These probes are best-effort only: they print a results table and are expected to skip cleanly on hosts without an exposed NVIDIA device.

#### Prerequisites

The official YA-WAMF images now package the CUDA/cuDNN userspace runtime needed by `onnxruntime-gpu`. NVIDIA Container Toolkit must still be installed on the host so the GPU driver/runtime is exposed inside the container. Add GPU access to `docker-compose.yml`:

```yaml
services:
  yawamf-backend:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

Or for a one-off run without modifying compose:

```bash
docker run --gpus all ghcr.io/jellman86/wamf-backend:dev \
    python -m pytest tests/test_model_nvidia_gpu.py -v -s
```

#### Full per-model survey (all strategies)

Tests every installed ONNX model through CUDA/fp32, CUDA/fp32+exhaustive, TRT/fp32, TRT/fp16, and TRT/fp16+exhaust:

```bash
docker exec yawamf-backend python -m pytest \
  tests/test_model_nvidia_gpu.py::test_nvidia_gpu_full_probe -v -s
```

#### ConvNeXt Large focused probe

ConvNeXt Large is broken on Intel iGPU (precision degradation, not fixable with OV 2025.4).  This probe checks whether NVIDIA GPU gives correct results and includes Intel iGPU reference data for direct comparison:

```bash
docker exec yawamf-backend python -m pytest \
  tests/test_model_nvidia_gpu.py::test_convnext_nvidia_probe -v -s
```

The table columns are the same as the Intel probes: `GPU range`, `ratio` (GPU/CPU), `spearman` (rank correlation vs CPU), `top5 ∩` (top-5 overlap with CPU), and `result`.  A strategy passes when ratio ≥ 0.5, Spearman ≥ 0.50, and top-5 ∩ ≥ 1.

#### Sharing results

If you run these probes, please paste the printed table into the relevant GitHub issue along with:

```bash
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
python -c "import onnxruntime; print(onnxruntime.__version__)"
```

---

## Test Fixture Details

The benchmark uses 60 research-grade photos from iNaturalist (CC-BY/CC0 licensed), covering:

| Species | Common Name | Region | iNat Taxon ID |
|---------|-------------|--------|---------------|
| Cardinalis cardinalis | Northern Cardinal | NA | 9083 |
| Cyanocitta cristata | Blue Jay | NA | 8229 |
| Turdus migratorius | American Robin | NA | 12727 |
| Haemorhous mexicanus | House Finch | NA | 199840 |
| Spinus tristis | American Goldfinch | NA | 145310 |
| Dryobates pubescens | Downy Woodpecker | NA | 18100 |
| Sitta carolinensis | White-breasted Nuthatch | NA | 13933 |
| Poecile atricapillus | Black-capped Chickadee | NA | 13028 |
| Sturnus vulgaris | European Starling | NA/EU | 12727 |
| Passer domesticus | House Sparrow | Global | 125813 |
| Hirundo rustica | Barn Swallow | Global | 14889 |
| Turdus merula | Eurasian Blackbird | EU | 12879 |
| Erithacus rubecula | European Robin | EU | 20823 |
| Columba livia | Rock Pigeon | Global | 4886 |
| Anas platyrhynchos | Mallard | Global | 6930 |

Images are downloaded once and cached in `backend/tests/fixtures/bird_images/`. Re-run `download_test_fixtures.py` to refresh them.

---

## Adding New Test Cases

Edit `backend/tests/fixtures/bird_image_manifest.json` to add species. Each entry requires:

```json
{
  "id": "unique_snake_case_id",
  "common_name": "Common Name",
  "scientific_name": "Genus species",
  "inat_taxon_id": 12345,
  "acceptable_labels": ["Common Name", "Genus species", "alias"],
  "scope": ["na", "birds_only", "wildlife_wide"],
  "min_top_n": 5,
  "notes": "Optional notes about this test case"
}
```

Then run `download_test_fixtures.py` to fetch 4 images for the new species.
