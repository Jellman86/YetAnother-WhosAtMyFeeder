# YA-WAMF Developer Guide

> Complete guide for developers maintaining or extending Yet Another WhosAtMyFeeder

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Data Flow](#data-flow)
4. [Development Setup](#development-setup)
5. [Backend Development](#backend-development)
6. [Frontend Development](#frontend-development)
7. [Database](#database)
8. [API Reference](#api-reference)
9. [Configuration](#configuration)
10. [Testing](#testing)
11. [Deployment](#deployment)
12. [Common Tasks](#common-tasks)
13. [Troubleshooting](#troubleshooting)
14. [Code Conventions](#code-conventions)
15. [Known Issues & Technical Debt](#known-issues--technical-debt)

---

## Architecture Overview

YA-WAMF is a full-stack application that integrates with [Frigate NVR](https://frigate.video) to detect and classify birds at feeders using machine learning.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Frigate NVR                                │
│  (Detects "bird" objects via MQTT, stores snapshots/clips)          │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ MQTT (frigate/events)
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        YA-WAMF Backend                               │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐     │
│  │ MQTTService │──│EventProcessor│──│  ClassifierService      │     │
│  │ (listener)  │  │ (orchestrator)│  │  (Bird + Wildlife ML)  │     │
│  └─────────────┘  └──────┬───────┘  └─────────────────────────┘     │
│                          │                                           │
│                          ▼                                           │
│  ┌───────────────────────────────────────┐  ┌────────────────────┐  │
│  │     DetectionRepository (SQLite)      │  │   Broadcaster      │  │
│  │     - Stores classifications          │  │   (SSE to clients) │  │
│  └───────────────────────────────────────┘  └────────────────────┘  │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    FastAPI Routers                           │    │
│  │  /events  /species  /settings  /frigate/*  /classifier      │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                      │ HTTP API + SSE
                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        YA-WAMF Frontend                              │
│  ┌──────────┐  ┌────────┐  ┌─────────┐  ┌──────────┐               │
│  │Dashboard │  │ Events │  │ Species │  │ Settings │               │
│  │(realtime)│  │ (list) │  │ (stats) │  │ (config) │               │
│  └──────────┘  └────────┘  └─────────┘  └──────────┘               │
│                     Svelte 5 + TypeScript + Tailwind                │
└─────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Backend** | Python 3.12 + FastAPI | Async web API |
| **ML Inference** | TensorFlow Lite | Bird species classification |
| **Database** | SQLite (aiosqlite) | Persistent detection storage |
| **Message Queue** | MQTT (aiomqtt) | Frigate event subscription |
| **Frontend** | Svelte 5 + TypeScript | Reactive UI |
| **Styling** | Tailwind CSS | Utility-first CSS |
| **Build** | Vite | Fast frontend bundling |
| **Serving** | Nginx | Static file serving |
| **Container** | Docker + Compose | Deployment |

---

## Project Structure

```
YA-WAMF/
├── backend/                      # Python FastAPI backend
│   ├── app/
│   │   ├── main.py              # Application entry, lifespan, routes
│   │   ├── config.py            # Configuration management
│   │   ├── database.py          # SQLite initialization
│   │   ├── models.py            # Pydantic response models
│   │   ├── repositories/
│   │   │   └── detection_repository.py  # Data access layer
│   │   ├── routers/
│   │   │   ├── events.py        # /events endpoints
│   │   │   ├── species.py       # /species endpoints
│   │   │   ├── settings.py      # /settings endpoints
│   │   │   ├── proxy.py         # /frigate/* proxy endpoints
│   │   │   ├── stream.py        # /sse endpoint
│   │   │   └── backfill.py      # /backfill endpoint
│   │   └── services/
│   │       ├── mqtt_service.py      # MQTT subscription
│   │       ├── classifier_service.py # TFLite model loading/inference
│   │       ├── event_processor.py   # Detection processing pipeline
│   │       ├── backfill_service.py  # Historical event processing
│   │       └── broadcaster.py       # SSE event broadcasting
│   ├── tests/                   # pytest test files
│   ├── Dockerfile               # Backend container build
│   └── requirements.txt         # Python dependencies
│
├── apps/ui/                     # Svelte frontend
│   ├── src/
│   │   ├── App.svelte           # Main app + routing
│   │   ├── app.css              # Global styles + Tailwind
│   │   └── lib/
│   │       ├── api.ts           # API client functions
│   │       ├── components/      # Reusable UI components
│   │       │   ├── DetectionCard.svelte
│   │       │   ├── VideoPlayer.svelte
│   │       │   ├── SpeciesDetailModal.svelte
│   │       │   ├── Header.svelte
│   │       │   └── Footer.svelte
│   │       ├── pages/           # Page components
│   │       │   ├── Dashboard.svelte
│   │       │   ├── Events.svelte
│   │       │   ├── Species.svelte
│   │       │   └── Settings.svelte
│   │       └── stores/          # Svelte stores
│   │           └── theme.ts     # Dark mode persistence
│   ├── Dockerfile               # Frontend container build
│   ├── nginx.conf               # Production nginx config
│   ├── vite.config.ts           # Vite build config
│   ├── tailwind.config.js       # Tailwind configuration
│   └── package.json             # Node dependencies
│
├── docker/                      # Additional Docker configs
│   └── mosquitto/               # MQTT broker config
│
├── config/                      # Runtime config (volume mount)
│   └── config.json              # Persisted settings
│
├── data/                        # Persistent data (volume mount)
│   ├── speciesid.db             # SQLite database
│   └── models/                  # Downloaded ML models
│       ├── model.tflite         # Bird classifier (Google AIY)
│       ├── labels.txt           # Bird species labels
│       ├── wildlife_model.tflite # Wildlife classifier (EfficientNet-Lite4, optional)
│       └── wildlife_labels.txt  # ImageNet animal labels (optional)
│
├── docker-compose.yml           # Deployment configuration
├── .env.example                 # Environment template
└── .github/workflows/           # CI/CD pipelines
```

---

## Data Flow

### Bird Detection Pipeline

```
1. Frigate detects motion → identifies "bird" object
                    │
                    ▼
2. Frigate publishes MQTT message to frigate/events topic
   {
     "type": "update",
     "after": {
       "id": "1234567890.abcdef",
       "label": "bird",
       "camera": "birdfeeder_cam",
       "start_time": 1703520000.0,
       ...
     }
   }
                    │
                    ▼
3. MQTTService receives message → passes to EventProcessor
                    │
                    ▼
4. EventProcessor validates:
   - Is label == "bird"?
   - Is camera in configured camera list?
                    │
                    ▼
5. EventProcessor fetches snapshot from Frigate:
   GET {frigate_url}/api/events/{event_id}/snapshot.jpg?crop=1&quality=95
                    │
                    ▼
6. ClassifierService runs TFLite inference on image
   Returns: [{"label": "House Sparrow", "score": 0.87, "index": 42}, ...]
                    │
                    ▼
7. EventProcessor applies filters:
   - Score > classification_threshold?
   - Score > min_confidence?
   - Label not in blocked_labels?
   - Transform unknown labels → "Unknown Bird"
                    │
                    ▼
8. DetectionRepository saves to SQLite:
   INSERT INTO detections (detection_time, score, display_name, ...)
                    │
                    ▼
9. Broadcaster pushes SSE event to connected clients:
   {"type": "detection", "data": {...}}
                    │
                    ▼
10. Frontend Dashboard receives SSE → updates detection grid
```

### API Request Flow

```
Frontend                    Backend                         External
   │                           │                               │
   │  GET /api/events          │                               │
   │ ─────────────────────────>│                               │
   │                           │  Query SQLite                 │
   │                           │──────────────────>            │
   │                           │<──────────────────            │
   │                           │                               │
   │                           │  Batch check clips            │
   │                           │ ─────────────────────────────>│ Frigate
   │                           │<─────────────────────────────│
   │                           │                               │
   │  [DetectionResponse[]]    │                               │
   │<─────────────────────────│                               │
   │                           │                               │
```

---

## Development Setup

### Prerequisites

- Docker & Docker Compose
- Python 3.12+ (for local backend development)
- Node.js 20+ (for local frontend development)
- A running Frigate instance with MQTT enabled

### Quick Start (Docker)

```bash
# Clone repository
git clone https://github.com/Jellman86/YetAnother-WhosAtMyFeeder.git
cd YetAnother-WhosAtMyFeeder

# Create environment file
cp .env.example .env
# Edit .env with your Frigate URL and MQTT settings

# Start services
docker-compose up -d

# View logs
docker-compose logs -f
```

### Local Backend Development

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export FRIGATE__FRIGATE_URL=http://your-frigate:5000
export FRIGATE__MQTT_SERVER=your-mqtt-broker

# Run with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Local Frontend Development

```bash
cd apps/ui

# Install dependencies
npm install

# Start dev server (proxies API to localhost:8000)
npm run dev

# Build for production
npm run build
```

### Running Both Locally

Terminal 1 (Backend):
```bash
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Terminal 2 (Frontend):
```bash
cd apps/ui && npm run dev
# Opens at http://localhost:5173
```

---

## Backend Development

### Adding a New API Endpoint

1. **Create or modify router** in `backend/app/routers/`:

```python
# backend/app/routers/example.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class ExampleResponse(BaseModel):
    message: str
    count: int

@router.get("/example", response_model=ExampleResponse)
async def get_example():
    """Endpoint description for OpenAPI docs."""
    return ExampleResponse(message="Hello", count=42)
```

2. **Register router** in `backend/app/main.py`:

```python
from app.routers import example

app.include_router(example.router, prefix="/api", tags=["example"])
```

3. **Add tests** in `backend/tests/test_example.py`:

```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_get_example():
    response = client.get("/api/example")
    assert response.status_code == 200
    assert response.json()["message"] == "Hello"
```

### Key Backend Patterns

**Repository Pattern:**
```python
# Data access is isolated in repositories
async with get_db() as db:
    repo = DetectionRepository(db)
    detections = await repo.get_all(limit=50)
```

**Async HTTP Clients:**
```python
# Use httpx for external API calls
async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.get(url, headers=headers)
```

**Error Handling:**
```python
# Use HTTPException for API errors
if not detection:
    raise HTTPException(status_code=404, detail="Detection not found")

# Wrap external calls in try/except
try:
    resp = await client.get(url)
    resp.raise_for_status()
except httpx.TimeoutException:
    raise HTTPException(status_code=504, detail="Request timed out")
except httpx.RequestError:
    raise HTTPException(status_code=502, detail="Failed to connect")
```

**Configuration Access:**
```python
from app.config import settings

# Access configuration values
frigate_url = settings.frigate.frigate_url
threshold = settings.classification.threshold
```

---

## Frontend Development

### Component Structure

Components use Svelte 5 runes syntax:

```svelte
<script lang="ts">
    import { onMount } from 'svelte';
    import type { Detection } from '../api';

    // Props using $props()
    interface Props {
        detection: Detection;
        onclick?: () => void;
    }
    let { detection, onclick }: Props = $props();

    // Reactive state using $state()
    let isLoading = $state(false);
    let error = $state<string | null>(null);

    // Derived values using $derived()
    let confidencePercent = $derived((detection.score * 100).toFixed(0));

    // Side effects using $effect()
    $effect(() => {
        console.log('Detection changed:', detection.frigate_event);
    });

    // Async data fetching
    onMount(async () => {
        isLoading = true;
        try {
            // fetch data...
        } catch (e) {
            error = e.message;
        } finally {
            isLoading = false;
        }
    });
</script>

<div class="card" {onclick}>
    <span>{detection.display_name}</span>
    <span>{confidencePercent}%</span>
</div>
```

### Adding a New Page

1. **Create page component** in `apps/ui/src/lib/pages/`:

```svelte
<!-- NewPage.svelte -->
<script lang="ts">
    import { onMount } from 'svelte';

    let data = $state([]);

    onMount(async () => {
        // Load data
    });
</script>

<div class="container mx-auto p-4">
    <h1 class="text-2xl font-bold">New Page</h1>
    <!-- Page content -->
</div>
```

2. **Add route** in `apps/ui/src/App.svelte`:

```svelte
<script>
    import NewPage from './lib/pages/NewPage.svelte';

    // Add to currentPage logic
</script>

{#if currentPage === 'newpage'}
    <NewPage />
{/if}
```

3. **Add navigation** in Header component

### API Client Pattern

All API calls go through `apps/ui/src/lib/api.ts`:

```typescript
const API_BASE = '/api';

// Helper for error handling
async function handleResponse<T>(response: Response): Promise<T> {
    if (!response.ok) {
        const error = await response.text();
        throw new Error(error || `HTTP ${response.status}`);
    }
    return response.json();
}

// Export typed API functions
export async function fetchEvents(options: FetchEventsOptions = {}): Promise<Detection[]> {
    const params = new URLSearchParams();
    // ... build params
    const response = await fetch(`${API_BASE}/events?${params}`);
    return handleResponse<Detection[]>(response);
}

// URL builders for media
export function getThumbnailUrl(frigateEvent: string): string {
    return `${API_BASE}/frigate/${frigateEvent}/thumbnail.jpg`;
}
```

---

## Database

### Schema

```sql
CREATE TABLE detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    detection_time TIMESTAMP NOT NULL,
    detection_index INTEGER NOT NULL,    -- Model label index
    score REAL NOT NULL,                 -- Confidence 0.0-1.0
    display_name TEXT NOT NULL,          -- Species common name
    category_name TEXT NOT NULL,         -- Same as display_name
    frigate_event TEXT NOT NULL UNIQUE,  -- Frigate event ID
    camera_name TEXT NOT NULL
);

-- Indexes for common queries
CREATE INDEX idx_detections_time ON detections(detection_time DESC);
CREATE INDEX idx_detections_species ON detections(display_name);
CREATE INDEX idx_detections_camera ON detections(camera_name);
```

### Location

- Container path: `/data/speciesid.db`
- Volume mount: `./data:/data`

### Migrations

Currently no migration system. Schema changes require:

1. Stop the application
2. Backup the database: `cp data/speciesid.db data/speciesid.db.backup`
3. Modify `database.py` with new schema
4. Manually alter table or recreate

**TODO:** Implement Alembic for proper migrations.

### Repository Methods

```python
class DetectionRepository:
    async def create(self, detection: Detection)
    async def update(self, detection: Detection)
    async def get_by_frigate_event(self, event_id: str) -> Detection | None
    async def get_all(self, limit, offset, filters...) -> list[Detection]
    async def get_count(self, filters...) -> int
    async def delete_by_frigate_event(self, event_id: str) -> bool
    async def delete_older_than(self, cutoff_date: datetime) -> int
    async def get_species_counts() -> list[dict]
    async def get_species_basic_stats(species_name: str) -> dict
    async def get_hourly_distribution(species_name: str) -> list[int]
    # ... and more
```

---

## API Reference

### Authentication

No authentication required. The API assumes network-level isolation.

For Frigate proxy endpoints, the backend forwards `Authorization: Bearer {token}` if `FRIGATE__FRIGATE_AUTH_TOKEN` is set.

### OpenAPI Documentation

FastAPI auto-generates OpenAPI docs at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

### Core Endpoints

#### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/events` | List detections (paginated) |
| GET | `/api/events/count` | Count detections |
| GET | `/api/events/filters` | Get available filter options |
| DELETE | `/api/events/{event_id}` | Delete a detection |
| PATCH | `/api/events/{event_id}` | Update species manually |
| POST | `/api/events/{event_id}/reclassify` | Re-run classification |

**Query Parameters for GET /api/events:**
```
limit: int (1-500, default 50)
offset: int (default 0)
start_date: YYYY-MM-DD
end_date: YYYY-MM-DD
species: string
camera: string
sort: "newest" | "oldest" | "confidence"
```

#### Species

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/species` | List species with counts |
| GET | `/api/species/{name}/stats` | Detailed statistics |
| GET | `/api/species/{name}/info` | Wikipedia information |
| DELETE | `/api/species/{name}/cache` | Clear Wikipedia cache |

#### Settings

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/settings` | Get current settings |
| POST | `/api/settings` | Update settings |
| GET | `/api/maintenance/stats` | Database statistics |
| POST | `/api/maintenance/cleanup` | Trigger data cleanup |

#### Frigate Proxy

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/frigate/test` | Test Frigate connection |
| GET | `/api/frigate/config` | Get Frigate config |
| GET | `/api/frigate/{id}/thumbnail.jpg` | Proxy thumbnail |
| GET | `/api/frigate/{id}/snapshot.jpg` | Proxy snapshot |
| GET | `/api/frigate/{id}/clip.mp4` | Stream video clip |
| HEAD | `/api/frigate/{id}/clip.mp4` | Check clip exists |

#### Classifier (Bird Model)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/classifier/status` | Bird model status |
| GET | `/api/classifier/labels` | Available bird species |
| POST | `/api/classifier/download` | Download bird model |

#### Wildlife Classifier (Optional)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/classifier/wildlife/status` | Wildlife model status |
| GET | `/api/classifier/wildlife/labels` | Available animal classes |
| POST | `/api/classifier/wildlife/download` | Download EfficientNet-Lite4 model |
| POST | `/api/events/{id}/classify-wildlife` | Classify detection as wildlife |

#### Streaming

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sse` | Server-Sent Events stream |

**SSE Event Format:**
```json
{"type": "detection", "data": {"frigate_event": "...", "display_name": "...", ...}}
{"type": "connected", "message": "SSE connection established"}
```

#### Backfill

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/backfill` | Process historical events |

**Request Body:**
```json
{
    "date_range": "day" | "week" | "month" | "custom",
    "start_date": "YYYY-MM-DD",  // if custom
    "end_date": "YYYY-MM-DD"     // if custom
}
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FRIGATE__FRIGATE_URL` | `http://frigate:5000` | Frigate instance URL |
| `FRIGATE__FRIGATE_AUTH_TOKEN` | (none) | Bearer token for Frigate |
| `FRIGATE__MQTT_SERVER` | `mqtt` | MQTT broker hostname |
| `FRIGATE__MQTT_PORT` | `1883` | MQTT broker port |
| `FRIGATE__MQTT_AUTH` | `false` | Enable MQTT authentication |
| `FRIGATE__MQTT_USERNAME` | (none) | MQTT username |
| `FRIGATE__MQTT_PASSWORD` | (none) | MQTT password |
| `FRIGATE__CLIPS_ENABLED` | `true` | Enable video clip fetching |
| `MAINTENANCE__RETENTION_DAYS` | `0` | Days to keep data (0=unlimited) |
| `TZ` | `UTC` | Timezone |

### Runtime Configuration (config.json)

```json
{
    "frigate": {
        "frigate_url": "http://frigate:5000",
        "camera": ["birdfeeder_cam"],
        "clips_enabled": true
    },
    "classification": {
        "threshold": 0.7,
        "min_confidence": 0.4,
        "blocked_labels": [],
        "unknown_bird_labels": ["background", "Background"]
    },
    "maintenance": {
        "retention_days": 30,
        "cleanup_enabled": true
    }
}
```

### Configuration Priority

1. Environment variables (highest)
2. config.json file
3. Code defaults (lowest)

---

## Testing

### Running Backend Tests

```bash
cd backend
source venv/bin/activate

# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_proxy.py -v

# Run specific test
pytest tests/test_proxy.py::test_proxy_clip_disabled -v
```

### Test Structure

```python
# tests/test_example.py
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app
from app.config import settings

client = TestClient(app)

def test_endpoint_success():
    """Test successful response."""
    response = client.get("/api/example")
    assert response.status_code == 200
    assert "expected_key" in response.json()

def test_endpoint_with_mock():
    """Test with mocked external service."""
    with patch("app.routers.example.external_service") as mock:
        mock.return_value = {"mocked": "data"}
        response = client.get("/api/example")
        assert response.status_code == 200
```

### Frontend Testing

Currently no frontend tests configured. To add:

```bash
cd apps/ui
npm install -D vitest @testing-library/svelte jsdom
```

Add to `vite.config.ts`:
```typescript
export default defineConfig({
    test: {
        environment: 'jsdom',
        globals: true
    }
});
```

---

## Deployment

### Docker Compose (Production)

```yaml
# docker-compose.yml
services:
  yawamf-backend:
    image: ghcr.io/jellman86/wamf-backend:latest
    ports:
      - "8946:8000"
    volumes:
      - ./config:/config
      - ./data:/data
    environment:
      - FRIGATE__FRIGATE_URL=${FRIGATE_URL}
      # ... other env vars
    networks:
      - yawamf_network
      - external_network  # For Frigate/MQTT access

  yawamf-frontend:
    image: ghcr.io/jellman86/wamf-frontend:latest
    ports:
      - "9852:80"
    depends_on:
      - yawamf-backend
    networks:
      - yawamf_network

networks:
  yawamf_network:
  external_network:
    external: true
    name: ${DOCKER_NETWORK}
```

### Building Images

```bash
# Build backend
docker build -t wamf-backend:local ./backend

# Build frontend
docker build -t wamf-frontend:local ./apps/ui

# Or use compose
docker-compose build
```

### CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/build-and-push.yml`):
- Triggers on push to main
- Builds both containers
- Pushes to GitHub Container Registry
- Tags: `latest` and full commit SHA

---

## Common Tasks

### Adding a New Bird Label Transformation

Edit `backend/app/config.py`:
```python
unknown_bird_labels: list[str] = Field(
    default=["background", "Background", "new_label"],
    ...
)
```

### Downloading a Different ML Model

1. Place model files in `/data/models/`:
   - `model.tflite` - TensorFlow Lite model
   - `labels.txt` - One label per line

2. Restart the backend

### Wildlife Classifier Notes

The wildlife classifier uses EfficientNet-Lite4 trained on ImageNet-1000:
- **Input size:** 300x300 (auto-detected from model)
- **Normalization:** [0, 1] range (different from MobileNet's [-1, 1])
- **Classes:** 1000 ImageNet categories (animals, objects, etc.)
- **Inference:** ~2-3 seconds per image on CPU

The classifier service auto-detects the model type based on input dimensions and applies the correct preprocessing.

### Backing Up Data

```bash
# Stop containers
docker-compose stop

# Backup database
cp data/speciesid.db data/speciesid.db.$(date +%Y%m%d)

# Backup config
cp config/config.json config/config.json.$(date +%Y%m%d)

# Restart
docker-compose start
```

### Viewing Logs

```bash
# All logs
docker-compose logs -f

# Backend only
docker-compose logs -f yawamf-backend

# Last 100 lines
docker-compose logs --tail=100 yawamf-backend
```

### Clearing All Data

```bash
docker-compose down
rm data/speciesid.db
rm config/config.json
docker-compose up -d
```

---

## Troubleshooting

### Backend won't start

1. Check logs: `docker-compose logs yawamf-backend`
2. Verify MQTT connectivity: `docker exec -it yawamf-backend ping mqtt`
3. Check Frigate URL: `curl http://frigate:5000/api/version`

### No detections appearing

1. Verify MQTT messages: Use MQTT Explorer to check `frigate/events`
2. Check camera filter in settings
3. Verify bird detection in Frigate UI
4. Check classifier status: `GET /api/classifier/status`

### Thumbnails not loading

1. Check Frigate proxy: `GET /api/frigate/test`
2. Verify Frigate auth token if used
3. Check browser console for CORS errors

### Classification model not loading

1. Check model files exist: `ls /data/models/`
2. Download default model via Settings UI
3. Check classifier status endpoint

### Database locked errors

1. Stop any concurrent writes
2. Check for orphaned connections
3. Restart backend container

---

## Code Conventions

### Python

- **Formatting:** Follow PEP 8 (TODO: enforce with Ruff)
- **Type hints:** Use everywhere, especially function signatures
- **Async:** Prefer `async def` for I/O operations
- **Docstrings:** Use for public functions and classes
- **Logging:** Use `structlog` with context

```python
import structlog
log = structlog.get_logger()

async def process_event(event_id: str) -> Detection:
    """Process a Frigate event and return the detection.

    Args:
        event_id: The Frigate event identifier

    Returns:
        The saved Detection object

    Raises:
        HTTPException: If event not found or processing fails
    """
    log.info("Processing event", event_id=event_id)
    # ...
```

### TypeScript/Svelte

- **Formatting:** Prettier (via Vite)
- **Types:** Use TypeScript strictly, define interfaces
- **Components:** Use Svelte 5 runes (`$state`, `$derived`, `$effect`)
- **Events:** Use `onclick` not `on:click` (Svelte 5)

```svelte
<script lang="ts">
    interface Props {
        value: string;
        onchange?: (value: string) => void;
    }

    let { value, onchange }: Props = $props();
</script>
```

### Git

- **Commits:** Use conventional commits format
- **Branches:** `main` for production, feature branches for development

```
feat: Add new species filter endpoint
fix: Resolve connection leak in video proxy
docs: Update API documentation
test: Add integration tests for backfill
```

---

## Known Issues & Technical Debt

### High Priority

1. **Minimal test coverage** - Most code paths untested
2. **No database migrations** - Schema changes require manual intervention
3. **Memory-based Wikipedia cache** - Lost on restart
4. **Duplicated Frigate header logic** - In 3 different files

### Medium Priority

1. **No rate limiting** - Could be DoS'd
2. **No API authentication** - Relies on network isolation
3. **Hardcoded model URLs** - Could break if sources change
4. **No frontend error boundaries** - Errors can crash UI
5. **Prometheus metrics stubbed** - Returns static placeholder

### Low Priority

1. **No structured logging config** - All in main.py
2. **Simple client-side routing** - Not a full router library
3. **No offline support** - Requires constant API connection
4. **No i18n** - English only

### Improvement Ideas

1. Add Alembic for database migrations
2. Implement Redis caching for Wikipedia data
3. Add proper health checks with dependency status
4. Create admin API with authentication
5. Add WebSocket support for lower latency updates
6. Implement batch Frigate API calls
7. Add model performance metrics
8. Create plugin system for custom classifiers

---

## Getting Help

- **Issues:** https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues
- **Discussions:** GitHub Discussions
- **Contributing:** See CONTRIBUTING.md

---

*Last updated: December 2025*
