# Issue #33 Harness

This harness validates two symptoms reported in issue `#33`:

1. live MQTT ingest stalls after running for a while
2. maintenance video work times out and opens the maintenance video circuit

It is intentionally separate from the issue `#22` harness because it needs to
exercise both MQTT recovery and the maintenance video-classifier path, either
independently or together.

## Use a disposable test environment

These are write-producing stress tests, not read-only health checks. They publish MQTT messages
that can create synthetic detections and audio history, queue maintenance work and trigger normal
notification/integration side effects. Use a separate YA-WAMF instance, database, media directory
and broker. Disable notifications, external submissions, AI calls and Frigate sublabel write-back
on that instance. Do not publish to a live feeder broker or stop a production Frigate container.
Read-only retained Frigate media may supply replay inputs; keep the test instance unable to write
back to the real NVR. The harness does not automatically remove every record it creates.

Run from the repository root with the backend environment prepared:

```bash
source backend/.venv/bin/activate
python scripts/run_issue33_harness.py --help
```

Supply the test broker's password through `SOAK_MQTT_PASSWORD` and owner JWT through
`SOAK_AUTH_TOKEN`, using your local secret manager rather than pasting them into command history.
The issue #33 harness also supports `SOAK_USERNAME` and `SOAK_PASSWORD` for login; issue #22 expects
an existing JWT. Keep result artifacts private until reviewed: they can include service addresses,
event IDs, camera names and failure context.

Direct publishing needs `paho-mqtt` in this environment. The optional `--mqtt-publish-container`
path runs `mosquitto_pub` inside a test broker container through Docker. Use only disposable
credentials on a trusted host: its child command may expose the broker password in process
arguments even when the parent read it from an environment variable.

For fixture-backed video tests, `ffmpeg` must also be available to the harness. The fixture HTTP
server defaults to `127.0.0.1:8799`; that address works only if the test backend can reach the same
loopback interface. Otherwise set `--fixture-frigate-host` to an address bound by the harness host
and reachable from the disposable backend, and allow that test port through the firewall.
`--fixture-update-backend-frigate-url` changes saved test settings temporarily; restoration is
best-effort. Check `backend_settings_restore` and the saved URL after interruption. Keep production
configuration out of this run.

## What It Does

1. Publishes Frigate and BirdNET MQTT traffic.
   Frigate load can be synthetic or replay-backed from real Frigate event ids.
2. Optionally pauses the synthetic Frigate publisher after a configured delay while BirdNET keeps running, and can later resume it.
3. Polls `/health` on a fixed interval.
4. Optionally polls `/api/diagnostics/workspace` when owner auth is available.
5. Optionally triggers unknown-analysis queueing to add maintenance video pressure.
6. Can apply an `issue33-live` stress profile that:
   - reduces MQTT publish intervals
   - starts multiple Frigate and BirdNET publisher replicas
   - triggers owner maintenance queueing in bursts
   - shortens the time before the induced Frigate stall
   - defaults Frigate load to replaying real Frigate-backed events
7. Produces separate track results for:
   - `maintenance_video_timeout`
   - `mqtt_no_frigate_resume`

For authenticated owner runs, the harness now also resolves the configured
Frigate camera from `/api/settings` when `--frigate-camera` is not provided, so
synthetic Frigate events hit a real allowed camera instead of the old `soak_cam`
placeholder.

If `--frigate-api-url` is not provided, the harness also resolves `frigate_url`
from `/api/settings` for replay-backed Frigate load.

## Heavy stress profile

Use this to exercise a running disposable container under heavy ingest and maintenance pressure.
The profile name contains `live`, but does not authorise using a production feeder. It is a stress
shape, not proof that the reporter's fault has been reproduced.

```bash
python scripts/run_issue33_harness.py \
  --backend-url http://test-yawamf:8080 \
  --stress-profile issue33-live \
  --scenario combined \
  --mqtt-host test-mosquitto \
  --mqtt-port 1883 \
  --mqtt-publish-container test-mosquitto \
  --duration-seconds 600
```

The `issue33-live` profile supplies these defaults:

