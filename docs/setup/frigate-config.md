# Recommended Frigate Configuration

To get the best results with YA-WAMF, your Frigate NVR should be configured to capture high-quality snapshots and recordings of birds. Below is a recommended configuration template.

## Global Settings

### 1. MQTT (Required)
YA-WAMF relies on MQTT to know when a bird arrives.
```yaml
mqtt:
  host: mosquitto # Service name in your docker stack
  user: your_user
  password: your_password
```

### 2. Objects
Ensure `bird` is in your tracked objects list.
```yaml
objects:
  track:
    - bird
    - cat # Optional: if you want to use the wildlife classifier
    - dog
```

## Camera-Specific Settings

For each camera pointing at a feeder, use these settings to ensure the AI gets the best possible images.

```yaml
cameras:
  birdcam: # Your camera name
    ffmpeg:
      inputs:
        - path: rtsp://...
          roles:
            - detect
            - record
    
    detect:
      enabled: True
      width: 1280 # Higher resolution detection helps with small birds
      height: 720
      fps: 5

    # --- CRITICAL FOR YA-WAMF ---
    snapshots:
      enabled: True
      timestamp: True
      bounding_box: False # YA-WAMF prefers clean images
      crop: True # Helps the AI focus on the bird
      quality: 95 # High quality is better for species ID
      retain:
        default: 7 # Days to keep snapshots in Frigate

    # --- REQUIRED FOR DEEP VIDEO ANALYSIS ---
    record:
      enabled: True
      retain:
        days: 3
        mode: all # Ensure clips are available for YA-WAMF to scan

    # --- OPTIONAL: TUNING ---
    objects:
      filters:
        bird:
          min_area: 500 # Ignore tiny movements
          min_score: 0.5
          threshold: 0.7
```

## Tips for Success

### 💡 Snapshot Timing
Frigate usually picks the "best" frame for a snapshot based on its own confidence. If you find your snapshots are often "too late" (bird flying away), you can try setting `required_zones` or adjusting motion sensitivity in Frigate to trigger earlier.

### 💡 Use Sublabels
YA-WAMF can push species names back to Frigate. If you enable this in YA-WAMF settings, make sure your Frigate UI is configured to display sublabels so you can see the bird names directly in the NVR.

### 💡 High Resolution
While Frigate's detection model often runs at a low resolution (e.g., 320x320), YA-WAMF's high-accuracy models (EVA-02) perform much better if the source snapshot is clear and high-resolution. Using a 720p or 1080p "detect" stream is recommended for birding cameras.
