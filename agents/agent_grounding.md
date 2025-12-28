# AI Agent Grounding: YA-WAMF

This document provides essential context for AI agents working on the **Yet Another WhosAtMyFeeder (YA-WAMF)** project.

## Project Overview
YA-WAMF is a bird classification system that integrates with **Frigate NVR**. It captures snapshots of bird detections, runs them through a specialized ML classifier, and displays the results in a real-time dashboard.

## Environment & Infrastructure
- **Runtime**: Docker-based environment.
- **Networking**: All containers (`yawamf-backend`, `yawamf-frontend`, `frigate`, `mosquitto`) are on the same Docker network.
- **External Dependencies**:
  - **Frigate**: Available at `http://frigate:5000` (Unauthenticated API).
  - **MQTT**: Broker (e.g., Mosquitto) handles event messages from Frigate.
- **Development Mode**: `docker-compose.yml` is configured to build images from local source code. Backend uses `uvicorn` with `--reload`.

## Tech Stack
- **Backend**: Python 3.12, FastAPI, SQLite (`aiosqlite`), Pydantic.
- **Frontend**: Svelte 5 (using Runes: `$state`, `$derived`, `$effect`), TypeScript, Tailwind CSS.
- **Machine Learning**: TensorFlow Lite (TFLite). Primary model: MobileNet V2 (iNaturalist Birds). Secondary: EfficientNet-Lite4 (Wildlife).
- **Communication**: MQTT (input), SSE (Server-Sent Events for UI updates).

## Key Components & Architecture
- **`backend/app/services/detection_service.py`**: Centralized logic for filtering, relabeling, and persisting detections. **Always use this service** instead of raw repository calls for saving detections.
- **`backend/app/services/event_processor.py`**: Handles real-time MQTT messages from Frigate.
- **`backend/app/services/backfill_service.py`**: Fetches historical events from the Frigate API and processes them.
- **`backend/app/routers/proxy.py`**: Proxies snapshots and video clips from Frigate. Supports HTTP Range requests for video seeking.
- **`backend/app/services/media_cache.py`**: Local caching of snapshots and clips to ensure availability after Frigate's retention period expires.
- **`apps/ui/src/lib/api.ts`**: Strongly typed TypeScript interface for the backend API.

## Core Rules & Conventions
1. **Detections**: Captured via `frigate/events` MQTT topic.
2. **Database**: SQLite database stored at `/data/speciesid.db`.
3. **ML Preprocessing**: Use **Letterbox Resizing** (padding) to maintain aspect ratio before classification.
4. **Logging**: Use `structlog`. Avoid using `event` as a keyword argument in log calls (use `event_id` instead) to prevent conflicts with the log message itself.
5. **Video Handling**: If Frigate returns an empty stream (0 bytes), return a `502 Bad Gateway`.

## Important Files
- `agents/IMPLEMENTATION_LOG.md`: Detailed history of all technical changes and fixes.
- `agents/errors.md`: Current known issues and resolution history.
