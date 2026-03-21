# Model Accuracy Improvement Plan

**Date:** 2026-03-21
**Status:** Proposed

## Background

Analysis of the current model pipeline identified several accuracy problems:

1. **Default model is severely weak** — `model.tflite` resolves to Google Coral MobileNetV2 (2019,
   int8 quantised for Edge TPU, ~960 iNat bird classes). Every user who has never changed their
   model setting is using this.
2. **Wildlife-wide models hurt bird-feeder confidence** — iNat21 10K-class models have ~85%
   non-bird classes (worms, fungi, insects, plants). Probability mass is diluted across ~8,500
   irrelevant classes, making scores on correct bird predictions look low.
3. **NA birds-only models use `direct_resize`** — both EfficientNet-B0 and Binocular/DINOv2 NA
   variants squish Frigate's landscape snapshots to 224×224 without cropping. Standard
   preprocessing for both architectures is `center_crop` with `crop_pct ≈ 0.875`. This is
   partially mitigated when the bird-crop generator is active (bounding-box crops are roughly
   square), but hurts uncropped inference.
4. **Threshold not model-aware** — the global 0.7 threshold is too strict for 10K-class
   wildlife-wide models (where a correct prediction routinely scores 0.3–0.6 on feeder images),
   causing excessive "Unknown Bird" outcomes.
5. **Better birder models exist** but aren't in the registry — the installed birder v0.4.11 has
   174 pretrained models available for download and ONNX export, several of which would
   significantly outperform current offerings.

---

## Phase 1 — Model Research & Selection

**Goal:** Identify the best candidates to export before writing any code.

### 1.1 Birder models available for immediate export (no training required)

The following are already downloadable via `birder.load_pretrained_model()`:

| Model ID | Region | Architecture | Notes |
|---|---|---|---|
| `focalnet_b_lrf_intermediate-eu-common` | EU | FocalNet-Base | ImageNet-21k → EU intermediate → EU common. Strong EU medium candidate. |
| `hiera_abswin_base_mim-intermediate-eu-common` | EU | Hiera-Base | MIM pretraining → intermediate → EU common. Excellent feeder candidate. |
| `convnext_v2_tiny_intermediate-eu-common` | EU | ConvNeXt-V2-Tiny | Better than plain `convnext_v2_tiny_eu-common` due to intermediate step. |
| `regnet_z_4g_eu-common` | EU | RegNetZ-4G | Efficient CNN, 256px variant available. |
| `vit_parallel_s16_18x2_ls_avg_data2vec-intermediate-eu-common` | EU | Data2Vec ViT-S | Self-supervised pretraining, strong small model. |
| `hieradet_d_small_dino-v2-inat21` | Wildlife | HieraDet-S DINOv2 | Better backbone than current `vit_reg4_m16` HieraDet. Already in registry as replacement candidate. |
| `flexivit_reg1_s16_rms_ls_dino-v2-il-all` | Global | FlexiViT DINOv2 | DINOv2 pretraining on il-all (all common birds worldwide). Strong global candidate. |
| `pvt_v2_b2_mmcr-il-all` | Global | PVT-V2-B2 MMCR | MMCR self-supervised, il-all. Compact and accurate. |
| `biformer_s_il-all` | Global | BiFormer-S | Bi-level routing attention, il-all. |
| `mvit_v2_t_il-all` | Global | MViT-V2-Tiny | Video-pretrained ViT variant, il-all. |

**Priority exports for Phase 2:**
1. `focalnet_b_lrf_intermediate-eu-common` — EU medium upgrade (replaces ConvNeXt V2 Tiny)
2. `hieradet_d_small_dino-v2-inat21-256px` — wildlife-wide small upgrade
3. `flexivit_reg1_s16_rms_ls_dino-v2-il-all` — global birds-only medium candidate
4. `hiera_abswin_base_mim-intermediate-eu-common` — EU large candidate (if size is acceptable)

### 1.2 HuggingFace candidates (require download + ONNX conversion)

These require fetching PyTorch weights from HuggingFace and converting, but are worth
evaluating because they address the NA birds gap specifically:

