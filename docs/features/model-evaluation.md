# Model Evaluation Harness

Owner-only diagnostic at **`/diagnostics/model-eval`** that benchmarks every installed classifier against auto-fetched, taxonomy-verified bird images and surfaces actionable accuracy / latency / config warnings.

## What it does

1. Builds a species panel: hand-curated 50-species **shared core** of common feeder birds plus a region-aware extension drawn from iNaturalist `species_counts` near the configured location (lat / lng from settings, falls back to shared core only when location is unset).
2. Fetches up to 3 taxonomy-verified images per species — **iNaturalist research-grade observations first, Wikimedia Commons fallback** when iNat returns fewer than the requested count.
3. For each installed classifier (detector models are skipped), activates the model through the live `ModelManager`, runs every fetched image through `ClassifierService.classify_async()` — the same pipeline production uses — and records the result.
4. Restores the originally-active model after the run finishes (even on failure).
5. Cleans up the image cache at the end of the run; **persistent artifacts are kept** until you delete the run from the UI.

## Where the data lives

Each run writes a directory at `/config/yawamf-eval/<run_id>/` containing:

| File | Content |
|---|---|
| `summary.json` | headline metrics + per-model breakdown (top-1/3/5 accuracy, latency, abstention, shared-core vs regional split, sanity-check warnings) |
| `runtime.json` | per-model provider / device / startup benchmark / drift factor / `InferenceHealth` snapshot |
| `confusions.csv` | top wrong→right confusions per model, ranked by frequency |
| `results.jsonl` | per-image top-5 predictions with scores and taxa_id resolution — only when **Include per-image details** is checked |
| `device_matrix.json` | image-aware classifier and crop-detector provider compile, finite-output, CPU-agreement and median inference-latency results when provider validation is enabled |

The container mount means you can pull these straight off the host:

```bash
docker exec yawamf-monalithic cat /config/yawamf-eval/<run_id>/summary.json | jq .
```

## Reading the results

### Headline accuracy

- **`top1_accuracy`** — strictest. Production threshold work usually compares against this.
- **`shared_core_top1`** — accuracy on the universal feeder species panel. This is the apples-to-apples cross-model number; if a model scores low here, look at warnings before anything else.
- **`regional_top1`** — accuracy on species observed near the configured location. EU-tuned models will look bad if the location is in North America — the harness flags this with `region_mismatch` rather than a regression.

### Latency

- **`mean_latency_ms`** / **`p95_latency_ms`** — observed inference time per image during the run.
- **`startup_benchmark_ms`** — what the model was measured at when it was first loaded (CPU baseline or accelerated).
- **`latency_drift_ratio`** = mean / startup_benchmark. A value above ~5 is unusual and surfaces as the `latency_drift_high` warning. This is the signature pattern from issue #33 (OpenVINO Intel GPU running at ~12 s/frame instead of ~600 ms).

### Warnings

| Code | What it means | What to do |
|---|---|---|
| `latency_drift_high` | measured mean > 5× the startup benchmark | suspect the accelerated provider — try toggling to CPU and rerun |
| `high_abstention` | model returned `Unknown` / `Background` on > 10% of images | check labels.txt; vocab may not include feeder species |
| `low_shared_core` | shared-core top-1 < 50% | broken install, wrong labels file, or model was trained on a non-overlapping vocabulary |
| `provider_fallback_active` | requested an accelerated provider but actually running on CPU | first check **Image** and **Packaged** under **Settings → Detection → Runtime diagnostics**, then inspect `runtime.json` for a device or model fallback reason |
| `incomplete_install` | `labels.txt` or `model_config.json` missing | use the Model Manager's repair download |
| `inference_health_unhealthy` | `InferenceHealth` verdict at run end is `unhealthy` | the runtime errored or timed out during the run; check classifier logs |
| `region_mismatch` | EU model evaluated against NA region (or vice versa) | informational — accuracy will look low but isn't a regression |

### Confusions CSV

Each row is `(expected_taxa, expected_common, predicted_taxa, predicted_common, count, mean_score)`. Sorted by frequency. Useful for spotting systematic biases — e.g. a model that consistently predicts "Purple Finch" for every "House Finch" suggests a vocabulary or training-set issue rather than a runtime problem.

## Scope and trade-offs

- Runs flat-out without yielding to live classification. A run can compete with real-time bird detections; the user-stated escape hatch is "wipe and backfill" if anything goes weird.
- Only one run at a time. Starting a second run while one is in progress returns 409 Conflict.
- Run history shows the most recent 20 runs; older runs persist on disk until manually deleted.
- Image fetch concurrency is capped at 5; iNat rate limits are the practical floor on overall wall-clock time.
- The shared-core species list is hand-maintained at `backend/app/services/eval/shared_core_species.json`. Add entries (sci name + common name) to grow coverage; `taxa_id` resolves at runtime.

## Repeatable crop-policy sweep

The feeder-specific CLI harness runs the same `ClassifierService` image-resolution path and can
compare automatic image preparation without changing saved Settings:

