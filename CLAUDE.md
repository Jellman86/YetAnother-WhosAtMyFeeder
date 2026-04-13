# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YA-WAMF (Yet Another WhosAtMyFeeder) is a bird classification system that integrates with Frigate NVR to identify birds visiting feeders using machine learning. The system receives MQTT events from Frigate, classifies bird species using local ML models (TFLite/ONNX), correlates with audio detections from BirdNET-Go, and provides a real-time web dashboard with notifications.

**Tech Stack:**
- Backend: Python 3.12 + FastAPI + SQLite + Alembic
- Frontend: Svelte 5 + TypeScript + Tailwind CSS + Vite
- ML: ONNX Runtime / TensorFlow Lite (MobileNetV2, ConvNeXt, EVA-02)
- Messaging: MQTT (aiomqtt) for Frigate events, SSE for frontend updates
- Deployment: Docker Compose with separate backend/frontend containers

## Git Commit Rules

- **Never** add `Co-Authored-By:`, `Co-authored-by:`, or any AI attribution trailer to commit messages.
- **Never** reference Claude, Gemini, or any AI tool in commit messages, PR descriptions, or issue comments.
- Commit messages should read as if written by the project owner.

## Development Commands

### Backend

```bash
cd backend

# Setup
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run development server (with auto-reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head

# Testing
pytest                                    # Run all tests
pytest --cov=app --cov-report=html        # With coverage
pytest tests/test_proxy.py -v             # Specific file
pytest tests/test_proxy.py::test_name -v  # Specific test

# Code quality
ruff check .                              # Linting
```

### Frontend

```bash
cd apps/ui

# Setup
npm install

# Development server (proxies API to localhost:8000)
npm run dev

# Build for production
npm run build

# Type checking
npm run check
```

### Docker

```bash
# Full stack
docker compose up -d
docker compose logs -f
docker compose logs -f yawamf-backend

# Rebuild after changes
docker compose build
docker compose up -d

# Development mode (with hot reload)
docker compose -f docker-compose.dev.yml up -d
```

## Architecture

### Data Flow

```
Frigate (MQTT) → MQTTService → EventProcessor → ClassifierService → DetectionRepository → SQLite
                                     ↓                                      ↓
                              FrigateClient (snapshot)              Broadcaster (SSE)
                              WeatherService                               ↓
                              AudioService (BirdNET)                  Frontend (realtime)
                              TaxonomyService
                              NotificationService
```

### Key Components

**Backend Services** (`backend/app/services/`):
- `mqtt_service.py` - Subscribes to `frigate/events` MQTT topic
- `event_processor.py` - Orchestrates detection pipeline (200+ lines, needs refactoring)
- `classifier_service.py` - ML inference engine (ONNX/TFLite model loading and prediction)
- `frigate_client.py` - Fetches snapshots and clips from Frigate API
- `audio/audio_service.py` - Correlates visual detections with BirdNET-Go audio buffer
- `taxonomy/taxonomy_service.py` - iNaturalist-based scientific ↔ common name mapping
- `ai_service.py` - LLM integration (Gemini/OpenAI) for behavioral analysis
- `broadcaster.py` - Server-Sent Events (SSE) for real-time frontend updates
- `notification_service.py` - Discord, Telegram, Pushover notifications
- `auto_video_classifier_service.py` - Background video frame analysis for higher accuracy
- `model_manager.py` - Model download and management
- `telemetry_service.py` - Anonymous usage metrics (opt-in)

**Backend Routers** (`backend/app/routers/`):
- `events.py` - Detection CRUD, filtering, pagination, deletion
- `species.py` - Species aggregation, statistics, counts
- `settings.py` - Configuration management (read/update config.json)
- `proxy.py` - Frigate media proxy (thumbnails, snapshots, clips with HTTP Range support)
- `stream.py` - SSE endpoint for real-time updates
- `classifier.py` - Model status, health checks
- `ai.py` - LLM behavioral analysis endpoint
- `audio.py` - Recent BirdNET audio detections
- `backfill.py` - Historical Frigate event reprocessing
- `stats.py` - Analytics and metrics
- `models.py` - Model management endpoints

**Frontend Pages** (`apps/ui/src/lib/pages/`):
- `Dashboard.svelte` - Real-time detection grid with SSE
- `Events.svelte` - Paginated detection list with filters
- `Species.svelte` - Species statistics and taxonomy info
- `Settings.svelte` - Configuration UI (camera selection, thresholds, notifications, etc.)

