# Recommended Frigate Configuration

> **Frigate version:** This guide targets **Frigate 0.17+**. If you are on an older version, the `record` section structure differs — see the [Frigate updating guide](https://docs.frigate.video/frigate/updating/) before upgrading.

To get the best results with YA-WAMF, your Frigate NVR should be configured to capture high-quality snapshots and recordings of birds. Using **go2rtc** is highly recommended for low-latency streaming and efficient handling of multiple roles (detect, record, etc.).

## Full Configuration Example (`config.yml`)

Merge this example into your existing Frigate configuration, replacing camera
addresses and credentials. Keep any existing detector and hardware-acceleration
settings; the example focuses on bird inputs and media retention.

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
    # Add other labels your detector supports if needed.
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
      fps: 5 # Start conservatively; raise only with measured detector headroom

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

    # --- RECORDINGS FOR VIDEO AND FULL-VISIT CLIPS ---
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
          threshold: 0.5   # Median tracked-object score to become a true positive.
                           # Lowering this can keep brief birds but also admits more false positives.
```

> For a bird feeder you usually want to catch quick visits, so this example lowers `threshold` below Frigate's `0.7` default. See [Detection FPS and Missing Events](#-detection-fps-and-missing-events) below and the [Event Not Found troubleshooting guide](../troubleshooting/frigate-event-not-found.md).

## Why use go2rtc?
Using the `go2rtc` section in Frigate provides several major benefits:
1. **Stream reuse:** Frigate can reuse the camera feed for detection, recording and live view.
2.  **Resource Efficiency:** Connects to your camera once and redistributes the stream internally to multiple Frigate roles (`detect`, `record`), reducing the load on your camera hardware.
3.  **Stability:** Handles stream reconnections much more gracefully than basic FFmpeg inputs.

## Important Considerations

### 🎯 Detection FPS and Missing Events
A brief detection may produce MQTT activity without usable retained media later.
Check the event in Frigate before assuming YA-WAMF lost it: false-positive filtering,
short tracking, disabled snapshots, retention expiry and camera outages can all
leave a snapshot or clip unavailable.

Frigate has separate tracking and confidence controls:

- `min_score` rejects low-scoring individual detections. `threshold` compares the
  tracked object's computed median score with the true-positive threshold. Lower
  settings can retain more brief birds but also admit more false positives; they
  do not guarantee every event will have media. See
  [Frigate's object-score reference](https://docs.frigate.video/configuration/object_filters/#object-scores).
- `detect.fps` determines the processed-frame rate. Start with `5` and increase only
  if brief birds are missed and the detector has headroom. Check initialization,
  skipped frames and detector latency rather than treating a higher rate as a fix
  for expired recordings.

YA-WAMF classifies available input and stores photographs for retained detections.
Clip copies are optional, recordings may still be finalizing, and unavailable media
is retried within bounded limits; arrival of MQTT does not guarantee an immediate
clip or a saved detection. See the
[Event Not Found guide](../troubleshooting/frigate-event-not-found.md).

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
`bounding_box: False`, and `crop: False`. Completed-event query transformations depend on the Frigate
version and whether a clean saved snapshot is available, so YA-WAMF deliberately requests the
uncropped representation and reconstructs the tracked-object crop locally.

That completed-event behaviour also applies to detection backfill and snapshot reclassification.
YA-WAMF uses Frigate's square snapshot geometry (1.1× the tracked box with at least 300 pixels of
context) when validated `box` or `region` coordinates are aligned with that saved snapshot. This
restores the input supplied to live classification and is independent of the model's optional local
crop-detector policy. A live/pre-cropped snapshot is not cropped twice, and a full frame sampled from
another recording moment does not reuse the final event box. The resulting classification then passes
through exactly the same confidence and filtering gate as a live detection; below-floor results remain
visible in the backfill reason counts rather than being stored under a different historical-only rule.

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
**Auto Video Analysis** needs a usable retained clip. Continuous recording with
positive retention gives the broader coverage needed by **Full-visit clips** and
recording-frame workflows. Keep `record.enabled: True`, a `record` FFmpeg role and
positive `continuous.days` on every selected camera when enabling full visits.
Longer continuous retention is optional and costs more storage. `mode: all` under
alerts/detections retains their overlapping segments, rather than guaranteeing
an uninterrupted timeline between those events. See
[Frigate recording retention](https://docs.frigate.video/configuration/record/).

The optional **Full-visit clips** feature uses the same recording store, but proxies a longer camera-level window around the detection time and persists that result locally in YA-WAMF. In YA-WAMF, this is gated in **Settings → Connection → Frigate** and only becomes switchable when **every selected camera** is enabled, has an FFmpeg input with the `record` role, has recording enabled, and inherits or declares a positive `record.continuous.days` value. The UI reports the guaranteed minimum continuous retention across those cameras and names each camera whose configuration is incomplete.

Frigate treats continuous, motion, alert, and detection retention as separate tiers. Keeping alerts or detections for 30 days does **not** provide an uninterrupted 30-day timeline: with `continuous.days: 0`, only matching event segments survive. YA-WAMF may keep a playable partial event clip as a fallback, but it does not advertise that as reliable Full-visit coverage because the requested pre/post window can start late or end early. See Frigate's [recording retention documentation](https://docs.frigate.video/configuration/record/) for the upstream semantics.

Important behavior:
- In-browser playback uses Frigate's HLS VOD endpoint when it is available. Safari and iOS use
  native HLS; other supported browsers use Media Source Extensions through `hls.js`. Cached,
  archived and downloaded clips continue to use YA-WAMF's MP4 endpoint, which is also the automatic
  fallback for older Frigate versions without HLS VOD support.
- When recording clips are enabled and YA-WAMF's local media folder is writable, YA-WAMF automatically tries to generate a full-visit clip after eligible Frigate `end` events. It waits beyond the requested end timestamp so Frigate can finalize the newest segment, validates the resulting duration, and makes bounded delayed attempts to upgrade a partial result.
- Recording downloads are written to a staging file. A validated candidate replaces the live cache atomically only when it is longer, so a failed or shorter retry cannot corrupt or shorten an existing playable visit.
- YA-WAMF's normal clip route (`/api/frigate/{event_id}/clip.mp4`) prefers a persisted recording automatically. A near-complete recording is presented as **Full visit**; a shorter but decodable recording remains playable and is explicitly presented as **Partial visit** instead of silently falling back to the much shorter event clip.
- The requested recording window is configurable in YA-WAMF with sane defaults of `30` seconds before the detection and `90` seconds after it, for a default target window of about `120` seconds total.
- A legacy or previously cached partial clip can still be shorter. The upgrade budget is deliberately bounded and expires after a day so reconciliation can try again without creating an endless download loop. With current capability validation and positive continuous retention, newly requested windows should have contiguous source coverage unless Frigate is still writing the newest segment, emergency storage cleanup has removed footage, or the camera/recording process was offline.

### ⏱️ “My clips are too short” / “My events are missing”
This is usually expected for birds. Much like the British summer, bird visits tend to be over before you've had time to put the kettle on.

Frigate “events” have a `start_time` and `end_time`. If the bird only triggers motion/detection for 1-3 seconds, the event is only 1-3 seconds long, and the event clip can be very short.

If you want more context around each detection, configure `record.alerts.pre_capture` / `post_capture` and `record.detections.pre_capture` / `post_capture` (example above). A common setup is `pre_capture: 5` and `post_capture: 25` to target roughly 30 seconds total context.

If events are **missing entirely** (YA-WAMF shows detections but Frigate returns 404 for event details and clips), see the [Detection FPS and Missing Events](#-detection-fps-and-missing-events) section above. Check tracking/score filters, snapshot and recording settings, retention expiry, and
recent camera/network outages. Positive continuous retention provides source footage
for recording workflows, but cannot recover footage from a camera that was offline.