- `--duration-seconds 1200`
- `--frigate-event-type new`
- `--poll-interval-seconds 2`
- `--trigger-analysis-interval-seconds 15`
- `--analysis-trigger-burst-count 4`
- `--analysis-trigger-burst-spacing-seconds 0.75`
- `--induce-frigate-stall-after-seconds 120`
- `--frigate-stall-duration-seconds 420`
- `--frigate-load-source replay`
- `--frigate-publish-interval-seconds 0.2`
- `--birdnet-publish-interval-seconds 0.25`
- `--frigate-publisher-replicas 4`
- `--birdnet-publisher-replicas 3`

Values different from the parser defaults are kept when the profile is applied. An explicit
value equal to a parser default can still be replaced by the profile; check `summary.json.config`
rather than assuming every explicitly typed flag won. Use `--stress-profile none` with a complete
set of flags when you need exact control.

Use `--mqtt-publish-container` when the broker is container-local or auth is
enabled and you want the harness to publish from inside the broker container.
That was required in the historical Apr 6 test topology; it is not required for every installation.

## Fixture Replay With Example Images

Set `TEST_FIXTURE_HOST` in your shell to the harness host's bind address reachable from the test
backend (use `127.0.0.1` only when they genuinely share loopback). The following run requests 600
seconds, which overrides the profile's 240-second duration without matching the parser's 900-second
default.

Use this when you want a repeatable hammer run that serves known example images
through the harness fixture Frigate API. This avoids synthetic missing-snapshot `404`s and exercises image admission under a repeatable
load. It does not prove species accuracy or the reporter's production workload.

```bash
python scripts/run_issue33_harness.py \
  --backend-url http://test-yawamf:8080 \
  --stress-profile issue33-fixture-replay \
  --scenario combined \
  --mqtt-host test-mosquitto \
  --mqtt-port 1883 \
  --fixture-image-dir /path/to/fixture-images \
  --fixture-frigate-host "$TEST_FIXTURE_HOST" \
  --duration-seconds 600
```

The `issue33-fixture-replay` profile supplies these fixture-backed defaults, with maintenance
queue pressure and an induced Frigate pause:

- `--duration-seconds 240`
- `--poll-interval-seconds 2`
- `--trigger-analysis-interval-seconds 20`
- `--analysis-trigger-burst-count 2`
- `--analysis-trigger-burst-spacing-seconds 0.5`
- `--induce-frigate-stall-after-seconds 60`
- `--frigate-stall-duration-seconds 0`
- `--frigate-load-source fixture`
- `--frigate-publish-interval-seconds 0.5`
- `--birdnet-publish-interval-seconds 0.5`
- `--frigate-publisher-replicas 2`
- `--birdnet-publisher-replicas 2`
- `--trigger-backfill`
- `--fixture-manual-tag-unknown`
- `--min-backfill-processed 3`
- `--min-analysis-total-candidates 1`
- `--max-analysis-accepted 50`
- `--max-video-pending 50`

## Reading the historical results

The April and May observations below belong to the builds, machines and private artifacts recorded
at that time. They are retained for reproduction context, not claimed as checks of the current
release. References to then-current `dev` do not establish current behavior. Never repeat the
production-stop experiments described in those historical notes; use an isolated broker and
fixture service for a new run.

## May 5 fixture and stall-probe notes (historical)

The May 5 validation informed the interpretation of
issue `#33`:

- Fixture replay against example images no longer reproduced live-image
  admission drops after the adaptive live-classifier queue timeout change.
- A 900 second stall-probe run passed with `event_dropped_delta: 0`,
  `live_image_admission_timeouts_delta: 0`, `video_failure_count_delta: 0`, and
  `video_circuit_open_observed: false`.
- The measured stall-probe window proved Frigate pause/resume health under
  lower pressure, but it did not force the default 1800 second
  Frigate-topic stale threshold. Extend the run or lower the threshold when you
  need to prove `topic_liveness_reconnects_delta` growth.

For a new run, start with `issue33-fixture-replay` for the overload symptom
and `issue33-stall-probe` for the MQTT pause/resume symptom. Treat
`issue33-live` as a heavy collapse profile, not the cleanest reconnect
validator.

## Replay-Backed Frigate Load

Use this when you want busy-feeder Frigate stress without synthetic snapshot
`404` artifacts. The harness fetches recent real bird events from Frigate and
loops them on the Frigate MQTT topic.

