# Backfill and classifier test hardening

## Scope and findings

This pass strengthens detection and weather backfill tests beyond mocked database writes.
Each integration case starts from the production Alembic migrations and uses the real
detection repository. Only external media, inference, taxonomy and reporting are substituted.

The tests reproduced and corrected four defects:

- Classifier scores above one could enter history; negative scores could enter through a
  direct save. Both filtering and persistence now enforce finite probabilities within 0–1.
- A media-cache lookup, write or upgrade scheduling failure after commit made a saved
  detection appear to have failed. These optional failures now record a warning separately.
- Failure to schedule an asynchronous detection or weather job left its status running.
  It now becomes terminal and releases maintenance capacity.
- Cancellation during a weather write counted unfinished work as processed. Counts now
  advance only once an outcome exists.

No schema, retention, notification policy, confidence threshold or execution-mode default
changes. Invalid scores are rejected, not clamped into plausible classifications.

## Coverage

| Path | Evidence | Boundary |
| --- | --- | --- |
| Detection backfill, synchronous and asynchronous | Real migrated database, mixed saved/filtered/missing outcomes, accurate counts, weather follow-up | Frigate HTTP and inference mocked in CI |
| Repeated detection import | Same row retained, lower confidence ignored, higher confidence updates automatic identity | Not a complete Frigate retention-window replay |
| User data preservation | Manual species identity, favourites, hidden state, weather and owner notes survive replay | Focused fixtures, not a copy of every production row |
| Weather backfill, synchronous and asynchronous | Real repository updates, missing archive data, archive errors and cancelled writes | External weather provider mocked |
| Classifier worker lifecycle | Real subprocesses and pipes, idle exit in either pool, concurrent live/background bursts, in-flight exit and deadline, successful replacement and process cleanup | Synthetic inference keeps ordinary CI independent of model downloads |
| Historical video, taxonomy identity, timezone repair | Existing dedicated suites remain part of the full backend run | No new full live-data replay of these maintenance paths in this pass |

The earlier [classifier recovery review](2026-09-23-classifier-recovery-review.md)
covers native timeout quarantine and hardware inference. These checks complement it;
they do not establish accuracy for every model or support for every device/driver.

## Verification results

- Full backend suite: **3,056 passed, 49 skipped**. This adds 33 regression cases.
- Repository-wide Ruff lint/format and documentation consistency pass.
- Quark, installed `rope_vit_b14_inat21`, retained bird crop: subprocess NPU and
  in-process NPU both passed with `Prunella modularis` at 0.3862720132; subprocess
  CPU passed at 0.3904895186. Each replay preserved four rows across duplicate
  imports, rejected the filtered event, reported corrupt media and passed SQLite
  integrity. The score difference is not treated as an accuracy comparison.
- An explicit `intel_cpu` run selected generic `cpu` in this clean configuration;
  the harness rejected the provider mismatch. This is not evidence for an
  OpenVINO CPU backfill pass. The separate earlier direct OpenVINO CPU probe
  remains distinct evidence.
- Production history was not used as the replay database; all writes were to
  temporary migrated databases. No live configuration or deployment changes were
  needed for these hardware checks.

## Repeatable real-model replay

From `backend`, in a disposable process with application dependencies installed:

```bash
PYTHONPATH=. python scripts/smoke_backfill_replay.py \
  --model-dir /data/models/rope_vit_b14_inat21 \
  --image /path/to/retained-bird-crop.jpg \
  --provider intel_npu
```

The harness creates a fresh migrated database, copies model metadata and links the
existing ONNX weights as read-only input. Its configuration, compiled caches and database
are temporary and removed on exit. It does not start ingestion, modify Frigate, send
notifications or write to production detection history. It still consumes real CPU/device
resources, so run one hardware check at a time on a busy feeder.

Application environment overrides are removed before imports so a host's NPU preference
cannot silently turn a CPU test into another NPU test. Device library paths are preserved.
The observed provider and execution mode must match the request; fallback is a failed
hardware assertion, not a pass for the requested accelerator. The test fails if the retained
crop cannot produce a usable candidate, so choose a real bird crop.

Each run checks four inserts, four duplicate replays, a confidence-filtered event,
corrupt media and SQLite integrity. `--provider cpu` checks CPU execution;
`--execution-mode in_process` explicitly exercises the compatibility path. Weather
service availability and model accuracy require separate checks.

## Remaining test work

- Replay representative retained clips through historical-video maintenance with real
  classifier/crop models, including vanished Frigate media and interrupted jobs.
- Exercise the published CUDA image on PICARD, beyond the already-tested native WSL
  ONNX Runtime path.
- Add a labelled, versioned multi-species crop corpus for accuracy regression checks;
  a repeated single crop proves pipeline consistency, not classification quality.
- Add sustained mixed live/backfill/video load checks with memory and queue bounds.

These remain part of the [inference isolation roadmap](../../ROADMAP.md#keep-the-web-service-and-ingest-off-the-inference-path-).
