# Issue #22 Soak Harness

This harness validates sustained MQTT ingestion continuity and pressure behavior for issue `#22` ("Termination of event flow from frigate").

It is designed to produce evidence artifacts for issue comments without automatically closing the issue.

## What It Does

1. Publishes synthetic Frigate + BirdNET MQTT traffic at configurable rates.
2. Polls backend `/health` on a fixed interval.
3. Detects potential stall conditions where:
   - BirdNET traffic is still active/increasing, and
   - Frigate topic age is stale and Frigate count stops increasing.
4. Evaluates backend event-pipeline continuity from `/health.event_pipeline`:
   - Detects when started events increase but completed events do not.
   - Detects increases in event-pipeline critical failures.
5. Writes machine-readable artifacts:
   - `samples.ndjson` (per-poll samples/errors/triggers)
   - `summary.json` (pass/fail evaluation + thresholds + publisher stats)

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
python scripts/run_issue22_soak.py --help
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

## Basic run

Choose addresses reachable from the process running the harness. From the host, the monolithic
app normally uses port `9852`; from a shared test Docker network its container uses port `8080`.
The script's legacy default is `8946`, so specify `--backend-url` explicitly. Match the broker
topics to the isolated instance's settings; `birdnet/text` and `birdnet` are different topics.

```bash
python scripts/run_issue22_soak.py \
  --backend-url http://127.0.0.1:9852 \
  --mqtt-host 127.0.0.1 \
  --mqtt-port 1883 \
  --birdnet-topic birdnet/text \
  --duration-seconds 1800 \
  --poll-interval-seconds 5
```

The host and port above must belong to your disposable stack. For a network-only test broker,
use its reachable container address and optionally `--mqtt-publish-container test-mosquitto`.
The container must already contain `mosquitto_pub`; this flag does not create a broker or grant
network access to the Python process.

## Synthetic Continuity Mode

If you want a synthetic Frigate stream that completes without requiring real snapshot files from Frigate, publish false-positive update events:

```bash
python scripts/run_issue22_soak.py \
  --backend-url http://test-yawamf:8080 \
  --mqtt-host test-mosquitto \
  --mqtt-port 1883 \
  --birdnet-topic birdnet \
  --mqtt-publish-container test-mosquitto \
  --frigate-event-type update \
  --frigate-false-positive \
  --duration-seconds 1800 \
  --poll-interval-seconds 5
```

This mode is useful for validating MQTT continuity, reconnect behavior, and event-pipeline counter movement.
It does **not** prove that real snapshot classification succeeds under production load.

## Real Snapshot Classification Validation

Synthetic `new` Frigate events do not create real snapshot files in Frigate, so they can be dropped at `classify_snapshot` with `snapshot unavailable`.
To investigate the issue-22 failure mode (`classify_snapshot` timeout under bursty real traffic),
replay retained real event IDs into the disposable instance using a read-only Frigate source or
fixture service. Synthetic continuity counters alone do not establish successful image inference,
correct species, or preservation of a production history.

## Replay Validation Mode

The harness can replay Frigate bird events that still have snapshots and are not yet saved in
the disposable YA-WAMF instance. This exercises more of the ingestion path than synthetic tracker
IDs. A successful replay establishes these observations for the selected events:

1. Frigate event selection from the Frigate API
2. MQTT publish delivery into YA-WAMF
3. Event-pipeline completion
4. Detection persistence in YA-WAMF for the exact replayed Frigate event id

Requirements:

1. Owner auth token for YA-WAMF
2. Reachable Frigate API base URL
3. MQTT broker credentials matching the backend

Example, replay one unsaved Frigate event and disable the continuous synthetic publishers:

```bash
python scripts/run_issue22_soak.py \
  --backend-url http://test-yawamf:8080 \
  --mqtt-host test-mosquitto \
  --mqtt-port 1883 \
  --mqtt-publish-container test-mosquitto \
  --frigate-topic frigate/events \
  --frigate-api-url http://test-frigate:5000 \
  --replay-unsaved-frigate-limit 1 \
  --disable-frigate-publisher \
  --disable-birdnet-publisher \
  --duration-seconds 10 \
  --poll-interval-seconds 1 \
  --min-samples 5 \
  --min-frigate-delta 0 \
  --min-birdnet-delta 0
```

Key result fields for replay mode:

1. `replay.result.target_event_ids`
2. `replay.result.saved_event_ids`
3. `replay.result.missing_event_ids`
4. `event_store.event_count_delta`
5. `evaluation.replay_validation`

If `missing_event_ids` is non-empty, the replay did not persist cleanly and the run should be treated as failed.

## Optional: Add Background Classification Pressure

If owner auth is available (or auth is disabled and owner is implicit), you can periodically trigger unknown-analysis queueing:

```bash
python scripts/run_issue22_soak.py \
  --backend-url http://test-yawamf:8080 \
  --mqtt-host test-mosquitto \
  --mqtt-port 1883 \
  --birdnet-topic birdnet \
  --mqtt-publish-container test-mosquitto \
  --trigger-analysis-interval-seconds 120
```

If authentication is enabled, set `SOAK_AUTH_TOKEN` before running the command.

## Output

By default artifacts are written under:

```text
tmp/issue22-soak/<timestamp>/
```

Key fields in `summary.json`:

1. `status`: `pass` or `fail`
2. `evaluation.failure_reasons`: explicit reasons for failed runs
3. `evaluation.stall_incidents`: time windows with Frigate stall while BirdNET remained active
4. `publishers`: published counts and failures for synthetic traffic generators

## Suggested Issue Comment Template

1. Runtime window (start/end UTC)
2. Command used (redact secrets)
3. `status` from `summary.json`
4. `evaluation.failure_reasons` (if any)
5. Attach `summary.json` and relevant excerpt from `samples.ndjson`

## Important

This harness does not close GitHub issues. A pass applies only to its actual duration, thresholds,
inputs and runtime. It does not prove a reporter's fault is fixed without reproducing their
workload and checking the relevant failure evidence. Remove or recreate the disposable stack's
data after retaining the artifacts; do not run cleanup against your real feeder history.
