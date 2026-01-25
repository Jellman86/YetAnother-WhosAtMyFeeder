# YA-WAMF API Documentation

## Overview

YA-WAMF provides a RESTful API for managing bird detections, classifications, and system settings. All API endpoints are prefixed with `/api` and are protected by either **JWT login** or a **legacy API key** (if configured).

**Base URL**: `http://your-server:8000`

**OpenAPI/Swagger Docs**: `http://your-server:8000/docs` (Interactive documentation)

**OpenAPI JSON**: `http://your-server:8000/openapi.json`

## Authentication

YA-WAMF supports two authentication methods:

1. **JWT (recommended):** Login with username/password and send a Bearer token.
2. **Legacy API key (deprecated):** Use `X-API-Key` (or `api_key` query parameter) if `API_KEY` is configured.

### JWT (Recommended)

1. **Login** to obtain a JWT:

```
POST /api/auth/login
{
  "username": "admin",
  "password": "your-password"
}
```

2. **Use the access token** on requests:

```bash
curl -H "Authorization: Bearer YOUR_JWT" http://localhost:8000/api/events
```

### API Key (Legacy)

If `API_KEY` is configured in your environment, requests can authenticate via:

- **Header**: `X-API-Key: your-api-key`
- **Query Parameter**: `?api_key=your-api-key`

**Security Note**: Use header authentication in production. Query parameters may be logged.

### Example

```bash
curl -H "Authorization: Bearer YOUR_JWT" http://localhost:8000/api/events
```

---

## Core Endpoints

### Health Check

**`GET /health`**

Check the health status of the backend service and ML models.

**No authentication required**

**Response**:
```json
{
  "status": "ok",
  "service": "ya-wamf-backend",
  "version": "2.6.3+abc1234",
  "ml": {
    "status": "ok",
    "runtimes": {
      "tflite": {"installed": true, "type": "tflite-runtime"},
      "onnx": {"installed": true, "available": true}
    },
    "models": {
      "bird": {"loaded": true, "runtime": "tflite", "error": null}
    }
  }
}
```

### Version Info

**`GET /api/version`**

Get application version information.

**Response**:
```json
{
  "version": "2.6.3+abc1234",
  "base_version": "2.6.3",
  "git_hash": "abc1234"
}
```

---

## Events & Detections

### List Events (Detections)

**`GET /api/events`**

Retrieve a list of bird detections with optional filtering.

