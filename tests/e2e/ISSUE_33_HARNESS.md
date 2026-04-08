# Issue #33 Harness

This harness validates the two current symptoms reported in issue `#33`:

1. live MQTT ingest stalls after running for a while
2. maintenance video work times out and opens the maintenance video circuit

It is intentionally separate from the issue `#22` harness because it needs to
exercise both MQTT recovery and the maintenance video-classifier path, either
independently or together.

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

## Live Stress Run

Use this when you want to hammer a live test container closer to the Apr 5
reporter conditions instead of just validating track logic.

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python \
  /config/workspace/YA-WAMF/scripts/run_issue33_harness.py \
  --backend-url http://yawamf:8080 \
  --stress-profile issue33-live \
  --scenario combined \
  --username <owner_username> \
  --password <owner_password> \
  --mqtt-host mosquitto \
  --mqtt-port 1883 \
  --mqtt-username <mqtt_username> \
  --mqtt-password <mqtt_password> \
  --mqtt-publish-container mosquitto \
  --duration-seconds 600
```

The `issue33-live` profile currently expands to:

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

Explicit CLI flags still win over the profile when you need to tune a run.

Use `--mqtt-publish-container` when the broker is container-local or auth is
enabled and you want the harness to publish from inside the broker container.
That was required on the live monolith used for the Apr 6 stress runs.

## Replay-Backed Frigate Load

Use this when you want busy-feeder Frigate stress without synthetic snapshot
`404` artifacts. The harness fetches recent real bird events from Frigate and
loops them on the Frigate MQTT topic.

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python \
  /config/workspace/YA-WAMF/scripts/run_issue33_harness.py \
  --backend-url http://yawamf:8080 \
  --scenario combined \
  --username <owner_username> \
  --password <owner_password> \
  --mqtt-host mosquitto \
  --mqtt-port 1883 \
  --mqtt-username <mqtt_username> \
  --mqtt-password <mqtt_password> \
  --mqtt-publish-container mosquitto \
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
   - `--mqtt-publish-container mosquitto`
   - a real configured camera name, which the harness now resolves automatically
2. A busy synthetic feeder can now be reproduced reliably enough to push the
   backend into sustained `critical` MQTT pressure.
3. Replaying a real Frigate-backed event id completed cleanly on the live
   backend and avoided the synthetic snapshot-404 failure.

However, the later Apr 8 live runs exposed a second reproduction caveat:

- synthetic Frigate event ids still cause snapshot fetch `404`s
- the backend then drops the work as `classify_snapshot_unavailable`
- replay-backed Frigate ids avoid that specific artifact

That means the current stress harness is good at reproducing high-load collapse,
but it is not yet a clean reporter-faithful reproducer for later `#33` symptoms
when synthetic Frigate ids are used. Prefer replay-backed Frigate load for that.

And even with replay-backed load, the MQTT stall track can still be invalid on a
live instance if the real Frigate keeps publishing on the same topic. Prefer a
test environment where the harness fully owns the Frigate topic, or temporarily
isolate real Frigate MQTT publishing during the stall window.

## Apr 8 Isolated Stall Run

The latest isolated live run used the replay-backed `issue33-live` profile and
temporarily stopped the real `frigate` container during the synthetic stall
window:

- artifact:
  `/config/workspace/YA-WAMF/tmp/issue33-harness/20260408-1340-isolated-frigate-stop/summary.json`
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
  `/config/workspace/YA-WAMF/tmp/issue33-harness/20260408-1423-isolated-hard-stop/summary.json`
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

Current defaults:

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
/config/workspace/YA-WAMF/backend/venv/bin/python \
  /config/workspace/YA-WAMF/scripts/run_issue33_harness.py \
  --backend-url http://yawamf:8080 \
  --stress-profile issue33-stall-probe \
  --scenario mqtt-no-frigate-resume \
  --username <owner_username> \
  --password <owner_password> \
  --mqtt-host mosquitto \
  --mqtt-port 1883 \
  --mqtt-username <mqtt_username> \
  --mqtt-password <mqtt_password> \
  --mqtt-publish-container mosquitto
```

## Apr 8 Stall-Probe Result

The corrected rerun with the lower-pressure profile passed:

- artifact:
  `/config/workspace/YA-WAMF/tmp/issue33-harness/20260408-1511-stall-probe-fixed/summary.json`
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

- the MQTT reconnect path does work on current `dev` when the harness creates a
  real Frigate-topic stall instead of a backlog-masked pseudo-stall
- the remaining `#33` work should no longer start with `mqtt_service.py`
- for Track B on current code, use `issue33-stall-probe`, not `issue33-live`

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

- `/config/workspace/YA-WAMF/tmp/issue33-harness/20260406-074431/summary.json`
- `/config/workspace/YA-WAMF/tmp/issue33-harness/20260406-074717/summary.json`
- `/config/workspace/YA-WAMF/tmp/issue33-harness/20260406-081950/summary.json`
- `/config/workspace/YA-WAMF/tmp/issue33-harness/20260406-082739/summary.json`
- `/config/workspace/YA-WAMF/tmp/issue33-harness/20260408-120457/summary.json`
- `/config/workspace/YA-WAMF/tmp/issue33-harness/20260408-123341/summary.json`

Recommended next step for another agent:

1. Keep the `issue33-live` stress profile.
2. Re-run the same busy-feeder stress shape with replay-backed Frigate load.
3. For MQTT no-resume testing, verify the stall was actually effective. If the
   harness reports that live Frigate traffic masked the stall, the run is not a
   valid Track B reproducer.
4. Only then judge whether the remaining `#33` root cause is:
   - early load-collapse / backpressure failure
   - maintenance timeout behavior
   - later MQTT no-Frigate-resume recovery
5. Treat the Apr 8 isolated-stall result as a harness-quality checkpoint:
   - the outage produced `classify_snapshot_unavailable` drops as expected
   - but Frigate-topic traffic still leaked during the pause
   - fix that leak before claiming Track B is tested

## Basic Combined Run

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python \
  /config/workspace/YA-WAMF/scripts/run_issue33_harness.py \
  --backend-url http://yawamf-backend:8000 \
  --scenario combined \
  --mqtt-host mosquitto \
  --mqtt-port 1883 \
  --birdnet-topic birdnet/text \
  --mqtt-publish-container mosquitto \
  --duration-seconds 900 \
  --poll-interval-seconds 5
```

## MQTT-Only Track

This mode starts both publishers, then pauses the synthetic Frigate publisher
while BirdNET continues. Use `--frigate-stall-duration-seconds` to control how
long the pause lasts.

Important:

- on a live instance, this only exercises Track B if the real Frigate is not
  still publishing on the same topic
- if the run fails with `Live Frigate traffic remained active during the induced
  stall window...`, the synthetic stall was masked and MQTT stall-recovery was
  not actually tested

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python \
  /config/workspace/YA-WAMF/scripts/run_issue33_harness.py \
  --backend-url http://yawamf-backend:8000 \
  --scenario mqtt-no-frigate-resume \
  --mqtt-host mosquitto \
  --mqtt-port 1883 \
  --birdnet-topic birdnet/text \
  --mqtt-publish-container mosquitto \
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
/config/workspace/YA-WAMF/backend/venv/bin/python \
  /config/workspace/YA-WAMF/scripts/run_issue33_harness.py \
  --backend-url http://yawamf-backend:8000 \
  --scenario maintenance-video-timeout \
  --auth-token <owner_jwt> \
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

This harness collects evidence only. It does not close GitHub issues.
