# Model Accuracy & Benchmark Results

See [October 2026 classifier additions](model-catalogue-2026-10.md) for the new experimental
models, their input contracts, sizes and catalogue integration. The historical tables below
retain their original benchmark scope.

This explanation records dated benchmark panels and the production evidence rules. It does not
rank every current model on one common test set. For current installation-specific hardware
measurements use [Model Evaluation](model-evaluation.md); for October public and retained-feeder
comparisons use the [integration validation report](../reviews/2026-10-10-model-integration-validation.md).
Compatibility results measure agreement with CPU, not agreement with the true bird species.

---

## Benchmark Results

Results are measured against 60 labeled bird images drawn from iNaturalist (15 species × 4 images each). Images cover both North American and European feeder birds, plus common rejection cases (out-of-scope birds that should still be classified but at lower confidence).

Each run tests two preprocessing modes — **raw** (image sent as-is) and **letterbox** (padded to a square with gray borders) — to identify whether padding helps or hurts each model.

> **Note on scope mismatch:** The birds-only models are not directly comparable to the wildlife-wide models on this mixed fixture set. `Small Birds` and `Medium Birds` resolve to regional variants, the published benchmark rows here use the EU variants, `EU FocalNet-B` is European-only, and `FlexiViT Israel Birds` covers a smaller 550-class Israel-checklist bird label space. Lower scores here often reflect out-of-scope input in the fixture set, not a real-world failure on their intended deployment.

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
| **FlexiViT Israel Birds** | small | birds_only (Israel checklist) | 33.3% | 31.7% | 40.0% | 38.3% | 199ms | intel_cpu |
| **Bird Crop Detector (Fast)** | fast | system | n/a | n/a | n/a | n/a | 5ms | cpu |
| **Bird Crop Detector Accurate (YOLOX-Tiny)** | accurate | system | n/a | n/a | n/a | n/a | 11–30ms provider sweep | host-validated |

> **Birds-only model note:** `Small Birds` and `Medium Birds` are region-resolved family entries, `EU FocalNet-B` is Europe-specific, and `FlexiViT Israel Birds` trades coverage and size for speed. The shared fixture set is still weighted toward North American species, so these rows should be read as scope-mismatch diagnostics rather than direct leaderboard entries against the wildlife-wide models.

> **Intel GPU support:** Support depends on the Intel generation and OpenVINO runtime. RoPE ViT-B14
> is validated on Arrow Lake-S with OpenVINO 2026.2.1, while older Intel GPU / OpenVINO 2025.4
> combinations produced NaNs. YA-WAMF's post-install device validation is the authority for a
> particular host. See the Intel GPU Support table below.

### What the March panel showed

- **EVA-02 Large** achieved the highest top-1 accuracy in this March panel (68.3% raw) but is slow (~1.6s) and requires ~3GB RAM.
- **RoPE ViT-B14** remains the configured default. This panel measured 63.3% top-1 / 80.0% top-5 at 493ms; that result does not establish a universal best model. Letterboxing gives a marginal top-1 gain (+1.7%) at the cost of top-5 (−5.0%).
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

The MogaNet-S EU, ConvNeXt-V1 Tiny EU, RegNet-Y-8G EU, and UniFormer-S EU rows are retained as
historical evidence from the full comparison. Those models are no longer present in the current
application catalogue; their pre-3.0 release assets remain temporarily available for older
applications.

| Model or variant | Crop on top-1 / top-3 | Full frame top-1 / top-3 | Automatic policy |
|---|---:|---:|---|
| MobileNet V2 | 54.86 / 66.67 | 50.00 / 60.42 | **Crop on** |
| Small Birds NA | 27.78 / 34.72 | 23.61 / 34.03 | **Crop on** |
| Medium Birds NA | 33.33 / 45.14 | 31.25 / 39.58 | **Crop on** |
| FlexiViT Israel Birds | 19.44 / 21.53 | 17.36 / 20.14 | **Crop on** |
| Small Birds EU | 25.69 / 28.47 | 25.69 / 29.86 | Full frame |
| Medium Birds EU | 27.08 / 31.25 | 27.78 / 33.33 | Full frame |
| ConvNeXt Large | 63.19 / 71.53 | 68.75 / 76.39 | Full frame |
| FocalNet-B EU | 36.81 / 40.28 | 38.19 / 41.67 | Full frame |
| RoPE ViT-B14 | 62.50 / 71.53 | 67.36 / 75.00 | Full frame |
| EVA-02 Large | 68.06 / 77.78 | 67.36 / 79.86 | Full frame |
| MogaNet-S EU (retired) | 27.78 / 31.94 | 27.78 / 34.72 | Full frame |
| ConvNeXt-V1 Tiny EU (retired) | 27.78 / 32.64 | 29.17 / 35.42 | Full frame |
| RegNet-Y-8G EU (retired) | 25.69 / 29.86 | 26.39 / 33.33 | Full frame |
| UniFormer-S EU (retired) | 28.47 / 31.94 | 27.08 / 34.03 | Full frame |

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