**Frontend Components** (`apps/ui/src/lib/components/`):
- `DetectionCard.svelte` - Individual detection display with video playback
- `VideoPlayer.svelte` - Proxied Frigate clip player with seeking support
- `SpeciesDetailModal.svelte` - Species info modal with LLM analysis
- `Header.svelte` - Navigation and dark mode toggle
- `Footer.svelte` - Footer with version and links

### Database Schema

**Primary Table:** `detections`
- Stores all bird detections with classification scores, Frigate event IDs, camera names, weather data, audio correlation
- `frigate_event` column is UNIQUE - prevents duplicate processing
- `is_hidden` flag for soft deletion
- `audio_confirmed`, `audio_species` for BirdNET-Go correlation
- `scientific_name`, `common_name`, `taxa_id` for taxonomy enrichment
- Video classification fields: `video_analysis_done`, `video_top_species`, `video_avg_score`

**Secondary Table:** `taxonomy_cache`
- Caches iNaturalist API lookups for scientific/common name mapping
- Reduces external API calls

**Migrations:** Managed with Alembic in `backend/migrations/`

### Configuration System

**Priority (highest to lowest):**
1. Environment variables (prefixed with section name, e.g., `FRIGATE__FRIGATE_URL`)
2. `config/config.json` (persisted runtime config)
3. Code defaults in `backend/app/config.py`

**Important:** Settings are read/written through `config.py` which uses Pydantic Settings. The `/api/settings` endpoint reads from and writes to `config.json`. Sensitive fields (API keys, passwords) are redacted as `"***REDACTED***"` in GET responses. The PUT endpoint's `should_update_secret()` helper skips any field that contains the placeholder, so the redacted value is safe to send back — the stored secret will be preserved.

### Authentication

Optional API key authentication via `YA_WAMF_API_KEY` environment variable. When set:
- All API requests must include `X-API-Key` header
- SSE streams authenticate via query parameter
- Frontend shows login screen

API key comparison uses `secrets.compare_digest()` in `auth.py` and `ratelimit.py` — timing-safe.

## Common Development Workflows

### Adding a New Feature

1. **Backend API:**
   - Create endpoint in appropriate router (`backend/app/routers/`)
   - Use repository pattern for data access (`backend/app/repositories/`)
   - Add Pydantic models for request/response in `backend/app/models/`
   - Register router in `backend/app/main.py`
   - Add tests in `backend/tests/`

2. **Frontend:**
   - Add API client function in `apps/ui/src/lib/api.ts`
   - Create/update Svelte component using Svelte 5 runes (`$state`, `$derived`, `$effect`)
   - Use TypeScript interfaces for type safety
   - Follow Tailwind utility-first CSS approach

3. **Service Logic:**
   - Add service in `backend/app/services/`
   - Use async/await for I/O operations
   - Use structlog for logging with context
   - Inject dependencies via function parameters

### Running a Single Test

```bash
cd backend
source venv/bin/activate
pytest tests/test_events.py::test_get_detections -v
```

### Database Migration

```bash
cd backend
source venv/bin/activate

# Auto-generate migration from schema changes
alembic revision --autogenerate -m "add new column"

# Review generated migration in backend/migrations/versions/
# Edit if needed (Alembic doesn't catch everything)

# Apply migration
alembic upgrade head

# Rollback if needed
alembic downgrade -1
```

### Adding a New ML Model

1. Place model files in `data/models/`:
   - `model.tflite` or `model.onnx`
   - `labels.txt` (one label per line)
2. Update `classifier_service.py` if different input size or preprocessing needed
3. Restart backend
4. Use Settings UI to select model

## Code Conventions

### Python (Backend)

- **Async by default:** Use `async def` for all I/O operations (HTTP, database, file access)
- **Type hints everywhere:** Function signatures, class attributes, variables where helpful
- **Repository pattern:** Data access through `DetectionRepository`, not direct SQLAlchemy in routers
- **Error handling:** Raise `HTTPException` for API errors, catch external exceptions and re-raise as HTTP errors
- **Logging:** Use `structlog.get_logger()` with context: `log.info("event", event_id=id, score=0.9)`
- **No blocking I/O:** Never use `open()`, `requests`, or synchronous database calls - use `aiofiles`, `httpx`, and SQLAlchemy async

### TypeScript/Svelte (Frontend)

- **Svelte 5 runes:** Use `$state()`, `$derived()`, `$effect()` instead of `let x = $state(0)` syntax
- **Props:** Define with `let { prop1, prop2 }: Props = $props()`
- **Events:** Use `onclick` attribute, not `on:click` (Svelte 5 change)
- **Types:** Define interfaces for all data structures, import from `api.ts`
- **API calls:** All API interactions through functions in `api.ts`, not inline fetch calls

