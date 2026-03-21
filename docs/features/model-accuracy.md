# Model Accuracy & Benchmark Results

This document describes how to run the model accuracy benchmark, explains the methodology, and documents the current results for all installed models on this hardware.

---

## Benchmark Results

Results are measured against 60 labeled bird images drawn from iNaturalist (15 species × 4 images each). Images cover both North American and European feeder birds, plus common rejection cases (out-of-scope birds that should still be classified but at lower confidence).

> **Note on scope mismatch:** Birds-only regional models (Small Birds, Medium Birds, EU FocalNet, FlexiViT) are trained on European species. When tested against our fixture set which includes many North American species (Northern Cardinal, Blue Jay, American Robin, etc.), their scores reflect correct handling of out-of-scope input — not a real-world performance failure on their intended region.

### Accuracy Table (15 March 2026)

| Model | Tier | Scope | Top-1 | Top-5 | Mean Inference | Provider |
|-------|------|-------|-------|-------|---------------|----------|
| **RoPE ViT-B14** | medium | wildlife_wide | **70.0%** | **86.7%** | 474ms | intel_cpu |
| **EVA-02 Large** | advanced | wildlife_wide | **75.0%** | **88.3%** | 1621ms | intel_cpu |
| **ConvNeXt Large** | large | wildlife_wide | **70.0%** | **86.7%** | 832ms | intel_cpu |
| **HieraDeT Small (DINO)** | small | wildlife_wide | 70.0% | 81.7% | 551ms | cpu |
| **HieraDeT Small** | small | wildlife_wide | 61.7% | 81.7% | 271ms | intel_cpu |
| **MobileNet V2** (legacy TFLite) | cpu_only | birds_only | 66.7% | 73.3% | 13ms | tflite |
| **EfficientNet Lite4** (legacy TFLite) | cpu_only | birds_only | 66.7% | 73.3% | 13ms | tflite |
| **EU FocalNet-B** | medium | birds_only (EU) | 56.7% | 65.0% | 716ms | intel_cpu |
| **Medium Birds** (EU variant) | medium | birds_only (EU) | 46.7% | 56.7% | 64ms | intel_cpu |
| **Small Birds** (EU variant) | small | birds_only (EU) | 46.7% | 53.3% | 62ms | intel_cpu |
| **FlexiViT Global** | small | birds_only (global) | 33.3% | 40.0% | 231ms | intel_cpu |
| **Bird Crop Detector** | dependency | system | n/a | n/a | 3ms | cpu |

> **EU/regional model note:** Medium Birds, Small Birds, EU FocalNet, and FlexiViT are designed for European or global species lists. The test fixture is approximately 60% North American species, so their apparent low accuracy is expected. On an EU-only fixture their real accuracy would be substantially higher.

### Key Takeaways

- **EVA-02 Large** achieves the highest top-1 accuracy (75%) but is slow (~1.6s) and requires ~3GB RAM.
- **RoPE ViT-B14** and **ConvNeXt Large** tie at 70% top-1 / 86.7% top-5 — RoPE is faster (474ms vs 832ms) making it the recommended default.
- **HieraDeT Small (DINOv2)** matches RoPE ViT on top-1 accuracy (70%) at slightly faster speed and smaller model size — worth considering for constrained systems.
- **Legacy TFLite models** (MobileNet V2, EfficientNet Lite4) are fast (13ms) but accuracy is lower. They are hidden in the UI by default and labeled as legacy/lower-performing.

---

## Intel GPU Support

All models were tested on OpenVINO 2024.6 with an Intel integrated GPU. **No model currently produces correct output on Intel GPU** on this hardware:

| Model | Intel GPU Status | Failure Mode |
|-------|-----------------|--------------|
| ConvNeXt Large | ❌ Not supported | Near-uniform output (~0.0001 per class) on real images — passes NaN check but produces garbage predictions |
| EVA-02 Large | ❌ Not supported | OpenCL execution crash (`clWaitForEvents -14`) |
| RoPE ViT-B14 | ❌ Not supported | NaN output — RoPE attention ops in f32 (caught by startup self-test) |
| HieraDeT Small | ❌ Not supported | NaN output — ViT attention in f32 (caught by startup self-test) |
| HieraDeT DINO Small | ❌ Not supported | Compile error — architecture fails to load on GPU plugin |
| FlexiViT Global | ❌ Not supported | NaN output — FlexiViT DINOv2 attention in f32 (caught by startup self-test) |
| EU FocalNet-B | ❌ Not supported | Degrades to CPU after startup — GPU output not reliable end-to-end |

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
