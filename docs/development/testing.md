# Run regression tests without extra hosted services

Run the normal gates before pushing. Browser matrices, downloaded models and long
soaks run on your own machine or a trusted test host, not automatically in GitHub
Actions. This adds no paid testing service, scheduled soak or self-hosted runner
that executes untrusted pull requests. Existing CI and image-build jobs remain;
their total usage still depends on how often you push and build.

## Normal gate

Use Python 3.12 and Node.js 22, matching CI. Install the locked/project dependencies
first. From the repository root:

```bash
source backend/.venv/bin/activate
python -m ruff check .
python -m ruff format --check .
python backend/scripts/run_regression_gate.py
npm --prefix apps/ui run check
npm --prefix apps/ui run lint:dead
npm --prefix apps/ui test
npm --prefix apps/ui run build
npm --prefix apps/telemetry-worker test
python backend/scripts/docs_consistency_check.py
```

The backend command collects everything in `backend/tests`, including the former
`tests/unit` cases now in `backend/tests/additional`. A regression rejects new
orphaned Python tests under the root `tests` directory. Both PR checks and image
builds use this same command and `backend/.coveragerc`: branch measurement with a
70% total floor. This is a minimum, not evidence that every important path works.
The test process must exit successfully within eight minutes. A printed pass
summary does not excuse a teardown hang or a failed coverage report.

Telemetry tests build the Worker without deploying it, then use local Miniflare
databases. They do not require credentials or write to production Cloudflare D1.
They now run before merge, not just during deployment.

## Local browser matrix

From `apps/ui`:

```bash
npm ci
npx playwright install chromium webkit
npm run test:browser:smoke
npm run test:browser
```

On Linux, Playwright may request operating-system browser dependencies; install
those on the test host before running the suite. The full command runs Chromium
and WebKit at desktop and mobile sizes. Mobile emulation is not physical iOS
validation.

The runner starts and stops its own Vite server on loopback port 4178. An occupied
port fails the run instead of silently testing another build. No live URL or
credentials are required. Browser traces and screenshots from failures stay in
the ignored `apps/ui/playwright-results` directory. Use
`npx playwright show-trace path/to/trace.zip` to inspect a failed interaction.

These are rendered-component regression tests, not full application end-to-end
tests. They mount the production Health timeline and previews with real styles
and translations, and substitute only media responses. They check:

- Recorded, filtered and failed detections remain distinguishable.
- Only recorded visits offer **View record**, and it returns the correct event.
- Previews escape a deliberately clipping ancestor and remain inside the viewport.
- Keyboard dismissal, focus, touch activation, unmount cleanup and expired images.
- Loading and empty states, and no horizontal overflow at mobile width.

Unexpected API requests and uncaught JavaScript errors fail the fixture. Its HTML
is a development test entry, not included in the production build. New browser
tests belong in `browser-tests/*.spec.ts`; do not replace interaction assertions
with checks that a source file merely contains a string.

## Joined backend paths and recovery

`test_live_notification_integration.py` sends MQTT payloads through the real
event processor, detection policy, migrated SQLite repositories, notification
queue, notification policy and channel selection. Only external inference,
media, taxonomy, weather and the outbound channel are substituted. It covers
standard/final/silent policy, repeated updates/end events, filtered detections,
missing initial events, delivery retry, expired media, transient inference/media
failure and optional Frigate write-back failure. It never sends Telegram messages.

`test_database_backups.py` now restores real SQLite snapshots, including committed
WAL rows and owner metadata. Uncommitted writes are excluded. Corrupt input, failed
writes, locked databases, filename collisions and clock corrections cannot replace
the previous restore point with a partial copy.

## Hardware and longer checks