### Testing

- **Backend:** Use `pytest` with `TestClient` from FastAPI
- **Mocking:** Mock external services (Frigate, MQTT, LLM APIs) using `unittest.mock.patch`
- **Coverage:** Aim for >80% coverage on new code
- **Current state:** Only ~5% E2E tests exist, no unit tests for most services (technical debt)

## Important Constraints

### Fast Path Optimization
The system supports "Trust Frigate Sublabels" mode where Frigate's built-in bird classification is used directly, skipping local ML inference. This is controlled by `settings.classification.trust_frigate_sublabels`.

### Video Clip Fetching
Can be disabled via `settings.frigate.clips_enabled` to save bandwidth. Video proxy in `routers/proxy.py` supports HTTP Range requests for seeking.

### Auto Video Analysis
Background task that downloads full video clips and analyzes multiple frames for higher accuracy. Managed by `auto_video_classifier_service.py`. Uses temporal ensemble logic to refine detections.

### BirdNET-Go Integration
Audio detections are buffered in memory (configurable size) and correlated with visual detections by timestamp proximity. Audio service maintains a deque of recent detections.

### Taxonomy Normalization
Scientific and common names are normalized via iNaturalist API lookups, cached in `taxonomy_cache` table. This handles variations like "House Sparrow" vs "Passer domesticus".

### Notification Filtering
Notifications (Discord, Telegram, Pushover) support per-platform filters:
- Minimum confidence threshold
- Species blocklist/allowlist
- Audio-only detections
- New species alerts

## Known Issues & Technical Debt

See `DEVELOPER.md` section "Known Issues & Technical Debt" for comprehensive list. Active items:

1. **EventProcessor refactoring needed** - `_process_event_payload()` in `event_processor.py` is ~168 lines; decomposition into smaller methods would improve readability and testability.

## File Locations

- **Configuration:** `config/config.json` (persisted), `.env` (Docker environment)
- **Database:** `data/speciesid.db` (SQLite)
- **ML Models:** `data/models/` (model.tflite, labels.txt, onnx files)
- **Migrations:** `backend/migrations/versions/`
- **Tests:** `backend/tests/`
- **Static Assets:** `apps/ui/public/` (icons, images)

## External Integrations

- **Frigate NVR:** MQTT events on `frigate/events`, HTTP API for media (`/api/events/{id}/snapshot.jpg`)
- **BirdNET-Go:** MQTT audio detections on configurable topic (default: `birdnet/text`)
- **iNaturalist:** Taxonomy API for name normalization
- **Weather APIs:** Local weather data enrichment (OpenWeatherMap or similar)
- **LLMs:** Google Gemini or OpenAI for behavioral analysis
- **BirdWeather:** Optional detection reporting to community science platform
- **Home Assistant:** Custom integration via `custom_components/yawamf/`

## Performance Considerations

- **SSE Broadcasting:** Use `Broadcaster` service to fan out events to multiple clients efficiently
- **Media Caching:** `media_cache.py` caches Frigate responses to reduce load
- **Batch Operations:** Frigate clip availability checks are batched in `events.py`
- **Model Loading:** Models loaded once at startup, not per-request
- **Database Queries:** Use pagination and limits (default: 50 detections per page)

## Security Notes

- **Path Traversal:** Event IDs used in media cache paths - ensure sanitization
- **MQTT Auth:** Support for username/password auth to MQTT broker
- **Frigate Auth:** Support for Bearer token auth to Frigate API
- **API Key:** Optional password protection for entire application
- **CORS:** Frontend and backend run on different ports, CORS configured in `main.py`
- **Markdown Injection:** Telegram notifications may be vulnerable to species name injection (escape markdown special chars)

## Troubleshooting

**No detections appearing:**
- Check MQTT connection: `docker compose logs yawamf-backend | grep MQTT`
- Verify Frigate is publishing to `frigate/events`
- Confirm camera is in configured camera list (Settings)
- Check model is loaded: `GET /api/classifier/status`

**Frontend not loading:**
- Verify backend is healthy: `curl http://localhost:8946/api/classifier/status`
- Check CORS configuration in `backend/app/main.py`
- Inspect browser console for errors

**Database errors:**
- Run migrations: `docker compose exec yawamf-backend alembic upgrade head`
- Check database permissions on `data/speciesid.db`
- Look for schema mismatches between `db_schema.py` and actual table

**Classification failures:**
- Verify model files exist: `ls data/models/`
- Check model format matches classifier type (TFLite vs ONNX)
- Review classifier logs for shape/type mismatches