Saved photographs carry source metadata. Genuine small generated crops remain usable instead
of being discarded as legacy thumbnails. Regular Frigate JPEGs fetched by the photo proxy have
unverified framing: ended-event crop queries may be ignored, and the camera may crop or resize
its saved image. Reclassification does not reapply full-frame coordinates to those JPEGs.
If Frigate has expired an event or cannot refresh an ambiguous legacy image, the retained image
stays available. Turning off future HQ scanning keeps existing photographs and owner selections.

HQ selection now treats Frigate's completed-event best frame as a protected baseline instead of
assuming that a sampled recording frame is automatically better. At Frigate `end`, YA-WAMF fetches
the full-resolution clean copy, applies the box tied to Frigate's selected snapshot (falling back
to the final track box for older payloads), and scores the clean full frame and
crop alongside independent video frames. A recording-derived candidate must predict a compatible
identity and improve classifier confidence by at least `0.02` before it can replace that baseline.
Both final Frigate candidates remain in the bounded audit set even when video wins.
The final still can also complete the HQ replacement by itself when all clip sources are absent.

When a sampled frame or Frigate's clean completed still contains more than one bird, the HQ
snapshot path scores up to three distinct detector crops in Standard mode, or eight in Intensive
mode. Intensive also searches overlapping tiles in large high-resolution frames. It compares
their classifications with the tracked visit's existing identity before choosing a stored
photograph. The detection and review views show spatially distinct crops as separate photo choices,
each with its own tentative model read; choosing a photo does not change the visit's species.
Every scored crop from the completed still is kept in the bounded review list, even when another
bird's crop scored higher.
These crops remain candidates for one Frigate event, not separate visits, and several crops from
one frame still count as one temporal observation. If only Frigate's regular, possibly pre-cropped
snapshot is available, it needs a matching classification before it can replace the current
photograph. Counts use every usable detector box, independently of the classified photo-choice
limit, in the scene with the most birds. They estimate birds in analyzed captures, not unique
individuals across a visit or day. A low-confidence species is kept as Unknown Bird.

Automatic portraits require usable image detail, matching species evidence and, for detector
crops, at least 0.08 localization confidence. A matching portrait with species confidence at least
0.65 may be preferred when within 0.05 of the whole scene. This avoids leaving an old, contradictory
portrait simply because the new correct scene is uncropped. An owner-selected photo is preserved
through later automatic updates; explicit regeneration releases that choice.

The same correction fixes time-aligned event crops: Frigate `path_data` coordinates describe each
tracked box's **bottom-centre**, not its geometric centre. YA-WAMF now reconstructs the box with
`left = path_x - width / 2` and `top = path_y - height`, and compares path samples with the final
box's bottom-centre when choosing frames. Final-still candidates do not count as an independent
video moment for multi-frame species refinement, preventing one visual frame from voting twice.

### Video consensus and safe abstention (1 August 2026)

Video reclassification samples unique frames with a deterministic centre-weighted distribution.
Event clips favour the centre more strongly; complete recording/full-visit clips retain broader
edge coverage. Rounding collisions are repaired beside their intended timestamp, so they cannot
silently turn into adjacent frames at the beginning of the clip.

Each representation is evaluated independently: unchanged full frame, Frigate-guided crop, and
detector-generated crop. Low-confidence predictions prove that a representation was evaluated but
do not vote against a fleeting subject; a missing dynamic crop is not an evaluated crop. Samples
less than 250 ms apart are correlated and collapse into one moment, retaining the strongest
observation. A source needs three independent evaluated moments before it can win, but it does not
need to occupy a fixed percentage of a long clip. Within an eligible source, one exact class needs
at least two votes and 60% of that source's **confident** votes. Its aggregate score is the median of
up to the five strongest independent supporting moments. If independently trustworthy sources
select different species, YA-WAMF abstains instead of choosing the most confident transformation.

