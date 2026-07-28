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
| **Bird Crop Detector (Fast)** | fast | system | n/a | n/a | n/a | n/a | 5ms | cpu |
| **Bird Crop Detector Accurate (YOLOX-Tiny)** | accurate | system | n/a | n/a | n/a | n/a | 11–30ms provider sweep | host-validated |

> **Birds-only model note:** `Small Birds` and `Medium Birds` are region-resolved family entries, `EU FocalNet-B` is Europe-specific, and `FlexiViT Global` trades coverage and size for speed. The shared fixture set is still weighted toward North American species, so these rows should be read as scope-mismatch diagnostics rather than direct leaderboard entries against the wildlife-wide models.

> **Intel GPU support:** Support depends on the Intel generation and OpenVINO runtime. RoPE ViT-B14
> is validated on Arrow Lake-S with OpenVINO 2026.2.1, while older Intel GPU / OpenVINO 2025.4
> combinations produced NaNs. YA-WAMF's post-install device validation is the authority for a
> particular host. See the Intel GPU Support table below.

### Key Takeaways

- **EVA-02 Large** achieves the highest top-1 accuracy (68.3% raw) but is slow (~1.6s) and requires ~3GB RAM.
- **RoPE ViT-B14** is the recommended default: 63.3% top-1 / 80.0% top-5 at 493ms — the best speed/accuracy balance for wildlife-wide classification. Letterboxing gives a marginal top-1 gain (+1.7%) at the cost of top-5 (−5.0%).
- **ConvNeXt Large** matches RoPE top-1 but is twice as slow (976ms) with no accuracy advantage.
- **Letterboxing** makes no meaningful difference across any model (±1–7% top-1). Raw preprocessing is recommended as the default.
- **Legacy TFLite MobileNet V2** is fast (13ms) but has fewer labels and lower top-5 accuracy. Hidden in the UI by default and labelled as legacy.
- **Bird Crop Detector (Fast)** remains the fail-soft cropped-thumbnail fallback because it is small,
  fast, and already validated for CPU use.
- **Bird Crop Detector Accurate (YOLOX-Tiny)** is the optional experimental cropped-thumbnail tier.
  Its artifact is published and it retries with the fast detector whenever it is unavailable or
  returns no usable crop. A 21 July 2026 Quark provider sweep validated CPU and OpenVINO
  CPU/GPU/NPU agreement on a varied clean species panel, with a separate 40-case private field panel
  covering 30 events across seven recorded labels and 10 real hard negatives. This is provider
  compatibility evidence, not a model-quality promotion; a larger owner-labelled box fixture
  remains pending. The latest accurate sweep measured 32.7 ms on CPU, 14.3 ms on Intel CPU,
  10.7 ms on Intel GPU, and 14.5 ms on Intel NPU. The private unguided field
  replay admitted only 6/30 positives at the safe `0.02` evidence floor (and 0/13 negatives), so
  distant-subject recall—not provider correctness—remains the main replacement-model question.
  The subsequent runtime optimization uses same-frame Frigate coordinates as a high-resolution
  YOLOX search region and activates bounded overlapping tiles only after an unguided native miss.
  Saved candidates retain the strategy, and model crops must materially improve downstream
  classifier confidence before replacing an available Frigate crop. A 30-positive/10-negative
  end-to-end run produced 7 guarded model promotions and 23 Frigate retentions, with one win, two
  ties, and no guarded loss across the three owner-labelled visits and no hard-negative crop above
  the active `0.40` classifier floor. This validates defensive selection, not detector superiority;
  more owner truth is still required.
- **Classifier cropping is separate from thumbnail generation.** Classifier crop-on/off is fixed per
  model from the Quark comparison below. Both crop-enabled classifiers and generated thumbnails try
  the validated accurate detector path automatically with a safe fast fallback.

> **Note on score changes from previous run (15 March 2026):** Accuracy is 5–7% lower than the March 15 results. This is due to iNaturalist serving different photos on re-download — the fixture set is the same 15 species but the 4 images per species changed. Scores will vary slightly between runs for this reason.

---

## Classifier crop policy (18 July 2026)

Quark compared a detector-generated bird crop with the unchanged full frame on the production
`ClassifierService` path. The fixed panel contains 144 taxonomy-verified images: three images for
each of 48 common feeder species. Across all standalone models and EU/NA family variants, the run
produced 4,032 classifications using the accurate YOLOX-Tiny detector.

