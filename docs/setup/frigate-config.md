# Recommended Frigate Configuration

> **Frigate version:** This guide targets **Frigate 0.17+**. If you are on an older version, the `record` section structure differs — see the [Frigate updating guide](https://docs.frigate.video/frigate/updating/) before upgrading.

To get the best results with YA-WAMF, your Frigate NVR should be configured to capture high-quality snapshots and recordings of birds. Using **go2rtc** is highly recommended for low-latency streaming and efficient handling of multiple roles (detect, record, etc.).

## Full Configuration Example (`config.yml`)

Below is a complete, commented configuration optimized for birding.

```yaml
# --- Global Settings ---
mqtt:
  host: mosquitto # Service name in your docker-compose
  user: your_user
  password: your_password

# --- High Performance Streaming (go2rtc) ---
go2rtc:
  streams:
    birdcam_hq: # Your camera's high-resolution stream
      - rtsp://admin:password@192.168.1.10:554/live
    birdcam_sub: # Your camera's low-resolution sub-stream (optional, for detection)
      - rtsp://admin:password@192.168.1.10:554/sub

# --- Global Object Tracking ---
objects:
  track:
    - bird
    - (other objects...)
    - dog

# --- Camera Settings ---
cameras:
  birdcam:
    ffmpeg:
      inputs:
        - path: rtsp://localhost:8554/birdcam_hq
          roles:
            - record
        - path: rtsp://localhost:8554/birdcam_sub # Use sub-stream for detection to save CPU
          roles:
            - detect
    
    detect:
      enabled: True
      width: 1280 # Resolution of your detect stream
      height: 720
      fps: 10 # Match your sub-stream's native FPS (see note below)

    # --- CRITICAL FOR YA-WAMF SNAPSHOTS ---
    snapshots:
      enabled: True
      timestamp: True
      bounding_box: False # YA-WAMF prefers clean images without red boxes
      crop: True # IMPORTANT: Focuses the AI on the bird
      quality: 95 # High quality is better for species identification
      retain:
        default: 7 # Days to keep snapshots in Frigate

    # --- REQUIRED FOR DEEP VIDEO ANALYSIS ---
    record:
      enabled: True
      # Frigate 0.17+ uses tiered retention. Keep at least 1 day of continuous
      # recording so clips are always available, even for very brief events.
      # Increase to 3+ days if you use Deep Video Analysis or backfill.
      continuous:
        days: 1
      # Optional: Add context before/after motion so bird clips aren't "blink-and-you-miss-it".
      # This affects Frigate review/detection recording segments (and therefore what YA-WAMF can analyze),
      # but the raw Frigate event duration can still be short if the bird only appears briefly.
      alerts:
        retain:
          days: 30
          mode: all # Keep all segments overlapping alerts
        pre_capture: 5
        post_capture: 25
      detections:
        retain:
          days: 7
          mode: all # Keep all segments overlapping detections
        pre_capture: 5
        post_capture: 25

    # --- TUNING FOR BIRDS ---
    objects:
      filters:
        bird:
          min_area: 500 # Filter out tiny movements (leaves, etc)
          min_score: 0.5
          threshold: 0.7
```

## Why use go2rtc?
Using the `go2rtc` section in Frigate provides several major benefits:
1.  **Lower Latency:** Provides a much faster stream for the YA-WAMF dashboard.
2.  **Resource Efficiency:** Connects to your camera once and redistributes the stream internally to multiple Frigate roles (`detect`, `record`), reducing the load on your camera hardware.
3.  **Stability:** Handles stream reconnections much more gracefully than basic FFmpeg inputs.

## Important Considerations

### 🎯 Detection FPS and Missing Events
Frigate publishes an MQTT event as soon as a bird is first detected, but **only persists the event to its database once the object has been tracked across multiple frames**. If your `detect.fps` is too low and a bird appears briefly, it may only be captured in a single frame. In that case:
- YA-WAMF receives the MQTT event and can grab the snapshot (served from memory).
- But Frigate never writes the event to its database, so `/api/events/{id}` returns 404 and no clip is available.

**Set `detect.fps` to match your sub-stream's native frame rate** (commonly 10-15 FPS). Higher FPS gives the tracker more frames to confirm the object, making brief detections far more likely to be persisted. Avoid setting it higher than the stream's actual FPS, as Frigate will duplicate frames with no benefit.

### 📷 Snapshot Resolution
While Frigate's detection model often runs at a low resolution (e.g., 320x320), YA-WAMF's high-accuracy models (EVA-02) perform much better if the source snapshot is clear. Ensure your `detect` role is assigned to a stream with decent resolution (720p or higher) for the best identification results.

### 🎥 Record Mode (Frigate 0.17+)
YA-WAMF's **Deep Video Analysis** requires access to the recording files. You must have `record: enabled: True` and set `continuous.days` to at least a few days so the system can go back and re-analyze any event. Use `mode: all` under `alerts.retain` and `detections.retain` to ensure all recording segments overlapping bird events are kept.

The optional **Full-visit clips** feature uses the same recording store, but proxies a longer camera-level window around the detection time instead of Frigate's shorter event clip. In YA-WAMF, this is gated in **Settings → Connection → Frigate** and only becomes switchable when the saved Frigate config indicates that continuous recordings and retention are available for at least one selected camera.

Important behavior:
- It does **not** replace the normal event clip. The default player mode stays `Event clip`, and `Full visit` only appears as a second selectable variant when the longer recording window is actually available for that event.
- The requested recording window is configurable in YA-WAMF with sane defaults of `30` seconds before the detection and `90` seconds after it, for a default target window of about `120` seconds total.
- The actual returned clip can still be shorter if Frigate has no retained recordings for part of that time range.

### ⏱️ “My clips are too short” / “My events are missing”
This is usually expected for birds. Much like the British summer, bird visits tend to be over before you've had time to put the kettle on.

Frigate “events” have a `start_time` and `end_time`. If the bird only triggers motion/detection for 1-3 seconds, the event is only 1-3 seconds long, and the event clip can be very short.

If you want more context around each detection, configure `record.alerts.pre_capture` / `post_capture` and `record.detections.pre_capture` / `post_capture` (example above). A common setup is `pre_capture: 5` and `post_capture: 25` to target roughly 30 seconds total context.

If events are **missing entirely** (YA-WAMF shows detections but Frigate returns 404 for event details and clips), see the [Detection FPS and Missing Events](#-detection-fps-and-missing-events) section above. This is almost always caused by `detect.fps` being too low, so the bird only appears in a single frame and Frigate never persists the event. Setting `record.continuous.days` to at least `1` also helps, as it ensures recording segments always exist for clip generation.
