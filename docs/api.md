# YA-WAMF API Documentation

This document is a practical map of the YA-WAMF API surface.
For exact request/response schemas, use the runtime OpenAPI docs:

- Swagger UI: `http://<host>:8946/docs`
- OpenAPI JSON: `http://<host>:8946/openapi.json`

If you run the backend directly (without Docker compose frontend/proxy), use port `8000`.

## Base URLs

- Docker compose default backend: `http://<host>:8946`
- Direct backend process: `http://<host>:8000`

All application endpoints are under `/api` except:

- `GET /health`
- `GET /ready`
- `GET /metrics`

## Authentication

YA-WAMF supports:

1. JWT bearer tokens (recommended)
2. Legacy API key (`YA_WAMF_API_KEY`) via `X-API-Key` header or `api_key` query param

### JWT flow

1. Login:

```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "your-password"
}
```

2. Use token:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8946/api/events
```

### Auth status

- `GET /api/auth/status`: returns auth/public-access capability flags used by the frontend.

## Health, Readiness, Version, Streaming

- `GET /health`: process + classifier health.
- `GET /ready`: startup readiness (returns `503` until ready).
- `GET /api/version`: app version metadata.
- `GET /api/sse`: Server-Sent Events stream.
  - Supports bearer token or `?token=<jwt>` for EventSource compatibility.

## Endpoint Map

This is the current route map (grouped). Use OpenAPI for full schemas.

### Authentication

- `POST /api/auth/login`
- `GET /api/auth/status`
- `POST /api/auth/initial-setup`
- `POST /api/auth/logout`

### Events

- `GET /api/events`
- `GET /api/events/count`
- `GET /api/events/filters`
- `GET /api/events/hidden-count` (owner)
- `PATCH /api/events/{event_id}` (owner)
- `DELETE /api/events/{event_id}` (owner)
- `POST /api/events/{event_id}/hide` (owner)
- `POST /api/events/{event_id}/reclassify` (owner)
- `POST /api/events/{event_id}/classify-wildlife` (owner)

### Media Proxy and Share Links

- `GET /api/frigate/{event_id}/snapshot.jpg`
- `GET /api/frigate/{event_id}/clip.mp4`
- `GET /api/frigate/{event_id}/thumbnail.jpg`
- `GET /api/frigate/{event_id}/clip-thumbnails.vtt`
- `GET /api/frigate/{event_id}/clip-thumbnails.jpg`
- `GET /api/frigate/camera/{camera}/latest.jpg`
- `GET /api/frigate/test`
- `GET /api/frigate/config`
- `POST /api/video-share`
- `GET /api/video-share/{event_id}`
- `GET /api/video-share/{event_id}/links`
- `PATCH /api/video-share/{event_id}/links/{link_id}`
- `POST /api/video-share/{event_id}/links/{link_id}/revoke`

### Species and Leaderboard

- `GET /api/species`
- `GET /api/species/search`
- `GET /api/species/{species_name}/stats`
- `GET /api/species/{species_name}/info`
- `GET /api/species/{species_name}/range`
- `DELETE /api/species/{species_name}/cache` (owner)
- `GET /api/leaderboard/species`

### Statistics

- `GET /api/stats/daily-summary`
- `GET /api/stats/detections/daily`
- `GET /api/stats/detections/timeline`
- `GET /api/stats/detections/activity-heatmap`

### Classifier and Models

- `GET /api/classifier/status`
- `GET /api/classifier/labels`
- `GET /api/classifier/wildlife/status`
- `GET /api/classifier/wildlife/labels`
- `GET /api/classifier/debug` (owner)
- `POST /api/classifier/test` (owner)
- `GET /api/classifier/wildlife/debug` (owner)
- `POST /api/classifier/wildlife/test` (owner)
- `POST /api/classifier/wildlife/download` (owner)
- `GET /api/models/available` (owner)
- `GET /api/models/installed` (owner)
- `POST /api/models/{model_id}/download` (owner)
- `GET /api/models/download-status/{model_id}` (owner)
- `POST /api/models/{model_id}/activate` (owner)

### AI

- `POST /api/events/{event_id}/analyze` (owner to generate)
- `GET /api/events/{event_id}/conversation`
- `POST /api/events/{event_id}/conversation` (owner)
- `GET /api/leaderboard/analysis` (owner)
- `POST /api/leaderboard/analyze` (owner)

### Settings and Maintenance

- `GET /api/settings` (owner)
- `POST /api/settings` (owner)
- `POST /api/settings/birdnet/test` (owner)
- `POST /api/settings/mqtt/test-publish` (owner)
- `POST /api/settings/notifications/test` (owner)
- `POST /api/settings/birdweather/test` (owner)
- `POST /api/settings/llm/test` (owner)
- `GET /api/maintenance/taxonomy/status` (owner)
- `POST /api/maintenance/taxonomy/sync` (owner)
- `GET /api/maintenance/stats` (owner)
- `POST /api/maintenance/cleanup` (owner)
- `POST /api/maintenance/purge-missing-clips` (owner)
- `POST /api/maintenance/purge-missing-snapshots` (owner)
- `POST /api/maintenance/analyze-unknowns` (owner)
- `GET /api/maintenance/analysis/status` (owner)
- `GET /api/cache/stats` (owner)
- `POST /api/cache/cleanup` (owner)

### Backfill

- `POST /api/backfill` (owner)
- `POST /api/backfill/async` (owner)
- `GET /api/backfill/status` (owner)
- `GET /api/backfill/status/{job_id}` (owner)
- `POST /api/backfill/weather` (owner)
- `POST /api/backfill/weather/async` (owner)
- `DELETE /api/backfill/reset` (owner)

### Integrations

- Audio:
  - `GET /api/audio/recent`
  - `GET /api/audio/context`
- eBird:
  - `GET /api/ebird/export`
  - `GET /api/ebird/nearby`
  - `GET /api/ebird/notable`
- iNaturalist:
  - `GET /api/inaturalist/status`
  - `GET /api/inaturalist/oauth/authorize`
  - `GET /api/inaturalist/oauth/callback`
  - `DELETE /api/inaturalist/oauth/disconnect`
  - `POST /api/inaturalist/draft`
  - `POST /api/inaturalist/submit`
  - `GET /api/inaturalist/seasonality`
- Email OAuth and testing:
  - `GET /api/email/oauth/gmail/authorize`
  - `GET /api/email/oauth/gmail/callback`
  - `GET /api/email/oauth/outlook/authorize`
  - `GET /api/email/oauth/outlook/callback`
  - `DELETE /api/email/oauth/{provider}/disconnect`
  - `POST /api/email/test`

### Debug (owner)

- `GET /api/debug/config`
- `GET /api/debug/db/stats`
- `GET /api/debug/connectivity`
- `GET /api/debug/fs/models`
- `GET /api/debug/system`

## Rate Limiting

- Login endpoint has strict per-IP limits.
- Guest/public endpoints are rate-limited by public-access settings.
- Video share-link creation is rate-limited.

## Best Practices

1. Prefer JWT auth over legacy API key.
2. Use HTTPS in production.
3. Put YA-WAMF behind a reverse proxy with explicit trusted proxy hosts.
4. Treat Swagger/OpenAPI as canonical for integration code generation.
5. Use SSE (`/api/sse`) for realtime UI updates instead of short polling.

## See Also

- [Getting Started](setup/getting-started.md)
- [Configuration](setup/configuration.md)
- [Authentication & Access](features/authentication.md)
- [Troubleshooting](troubleshooting/diagnostics.md)
