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
    birdcam_sub: # Your camera's lower-resolution sub-stream (optional, for detection)
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
        - path: rtsp://localhost:8554/birdcam_sub # Close feeder: use a sufficiently detailed sub-stream
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
      clean_copy: True # Gives YA-WAMF Frigate's unmodified final best frame
      timestamp: False
      bounding_box: False
      crop: False # YA-WAMF applies Frigate's exact tracked box itself
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
          min_score: 0.45  # per-frame floor to start tracking (Frigate default 0.5)
          threshold: 0.5   # MEDIAN score needed for Frigate to SAVE the object as an event
                           # (Frigate default 0.7). Lower = brief visits persist instead of
                           # becoming "event not found"; raise toward 0.7 for fewer, stricter events.
```

> For a bird feeder you usually want to catch quick visits, so this example lowers `threshold` below Frigate's `0.7` default. See [Detection FPS and Missing Events](#-detection-fps-and-missing-events) below and the [Event Not Found troubleshooting guide](../troubleshooting/frigate-event-not-found.md).

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

There are two levers, and it is easy to change the wrong one:

- **`threshold`** (median score to *save* the object as an event) is the main control. A brief bird fires MQTT but only becomes a persistent event once its median crosses `threshold`. **Lower `threshold` (e.g. `0.5`) to keep brief visits**; raising it *increases* "event not found", it does not reduce it.
- **`detect.fps`** and **`detect.min_initialized`** control how quickly an object starts being tracked. Higher fps lets a brief bird reach its `min_initialized` frame count sooner (5 frames = 0.5 s at 10 fps). Frigate now recommends `fps: 5` and derives `min_initialized` as ½ the fps; raise fps only if your detector has headroom, and keep `min_initialized` low if you want brief visits tracked.

Whatever you choose, YA-WAMF caches the snapshot and clip the instant the MQTT event arrives, so brief visits are still classified even when Frigate never persists the event. Full explanation: [Frigate "Event Not Found" guide](../troubleshooting/frigate-event-not-found.md).

### 📷 Detection stream and snapshot resolution

Frigate chooses its best event frame from the stream assigned the `detect` role. A close feeder can
usually use a 720p or 1080p sub-stream to save decode and detector work. Do not use a very small
sub-stream merely because one exists: if birds are distant or occupy only a few pixels, assign
`detect` to the main stream (it may share the same input as `record`) and cap `detect.fps` at the
lowest rate that still catches brief visits. This trades additional decode/detection cost for the
pixels needed by both Frigate tracking and species classification; verify `process_fps`, skipped
frames, and detector latency after the change.

Frigate 0.17 [selects one best frame over the completed track](https://docs.frigate.video/configuration/snapshots/).
YA-WAMF fetches its unannotated,
uncropped, full-resolution clean copy, anchors a crop to Frigate's final tracked box, and scores that
against independent recording frames. Keep `snapshots.clean_copy: True`, `timestamp: False`,
`bounding_box: False`, and `crop: False`. Frigate ignores snapshot query overrides after an event
ends, so a pre-cropped regular snapshot is not a safe substitute for the clean copy.

### Reolink 6MP/4K cameras

For older high-resolution RLC-8xx cameras, Frigate's current
[camera-specific guidance](https://docs.frigate.video/configuration/camera_specific/#reolink-cameras)
recommends RTSP. In the camera, select constant bitrate (`On, fluency first` on supported Reolink firmware),
disable smart `+` codecs, and set the I-frame interval/interframe space to `1x` (the frame rate).
Use the highest useful main-stream bitrate for recording and distant-subject detection. H.264 is the
most broadly playable codec; if a 4K mode requires H.265, confirm the browsers used for playback can
decode it. Frigate's [live-view guidance](https://docs.frigate.video/configuration/live/) recommends
AAC as the most compatible audio format, and `preset-record-generic-audio-copy` avoids
unnecessary transcoding when the camera already emits AAC.

### 🎥 Record Mode (Frigate 0.17+)
YA-WAMF's **Deep Video Analysis** requires access to the recording files. You must have `record: enabled: True` and set `continuous.days` to at least `1`; increase it only if you need to re-analyze older events from Frigate rather than YA-WAMF's media cache. Use `mode: all` under `alerts.retain` and `detections.retain` when you want every recording segment overlapping a retained bird event to remain available.

The optional **Full-visit clips** feature uses the same recording store, but proxies a longer camera-level window around the detection time and persists that result locally in YA-WAMF. In YA-WAMF, this is gated in **Settings → Connection → Frigate** and only becomes switchable when **every selected camera** is enabled, has an FFmpeg input with the `record` role, has recording enabled, and inherits or declares a positive `record.continuous.days` value. The UI reports the guaranteed minimum continuous retention across those cameras and names each camera whose configuration is incomplete.

Frigate treats continuous, motion, alert, and detection retention as separate tiers. Keeping alerts or detections for 30 days does **not** provide an uninterrupted 30-day timeline: with `continuous.days: 0`, only matching event segments survive. YA-WAMF may keep a playable partial event clip as a fallback, but it does not advertise that as reliable Full-visit coverage because the requested pre/post window can start late or end early. See Frigate's [recording retention documentation](https://docs.frigate.video/configuration/record/) for the upstream semantics.

Important behavior:
- When recording clips and the YA-WAMF media cache are enabled, YA-WAMF automatically tries to generate a full-visit clip after eligible Frigate `end` events and persists it to the filesystem cache.
- Once that persisted full-visit file exists, YA-WAMF's normal clip route (`/api/frigate/{event_id}/clip.mp4`) prefers it automatically, so the longer clip replaces the short Frigate event clip inside YA-WAMF without altering Frigate's own stored media.
- The requested recording window is configurable in YA-WAMF with sane defaults of `30` seconds before the detection and `90` seconds after it, for a default target window of about `120` seconds total.
- A legacy or previously cached partial clip can still be shorter. With current capability validation and positive continuous retention, newly requested windows should have contiguous source coverage unless Frigate is still writing the newest segment, emergency storage cleanup has removed footage, or the camera/recording process was offline.

### ⏱️ “My clips are too short” / “My events are missing”
This is usually expected for birds. Much like the British summer, bird visits tend to be over before you've had time to put the kettle on.

Frigate “events” have a `start_time` and `end_time`. If the bird only triggers motion/detection for 1-3 seconds, the event is only 1-3 seconds long, and the event clip can be very short.

If you want more context around each detection, configure `record.alerts.pre_capture` / `post_capture` and `record.detections.pre_capture` / `post_capture` (example above). A common setup is `pre_capture: 5` and `post_capture: 25` to target roughly 30 seconds total context.

If events are **missing entirely** (YA-WAMF shows detections but Frigate returns 404 for event details and clips), see the [Detection FPS and Missing Events](#-detection-fps-and-missing-events) section above. This is almost always caused by `detect.fps` being too low, so the bird only appears in a single frame and Frigate never persists the event. Setting `record.continuous.days` to at least `1` also helps, as it ensures recording segments always exist for clip generation.