| HF repo | Architecture | Training data | Use case |
|---|---|---|---|
| `chriamue/bird-species-classifier` | EfficientNetV2-S | CUB-200 + augmentation | NA species, small, fast |
| `dennisjooo/Birds-Classifier-EfficientNetB2` | EfficientNet-B2 | 525 bird species | Global birds, reasonable size |
| Various BirdCLEF 2024 finalists | EfficientNetV2-M/L | BirdCLEF audio+image | Diverse global coverage |
| `Narrativaai/aves-classification` | ViT-B/16 | 525 species | Global, clean taxonomy |

**Note:** HuggingFace conversions require torch + onnxruntime. Do only after birder
candidates are benchmarked — birder models may be sufficient.

### 1.3 Reject list (not worth pursuing)

- BirdNET — audio-only, no image classification
- Merlin Bird ID — Cornell Lab, closed source
- eBird ML models — proprietary, not licensed for third-party use
- CLIP zero-shot for birds — poor on fine-grained species (works for "bird" not "Parus major")

---

## Phase 2 — Export New Models

**Goal:** Convert the Phase 1 priority candidates to ONNX and produce accompanying
`model_config.json`, `labels.txt`, and `labels_map.json` (scientific → common name).

### 2.1 Export pipeline (reuse existing scripts)

The project already has:
- `backend/scripts/export_birder_model.py` — downloads and exports a birder model to ONNX
- `backend/scripts/export_birds_only_model.py` — EU/NA birds-only export workflow

For each candidate:

```bash
cd backend
source venv/bin/activate

# EU FocalNet-B (medium upgrade)
python scripts/export_birder_model.py \
    --model focalnet_b_lrf_intermediate-eu-common \
    --output data/models/eu_medium_focalnet_b \
    --input-size 256

# Wildlife-wide HieraDet DINOv2 (small upgrade)
python scripts/export_birder_model.py \
    --model hieradet_d_small_dino-v2-inat21-256px \
    --output data/models/hieradet_dino_small_inat21 \
    --input-size 256

# Global il-all FlexiViT DINOv2 (global birds medium)
python scripts/export_birder_model.py \
    --model flexivit_reg1_s16_rms_ls_dino-v2-il-all \
    --output data/models/flexivit_il_all \
    --input-size 256
```

### 2.2 Per-model preprocessing to record

For each exported model, retrieve normalisation values from the birder model spec:

```python
import birder
model, info = birder.load_pretrained_model("focalnet_b_lrf_intermediate-eu-common", inference=True)
print(info.rgb_stats)   # mean, std
print(info.size)        # input resolution
```

Write this into the model's `model_config.json` sidecar so it travels with the weights.

### 2.3 Checklist per export

- [ ] ONNX file runs inference without errors under `onnxruntime` CPU
- [ ] Output shape is `[1, num_classes]`
- [ ] `labels.txt` has correct class count matching output shape
- [ ] `model_config.json` has correct `mean`, `std`, `input_size`, `resize_mode`, `crop_pct`
- [ ] Model passes the Phase 3 accuracy harness before being added to the registry

---

## Phase 3 — Fix Existing Preprocessing & Registry Issues

**Goal:** Fix the known bugs regardless of whether new models are added.

### 3.1 Fix NA `direct_resize` → `center_crop`

In `backend/app/services/model_manager.py`, change both NA variant preprocessing blocks:

```python
# small_birds / na variant
"preprocessing": {
    "color_space": "RGB",
    "resize_mode": "center_crop",   # was: direct_resize
    "interpolation": "bilinear",
    "crop_pct": 0.875,              # standard EfficientNet-B0 value
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225],
    "normalization": "float32",
},

# medium_birds / na variant (Binocular/DINOv2)
"preprocessing": {
    "color_space": "RGB",
    "resize_mode": "center_crop",   # was: direct_resize
    "interpolation": "bicubic",
    "crop_pct": 0.875,              # standard DINOv2 value
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225],
    "normalization": "float32",
},
```

**Note:** When the bird-crop generator is active, inputs are already roughly square crops
so the difference is minimal. On uncropped full-frame inference this is a meaningful fix.

