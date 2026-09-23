# Classifier recovery review

Review of admission, isolated workers, native fallback, image and video callers,
backfill, runtime health and the Detection settings status after issue #490.

## Findings corrected

| Finding | Result |
| --- | --- |
| Native recovery completion updated a private dictionary but left health telemetry recovering | Completion is published to runtime health once; newer worker failures remain visible |
| Repeated old worker telemetry could replace a newer recovery for the same runtime | Recovery timestamps prevent stale state from replacing newer state |
| Reload could clean up a model still held by a timed-out native call | A quarantined parent retains that model; reload applies to workers |
| A late invalid native result could start another model recovery | Quarantined native results cannot reload or replace the model |
| A fallback waiter could load another model after quarantine | The fallback lock rechecks quarantine before native work starts |
| Wildlife requests bypassed isolated workers, then failed after bird-runtime quarantine | Subprocess mode routes wildlife through the background worker protocol; wildlife reload restarts that pool |
| Uploaded classifier tests bypassed admission in native mode | Bird and wildlife upload tests use the coordinated asynchronous entry points |
| Default model download called the removed `_load_model` method | Download completion uses the supported asynchronous model reload API |
| A filtered fallback snapshot concealed the video timeout or worker failure | The circuit retains the original infrastructure failure when fallback does not recover the visit |
| The settings status displayed the saved execution mode after automatic recovery | It displays the running mode, distinguishes pending/completed recovery and retains restart advice |

Backfill coverage also exercises the asynchronous job endpoint: three consecutive
classifier failures stop the job with accurate partial counts, emit a failed job
event, release maintenance ownership and do not schedule weather follow-up.
Expected filtering and missing media do not count as classifier outages.

## Verification

- Local backend: the full suite passes. Skips do not establish hardware coverage.
- Frontend: 1,133 passed; Svelte check has zero errors/warnings; dead-code check and production build pass.
- Repository-wide Ruff and documentation consistency checks pass.
- Quark, Intel NPU, `rope_vit_b14_inat21`: a disposable classifier service first
  classified a retained crop, then expired an injected cooperative native stall.
  Real live and background workers resumed with identical top label and score.
  Only one call reached the injected native function. The production singleton,
  ingestion and detection database were not modified by the test.
- Quark, Intel GPU, same installed model and retained crop: compile and inference
  passed with 10,000 finite outputs; observed median inference was 243.2 ms.
- Quark, Intel CPU, same model and crop: 10,000 finite outputs and the same top
  five indices as GPU; observed median inference was 122.3 ms. These single-crop
  checks are not a benchmark under production load or a reason to change providers.
- PICARD, RTX 4070 under WSL, ONNX Runtime 1.26.0: the application's ONNX model
  loader and preprocessing executed a deterministic three-class fixture on CPU
  and CUDA. Runtime profiles confirmed CUDA kernels, with CPU agreement within
  `1e-5`. This is a runtime contract check, not validation of every bird model or
  the published CUDA container.

## Repeatable hardware checks

Run these in a disposable process with the application's dependencies and
`PYTHONPATH` pointing at `backend`. Use the existing model/provider configuration
for the recovery check. It deliberately injects a bounded stall only into its own
classifier instance; it does not alter the live service.

```bash
PYTHONPATH=. python scripts/smoke_classifier_recovery.py /path/to/retained-bird-crop.jpg
PYTHONPATH=. python scripts/probe_bird_model_provider.py --provider intel_gpu --model-id rope_vit_b14_inat21 --images /path/to/retained-bird-crop.jpg
PYTHONPATH=. python scripts/smoke_onnx_provider.py --provider CUDAExecutionProvider
```

The ONNX contract check additionally requires the optional `onnx` package. It
generates its own small model and removes its temporary files on completion.

## Remaining boundaries

In-process mode remains an explicit compatibility option. Cancelling a Python
future cannot terminate a native inference call. Recovery therefore redirects
new work to isolated processes and recommends a container restart to release
stalled threads and retained models. A successful worker result does not prove
that the old native thread stopped.

The default remains subprocess execution. Removing in-process support would
also require an explicit replacement policy for worker startup failure, memory
pressure and unsupported model/runtime combinations. It is not necessary for
the corrected timeout recovery and has not been done here.

These tests do not prove model accuracy across every model, operating system or
driver. The low-level diagnostic endpoints still have separate native probe
behaviour; they should be assessed independently before claiming every endpoint
has the same isolation guarantees as classification requests.