```bash
python scripts/run_issue33_harness.py \
  --backend-url http://test-yawamf:8080 \
  --scenario combined \
  --mqtt-host test-mosquitto \
  --mqtt-port 1883 \
  --mqtt-publish-container test-mosquitto \
  --frigate-load-source replay \
  --replay-frigate-seed-count 30 \
  --replay-frigate-source-limit 200
```

Optional controls:

- `--replay-frigate-event-id <id>`
  Use one or more explicit Frigate event ids instead of auto-discovered seeds.
- `--frigate-api-url <url>`
  Override the Frigate API base URL instead of resolving it from owner settings.
- `--frigate-camera <name>`
  Restrict auto-discovered replay seeds to one camera.

The live monolith testing on Apr 6 showed that replaying a real Frigate event id
completed cleanly and avoided `classify_snapshot_unavailable`, so replay-backed
Frigate load should be preferred for reporter-faithful stress runs.

For the post-stall MQTT recovery path specifically, there are now two separate
constraints:

1. the run must be long enough to cross the backend's stalled-topic threshold
2. the harness must actually own the Frigate topic during the stall window

On a live feeder, ambient real Frigate traffic can keep the topic active even
after the replay publisher pauses. In that case the harness now reports:

- `Live Frigate traffic remained active during the induced stall window...`

That means Track B was **not** exercised, even if the replay publisher paused.

## Apr 6 Live Run Notes

The Apr 6 live monolith runs established two important operational facts:

1. To hammer the real instance, the harness needed all of:
   - owner auth for `/api/settings` and `/api/diagnostics/workspace`
   - broker auth (`--mqtt-username` / `--mqtt-password`)
   - `--mqtt-publish-container test-mosquitto`
   - a real configured camera name, which the harness now resolves automatically
2. A busy synthetic feeder can now be reproduced reliably enough to push the
   backend into sustained `critical` MQTT pressure.
3. Replaying a real Frigate-backed event id completed cleanly on the live
   backend and avoided the synthetic snapshot-404 failure.

However, the later Apr 8 live runs exposed a second reproduction caveat:

- synthetic Frigate event ids still cause snapshot fetch `404`s
- the backend then drops the work as `classify_snapshot_unavailable`
- replay-backed Frigate ids avoid that specific artifact

Those historical runs showed high-load collapse,
but it is not yet a clean reporter-faithful reproducer for later `#33` symptoms
when synthetic Frigate ids are used. Prefer replay-backed Frigate load for that.

And even with replay-backed load, the MQTT stall track can still be invalid on a
live instance if the real Frigate keeps publishing on the same topic. Prefer a
test environment where the harness fully owns the Frigate topic, and keep production Frigate publishing entirely outside that broker.

## Apr 8 Isolated Stall Run

The latest isolated live run used the replay-backed `issue33-live` profile and
temporarily stopped the real `frigate` container during the synthetic stall
window:

- artifact:
  `tmp/issue33-harness/20260408-1340-isolated-frigate-stop/summary.json`
- pause marker:
  `2026-04-08T13:42:20.226426+00:00`
- resume marker:
  `2026-04-08T13:49:18.643696+00:00`

What this run proved:

- drops started exactly when the Frigate stall began
- drops plateaued exactly when the synthetic Frigate publisher resumed
- no maintenance timeout or video-circuit opening was observed
- no live-image admission timeouts were observed

Important outcome:

- the drop reason was `classify_snapshot_unavailable`
- diagnostics showed `focused_video_likely_last_error=event_http_500` during the
  outage window
- `topic_liveness_reconnects_delta` still stayed `0`
- the run therefore still did **not** reproduce
  `frigate_recovery_no_frigate_resume`

The most important caveat from this run is new:

- even after the real `frigate` container was stopped and the harness recorded
  `frigate_publisher_paused`, `mqtt_frigate_count` still continued to rise
- that means Frigate-topic traffic was still leaking during the intended stall
  window
- because the topic never went quiet, the backend's stalled-topic reconnect
  logic still was not being cleanly exercised

Interpretation:

- this run is useful evidence for outage handling under load
- it is **not** a clean Track B reproducer for the MQTT reconnect path
- the next harness fix should be to eliminate Frigate-topic leakage during the
  pause window before changing `mqtt_service.py` again