```bash
python backend/scripts/eval_feeder_model_harness.py \
  --manifest /config/yawamf-eval/panel/manifest.csv \
  --output-dir /config/yawamf-eval/crop-policy-eu/results \
  --models small_birds,medium_birds \
  --crop-modes on,off \
  --source-mode standard \
  --bird-model-region eu
```

Use `--bird-model-region na` for the NA variants. Crop and source overrides exist only in the harness
manager instance and are restored after every case group; `summary.json`, `results.csv`, and
`failures.csv` remain available for review. A forced crop-on run now fails if the detector cannot
load, inference fails, or no image is actually cropped, preventing a fail-soft production fallback
from becoming false benchmark evidence. The current decision rule and baseline measurements are
documented in [`../plans/2026-07-16-model-crop-policy.md`](../plans/2026-07-16-model-crop-policy.md).

## Provider compatibility and the post-install gate

The `compat_only` provider sweep writes schema-4 `device_eligibility.json` evidence containing
every provider that compiled, produced finite output, and agreed with its CPU baseline. The
registry has two layers: `supported_inference_providers` is the globally safe baseline, while
`candidate_inference_providers` is a reviewed wider set that an isolated install may probe.
Candidates are still limited to the running image/host/model intersection, covering ONNX CPU/CUDA
and OpenVINO CPU/GPU/NPU when applicable. An undeclared discovery row remains informational.

Each model result is bound to the exact registry artifact checksum and a cached runtime signature
covering image flavour, inference package versions, kernel, architecture, and visible accelerator
identity. A model replacement, runtime or kernel upgrade, image switch, or config-volume move to
different hardware therefore invalidates the accelerator proof and restores the global safe
baseline until the model is revalidated. Old schema evidence is not silently promoted.

Each compile and inference run is isolated in a child process; one model/provider failure is
retained in the matrix without aborting the rest of the run. Classifiers use up to 24 images
selected round-robin across species and compare their output ranking. Installed
crop detectors use the same real panel plus three deterministic hard negatives and compare
detection presence, top-box IoU, and confidence with CPU. Detector rows live under the separate
schema-3 `crop_detectors` key, so they cannot affect classifier scoring or setup recommendations.
Panel labels include their stable selection index because upstream downloads often reuse a generic
basename such as `image.jpg`; duplicate, missing, or unexpected comparison rows now fail closed.
Detector comparison applies the most permissive crop threshold production can admit (`0.02` for an
accurate evidence candidate), rather than comparing arbitrary near-zero raw proposals.