### 3.2 Change the default model

In `backend/app/config_models.py`, `ClassificationSettings`:

```python
# Before:
model: str = "model.tflite"

# After:
model: str = "convnext_large_inat21"
```

`convnext_large_inat21` is installed by default on the dev image. For users who don't have
it, fall back gracefully to `model.tflite` if the model directory is missing (the model
manager already handles this). Alternatively, default to `small_birds` which auto-selects
by region.

Consider adding an onboarding banner to the Settings UI that nudges users who are still
running `model.tflite` to upgrade.

### 3.3 Per-model threshold guidance

Add a `recommended_threshold` field to each model's registry entry:

```python
{
    "id": "convnext_large_inat21",
    ...
    "recommended_threshold": 0.45,   # 10K-class model; 0.7 is too strict
},
{
    "id": "eva02_large_inat21",
    ...
    "recommended_threshold": 0.45,
},
{
    "id": "mobilenet_v2_birds",
    ...
    "recommended_threshold": 0.70,   # 960-class, high scores are expected
},
{
    "id": "small_birds",
    ...
    "recommended_threshold": 0.65,
},
```

Surface this in the Settings UI as a hint next to the model picker: "Recommended confidence
threshold for this model: 0.45". Do not auto-apply it (users may have intentional overrides),
just show it.

### 3.4 Fix MobileNet V2 letterbox padding colour

Currently uses `padding_color: 128` (medium grey). The original Google Coral model was
exported expecting black padding (`0`). This is a minor issue since most bird images are
close to square, but worth aligning:

```python
"preprocessing": {
    "color_space": "RGB",
    "resize_mode": "letterbox",
    "interpolation": "bicubic",
    "padding_color": 0,    # was: 128 (grey); original trained with black padding
    ...
```

---

## Phase 4 — Accuracy Test Suite

**Goal:** A reproducible benchmark harness that measures top-1 accuracy, top-5 accuracy,
mean confidence on correct predictions, and inference time for every model in the registry
against a standardised labeled bird dataset.

### 4.1 Test dataset strategy

We need labeled ground-truth bird images. Three complementary sets:

**Set A — CUB-200-2011** (recommended starting point)
- 11,788 images, 200 NA bird species
- Free download, well-known, widely used
- Covers common feeder birds (house sparrow, blue jay, cardinal, etc.)
- Limitation: controlled photography, not CCTV/snapshot style
- Download: `http://www.vision.caltech.edu/datasets/cub_200_2011/`

**Set B — iNaturalist research-grade observations (API scrape)**
- Pull recent observations for ~50 target feeder species per region
- Filter: `quality_grade=research`, `photos=true`, bounding box around the species
- More representative of real-world photo conditions than CUB-200
- Script: `backend/scripts/scrape_inat_test_images.py` (to be written)
- Rate limit: iNat API allows ~100 req/min; scrape overnight

**Set C — Frigate snapshot simulation**
- Take CUB-200 or iNat images and simulate Frigate snapshot conditions:
  - Resize to 1280×720 or 1920×1080 landscape (adds letterbox context)
  - Add JPEG compression at quality=75 (Frigate default)
  - Optional: add motion blur and low-contrast variants
- Tests preprocessing robustness, not just model accuracy

**Immediate recommendation:** Start with CUB-200-2011 (Set A) for NA model benchmarking
and a 500-image iNat EU scrape (Set B) for EU model benchmarking.

### 4.2 Harness design

**Location:** `backend/scripts/eval_model_accuracy.py`

```
Input:
  --model <model_id>          Model ID from registry (or "all")
  --dataset <path>            Path to test dataset directory
  --dataset-format <format>   "cub200" | "inat_scrape" | "flat_labeled"
  --simulate-frigate          Apply Frigate-like landscape + JPEG transform (Set C)
  --output <csv_path>         Write per-image results to CSV
  --top-k 5                   Report top-1 through top-k accuracy

Output per model:
  - Top-1 accuracy (%)
  - Top-5 accuracy (%)
  - Mean confidence on correct top-1 predictions
  - Mean confidence on incorrect top-1 predictions
  - Calibration curve (reliability diagram)
  - Inference time: mean, p50, p95, p99 (ms)
  - Per-species breakdown (confusion matrix for top 20 most common species)
  - "Unknown" rate at various threshold levels (0.3, 0.4, 0.5, 0.6, 0.7, 0.8)
```