**Query Parameters**:
- `start_date` (optional): ISO 8601 datetime
- `end_date` (optional): ISO 8601 datetime
- `camera` (optional): Camera name filter
- `species` (optional): Filter by species (display_name or scientific_name)
- `min_score` (optional): Minimum confidence score (0.0-1.0)
- `include_hidden` (optional): Include hidden detections (default: false)
- `limit` (optional): Maximum results (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Response**:
```json
[
  {
    "id": 1,
    "frigate_event": "1234567890.123456-abc123",
    "detection_time": "2026-01-09T08:00:00Z",
    "display_name": "Turdus merula",
    "scientific_name": "Turdus merula",
    "common_name": "Eurasian Blackbird",
    "score": 0.95,
    "camera_name": "BirdCam",
    "is_hidden": false,
    "frigate_score": 0.85,
    "temperature": 15.5,
    "weather_condition": "sunny",
    "taxa_id": 12345,
    "video_classification_score": 0.92,
    "video_classification_label": "Turdus merula",
    "video_classification_status": "completed"
  }
]
```

### Get Single Detection

**`GET /api/events/{event_id}`**

Retrieve a specific detection by ID.

**Path Parameters**:
- `event_id`: Frigate event ID (string)

**Response**: Single detection object (same structure as list item above)

### Update Detection

**`PATCH /api/events/{event_id}`**

Update a detection (e.g., hide/unhide, update classification).

**Request Body**:
```json
{
  "is_hidden": true,
  "display_name": "Corrected Species Name"
}
```

**Response**: Updated detection object

### Delete Detection

**`DELETE /api/events/{event_id}`**

Delete a specific detection.

**Response**: `204 No Content`

### Video Reclassification

**`POST /api/events/{event_id}/reclassify`**

Trigger video reclassification for a specific event.

**Path Parameters**:
- `event_id`: Frigate event ID

**Request Body**:
```json
{
  "strategy": "video"
}
```

**Response**:
```json
{
  "status": "started",
  "event_id": "1234567890.123456-abc123"
}
```

---

## Settings

### Get Settings

**`GET /api/settings`**

Retrieve current system settings. **Secrets are redacted.**

**Response**:
```json
{
  "mqtt_server": "mosquitto.local",
  "mqtt_port": 1883,
  "mqtt_password": "***REDACTED***",
  "classification_threshold": 0.5,
  "auto_video_classification": true,
  "display_common_names": true,
  "scientific_name_primary": false,
  "notifications_discord_enabled": true,
  "birdweather_enabled": true
}
```

### Update Settings

**`PUT /api/settings`**

Update system settings. Only provide fields you want to change.

**Request Body**:
```json
{
  "classification_threshold": 0.6,
  "auto_video_classification": false,
  "mqtt_password": "new-password-here"
}
```

**Notes**:
- Secrets must include actual values (not "***REDACTED***")
- Settings are saved to `/config/config.json`
- Changes take effect immediately

**Response**: Updated settings object (with secrets redacted)

### Redact Secrets

**`POST /api/settings/redact`**

Get settings with all secrets redacted (utility endpoint).

**Response**: Settings object with all secrets as "***REDACTED***"

---

## Species & Taxonomy

### List Species

**`GET /api/species`**

Get list of detected species with counts.

**Query Parameters**:
- `start_date` (optional): Filter by date range
- `end_date` (optional): Filter by date range
- `camera` (optional): Filter by camera

**Response**:
```json
{
  "species": [
    {
      "display_name": "Turdus merula",
      "scientific_name": "Turdus merula",
      "common_name": "Eurasian Blackbird",
      "taxa_id": 12345,
      "count": 42,
      "last_seen": "2026-01-09T08:00:00Z"
    }
  ]
}
```

### Get Species Details

**`GET /api/species/{species_name}`**

Get detailed information about a specific species.

**Path Parameters**:
- `species_name`: Scientific or common name

**Response**:
```json
{
  "scientific_name": "Turdus merula",
  "common_name": "Eurasian Blackbird",
  "taxa_id": 12345,
  "taxonomy": {
    "kingdom": "Animalia",
    "phylum": "Chordata",
    "class": "Aves",
    "order": "Passeriformes",
    "family": "Turdidae",
    "genus": "Turdus"
  },
  "detections_count": 42,
  "first_seen": "2026-01-01T10:00:00Z",
  "last_seen": "2026-01-09T08:00:00Z"
}
```

---

## Classification & Models

### Get Classifier Status

**`GET /api/classifier/status`**

Get status of loaded ML models.

**Response**:
```json
{
  "runtime": "tflite-runtime",
  "runtime_installed": true,
  "models": {
    "bird": {
      "loaded": true,
      "error": null,
      "labels_count": 1502,
      "enabled": true,
      "model_path": "/data/models/v2m1.tflite",
      "runtime": "tflite"
    }
  }
}
```

### List Available Models

**`GET /api/models`**

List all available ML models (local and remote).

**Response**:
```json
{
  "models": [
    {
      "id": "v2m1",
      "name": "BirdNET Lite v2.1",
      "runtime": "tflite",
      "size_mb": 45,
      "species_count": 1502,
      "accuracy": "high",
      "installed": true,
      "active": true
    }
  ]
}
```

### Download Model

**`POST /api/models/download`**

Download a model from remote registry.

**Request Body**:
```json
{
  "model_id": "v2m1"
}
```

**Response**:
```json
{
  "status": "downloading",
  "model_id": "v2m1",
  "progress": 0
}
```

### Activate Model

**`POST /api/models/activate`**

Switch to a different model.

**Request Body**:
```json
{
  "model_id": "v2m1"
}
```

**Response**:
```json
{
  "status": "activated",
  "model_id": "v2m1"
}
```

---

## Statistics

### Get Detection Stats

**`GET /api/stats`**

Get detection statistics and analytics.

**Query Parameters**:
- `period` (optional): `day`, `week`, `month`, `year` (default: `week`)
- `camera` (optional): Filter by camera
- `group_by` (optional): `hour`, `day`, `week`, `species`, `camera`

**Response**:
```json
{
  "period": "week",
  "total_detections": 250,
  "unique_species": 18,
  "top_species": [
    {"name": "Turdus merula", "count": 42},
    {"name": "Parus major", "count": 35}
  ],
  "detections_by_day": [
    {"date": "2026-01-08", "count": 35},
    {"date": "2026-01-09", "count": 40}
  ],
  "cameras": {
    "BirdCam": 150,
    "FeederCam": 100
  }
}
```

---

## Media Proxy

### Get Snapshot

**`GET /api/events/{event_id}/snapshot.jpg`**

Get snapshot image for an event (proxied from Frigate or cache).

**Path Parameters**:
- `event_id`: Frigate event ID

**Response**: JPEG image

### Get Clip

**`GET /api/events/{event_id}/clip.mp4`**

Get video clip for an event (proxied from Frigate or cache).

**Path Parameters**:
- `event_id`: Frigate event ID

**Response**: MP4 video

---

## Streaming & Real-time Updates

### Server-Sent Events (SSE)

**`GET /api/sse`**

Subscribe to real-time updates via Server-Sent Events.

**Events**:
- `connected`: Initial connection confirmation
- `detection`: New bird detection
- `detection_updated`: Detection updated
- `reclassification_started`: Video reclassification started
- `reclassification_progress`: Progress update during reclassification
- `reclassification_completed`: Reclassification finished

**Example Event**:
```json
{
  "type": "detection",
  "data": {
    "frigate_event": "1234567890.123456-abc123",
    "display_name": "Turdus merula",
    "score": 0.95,
    "timestamp": "2026-01-09T08:00:00Z",
    "camera": "BirdCam"
  }
}
```

**JavaScript Example**:
```javascript
const eventSource = new EventSource('/api/sse?api_key=your-key');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data);
};
```

---

## Backfill & Maintenance

### Start Backfill

**`POST /api/backfill`**

Reprocess past Frigate events.

**Request Body**:
```json
{
  "start_date": "2026-01-01T00:00:00Z",
  "end_date": "2026-01-09T23:59:59Z",
  "camera": "BirdCam",
  "overwrite": false
}
```

**Response**:
```json
{
  "status": "started",
  "events_to_process": 150
}
```

### Cleanup Old Detections

**`POST /api/maintenance/cleanup`**

Manually trigger cleanup of old detections based on retention policy.

**Response**:
```json
{
  "status": "completed",
  "deleted_count": 42,
  "cache_freed_mb": 150
}
```

---

## AI Features

### AI Chat

**`POST /api/ai/chat`**

Ask questions about your bird detections using AI.

**Request Body**:
```json
{
  "message": "What are the most common birds I've seen this week?"
}
```

**Response**:
```json
{
  "response": "Based on your detections this week, the top 3 birds are...",
  "detections_analyzed": 250
}
```

**Note**: Requires LLM configuration (Gemini/OpenAI)

### AI Naturalist Analysis

**`POST /api/events/{event_id}/analyze`**

Generate (or fetch) the AI Naturalist analysis for a specific detection event.

**Query Params**:

- `force` (boolean, default `false`) - Regenerate analysis even if one already exists.
- `use_clip` (boolean, default `true`) - Prefer video clip frames when available; falls back to snapshot.
- `frame_count` (integer, default `5`, range `1-10`) - Number of frames to extract from the clip.

**Response**:
```json
{
  "analysis": "## Appearance\n- ...\n\n## Behavior\n- ...\n\n## Naturalist Note\n- ...\n\n## Seasonal Context\n- ..."
}
```

**Notes**:
- Requires LLM configuration (Gemini/OpenAI/Claude).
- Owner access is required to generate analysis; guests can view stored analysis in event payloads.
- The response is standardized Markdown with fixed headings: `Appearance`, `Behavior`, `Naturalist Note`, `Seasonal Context`.

---

## Debug Endpoints

### Get Logs

**`GET /api/debug/logs`**

Get recent application logs (last 100 lines).

**Response**:
```json
{
  "logs": [
    "2026-01-09 08:00:00 [info] Detection created",
    "2026-01-09 08:01:00 [info] Video classification completed"
  ]
}
```

### System Info

**`GET /api/debug/system`**

Get system information and resource usage.

**Response**:
```json
{
  "cpu_percent": 15.2,
  "memory_percent": 45.8,
  "disk_usage_percent": 60.5,
  "uptime_seconds": 86400,
  "active_tasks": 3
}
```

---

## Metrics

### Prometheus Metrics

**`GET /metrics`**

Prometheus-compatible metrics endpoint.

**No authentication required**

**Response**: Prometheus text format

```
# HELP events_processed_total Total number of events processed
# TYPE events_processed_total counter
events_processed_total 1234

# HELP detections_total Total number of bird detections
# TYPE detections_total counter
detections_total 567

# HELP api_requests_total Total API requests
# TYPE api_requests_total counter
api_requests_total 8901
```

---

## Error Responses

All endpoints return standard HTTP status codes and error responses:

### 400 Bad Request
```json
{
  "detail": "Invalid parameter: start_date must be ISO 8601 format"
}
```

### 401 Unauthorized
```json
{
  "detail": "Missing credentials"
}
```

### 403 Forbidden
```json
{
  "detail": "Not authorized"
}
```

### 404 Not Found
```json
{
  "detail": "Detection not found"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error"
}
```

---

## Rate Limiting

Rate limiting is applied to login attempts and guest/public access endpoints. Configure public rate limits in **Settings > Security** when exposing your instance.

---

## Best Practices

1. **Use Header Authentication**: Avoid query parameter auth in production
2. **Enable HTTPS**: Always use TLS in production environments
3. **Implement Rate Limiting**: Consider a reverse proxy (nginx) for rate limiting
4. **Monitor Metrics**: Use the `/metrics` endpoint with Prometheus
5. **Use SSE for Real-time**: Subscribe to `/api/sse` instead of polling
6. **Paginate Large Queries**: Use `limit` and `offset` for large result sets
7. **Cache Media**: Enable media cache for faster snapshot/clip access

---

## Client Libraries

### Python Example

```python
import requests

API_URL = "http://localhost:8000"
TOKEN = "your-jwt"

headers = {"Authorization": f"Bearer {TOKEN}"}

# Get recent events
events = requests.get(f"{API_URL}/api/events", headers=headers).json()

print(f"Found {len(events)} events")
```

### JavaScript Example

```javascript
const API_URL = "http://localhost:8000";
const TOKEN = "your-jwt";

async function getDetections() {
  const response = await fetch(`${API_URL}/api/events`, {
    headers: {
      "Authorization": `Bearer ${TOKEN}`
    }
  });
  return await response.json();
}

getDetections().then(data => {
  console.log(`Found ${data.length} events`);
});
```

---

## See Also

- [Getting Started Guide](setup/getting-started.md)
- [Configuration Reference](setup/configuration.md)
- [Frigate Integration](integrations/frigate.md)
- [Troubleshooting](troubleshooting/diagnostics.md)
