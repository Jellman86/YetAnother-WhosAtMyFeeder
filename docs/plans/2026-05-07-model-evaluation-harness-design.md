# Model Evaluation Harness — Design

**Date:** 2026-05-07
**Status:** Approved, implementation in progress
**Scope:** New owner-only diagnostic that benchmarks every installed classifier against auto-fetched, taxonomy-verified bird images and surfaces accuracy / latency / config-error signals.

## Goals

- Test all installed classifier models in a single run, finishing in ~30 minutes on the production container.
- Auto-source labeled images at run time; clean up image cache after the run completes.
- Exercise the live `ClassifierService` pipeline so the eval reflects what users actually experience.
- Persist results as files in a mounted volume so artifacts can be retrieved with `docker exec` after the UI is closed.
- Surface concrete, actionable diagnostics: provider misconfig, latency drift, broken installs, vocab mismatches.
- Owner-initiated via a dedicated UI page; no scheduled or unattended runs.

## Non-goals

- A/B comparison view between two runs.
- "Promote model to default" action from the UI — this is a measurement tool only.
- Replacing the existing feeder harness. Feeder harness still owns "is the production pipeline correct against real feeder snapshots?"; this harness owns "are the models themselves healthy?"
- PDF export, recurring evals, per-image preview thumbnails in the UI.

## Architecture

```
[UI: /diagnostics/model-eval]
        │  POST /api/diagnostics/model-eval/runs
        ▼
[ModelEvalService — background task]
        │
        ├── 1. Build species panel
        │     ├─ Shared core (~50 common feeder species, hand-curated taxa_ids in repo)
        │     └─ Region extension (~150 species from eBird regional list, fallback iNat)
        │
        ├── 2. Fetch images (≤3 per species)
        │     ├─ iNaturalist research-grade observations (primary)
        │     └─ Wikimedia Commons (fallback when iNat returns < N)
        │     Cache: /config/yawamf-eval/<run_id>/images/<taxa_id>/*.jpg
        │
        ├── 3. For each installed classifier model:
        │     ├─ Activate via ModelManager (live code path)
        │     ├─ For each image: ClassifierService.classify() — production pipeline
        │     ├─ Compare predicted taxa_id vs ground-truth taxa_id
        │     └─ Restore original active model after run (even on failure)
        │
        ├── 4. Write artifacts to /config/yawamf-eval/<run_id>/
        │     ├─ summary.json     headline + per-model breakdown
        │     ├─ results.jsonl    per-image top-5 (opt-in)
        │     ├─ confusions.csv   wrong→right pairs per model
        │     └─ runtime.json     provider / benchmark / InferenceHealth
        │
        └── 5. Delete /config/yawamf-eval/<run_id>/images/
                Persistent artifacts kept until user deletes the run from UI.

[UI ← SSE progress channel]
```

## Components

### Backend (new)

- `backend/app/services/eval/image_fetcher.py` — iNat + Wikimedia client with on-disk cache, dedup, retry/backoff.
- `backend/app/services/eval/species_panel.py` — builds the species panel (shared core + regional extension).
- `backend/app/services/eval/shared_core_species.json` — hand-curated 50 common feeder species with `taxa_id`, `scientific_name`, `common_name`.
- `backend/app/services/eval/sanity_checks.py` — pure functions producing warnings from per-model results.
- `backend/app/services/model_eval_service.py` — orchestrator and background task.
- `backend/app/routers/diagnostics.py` — `POST /runs`, `GET /runs`, `GET /runs/<id>`, artifact downloads, `DELETE /runs/<id>`.

### Backend (reused)

`ClassifierService`, `ModelManager`, `TaxonomyService`, `EbirdClient`, `InferenceHealth`, `Broadcaster`, `create_background_task`.

### Frontend (new)

- `apps/ui/src/lib/pages/ModelEvaluation.svelte` mounted at `/diagnostics/model-eval`.
- API client additions in `apps/ui/src/lib/api.ts`.
- Owner-only auth guard.

## Data contracts

### `summary.json`