Top-1 accuracy is primary. Differences below two percentage points are treated as ties, resolved by
top-3 accuracy, Unknown rate, then median latency.

| Model or variant | Crop on top-1 / top-3 | Full frame top-1 / top-3 | Automatic policy |
|---|---:|---:|---|
| MobileNet V2 | 54.86 / 66.67 | 50.00 / 60.42 | **Crop on** |
| Small Birds NA | 27.78 / 34.72 | 23.61 / 34.03 | **Crop on** |
| Medium Birds NA | 33.33 / 45.14 | 31.25 / 39.58 | **Crop on** |
| FlexiViT Global | 19.44 / 21.53 | 17.36 / 20.14 | **Crop on** |
| Small Birds EU | 25.69 / 28.47 | 25.69 / 29.86 | Full frame |
| Medium Birds EU | 27.08 / 31.25 | 27.78 / 33.33 | Full frame |
| ConvNeXt Large | 63.19 / 71.53 | 68.75 / 76.39 | Full frame |
| FocalNet-B EU | 36.81 / 40.28 | 38.19 / 41.67 | Full frame |
| RoPE ViT-B14 | 62.50 / 71.53 | 67.36 / 75.00 | Full frame |
| EVA-02 Large | 68.06 / 77.78 | 67.36 / 79.86 | Full frame |
| MogaNet-S EU | 27.78 / 31.94 | 27.78 / 34.72 | Full frame |
| ConvNeXt-V1 Tiny EU | 27.78 / 32.64 | 29.17 / 35.42 | Full frame |
| RegNet-Y-8G EU | 25.69 / 29.86 | 26.39 / 33.33 | Full frame |
| UniFormer-S EU | 28.47 / 31.94 | 27.08 / 34.03 | Full frame |

All 2,016 crop-on cases attempted localization. The detector applied 1,736 crops, rejected 182
images below its confidence threshold, rejected 98 candidates as too small, and recorded zero load
or inference failures. The complete method, latency measurements, retained artifact paths, limits,
and follow-up criteria are in the [automatic crop-policy report](../plans/2026-07-16-model-crop-policy.md).

### Distant-camera field check (20 July 2026)

The moved Quark `birdcam` view was checked separately because its birds occupy much less of the
2560×1920 frame than the public evaluation images. Across 12 recent events with generated HQ
candidates, a crop was selected for 9. The mean best crop classification score was 0.762, compared
with 0.154 for the best unchanged full-frame candidate, a mean gain of 0.598. The original live
classification averaged 0.806, but that path already receives Frigate's event crop and therefore is
not a wide-frame control.

These are model scores, not hand-labelled accuracy results, so they justify using crop candidates
as additional evidence rather than claiming that every higher score is correct. One event's best
crop scored only 0.144 with an implausible conflicting label; this is why automatic refinement
requires confidence, independent-frame agreement, a clear winner, and compatibility with the
existing identification. The manually verified feeder fixture remains the required follow-up for
measuring accuracy rather than confidence.

### Completed-track baseline (21 July 2026)

HQ selection now treats Frigate's completed-event best frame as a protected baseline instead of
assuming that a sampled recording frame is automatically better. At Frigate `end`, YA-WAMF fetches
the full-resolution clean copy, applies the box tied to Frigate's selected snapshot (falling back
to the final track box for older payloads), and scores the clean full frame and
crop alongside independent video frames. A recording-derived candidate must predict a compatible
identity and improve classifier confidence by at least `0.02` before it can replace that baseline.
Both final Frigate candidates remain in the bounded audit set even when video wins.
The final still can also complete the HQ replacement by itself when all clip sources are absent.

The same correction fixes time-aligned event crops: Frigate `path_data` coordinates describe each
tracked box's **bottom-centre**, not its geometric centre. YA-WAMF now reconstructs the box with
`left = path_x - width / 2` and `top = path_y - height`, and compares path samples with the final
box's bottom-centre when choosing frames. Final-still candidates do not count as an independent
video moment for multi-frame species refinement, preventing one visual frame from voting twice.

---

## Intel GPU Support

The original matrix was tested on OpenVINO 2025.4.1 with an Intel integrated GPU. RoPE ViT-B14 was
revalidated on 18 July 2026 and ConvNeXt Large on 21 July 2026 on Arrow Lake-S with OpenVINO
2026.2.1, using isolated full-device sweeps against real images:

