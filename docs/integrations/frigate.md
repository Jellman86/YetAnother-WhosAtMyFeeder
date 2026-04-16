# Frigate NVR Integration

YA-WAMF is designed to be the perfect companion to [Frigate NVR](https://frigate.video/).

## Prerequisites

Before connecting YA-WAMF to Frigate you need:

- A running Frigate instance accessible from the YA-WAMF container
- An MQTT broker (Mosquitto) that both Frigate and YA-WAMF can reach — see the [MQTT Broker Setup](../setup/mqtt-broker.md) guide if you don't have one yet
- All three containers (Frigate, Mosquitto, YA-WAMF) on the same Docker network

## MQTT Configuration

YA-WAMF listens for events published by Frigate on the `frigate/events` topic. Ensure your Frigate `config.yml` has MQTT enabled with `topic_prefix: frigate`:

```yaml
mqtt:
  enabled: true
  host: mosquitto        # service name in your docker-compose
  port: 1883
  topic_prefix: frigate  # YA-WAMF expects frigate/events
  # Only needed if your broker requires authentication:
  user: YOUR_USERNAME
  password: YOUR_PASSWORD
```

> The `topic_prefix` must be `frigate` (the default). YA-WAMF subscribes to `{topic_prefix}/events`.

See the full [Recommended Frigate Config](../setup/frigate-config.md) for optimized snapshot, recording, and detection settings.

## API Connection

In YA-WAMF, set **Settings > Connections > Frigate URL** to the internal URL of your Frigate instance (e.g., `http://frigate:5000`). The backend uses the Frigate HTTP API to fetch:

- **Snapshots** — the high-quality still image for each bird event
- **Video clips** — used for Deep Video Analysis and Full-visit clips
- **Config** — to auto-discover your configured camera names

## Sublabel Proxy

When YA-WAMF identifies a species with high confidence, it pushes the label back to Frigate as a **sublabel**. This lets you see the species name directly in the Frigate UI and use it in Frigate's own notification rules and filters.

This can be disabled in **Settings > Detection** if you do not want YA-WAMF writing back to Frigate events.

## Camera Selection

After connecting, go to **Settings > Connections** and select which Frigate cameras YA-WAMF should monitor. Only events from selected cameras are processed.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| No detections appearing | MQTT not connected | Check `docker compose logs yawamf \| grep -i mqtt` — you should see `Connected to MQTT topic=frigate/events` |
| Events received but no clips | Frigate recording not enabled | Enable `record: enabled: True` and set `continuous.days: 1` in Frigate config |
| Detections missing for brief visits | `detect.fps` too low | Set `detect.fps` to match your sub-stream's native frame rate (10–15 FPS) so brief events are confirmed across multiple frames |
| `404` when fetching clips | Frigate URL wrong or not on same network | Confirm `FRIGATE_URL` and that all containers share a Docker network |