## Apr 8 Hard-Stop Rerun

The next Apr 8 rerun updated the harness to fully stop and join all synthetic
Frigate publisher threads during the stall window, then recreate them on resume.

- artifact:
  `tmp/issue33-harness/20260408-1423-isolated-hard-stop/summary.json`
- pause marker:
  `2026-04-08T14:25:24.071541+00:00`
- resume marker:
  `2026-04-08T14:32:23.750483+00:00`

What changed:

- the harness no longer relies on a cooperative pause flag for Frigate traffic
- synthetic Frigate publishers are torn down during the stall and recreated at
  resume

What the rerun showed:

- the result shape improved slightly:
  - `event_dropped_delta: 780` instead of `798`
  - drops froze exactly at the resume marker
  - completions resumed immediately after replay resumed
- `maintenance_video_timeout.failed=false`
- `mqtt_no_frigate_resume.failed=false`
- `topic_liveness_reconnects_delta` still stayed `0`

Most important interpretation:

- hard-stopping the synthetic publishers did **not** make the Frigate topic go
  stale under the `issue33-live` load profile
- `mqtt_frigate_count` still rose through the whole stall window while the real
  `frigate` container was stopped
- the backend stayed at `mqtt.in_flight=200`, so the remaining "fresh Frigate"
  signal is likely backlog drain rather than live publisher leakage

This changes the next harness task:

- the primary problem is no longer just synthetic-publisher leakage
- the stall detector now also needs to distinguish real new Frigate traffic from
  backlog already queued inside YA-WAMF
- until that is fixed, a heavy `issue33-live` stall run still cannot cleanly
  validate the MQTT reconnect path

## Apr 8 Stall-Probe Profile

To address the backlog-masking problem, the harness now supports a dedicated
lower-pressure Track B profile:

- `--stress-profile issue33-stall-probe`

This profile keeps replay-backed Frigate and BirdNET traffic alive, but avoids
the `issue33-live` queue saturation that kept the Frigate topic from ever aging
out.

The current script retains these stall-probe defaults:

- `--duration-seconds 900`
- `--poll-interval-seconds 2`
- `--trigger-analysis-interval-seconds 0`
- `--induce-frigate-stall-after-seconds 90`
- `--frigate-stall-duration-seconds 420`
- `--frigate-load-source replay`
- `--frigate-publish-interval-seconds 0.75`
- `--birdnet-publish-interval-seconds 0.5`
- `--frigate-publisher-replicas 1`
- `--birdnet-publisher-replicas 1`

Use it like this:

```bash
python scripts/run_issue33_harness.py \
  --backend-url http://test-yawamf:8080 \
  --stress-profile issue33-stall-probe \
  --scenario mqtt-no-frigate-resume \
  --mqtt-host test-mosquitto \
  --mqtt-port 1883 \
  --mqtt-publish-container test-mosquitto
```

## Apr 8 Stall-Probe Result

The corrected rerun with the lower-pressure profile passed:

- artifact:
  `tmp/issue33-harness/20260408-1511-stall-probe-fixed/summary.json`
- pause marker:
  `2026-04-08T15:13:10.829542+00:00`
- resume marker:
  `2026-04-08T15:20:10.857333+00:00`

Key outcome:

- `status: pass`
- `topic_liveness_reconnects_delta: 1`
- `last_reconnect_reason: frigate_topic_stalled`
- `mqtt_no_frigate_resume.failed=false`
- `degraded_ratio: 0.0`
- `event_dropped_delta: 13`
- `live_image_admission_timeouts_delta: 0`

Interpretation:

- the tested build exercised MQTT reconnect when the harness created a
  real Frigate-topic stall instead of a backlog-masked pseudo-stall
- the remaining `#33` work should no longer start with `mqtt_service.py`
- for a new Track B run, prefer `issue33-stall-probe`, not `issue33-live`

Observed live failure shape from the Apr 6 runs:

- MQTT pressure stayed at `critical`
- Frigate and BirdNET counts both climbed quickly
- event starts rose sharply
- event completions stayed flat
- drops rose almost one-for-one with starts
- replay-backed runs were materially healthier but still failed on live-image
  admission pressure before reproducing the reporter's later MQTT symptom