| Model | Intel GPU Status | Notes |
|-------|-----------------|-------|
| EU FocalNet-B | ✅ Validated | Correct finite output. Static-batch reshape required (applied automatically). |
| Small Birds EU (MobileNetV4-L) | ✅ Validated | ratio=1.03, Spearman=0.996, top5∩=5. Excellent GPU match. Probed 22 March 2026. |
| Medium Birds EU (ConvNeXt-V2-Tiny) | ✅ Validated | ratio=0.98, Spearman=0.959, top5∩=3. Smaller kernel avoids ConvNeXt Large's precision issue. Probed 22 March 2026. |
| ConvNeXt Large | ✅ Host-gated candidate | Arrow Lake-S / OpenVINO 2026.2.1: 24/24 GPU top-1 results matched CPU, mean top-5 overlap was 5/5, and median inference was about 379 ms. OpenVINO 2025.4.1 produced systematically wrong rankings on the same model, so Intel GPU is deliberately a registry candidate rather than globally safe. |
| RoPE ViT-B14 | ✅ Host-validated | Arrow Lake-S / OpenVINO 2026.2.1: GPU compiled, produced finite output on 12 real images, matched CPU top-1 on all 12, and averaged 5/5 top-5 overlap. Older Intel GPU / OpenVINO 2025.4 combinations produced NaNs, so per-host validation is required. |
| FlexiViT Global | ❌ Not supported | NaN in both f32 and f16. FlexiViT DINOv2 RMSNorm produces non-finite values. |
| Small Birds NA (EfficientNet-B0) | ❌ Not supported | Non-deterministic crash — first inference after clean state may pass (f32: ratio=0.83, Spearman=0.821), but subsequent GPU compilations crash with `CL_OUT_OF_RESOURCES`. f16 → NaN. Too unreliable for production use. |
| Medium Birds NA (Binocular) | ❌ Not supported | NaN in both f32 and f16. |
| EVA-02 Large | ❌ Fatal crash | Non-deterministic: first attempt may return NaN, second attempt crashes the process with `clWaitForEvents -14` / `CL_OUT_OF_RESOURCES`. Not a RAM issue — iGPU can address 28.7 GB with 4 GB max allocation; the 1.2 GB model fits easily. Root cause is an EVA-CLIP attention op incompatibility on this iGPU generation. Confirmed on OV 2024.6.0, 2026.0.0, and 2025.4.1. Do not use with Intel GPU. |

**Intel CPU (OpenVINO)** works correctly for all ONNX models and provides a meaningful speedup over plain ONNX Runtime CPU. It remains the safe fallback when host validation rejects an accelerator.

The `auto` provider setting uses the measured passing order for the exact model artifact, runtime
stack, image, and visible hardware. Without current evidence it stays within the model's globally
safe provider list; it does not assume that a detected GPU is numerically correct.

### Intel NPU support

The 18 July 2026 Arrow Lake-S / OpenVINO 2026.2.1 sweep validated NPU execution for RoPE ViT-B14,
ConvNeXt Large, EVA-02 Large, FlexiViT, FocalNet-B, MogaNet-S, ConvNeXt-V1 Tiny EU, RegNet-Y-8G EU,
and UniFormer-S EU. Each compiled in an isolated process, produced finite output for 12 real images,
and matched CPU top-1 on all 12. NPU was not the fastest device for most models on this host, so the
guided validation still benchmarks the available devices and selects the fastest passing provider.

MobileNet V2 remains TFLite/CPU-only. Small and Medium regional families are not given a global NPU
flag yet because the retained eligibility record is keyed by family ID rather than EU/NA artifact;
both variants need independent validation before that claim is safe.

---

## Running the Accuracy Benchmark

### Prerequisites

1. **Docker container running**: `docker compose up -d`
2. **Models installed**: Download at least one model from **Settings → Detection → Model Manager**.
3. **Fixture images**: Download iNaturalist test images (one-time setup):

```bash
python3 backend/scripts/download_test_fixtures.py
# Downloads 60 images (15 species × 4 each) to backend/tests/fixtures/bird_images/
```

Alternatively, pass `--auto_download` and the script will fetch them automatically if not already present.