Worker lifecycle regressions run without model downloads in
`test_classifier_worker_client.py`, `test_classifier_supervisor.py` and
`test_classifier_subprocess_integration.py`. They distinguish pipe closure from
confirmed process exit, exercise a real POSIX child that ignores termination,
and cover cancellation, bounded escalation and replacement blocked by failed
cleanup. A killed child must have an exit code before its capacity is reused.
The real signal-handler case is POSIX-only; portable lifecycle cases still run
on other platforms. Process waiting follows Python's
[asyncio subprocess contract](https://docs.python.org/3.12/library/asyncio-subprocess.html).

Use the [backfill replay recipe](../reviews/2026-09-23-backfill-test-hardening.md#repeatable-real-model-replay)
with an already installed model and a retained bird crop. Run one accelerator
probe at a time on a busy feeder. The harness owns a temporary migrated database,
checks the actual provider and fails on unexpected fallback. Never point fixture
writes at production detection history or change its model settings for a test.

Read-only fleet telemetry can guide fixtures, but preserve anonymity and use
bounded aggregate queries. A healthy latest heartbeat does not erase historical
fault reports, and cumulative report counters are not incident counts.

### Mandatory local model/provider gate

Use the installed-model gate on a trusted hardware host before certifying a model,
provider or runtime update. From the repository root with runtime dependencies
installed, choose the model directory and providers available on that host:

```bash
python backend/scripts/run_model_hardware_gate.py \
  --models-dir /data/models --output /tmp/yawamf-hardware-validation \
  --provider intel_npu --provider intel_gpu --repeat 2
```

The output directory must not already exist. On the NVIDIA host, request
`--provider cuda` instead. Use `--model medium_birds/eu` to select an exact
regional artifact. CPU is always run as the comparison baseline. Eight committed
real images are used by default; when running from an image without the test
fixtures, supply retained images with repeated `--image /path/to/image.jpg`
arguments. Missing images or unknown models fail instead of validating a fallback.

Each model/provider/repeat gets a disposable subprocess with a 240-second default
deadline. Native crashes, timeouts, malformed reports, missing image coverage,
non-finite output and CPU disagreement fail the command. Crop detectors use the
production crop service and detection-box comparisons, not species-classifier
tensor/label assumptions. Cold compilation uses a private cache on each repeat;
the production probe also warms up before measured inference. This is not yet a
cross-process warm-cache or sustained-load certification.

The runner records package versions, model/config/label and image hashes, raw probe
reports, process logs and a `summary.json`, including failures. A requested provider
must actually be exercised to pass. Registry-incompatible combinations are explicitly
not applicable; candidate combinations are tested but do not gain supported status
from a single pass. Review every failure, even when another repeat passes.

### Native OpenVINO crash reproducer

Verify the application recovery contract separately with real installed weights:

```bash
PYTHONPATH=. python scripts/smoke_native_cpu_recovery.py \
  --model-dir /data/models/small_birds/eu --model-id small_birds --region eu \
  --image /path/to/retained-bird-crop.jpg
```

This creates disposable config, database, media and compiled-cache paths, seeds a
**synthetic** native-fault record, and checks cold live CPU recovery, background
inference, video progress/abstention and backfill idempotency. It never starts
ingestion or sends notifications. Original weights and the input image are read-only.
The separate Linux supervisor regression exercises a real SIGABRT child; a seeded
record must never be described as reproducing the underlying GPU fault. CPU
recovery remains degraded even after success, and wrong artifacts, native CPU
crashes, cancellation, missed deadlines and failed reaping fail closed.

Run this Linux-only tool serially on a trusted hardware host. It imports OpenVINO
directly, not YA-WAMF services, and uses deterministic synthetic tensors. It tests
runtime stability, not species accuracy or equivalence to the application pipeline.

```bash
python backend/scripts/reproduce_native_gpu_crash.py \
  --model /data/models/small_birds/eu/model.onnx --device GPU \
  --shape 1,3,224,224 --repeat 3 --iterations 10 --cache cold \
  --output /tmp/yawamf-gpu-cold
```

Use the actual shape required by the selected artifact; omit `--shape` for a
model with fully static inputs. Repeat with `--cache warm` and a new output path
to reuse an OpenVINO cache between child processes. `--cache off` disables that
explicit cache. These controls do not flush operating-system caches or certify
that every driver-internal cache is cold. Production caches are never modified.

The parent has a default 240-second deadline per child and retains every exit
code, last reported phase, process log and output hash. A native crash, timeout,
invalid output or incomplete report fails the command even if later repeats pass.
Unreaped children stop further launches. Core dumps are disabled and child
environments exclude application credentials. Keep output private: native library
errors can include local paths. This probe neither changes production settings nor
clears quarantine or marks a provider eligible. Compare retained failures against
the exact image, device and driver packages before filing an upstream runtime issue.

In the installed-model gate, model weights are read-only, configuration/databases/
media paths are disposable, and the runner never writes production eligibility or
changes the active model. Its parent owns scratch directories so a crashing child does not leave compiled
caches behind. Keep hardware runs serial alongside a live feeder and watch its
health; do not run the full model library concurrently with other heavy tests.

`test_model_hardware_installed.py` invokes the same strict gate when the model
library and device are present. On ordinary CI without them, skips describe the
missing prerequisite, not successful hardware validation. Synthetic runner tests
still exercise crash, timeout, empty coverage and invalid-report failures in CI.
Legacy GPU/NPU/CUDA diagnostic tests require
`YAWAMF_LEGACY_HARDWARE_DIAGNOSTICS=1`; they are exploratory, may crash their own
pytest process, and must never be used as a release gate or run in the API process.

Accuracy tests load only the model currently being exercised and discover regional
subdirectories. Detector accuracy remains a separate box/field benchmark. Provider
agreement establishes consistency, not species correctness; the labelled accuracy
corpus still needs pinned, reviewed images and a previous-release baseline.

## Remaining gaps

- Full-app owner/guest authentication, settings save/reload, backfill controls,
  SSE reconnection and detection-modal/media journeys across browsers.
- Concurrent duplicate notification jobs and delivery interrupted between send
  and marking the row notified; sequential replay tests do not prove exactly-once delivery.
- A labelled multi-species accuracy corpus, retained-video maintenance replay,
  published CUDA-image checks and sustained mixed-load memory/queue bounds.
- Removing the old test-wide aiosqlite daemon-thread workaround by fixing each
  leaking fixture. Strict process exit catches other hangs but does not prove that
  all database connections are currently closed.
- Populated historical-schema upgrade/rollback matrices beyond the existing
  migration and runtime-flavour tests, plus restore through the owner workflow.

These remain on the [broader coverage roadmap](../../ROADMAP.md#broader-end-to-end-coverage-).

## Deterministic test boundaries

Diagnostics API fixtures substitute the media-probe boundary, so running next to a
real Frigate cannot change an unavailable-media assertion or fetch real clips.
Media parsing and probe behavior have their own tests.

Route/name-lookup tests track which asyncio task owns each acquired connection and
check ownership when the mocked provider is called. Background tasks inherit context
variables, so a depth flag alone would falsely classify a background task as holding
its parent's connection. A negative-control test deliberately awaits the provider
inside a real hold and proves the guard rejects it. This verifies ownership, not a
latency budget; performance still needs a separately controlled workload.

The species-reference packaging test checks both Git tracking and ignore rules in a
checkout. In a production image without Git metadata it checks that the asset exists
and skips only the source-control assertion; separate runtime tests exercise the
reference database's contents and lookups. Installing Git in a production image is
not necessary to validate its runtime assets.

## Accuracy fixture provenance

`backend/scripts/download_test_fixtures.py` checks each photo's CC0/CC-BY licence,
not just the observation licence. iNaturalist documents these as
[separate licences](https://help.inaturalist.org/en/support/solutions/articles/151000175695).
The downloader retains attribution, observation/photo IDs, source URL and SHA-256;
normal reruns verify existing bytes without selecting new popular observations.
It respects manifest exclusions and takes at most one photo per observation.

Use `--force` only for an intentional corpus refresh. Legacy records without full
provenance, missing files and checksum mismatches require that explicit refresh.
New files have content-addressed names, so a refresh does not overwrite previous
images. `--case` preserves other species' metadata. Incomplete refreshes return a
nonzero exit and retain the previous case record; image decoding must succeed
before a newly downloaded file is accepted. Do not run concurrent refresh writers.

This locks the local selection, not a release accuracy benchmark. Labels and image
quality still need review, a portable curated manifest must be committed, and the
same corpus must be compared against a previous release before setting thresholds.
