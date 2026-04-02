# Issue #33 Harness

This harness validates the two symptoms reported in issue `#33`:

1. live MQTT ingest stalls after running for a while
2. batch video classification accumulates backlog or opens its circuit

It is intentionally separate from the issue `#22` harness because it needs to
exercise both MQTT recovery and the video-classifier queue at the same time.

## What It Does

1. Publishes synthetic Frigate and BirdNET MQTT traffic.
2. Optionally stops the Frigate publisher after a configured delay while BirdNET keeps running.
3. Polls `/health` on a fixed interval.
4. Optionally triggers unknown-analysis queueing to add video-classifier pressure.
5. Fails the run if it sees:
   - Frigate stall incidents while BirdNET remains active
   - too few MQTT stall-recovery reconnects
   - video-classifier circuit openings
   - excessive video pending backlog
   - video failure-count growth

## Basic Run

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python \
  /config/workspace/YA-WAMF/scripts/run_issue33_harness.py \
  --backend-url http://yawamf-backend:8000 \
  --mqtt-host mosquitto \
  --mqtt-port 1883 \
  --birdnet-topic birdnet/text \
  --mqtt-publish-container mosquitto \
  --duration-seconds 900 \
  --poll-interval-seconds 5
```

## Reproduce The Live-Ingest Stall Window

This mode starts both publishers, then stops Frigate after three minutes while
BirdNET continues. That should force the backend into its stall-recovery path.

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python \
  /config/workspace/YA-WAMF/scripts/run_issue33_harness.py \
  --backend-url http://yawamf-backend:8000 \
  --mqtt-host mosquitto \
  --mqtt-port 1883 \
  --birdnet-topic birdnet/text \
  --mqtt-publish-container mosquitto \
  --induce-frigate-stall-after-seconds 180 \
  --min-reconnect-delta 1
```

## Add Video-Queue Pressure

If owner auth is available, periodically trigger unknown-analysis queueing so
the harness can catch the batch-classifier half of issue `#33` too.

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python \
  /config/workspace/YA-WAMF/scripts/run_issue33_harness.py \
  --backend-url http://yawamf-backend:8000 \
  --auth-token <owner_jwt> \
  --mqtt-host mosquitto \
  --mqtt-port 1883 \
  --birdnet-topic birdnet/text \
  --mqtt-publish-container mosquitto \
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
2. `evaluation.stall_incidents`
3. `evaluation.topic_liveness_reconnects_delta`
4. `evaluation.video_circuit_open_observed`
5. `evaluation.max_video_pending_seen`
6. `evaluation.video_failure_count_delta`

## Important

This harness collects evidence only. It does not close GitHub issues.