- maintenance `video_timeout` did not reproduce in these runs
- `frigate_recovery_no_frigate_resume` did not reproduce in these runs

Primary artifact examples:

- `tmp/issue33-harness/20260406-074431/summary.json`
- `tmp/issue33-harness/20260406-074717/summary.json`
- `tmp/issue33-harness/20260406-081950/summary.json`
- `tmp/issue33-harness/20260406-082739/summary.json`
- `tmp/issue33-harness/20260408-120457/summary.json`
- `tmp/issue33-harness/20260408-123341/summary.json`

For a new investigation, keep overload, media-availability and MQTT-stall evidence separate.
Use `issue33-fixture-replay` for repeatable overload input and `issue33-stall-probe` for a quiet
topic. Confirm the run actually crossed the backend's configured stale threshold and that no
ambient publisher or backlog masked the pause before judging reconnect recovery. Treat no
observed fault as unproven when the relevant condition was never exercised.

## Basic Combined Run

```bash
python scripts/run_issue33_harness.py \
  --backend-url http://test-yawamf:8080 \
  --scenario combined \
  --mqtt-host test-mosquitto \
  --mqtt-port 1883 \
  --birdnet-topic birdnet/text \
  --mqtt-publish-container test-mosquitto \
  --duration-seconds 900 \
  --poll-interval-seconds 5
```

## MQTT-Only Track

This mode starts both publishers, then pauses the synthetic Frigate publisher
while BirdNET continues. Use `--frigate-stall-duration-seconds` to control how
long the pause lasts.

Important:

- in the disposable instance, this only exercises Track B if no other publisher or draining
  backlog keeps the same topic active
- if the run fails with `Live Frigate traffic remained active during the induced
  stall window...`, the synthetic stall was masked and MQTT stall-recovery was
  not actually tested

```bash
python scripts/run_issue33_harness.py \
  --backend-url http://test-yawamf:8080 \
  --scenario mqtt-no-frigate-resume \
  --mqtt-host test-mosquitto \
  --mqtt-port 1883 \
  --birdnet-topic birdnet/text \
  --mqtt-publish-container test-mosquitto \
  --induce-frigate-stall-after-seconds 180 \
  --frigate-stall-duration-seconds 420 \
  --min-reconnect-delta 1
```

## Maintenance-Only Track

If owner auth is available, trigger unknown-analysis queueing and poll
`/api/diagnostics/workspace` so the harness can classify maintenance `video_timeout`
evidence directly.

The maintenance-only scenario now ignores MQTT/BirdNET growth and reconnect
threshold failures automatically, so you do not need manual `--min-birdnet-delta 0`
or `--min-reconnect-delta 0` overrides just because both publishers are disabled.

```bash
python scripts/run_issue33_harness.py \
  --backend-url http://test-yawamf:8080 \
  --scenario maintenance-video-timeout \
  --disable-frigate-publisher \
  --disable-birdnet-publisher \
  --trigger-analysis-interval-seconds 120 \
  --max-video-pending 25 \
  --max-video-failure-count-delta 0
```

## Output

Artifacts are written under:

```text
tmp/issue33-harness/<timestamp>/
```

Important `summary.json` fields:

1. `evaluation.failure_reasons`
2. `tracks.maintenance_video_timeout`
3. `tracks.mqtt_no_frigate_resume`
4. `evaluation.topic_liveness_reconnects_delta`
5. `evaluation.max_video_pending_seen`
6. `evaluation.video_failure_count_delta`
7. `config.scenario`
8. `config.stress_profile`
9. `config.analysis_trigger_burst_count`
10. `config.frigate_publisher_replicas`
11. `config.birdnet_publisher_replicas`
12. `config.frigate_load_source`
13. `replay.seed_event_ids`
14. `config.frigate_stall_duration_seconds`
15. `evaluation.frigate_stall_effective`

## Important

This harness does not close GitHub issues. It creates real test records and can change test
settings; retain artifacts and then discard the isolated stack's data. A pass is bounded to the
actual inputs, duration, thresholds, providers and runtime in the report. Check the precise track
was exercised before describing a reporter's issue as resolved.
