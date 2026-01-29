# Recommended Frigate Configuration

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
    - cat # Optional: if you want to use the wildlife classifier
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
      fps: 5

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
      retain:
        days: 3
        mode: all # Ensure clips are available for YA-WAMF to scan

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

### 📷 Snapshot Resolution
While Frigate's detection model often runs at a low resolution (e.g., 320x320), YA-WAMF's high-accuracy models (EVA-02) perform much better if the source snapshot is clear. Ensure your `detect` role is assigned to a stream with decent resolution (720p or higher) for the best identification results.

### 🎥 Record Mode
YA-WAMF's **Deep Video Analysis** requires access to the recording files. You must have `record: enabled: True` and I recommend `mode: all` for at least a few days to ensure the system can go back and re-analyze any event you click on.
