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
| `provider_fallback_active` | requested an accelerated provider but actually running on CPU | the provider library is missing or refused to load — see `runtime.json` for the fallback reason |
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

## Related files

- Backend service: `backend/app/services/model_eval_service.py`
- Image fetch + species panel: `backend/app/services/eval/`
- Sanity checks: `backend/app/services/eval/sanity_checks.py`
- HTTP router: `backend/app/routers/model_eval.py`
- Frontend page: `apps/ui/src/lib/pages/ModelEvaluation.svelte`
- Design doc: `docs/plans/2026-05-07-model-evaluation-harness-design.md`
