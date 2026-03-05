# Issue #22 Soak Harness

This harness validates sustained MQTT ingestion continuity and pressure behavior for issue `#22` ("Termination of event flow from frigate").

It is designed to produce evidence artifacts for issue comments without automatically closing the issue.

## What It Does

1. Publishes synthetic Frigate + BirdNET MQTT traffic at configurable rates.
2. Polls backend `/health` on a fixed interval.
3. Detects potential stall conditions where:
   - BirdNET traffic is still active/increasing, and
   - Frigate topic age is stale and Frigate count stops increasing.
4. Writes machine-readable artifacts:
   - `samples.ndjson` (per-poll samples/errors/triggers)
   - `summary.json` (pass/fail evaluation + thresholds + publisher stats)

## Prerequisites

1. YA-WAMF backend is running and reachable.
2. MQTT broker is reachable from this host.
3. `paho-mqtt` is available (recommended: use backend venv Python).

Example Python path:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python
```

## Basic Run

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python \
  /config/workspace/YA-WAMF/scripts/run_issue22_soak.py \
  --backend-url http://127.0.0.1:8946 \
  --mqtt-host 127.0.0.1 \
  --mqtt-port 1883 \
  --duration-seconds 1800 \
  --poll-interval-seconds 5
```

## Optional: Add Background Classification Pressure

If owner auth is available (or auth is disabled and owner is implicit), you can periodically trigger unknown-analysis queueing:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python \
  /config/workspace/YA-WAMF/scripts/run_issue22_soak.py \
  --backend-url http://127.0.0.1:8946 \
  --mqtt-host 127.0.0.1 \
  --mqtt-port 1883 \
  --trigger-analysis-interval-seconds 120
```

If auth is enabled, pass:

```bash
--auth-token <owner_jwt>
```

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

This harness **does not** close GitHub issues and should not be used as an auto-close mechanism.
