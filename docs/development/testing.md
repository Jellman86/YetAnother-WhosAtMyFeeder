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