**Label mapping:** Model labels are scientific names. CUB-200 labels are common names.
Resolve via the taxonomy_service (iNaturalist API) to match them.

### 4.3 Evaluation metrics interpretation

The key metric for a feeder install is not raw accuracy but:

> **"At threshold T, what fraction of birds are correctly identified vs left as Unknown?"**

This produces a precision-recall curve over T. The optimal T is where:
- Precision stays above ~95% (false IDs are worse than unknowns)
- Recall is maximised (fewest unknowns)

A model that gets 85% accuracy but is well-calibrated (high-confidence on correct
predictions) will perform better at a feeder than one with 90% accuracy but poor
calibration (spreads confidence across multiple plausible species).

### 4.4 Feeder-specific test scenarios

Beyond raw accuracy, test these edge cases specifically:

| Scenario | How to simulate | Why it matters |
|---|---|---|
| Multiple birds in frame | Frigate snapshot with 2+ birds | Model may fire on wrong bird |
| Partial occlusion | Mask 25–50% of image | Feeder perches often occlude body |
| Backlit / silhouette | Reduce image contrast, darken | Common at dawn/dusk feeders |
| Wrong species at feeder | Show a squirrel or rat | Model should score low, not misidentify |
| Small/distant bird | Resize to simulate 50px bird in 1080p | Crop generator benefit |
| Wet/fluffed plumage | No easy simulation; gather from iNat | Winter feeder common condition |

### 4.5 Test runner integration

Once the harness is working, add a `pytest` test that:
1. Uses a small fixed labeled set (20–50 images, committed to the repo under `tests/fixtures/eval_images/`)
2. Asserts top-1 accuracy ≥ some minimum per model (e.g., ≥ 70% on the fixture set)
3. Asserts top-1 for the *default* model ≥ 80%

This prevents regressions when preprocessing configs change.

---

## Implementation Order

```
Phase 1 (research, no code)
  └── Identify which birder models to export
  └── Decide on CUB-200 vs iNat scrape for test data

Phase 2 (export)
  └── Export EU FocalNet-B
  └── Export HieraDet DINOv2 iNat21
  └── Export FlexiViT il-all
  └── Validate ONNX outputs

Phase 3 (fixes — independent of Phase 2, can do first)
  └── Fix NA direct_resize → center_crop
  └── Change default model
  └── Add recommended_threshold to registry
  └── Fix MobileNet padding_color
  └── Add threshold hint to Settings UI

Phase 4 (test harness)
  └── Download CUB-200-2011
  └── Write eval_model_accuracy.py
  └── Run benchmark on all current models
  └── Benchmark Phase 2 exports
  └── Promote best performers to recommended tier
  └── Add regression fixtures to pytest
```

Phases 3 and 4.1–4.3 (harness script) can be done in parallel. Phase 3 fixes are
self-contained and can ship to dev before any new models are ready.

---

## Open Questions

1. **What is the region of the target install?** EU or NA birds-only will outperform
   wildlife-wide for a feeder. If we know the user's region we can make the birds-only
   model the recommended default rather than ConvNeXt Large.

2. **Is the bird-crop detector installed on typical user setups?** If not, the NA
   `direct_resize` fix is high priority. If most users have it, it's lower priority.

3. **Should we pursue a training run?** If a small fine-tuned model on actual Frigate
   feeder snapshots (with human labels) were built, it would likely outperform everything
   else for this specific use case. Scope: collect 5K labeled feeder images, fine-tune
   EfficientNet-B0 or ConvNeXt-Tiny. Out of scope for now but worth noting.

4. **License constraints:** EVA-02 and ConvNeXt Large are CC-BY-NC-4.0 (non-commercial
   only). Birds-only birder exports inherit Apache-2.0 from birder. HuggingFace candidates
   vary. All licenses must be checked before releasing new model files.