The `--base_url` should point at your running YA-WAMF instance. Use `http://localhost:9852` for the monolithic deployment (host port 9852) or `http://localhost:8946` for the legacy split deployment.

### Run against the active model

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:9852 \
  --username YOUR_USERNAME --password YOUR_PASSWORD
```

If auth is disabled:
```bash
python3 backend/scripts/pipeline_api_test.py --base_url http://localhost:9852
```

### Run against all installed models

This cycles through every installed model in turn, activates it, tests it, then restores the original:

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:9852 \
  --username YOUR_USERNAME --password YOUR_PASSWORD \
  --all_models
```

With auto-download and preprocessing comparison (letterbox vs center-crop):

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:9852 \
  --username YOUR_USERNAME --password YOUR_PASSWORD \
  --all_models --preprocess compare --auto_download
```

### Save a JSON report

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:9852 \
  --all_models \
  --output report.json
```

### Test specific species only

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:9852 \
  --cases house_sparrow,blue_jay,european_robin
```

### Show per-image predictions

```bash
python3 backend/scripts/pipeline_api_test.py \
  --base_url http://localhost:9852 \
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

The Intel GPU is only accessible inside the running container, not from the host shell. Run the tests there (use `yawamf-backend` for the legacy split deployment):

```bash
docker exec yawamf-monalithic python -m pytest tests/test_model_openvino_gpu.py -v
```

#### Diagnostic probes (no pass/fail — print a results table)

Two additional probes help investigate GPU failures. They never fail; use `-s` to see the output table.

**NaN / wrong-prediction fix probe** — tries HETERO, SDPA-off, and combined strategies on every model currently failing on GPU:

```bash
docker exec yawamf-monalithic python -m pytest \
  tests/test_model_openvino_gpu.py::test_gpu_nan_fix_probe -v -s
```

**ConvNeXt Large precision probe** — tries seven compilation strategies specifically for ConvNeXt's precision-degradation failure (f16, ACCURACY hint, no-Winograd, HETERO, combinations):

```bash
docker exec yawamf-monalithic python -m pytest \
  tests/test_model_openvino_gpu.py::test_convnext_gpu_precision_probe -v -s
```

The table columns are: `GPU range`, `ratio` (GPU/CPU), `spearman` (rank correlation vs CPU), `top5 ∩` (top-5 overlap with CPU), and `result`. A strategy is considered fixed when ratio ≥ 0.5, Spearman ≥ 0.50, and top-5 ∩ ≥ 1.

Results from OV 2025.4.1 and the newer Arrow Lake-S / OV 2026.2.1 RoPE validation are documented in
the Intel GPU Support table above and in the validation matrices in
`tests/test_model_openvino_gpu.py`.

---

### NVIDIA GPU diagnostic probes

Contributors with NVIDIA GPUs can run a separate diagnostic suite that tests every installed model through ONNX Runtime's `CUDAExecutionProvider` and `TensorrtExecutionProvider`. These probes are best-effort only: they print a results table and are expected to skip cleanly on hosts without an exposed NVIDIA device.

#### Prerequisites

Use the unsuffixed full image or a `-cuda` image for these probes; the CPU,
Intel, and Raspberry Pi images deliberately omit CUDA. NVIDIA Container Toolkit
must still be installed on the host so the GPU driver/runtime is exposed inside
the container. Confirm **Settings → Detection → Runtime diagnostics** lists
`cuda` under **Packaged**, then add GPU access to your Compose file. For
`docker-compose.monolith.yml`:

```yaml
services:
  yawamf:
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
docker run --gpus all ghcr.io/jellman86/yawamf-monalithic:latest \
    python -m pytest tests/test_model_nvidia_gpu.py -v -s
```

#### Full per-model survey (all strategies)

Tests every installed ONNX model through CUDA/fp32, CUDA/fp32+exhaustive, TRT/fp32, TRT/fp16, and TRT/fp16+exhaust:

```bash
docker exec yawamf-monalithic python -m pytest \
  tests/test_model_nvidia_gpu.py::test_nvidia_gpu_full_probe -v -s
```

#### ConvNeXt Large focused probe

ConvNeXt Large was broken on the tested OpenVINO 2025.4 Intel path but passes on Quark's current
OpenVINO 2026.2.1 stack. This focused probe remains useful for NVIDIA validation and for detecting
future Intel runtime regressions:

```bash
docker exec yawamf-monalithic python -m pytest \
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