```json
{
  "run_id": "20260507-204512",
  "started_at": "...",
  "finished_at": "...",
  "duration_seconds": 1676,
  "test_set": {
    "shared_core_species": 50,
    "regional_species": 142,
    "total_species": 192,
    "images_per_species": 3,
    "total_images": 561,
    "region": "US-CA",
    "image_sources": { "inat": 489, "wikimedia": 72 }
  },
  "models": [
    {
      "model_id": "eva02_large_inat21",
      "active_provider": "OpenVINOExecutionProvider",
      "device": "Intel iGPU",
      "top1_accuracy": 0.78,
      "top3_accuracy": 0.91,
      "top5_accuracy": 0.94,
      "abstention_rate": 0.02,
      "high_confidence_unknown_rate": 0.005,
      "mean_latency_ms": 312,
      "p50_latency_ms": 285,
      "p95_latency_ms": 540,
      "startup_benchmark_ms": 290,
      "latency_drift_ratio": 1.08,
      "shared_core_top1": 0.86,
      "regional_top1": 0.75,
      "warnings": []
    }
  ],
  "config_snapshot": {
    "min_confidence": 0.65,
    "trust_frigate_sublabel": false,
    "personalized_rerank_enabled": true,
    "crop_mode": "default"
  }
}
```

### `results.jsonl` (opt-in)

One line per `(model, image)`:
```json
{"model_id":"eva02_large_inat21","taxa_id":13858,"expected_common":"House Finch","image_url":"...","image_source":"inat","top5":[...],"latency_ms":284,"crop_used":true,"crop_score":0.87,"correct":true}
```

### `confusions.csv`
```
model_id,expected_taxa,expected_common,predicted_taxa,predicted_common,count,mean_score
```

### `runtime.json`

Per-model: `active_provider`, `fallback_provider`, `startup_benchmark_ms`, `measured_mean_ms`, `measured_p95_ms`, `drift_factor`, `inference_health_verdict`, `inference_health_recent_failures`, `labels_count`, `labels_file_present`, `model_config_present`, `ready`, `warnings`.

## Sanity-check warnings

Computed by `sanity_checks.py` and attached to `summary.json/models[].warnings`:

| Code | Trigger |
|---|---|
| `latency_drift_high` | measured mean > 5× startup benchmark |
| `high_abstention` | abstention rate > 10% |
| `low_shared_core` | shared-core top-1 < 50% |
| `provider_fallback_active` | running on CPU when accelerated provider was configured |
| `incomplete_install` | missing `labels.txt` or `model_config.json` |
| `inference_health_unhealthy` | `InferenceHealth` verdict at run end is `unhealthy` |
| `region_mismatch` | EU model evaluated against NA region (or vice versa); informational |

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/diagnostics/model-eval/runs` | Start run. Body: `{ include_per_image?: bool, region_override?: str }` |
| `GET` | `/api/diagnostics/model-eval/runs` | List recent runs (last 20) |
| `GET` | `/api/diagnostics/model-eval/runs/{run_id}` | Full summary + runtime |
| `GET` | `/api/diagnostics/model-eval/runs/{run_id}/results.jsonl` | Per-image artifact (if generated) |
| `GET` | `/api/diagnostics/model-eval/runs/{run_id}/confusions.csv` | Confusion pairs |
| `DELETE` | `/api/diagnostics/model-eval/runs/{run_id}` | Delete run dir |

Owner-only on every endpoint.

Progress streamed through the existing `Broadcaster` SSE channel under event type `model_eval_progress`.

## Behavior

- **Run isolation:** one run at a time. `POST /runs` returns 409 if a run is in progress.
- **Pipeline used:** live `ClassifierService` against the activated model, exactly as user-facing classification works. No bypass, no offline path.
- **Pressure handling:** none — runs flat-out. User trade-off accepted: live classification may queue while eval is running. User can wipe and backfill if needed.
- **Image cache cleanup:** images deleted at run end (success or failure). Persistent artifact files retained.
- **Active model restore:** wrapped in `try/finally` — original active model is restored even if the run aborts.
- **Run history:** last 20 runs visible in UI, individually deletable. No automatic eviction.

## Implementation phases

1. **Image fetcher + species panel** — no UI, no eval. Mocked-network tests.
2. **Evaluation engine + router** — backend complete, validated via `curl`.
3. **Frontend page** — UI + SSE progress + Playwright smoke.
4. **Polish & docs** — CHANGELOG, ROADMAP, `agents/` index, interpretation doc.

Phases ship independently. Each commits cleanly; UI gates on backend.

## Open risks

- iNat rate limiting for ~600 images may push wall-clock time. Mitigation: parallel image fetch (capped concurrency), Wikimedia fallback, per-species early-out at 3 images.
- 30-min budget is target, not contract. First real run determines whether 192 × 3 × 9 fits. If it overruns, cut images-per-species first, regional species second.
- Model activation cost is non-trivial for some models (EVA-02). Activating 9 models sequentially adds overhead beyond inference time. Acceptable; this is what "exercise the live pathway" buys us.