This is a sparse multiple-instance decision rather than majority voting over every decoded frame:
brief recurring evidence should survive a long visit containing empty frames, while near-duplicate
decodes must not manufacture support. The design follows the sparse-evidence motivation in
[attention-based multiple-instance learning](https://proceedings.mlr.press/v80/ilse18a.html) and
[sparse temporal pooling](https://openaccess.thecvf.com/content_cvpr_2018/html/Nguyen_Weakly_Supervised_Action_CVPR_2018_paper.html).
YA-WAMF deliberately does not call raw model scores calibrated probabilities. The model's reviewed
admission floor and the user's configured promotion threshold remain safety gates; probability
calibration and formal risk/coverage selection require a representative labelled clip set, as
described by [Guo et al.](https://proceedings.mlr.press/v70/guo17a.html) and
[Geifman and El-Yaniv](https://papers.nips.cc/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html).

Frigate `path_data` guides precise video crops only when the first frame's absolute timestamp is
known. The event's start time alone cannot establish that timestamp because event clips include
pre-capture footage. Video classification and HQ scanning withhold exact path crops and
path-targeted frame indices when the clip origin is unknown. Retained recording metadata can
supply a trustworthy origin; stale path points more than 0.75 seconds away remain unusable.

The tracked region, extended to cover observed path positions, also bounds primary video evidence.
An old label alone cannot select a distant bird outside that region.
Native crops need at least half their area inside that region; the broader region itself is
scored as another input. Confidence and independent-frame requirements remain unchanged. Bird
counts and alternate HQ photo choices still inspect the whole scene. Retained event hints can
supply this spatial context after Frigate deletes its event; no clip start is inferred from them.
Only normalized hints can guide video when the original detect-stream resolution is unknown.
MQTT pixel corners are not scaled using recording dimensions. Conflicting confident region and
current-target evidence abstains instead of reinforcing an old identity.

Reclassification finishes photo work before reporting completion. The previous photograph is
retained as a separate choice before video or HQ work replaces it, even if Frigate has removed
its copy. The retained still has no inferred clip timestamp. Photo-update outcomes appear in
completion events and structured logs. Owner, identity, storage and failure outcomes also enter
diagnostics; routine replacements and matching photographs do not. A kept photo can be
distinguished from extraction or storage failure without filling the warning history with
successful work.

Open records, review windows, cards and previews reread their photographs after the run settles,
including when the accepted species did not change. They keep existing choices visible while
rereading, and retry a failed image when a later photograph has been saved. Progress ticks do
not refresh media. Earlier photographs are separate photo options, with no claimed clip timing
or individual classifier read.

The photo strip offers controls at either end that has more choices, native touch scrolling,
and Left/Right/Home/End keyboard movement. It brings an offscreen chosen photo into view. Escape
closes the comparison before the record and returns focus appropriately. **Needs your call**
uses the record's dialog styling, fills the phone screen and keeps its decision controls within
reach as the species list scrolls.

When no source clears the policy, YA-WAMF stores a bounded diagnostic summary on the detection:
decoded frames, independent moments, confident votes, the support required for each source, up to
three confident candidates, and separate all-score observation context. **Detection details → Show
technical details** presents the voting evidence. The summary explains the decision; it never
promotes a rejected candidate or replaces the raw media needed for later reclassification.

Manual reclassification uses the same safety and configured confidence rules; choosing **Score again**
does not bypass the promotion threshold. A video abstention or below-threshold candidate triggers
the best retained snapshot before the run finishes. Its progress view ends with one explicit
outcome: a new identification, **Identification unchanged** when both routes abstain, or a technical
failure with its reason. An unchanged result includes the confident-frame count, leading-species
support, and matching requirement, then keeps the previous identification intact. The detection
details notice remains visible after the progress view closes, with the full per-source evidence
available under **Show technical details**.

---

## Intel GPU Support

The original matrix was tested on OpenVINO 2025.4.1 with an Intel integrated GPU. The complete
matrix was revalidated on 28 July 2026 on Arrow Lake-S with OpenVINO 2026.2.1, using the isolated
schema-4 sweep against 24 real images per classifier:

| Model | Intel GPU Status | Notes |
|-------|-----------------|-------|
| EU FocalNet-B | ✅ Validated | 24/24 top-1 matched CPU, 5/5 mean top-5 overlap, 146.6 ms. |
| Small Birds EU (MobileNetV4-L) | ✅ Host-gated candidate | Two explicit EU runs matched CPU top-1 on 24/24 images with 5/5 mean top-5 overlap; the latest measured 25.3 ms. An older shared-context run failed, so the isolated exact-installation gate remains required. |
| Medium Birds EU (ConvNeXt-V2-Tiny) | ✅ Validated | The explicit EU run matched CPU top-1 on 24/24 images with 5/5 mean top-5 overlap at 36.1 ms. |
| MogaNet-S EU (retired) | Historical pass | 24/24 top-1 matched CPU, 5/5 mean top-5 overlap, 72.2 ms. Retained as retirement evidence, not a current option. |
| FlexiViT Israel Birds | ✅ Host-gated candidate | 24/24 top-1 matched CPU, 5/5 mean top-5 overlap, 71.1 ms. Older OpenVINO runs produced non-finite output. |
| ConvNeXt Large | ✅ Host-gated candidate | 24/24 GPU top-1 results matched CPU, mean top-5 overlap was 5/5, and median inference was 355.8 ms. OpenVINO 2025.4.1 produced systematically wrong rankings, so Intel GPU is a candidate rather than globally safe. |
| RoPE ViT-B14 | ✅ Host-gated candidate | 24/24 top-1 matched CPU, 5/5 mean top-5 overlap, 310.8 ms. Older Intel GPU / OpenVINO 2025.4 combinations produced NaNs, so per-host validation remains required. |
| ConvNeXt-V1 Tiny EU (retired) | Historical pass | 24/24 top-1 matched CPU, 5/5 mean top-5 overlap, 57.8 ms. Retained as retirement evidence, not a current option. |
| RegNet-Y-8G EU (retired) | Historical pass | 24/24 top-1 matched CPU, 5/5 mean top-5 overlap, 73.0 ms. Retained as retirement evidence, not a current option. |
| UniFormer-S EU (retired) | Historical pass | Finite output, 24/24 top-1 matched CPU, 5/5 mean top-5 overlap, 49.8 ms. Retained as retirement evidence, not a current option. |
| EVA-02 Large | ✅ Host-gated candidate | The isolated current-runtime sweep completed 24/24 images with exact CPU top-1 and 5/5 top-5 overlap at 692.3 ms. OpenVINO 2024.6.0 through 2025.4.1 could abort with `CL_OUT_OF_RESOURCES`, so it is never globally enabled. |
| Small Birds NA (EfficientNet-B0) | ✅ Host-gated candidate | The post-deploy NA run matched CPU top-1 on 24/24 images at 5.4 ms, but historical runs crashed or produced non-finite output. It is never assumed safe and must pass on the exact artifact and installation. |
| Medium Birds NA (Binocular) | ✅ Host-gated candidate | The post-deploy NA run matched CPU top-1 on 24/24 images with 5/5 mean top-5 overlap at 96.6 ms. Older runs produced non-finite output, so exact-installation validation remains mandatory. |

**Intel CPU (OpenVINO)** is a declared route for the registered ONNX models. Its correctness and
speed still depend on the exact model and installation; it is not guaranteed to outperform ONNX
Runtime CPU. Follow the current passing order rather than the device's name.

The 10 October 2026 Quark compatibility run rejected **Medium Birds** on Intel GPU for non-finite
output, despite the dated pass above. The gate excluded that path. EVA-02's isolated host pass also
does not resolve the reporter's sustained Intel GPU/backfill failure in
[issue #490](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/490). Keep the exact
runtime, artifact and test workload alongside any claimed hardware result.

The `auto` provider setting uses the measured passing order for the exact model artifact, runtime
stack, image, and visible hardware. Without current evidence it stays within the model's globally
safe provider list; it does not assume that a detected GPU is numerically correct.

### Intel NPU support

The 28 July 2026 Arrow Lake-S / OpenVINO 2026.2.1 sweeps validated current NPU execution for RoPE
ViT-B14, ConvNeXt Large, EVA-02 Large, FlexiViT, FocalNet-B, Small Birds EU, and Medium Birds NA.
Each compiled in an isolated process, produced finite output for 24 real images, and matched CPU
top-1 on all 24. Small Birds EU repeated that result in two explicit regional runs and is a
host-gated candidate; Medium Birds NA also remains host-gated because older runtime evidence
conflicted. MogaNet-S, ConvNeXt-V1 Tiny EU, RegNet-Y-8G EU, and UniFormer-S also passed that
historical sweep but have since been retired from the application catalogue.

MobileNet V2 remains TFLite/CPU-only. Medium Birds EU's NPU output disagreed on one of 24 top-1
results, and Small Birds NA disagreed in an earlier run despite passing the post-deploy panel, so
NPU remains excluded for both artifacts. NPU was not the fastest device for every model; the guided
validation therefore benchmarks the current installation and selects the fastest passing provider
rather than preferring an accelerator by name.

---

## Running the Accuracy Benchmark

### Prerequisites

1. **Docker container running**: `docker compose up -d`
2. **Models installed**: Download at least one model from **Settings → Detection → Model Manager**.
3. **Fixture images**: Download iNaturalist test images (one-time setup):

```bash
python3 backend/scripts/download_test_fixtures.py --count 4
# Requests up to 60 images (15 species × 4 each) to backend/tests/fixtures/bird_images/
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

This cycles through every installed model in turn, activates it, tests it, then restores the original.

Let the run finish before choosing a different operating model. The diagnostic temporarily
changes the active model and restores the selection it started with, so a model selected during
the run may be replaced. Location-aware models use the saved location during normal in-app
diagnostics; record whether location was present when comparing separate benchmark results.

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

## Validate installed hardware safely

Use the in-app compatibility check for normal setup. For a maintainer's independent check, use
the isolated, fail-closed [installed-model gate](../development/testing.md#mandatory-local-modelprovider-gate).
It uses production preprocessing and read-only weights, keeps configuration and databases in
scratch space, and does not change the application's active model or provider eligibility.

For example, with an Intel image, an installed DINOv2 model and retained images already inside the
container:

```bash
docker exec -w /app -e PYTHONPATH=/app yawamf-monalithic \
  python scripts/run_model_hardware_gate.py \
  --models-dir /data/models \
  --output /config/yawamf-eval/local-dino-hardware-check \
  --model dinov2_b14_inat21_metadata_336 \
  --provider intel_npu --repeat 2 \
  --image /config/retained-bird-1.jpg \
  --image /config/retained-bird-2.jpg
```

Replace the image paths with existing retained inputs and use a new output directory. Add a
representative panel rather than treating two example images as sufficient evidence. Request only
providers packaged by your image and exposed to it; use `--provider cuda` on an appropriately
configured NVIDIA host. CPU is always the comparison baseline. This isolated recipe does not
inherit the running app's saved feeder coordinates, so record location absent for a DINOv2 check.
Use normal in-app diagnostics when comparing its saved-location path.

Every requested model/provider/repeat gets a disposable child process and bounded deadline.
Missing inputs, crashes, timeouts, non-finite output, incomplete coverage and CPU disagreement fail
the command. A skipped hardware test is not a passing device check. Keep runs serial on a live
feeder and retain the exact artifact, image, runtime and device evidence with the result.

The source checkout also contains model smoke/integration tests and exploratory Intel/NVIDIA
pytest probes. Published images do not include the test suite. Run source tests in a prepared
`.venv`; filter parametrised cases with `-k`, not a `--model` pytest option. Legacy hardware probes
require `YAWAMF_LEGACY_HARDWARE_DIAGNOSTICS=1`, can crash their pytest process and are not release
or provider-selection gates. See [development testing](../development/testing.md) for the current
commands and safeguards.

## Test Fixture Details

The March benchmark requested four photos for each of 15 species. The current downloader defaults
to three per species; use `--count 4` to request the original panel size. Downloads retain verified
source provenance and may return fewer usable images. The current species and taxon IDs below
come from `backend/tests/fixtures/bird_image_manifest.json`; changing or refreshing inputs means
you must report a new panel rather than presenting the historical score as reproduced.

| Species | Common name | Scope | iNaturalist taxon ID |
| --- | --- | --- | --- |
| Cardinalis cardinalis | Northern Cardinal | NA | 9083 |
| Cyanocitta cristata | Blue Jay | NA | 8229 |
| Turdus migratorius | American Robin | NA | 12727 |
| Haemorhous mexicanus | House Finch | NA | 199840 |
| Spinus tristis | American Goldfinch | NA | 145310 |
| Dryobates pubescens | Downy Woodpecker | NA | 792988 |
| Erithacus rubecula | European Robin | EU | 13094 |
| Parus major | Great Tit | EU | 203153 |
| Cyanistes caeruleus | Blue Tit | EU | 144849 |
| Fringilla coelebs | Chaffinch | EU | 10070 |
| Turdus merula | Eurasian Blackbird | EU | 12716 |
| Passer domesticus | House Sparrow | NA / EU / GLOBAL | 13858 |
| Hirundo rustica | Barn Swallow | NA / EU / GLOBAL | 11901 |
| Anas platyrhynchos | Mallard | NA / EU / GLOBAL | 6930 |
| Columba livia | Rock Pigeon | NA / EU / GLOBAL | 3017 |

Images are downloaded once and cached in `backend/tests/fixtures/bird_images/`. Use `--force` only when deliberately refreshing them; keep the previous inputs and provenance if you need a repeatable comparison.

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

Then run `download_test_fixtures.py --count 4` to request four images for the new species, and review their labels before scoring.
