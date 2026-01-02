# YA-WAMF Handoff Documentation

**Date:** 2 January 2026
**Version:** 2.0.0 (Refactored)

## 1. System Overview
Yet Another WhosAtMyFeeder (YA-WAMF) is a sophisticated bird identification system that integrates with Frigate NVR and BirdNET-Go. It uses local AI (TFLite) to classify bird species from Frigate events and correlates them with audio detections for high-confidence identification.

### Key Features
- **Dynamic Model Market**: Switch between "MobileNet V2" (Fast) and "EfficientNet-EdgeTPU-L" (High Accuracy) on the fly.
- **Deep Video Reclassification**: Uses "Temporal Ensemble" logic to analyze video clips frame-by-frame, significantly improving accuracy over single snapshots.
- **Audio-Visual Correlation**: Matches visual bird detections with BirdNET audio events (via MQTT) using a configurable camera-to-sensor mapping.
- **Contextual Intelligence**: Fetches local weather (OpenMeteo) and uses Gemini/OpenAI for behavioral analysis of bird snapshots.
- **Real-time Dashboard**: A "Command Center" UI with live activity histograms, top visitor stats, and immediate feedback.
- **Home Assistant Integration**: A custom component (`yawamf`) providing sensors and cameras for smart home automation.

## 2. Architecture

### Backend (`backend/`)
- **Framework**: FastAPI (Python 3.12).
- **Database**: SQLite (`/data/speciesid.db`) with `aiosqlite` for async access.
- **ML Engine**: TensorFlow Lite (via `tflite-runtime` or `tensorflow-cpu`).
- **Services**:
  - `ClassifierService`: Handles model loading, image preprocessing, and inference (async/threaded).
  - `EventProcessor`: Orchestrates MQTT ingestion, snapshot fetching, classification, and database storage.
  - `ModelManager`: Manages downloading and activating TFLite models from remote sources.
  - `AudioService`: Buffers BirdNET messages for correlation.

### Frontend (`apps/ui/`)
- **Framework**: Svelte 5 (Runes) + Tailwind CSS.
- **State Management**: Reactive `$state` runes and custom stores (`settingsStore`).
- **Communication**: REST API + Server-Sent Events (SSE) for real-time updates.

### Integrations
- **Home Assistant**: `custom_components/yawamf/` connects via REST API to provide:
  - `sensor.last_bird_detected`: Species, confidence, and context attributes.
  - `camera.latest_bird_snapshot`: Always-current image of the last visitor.

## 3. Maintenance & Troubleshooting

### Models
- Models are stored in `/data/models`.
- If the downloader fails, you can manually place `model.tflite` and `labels.txt` in a subfolder (e.g., `/data/models/custom_model/`).
- **High-Res Model**: Uses `EfficientNet-EdgeTPU-L` (300x300 input). Requires `download_model` via the UI.

### Database
- Schema migrations are handled automatically in `database.py` (`init_db`).
- New columns (`is_hidden`, `audio_confirmed`) are added on startup if missing.

### Dependencies
- **OpenCV**: `opencv-python-headless` is required for video frame extraction. It is pinned to `<4.11` to avoid conflicts with `numpy 1.x`.
- **NumPy**: Pinned to `<2.0.0` for TensorFlow compatibility.

## 4. Known Limitations
- **Video Analysis Latency**: Deep reclassification can take 5-10 seconds depending on CPU power. The UI handles this with a loading state.
- **BirdNET Latency**: Audio detections sometimes arrive *after* the visual event. The `EventProcessor` has a buffer window, but extreme delays (>30s) might miss the correlation.

## 5. Future Roadmap Suggestions
- **RTSP Re-streaming**: Proxy the Frigate stream directly to the Dashboard.
- **Cloud Backup**: Optional backup of the SQLite database to Google Drive/S3.
- **Custom Training**: A UI to upload corrected images for re-training a custom TFLite model.

## 6. Commands
- **Start Stack**: `docker compose up -d`
- **Tail Logs**: `docker logs -f yawamf-backend`
- **Rebuild**: `docker compose build` (or via GitHub Actions)
