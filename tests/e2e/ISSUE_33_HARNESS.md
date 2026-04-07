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
2. Optionally stops the Frigate publisher after a configured delay while BirdNET keeps running.
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

For the post-stall MQTT recovery path specifically, use a long enough run to
cross the backend's stalled-topic threshold. On Apr 6, both a 420s run and a
600s run with `--induce-frigate-stall-after-seconds 60` still only reached
`298.3s` and `298.5s` max Frigate age, stopping just short of the backend's
`300s` threshold. Do not assume 600s is sufficient on every host; verify the
actual `evaluation.stall_incidents[].max_frigate_age_seconds` in `summary.json`.

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

However, those same runs also exposed a reproduction caveat:

- synthetic Frigate event ids still cause snapshot fetch `404`s
- the backend then drops the work as `classify_snapshot_unavailable`
- replay-backed Frigate ids avoid that specific artifact

That means the current stress harness is good at reproducing high-load collapse,
but it is not yet a clean reporter-faithful reproducer for later `#33` symptoms
when synthetic Frigate ids are used. Prefer replay-backed Frigate load for that.

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

Recommended next step for another agent:

1. Keep the `issue33-live` stress profile.
2. Re-run the same busy-feeder stress shape with replay-backed Frigate load.
3. Use a duration long enough to cross the stalled-topic threshold when testing
   MQTT no-resume behavior.
4. Only then judge whether the remaining `#33` root cause is:
   - early load-collapse / backpressure failure
   - maintenance timeout behavior
   - later MQTT no-Frigate-resume recovery

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

This mode starts both publishers, then stops Frigate after three minutes while
BirdNET continues. That should force the backend into its stall-recovery path.

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

## Important

This harness collects evidence only. It does not close GitHub issues.