This record clears the **post-install selection gate** — a model cannot become active until this
host has proven at least one valid route. The Model Manager's **Validate & enable** endpoint
(`POST /api/models/{id}/validate`) uses the same provider engine for one model and restores the
previously active model after the trial. The setup wizard also requests a single-model
compatibility run; Detection Diagnostics tests installed models by default and can optionally
download and test every registry classifier and crop detector. See
[AI Models — Validate before you select](ai-models.md#validate-before-you-select-post-install-gate).
Every sweep stores the passing providers and their measured latency. `Auto` uses that per-model
order; Setup, Model Manager, and Settings display the same order and remove providers that failed
for the selected model. Activation applies the first still-eligible recommendation only after the
model switch succeeds and never carries an explicit provider from the previous model. The settings
and activation APIs enforce the same gate, so a stale client cannot select a hidden provider.
Re-running a failed sweep invalidates old evidence for that model instead of silently retaining a
previously passing result.

Maintainers auditing registry metadata can send `discover_providers: true` with an owner-only run.
Discovery tests every provider packaged by the image and exposed by the host, including providers
the model does not currently declare. The matrix marks those rows `declared: false` and reports
passing candidates under `discovered_providers`. Discovery evidence is deliberately informational:
it does not widen `device_eligibility.json`, change the activation recommendation, or let historical
host evidence override the reviewed registry contract. This makes known-risk probes such as a model
that crashes an Intel GPU safe to contain in the existing child process.

For a complete metadata audit on the Intel image, use:

```json
{
  "sweep_devices": true,
  "compat_only": true,
  "sweep_all_models": true,
  "discover_providers": true
}
```

The hardware sweep validates runtime compatibility, not classifier image-selection accuracy. Crop
policy is evaluated separately with the feeder harness. Distant-bird validation must retain each
full frame and compare it with timestamp-distinct Frigate-hint and detector crops; multiple crops of
one frame are one vote, and a confident crop consensus is not ground truth without an owner-labelled
field set. This preserves the fail-soft full-frame path while still measuring whether localization
helps small, distant subjects.

For a private, repeatable detector-quality panel, build same-frame references from persisted HQ
candidates rather than applying an event's final box to a different video frame:

```bash
python backend/scripts/build_crop_field_manifest.py \
  --database /data/speciesid.db \
  --snapshot-dir /config/media_cache/snapshots \
  --output-dir /config/yawamf-eval/crop-detector-field

python backend/scripts/eval_crop_detector_accuracy.py \
  --manifest /config/yawamf-eval/crop-detector-field/manifest.json \
  --output-json /config/yawamf-eval/crop-detector-field/results.json
```

The builder selects one independent event per visit, round-robins apparent distance and recorded
species, and uses only a Frigate hint persisted for the exact same frame. It also creates real
feeder/foliage regions that do not intersect the known hint box. Those are useful hard negatives,
but are explicitly not claims that the entire source frame contained no other bird. The evaluator
reports positive recall separately from negative false-positive/specificity rates and groups results
by manifest tag. Camera images and generated negatives stay in the private config volume.

The schema-3 manifest also records the exact frame index, Frigate crop/classifier baseline, and
label provenance. Only manual owner identities populate `expected_labels`; automatically inferred
labels remain useful panel context but cannot become promotion evidence. Run the end-to-end
challenger after changing crop geometry or selection policy:

```bash
python backend/scripts/eval_crop_strategy_challenger.py \
  --manifest /config/yawamf-eval/crop-detector-field/manifest.json \
  --output /config/yawamf-eval/crop-detector-field/challenger-results.json
```

This classifies the unchanged full frame, same-frame Frigate crop, and optimized model crop through
the active classifier with further crop resolution disabled. YOLOX first receives a square
Frigate-guided HQ region; without a hint it uses native full-frame inference and only then a bounded
2×2, 20%-overlapping slice fallback on large images. Results retain `native`, `frigate_guided`,
`sliced_2x2`, or `fast_native` provenance. A model win requires it alone to be correct, or both
representations to be correct with at least a two-point classifier-score gain. Unlabelled cases and
hard negatives are reported separately rather than inflating win/tie/loss counts. The evaluator
fails closed on stale schemas, duplicate cases or positive visits, ambiguous multi-box rows, and
promotion labels without owner-manual provenance; its summary also records detector p50/p95/max
latency so an accuracy win cannot hide an impractical runtime cost. A second guarded summary mirrors
production selection: the model crop replaces Frigate only for the same classifier identity with
the required score gain. It records model promotions, Frigate retentions, blocked reasons, and
owner-labelled guarded outcomes. Hard negatives report both raw detector candidates and candidates
whose classifier score reaches the active minimum. The result captures the image flavour plus
classifier and crop-detector model/provider provenance, making CPU/GPU/NPU runs directly auditable.

### External candidate screening

Maintainers can screen an exported candidate without adding it to the model registry or making it
downloadable. The probe implements the official D-FINE-N and DEIMv2-N deployment contract and runs
one provider per process so a compiler failure cannot be mistaken for a passing fallback:

```bash
python backend/scripts/probe_crop_candidate.py \
  --candidate deimv2_n_coco \
  --model /config/yawamf-eval/candidates/deimv2_n_coco.onnx \
  --manifest /config/yawamf-eval/crop-detector-field/manifest.json \
  --provider intel_gpu \
  --output-json /config/yawamf-eval/candidates/deimv2-intel-gpu.json
```

Run CPU first, then each packaged/provider-visible accelerator in a disposable subprocess and retain
non-zero exits as failures. The JSON records the artifact checksum and input contract, compile time,
median/p95 preprocessing and inference time, per-case boxes/scores, threshold curves, IoU recall,
and real-negative false-positive rate. Recall scores the highest-confidence bird box that runtime
selection would use; any-candidate IoU is retained separately for selection-policy diagnosis. A
passing provider comparison proves only that the artifact
executes consistently; promotion still requires manually labelled visit-level downstream species
results against Frigate. Candidate weights and private camera results must not be committed or
uploaded to a release while provenance or redistribution terms remain unconfirmed.

Both `summary.json` and `device_matrix.json` contain compatibility-only results. The latter is
available through `GET /api/diagnostics/model-eval/runs/{run_id}/{artifact}` with `artifact` set to
`device_matrix.json`; older runs that used `devices` remain readable while new matrices also expose
provider-native `providers` fields.

## Related files

- Backend service: `backend/app/services/model_eval_service.py`
- Selection gate + validate probe: `backend/app/services/model_validation.py`
- Image fetch + species panel: `backend/app/services/eval/`
- Sanity checks: `backend/app/services/eval/sanity_checks.py`
- HTTP router: `backend/app/routers/model_eval.py`
- Release-sidecar generator: `backend/scripts/generate_model_release_configs.py`
- Crop provider probe: `backend/scripts/probe_crop_model_provider.py`
- Private crop field-panel builder: `backend/scripts/build_crop_field_manifest.py`
- Crop detector quality evaluator: `backend/scripts/eval_crop_detector_accuracy.py`
- External crop-candidate probe: `backend/scripts/probe_crop_candidate.py`
- End-to-end Frigate challenger: `backend/scripts/eval_crop_strategy_challenger.py`
- Frontend page: `apps/ui/src/lib/pages/ModelEvaluation.svelte`
- Design doc: `docs/plans/2026-05-07-model-evaluation-harness-design.md`
