# Frigate NVR Integration

YA-WAMF is designed to be the perfect companion to [Frigate NVR](https://frigate.video/).

## MQTT Configuration
YA-WAMF listens for events published by Frigate. Ensure your Frigate configuration has MQTT enabled:

```yaml
mqtt:
  host: your_broker_ip
  user: your_user
  password: your_password
```

YA-WAMF subscribes to `{main_topic}/events`. By default, this is `frigate/events`.

## API Connection
The backend uses the Frigate HTTP API to fetch:
- **Snapshots:** High-quality images of the bird.
- **Video Clips:** Used for Deep Video Analysis.
- **Config:** To auto-discover your camera names.

## Sublabel Proxy
If YA-WAMF identifies a species with high confidence, it will **push the label back to Frigate** as a "sublabel". This allows you to see the species name directly in the Frigate UI and use it for Frigate's own notifications and filters.
