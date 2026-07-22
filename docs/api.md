# YA-WAMF API Documentation

This document is a practical map of the YA-WAMF API surface.

## Swagger / OpenAPI docs

Swagger UI (`/docs`) is served directly by the FastAPI process. How you access it depends on your deployment:

| Deployment | Swagger URL |
|---|---|
| **Monolithic container** (recommended) | Not proxied through nginx — access via `docker exec` or a temporary port-forward. From inside the container: `http://127.0.0.1:8000/docs` |
| **Split deployment (legacy)** | `http://localhost:8946/docs` (backend bound to localhost by default) |
| **Direct backend process** | `http://localhost:8000/docs` |

To inspect the schema from a monolith install without modifying docker-compose:

```bash
docker exec yawamf-monalithic curl -s http://127.0.0.1:8000/openapi.json | python3 -m json.tool | head -40
```

## Base URLs

- Monolithic container (via nginx): `http://localhost:9852` (maps to internal port 8080)
- Split deployment backend: `http://localhost:8946` (bound to localhost by default)
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
# Monolithic deployment (host port 9852):
curl -H "Authorization: Bearer <token>" http://localhost:9852/api/events
# Legacy split deployment (backend exposed on 8946):
# curl -H "Authorization: Bearer <token>" http://localhost:8946/api/events
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
- `POST /api/auth/initial-setup` — available only while
  `auth.initial_setup_complete=false` and no password exists. Enabling auth requires a
  password and returns `access_token`, `token_type`, `username`, and
  `expires_in_hours` so the first-run UI can continue across the newly protected API
  boundary. Skipping auth returns those session fields as `null`. Once either choice
  succeeds, later calls are rejected and authentication changes use the owner-only
  Settings API.
- `POST /api/auth/logout`

### Guided setup

- `GET /api/setup/state` (owner; also reachable before auth is enabled) — returns
  deterministic `ok`, `attention`, or `optional` states for account, connection,
  cameras, classifier, snapshot quality, and integrations. This is saved
  configuration/credential readiness, not a live external-service health check.

### Events

- `GET /api/events`
- `GET /api/events/count`
- `GET /api/events/filters`
- `GET /api/events/hidden-count` (owner)
- `GET /api/events/{event_id}/classification-status` (owner)
- `PATCH /api/events/{event_id}` (owner)
- `PATCH /api/events/bulk/manual-tag` (owner)
- `DELETE /api/events/{event_id}` (owner)
- `POST /api/events/{event_id}/hide` (owner)
- `POST /api/events/{event_id}/favorite` (owner)
- `DELETE /api/events/{event_id}/favorite` (owner)
- `POST /api/events/{event_id}/reclassify` (owner)
- `POST /api/events/{event_id}/classify-wildlife` (owner)

Event rows and `GET /api/events/{event_id}/classification-status` expose
`video_classification_input_source` when YA-WAMF knows which representation produced the retained
analysis result. Current video values are `full_frame`, `frigate_hint_crop`, `model_crop`, or
`provided_crop`. Snapshot fallbacks use their cache/media source, such as `high_quality_snapshot`,
`high_quality_bird_crop`, `frigate_snapshot`, or `frigate_snapshot_cropped`; an additional
model-driven crop is reported as `snapshot_model_crop` or `snapshot_frigate_hint_crop`. The field is
`null` for historical results that predate provenance tracking; clients must not infer crop state
from image dimensions. A trusted upstream label that won because local image evidence did not
clear policy is reported as `frigate_sublabel` rather than as snapshot or video inference.

An HQ baseline built from Frigate's regular ended-event snapshot because the clean copy was absent
uses `hq_candidate_frigate_snapshot_fallback`. It is treated conservatively as already cropped: the
ended-event API ignores crop query overrides, so YA-WAMF must not run localisation a second time.

`POST /api/events/{event_id}/reclassify` returns `status: "success"` and `updated: true` only after
the selected result has been persisted. If all video and snapshot candidates are unusable, it
returns HTTP 200 with `status: "no_result"`, `reason: "no_confident_result"`, and `updated: false`;
the existing species and score are returned unchanged. Media-fetch, decode, and inference faults
remain non-2xx errors.

With `strategy=video`, the request performs temporal analysis whenever a usable video exists. The
source order is complete cached recording, decodable partial cached recording, cached event clip,
then the live Frigate event clip. A snapshot is used only after those sources are absent or fail
validation; a confident snapshot does not short-circuit an available cached video.

### Media Proxy and Share Links

- `GET /api/frigate/{event_id}/snapshot.jpg`
- `GET /api/frigate/{event_id}/snapshot/status` (owner; reports the effective best-available policy)
- `GET /api/frigate/{event_id}/snapshot/candidates` (owner)
  - Candidate rows include optional `crop_strategy` provenance (`native`, `frigate_guided`,
    `sliced_2x2`, or `fast_native`) for model-generated crops, and `frigate_final_box` for the
    completed-track clean-snapshot baseline.
- `GET /api/frigate/{event_id}/snapshot/candidates/{candidate_id}/thumbnail.jpg` (owner)
- `POST /api/frigate/{event_id}/snapshot/apply` (owner)
- `GET /api/frigate/{event_id}/snapshot/original.jpg` (owner)
- `POST /api/frigate/{event_id}/snapshot/hq-bird-crop` (owner; legacy route name, generates the best available HQ image)
- `GET /api/frigate/{event_id}/clip.mp4`
- `GET /api/frigate/{event_id}/recording-clip.mp4`
- `POST /api/frigate/{event_id}/recording-clip/fetch`
- `GET /api/frigate/{event_id}/thumbnail.jpg`
- `GET /api/frigate/{event_id}/clip-thumbnails.vtt`
- `GET /api/frigate/{event_id}/clip-thumbnails.jpg`
- `GET /api/frigate/cameras/status` (owner; normalized camera health from Frigate stats, never cached)
- `GET /api/frigate/camera/{camera}/latest.jpg` (owner; current frame, never cached)
- `GET /api/frigate/test` (owner) — accepts an optional `url` query override for testing
  the value currently being edited without saving it. Stored Frigate credentials are
  forwarded only when the normalized override matches the saved Frigate base URL.
- `GET /api/frigate/config`
- `GET /api/frigate/recording-clip-capability`
- `POST /api/video-share`
- `GET /api/video-share/{event_id}`
- `GET /api/video-share/{event_id}/links`
- `PATCH /api/video-share/{event_id}/links/{link_id}`
- `POST /api/video-share/{event_id}/links/{link_id}/revoke`

The HQ snapshot worker also publishes `crop_policy`, queued final-refresh count, selected-source
counts, outcomes, and recovered job totals under `GET /health` → `high_quality_snapshots`. Its retry state is persisted independently
from species identity, with bounded 5/15/45-minute backoff and a terminal fourth failure; successful
explicit or automatic generation clears the failure state.

Snapshot-candidate `frame_offset_seconds` values are temporal evidence, not presentation metadata.
Automatic crop selection/refinement requires supporting offsets to be at least 250 ms apart;
neighbouring decode fallbacks never become additional votes. Event-clip Frigate boxes are translated
to the nearest timestamped path point. Recording clips do not reuse a static event box when their
timeline start cannot be proven.

Notes:
- `GET /api/frigate/{event_id}/clip.mp4` is the canonical YA-WAMF clip route. When a persisted full-visit clip exists for the event, this route serves that full-visit file before falling back to the shorter Frigate event clip.
- `GET /api/frigate/{event_id}/recording-clip.mp4` remains available as an explicit full-visit route and uses the same persisted `{event_id}_recording.mp4` cache file when ready.
- `POST /api/frigate/{event_id}/recording-clip/fetch` remains available as a manual recovery/warm endpoint, but with recording clips and the media cache enabled YA-WAMF also generates full-visit clips automatically for eligible completed detections.

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
- `POST /api/classifier/classify` (owner)
- `POST /api/classifier/probe` (owner)
- `GET /api/classifier/wildlife/debug` (owner)
- `POST /api/classifier/wildlife/test` (owner)
- `POST /api/classifier/wildlife/download` (owner)
- `POST /api/classifier/download` (owner)
- `GET /api/models/available` (owner)
- `GET /api/models/installed` (owner)
- `GET /api/models/families/resolved` (owner)
- `POST /api/models/{model_id}/download` (owner)
- `GET /api/models/download-status/{model_id}` (owner)
- `POST /api/models/{model_id}/validate` (owner) — trial-activates a classifier, validates every provider in the running image/host/model intersection in isolated processes, compares accelerator output with a CPU baseline, records provider eligibility and median inference latency, chooses the fastest passing provider, and restores the previously active model. Crop-detector artifacts are rejected with `409`.
- `POST /api/models/{model_id}/activate` (owner) — rejected with `409` if the artifact is a crop detector or the classifier has not been validated in the current image on this host (unless it is bundled or already active); after activation succeeds, applies the fastest still-eligible provider recorded by the shared validation engine.

`GET /api/classifier/status` separates packaging, hardware availability, and the
active model session. Important deployment fields are:

| Field | Meaning |
|---|---|
| `image_flavor` | Image-owned runtime family: `full`, `cpu`, `intel`, `cuda`, `rpi`, or `unknown` outside a published image. |
| `packaged_inference_providers` | Providers the image is designed to contain. This does not claim a host device works. |
| `image_flavor_warning` | `selected_provider_not_packaged` when the saved explicit provider is outside this image; otherwise `null`. |
| `active_model_id` | Model saved in persistent configuration. Its files may be unavailable after an image or storage change. |
| `effective_model_id` | Model whose files and preprocessing contract the current runtime actually resolved, including the bundled MobileNet fallback. |
| `runtime` | Active TFLite implementation (`litert`, `tflite-runtime`, `tensorflow`, or `unavailable`); ONNX session details remain in `inference_backend`. |
| `host_available_providers` | Providers packaged in this image whose runtime/device probe passed, before applying a model-specific compatibility filter. Used when choosing a different model. |
| `available_providers` | Providers packaged in this image whose runtime/device probe passed and which the active model supports, ordered with the active recovery path first and other valid manual choices afterwards. |
| `provider_preference_order` | The active provider followed by the concrete providers the current runtime will try if inference recovery is required. This is a subset of `available_providers`. |
| `selected_provider` | Saved preference from configuration. An image mismatch does not rewrite it. |
| `active_provider` / `inference_backend` | Provider and backend used by the loaded model session. |
| `fallback_reason` | Why the active session differs from the selected provider, when known. |

Use these fields together. For example, an Intel image can legitimately report
`intel_gpu` as packaged but omit it from `available_providers` when `/dev/dri`
was not passed through or the active model does not support that provider.
See [Hardware Acceleration](setup/hardware-acceleration.md) for the complete
image/provider contract.

The owner-only model-evaluation API accepts `sweep_devices`, `compat_only`,
`sweep_all_models`, `discover_providers`, and an optional `model_ids` list on
`POST /api/diagnostics/model-eval/runs`. The setup wizard sends its selected installed
model as the sole `model_ids` entry; Diagnostics defaults to installed models and can
opt into downloading the full registry. Compatibility runs publish their normal
summary plus `GET /api/diagnostics/model-eval/runs/{run_id}/{artifact}` with
`artifact=device_matrix.json`. Its provider matrix records image flavor, baseline,
compile/finite-output status, real-image agreement, eligibility, and inference latency.
Compatibility summaries also expose `validated_providers` and `failed_providers` per model; the
fastest passing declared provider becomes the current-image activation recommendation.
`discover_providers=true` additionally probes packaged, host-visible providers omitted by current
model metadata. Passing undeclared rows are reported as `declared: false` and under
`discovered_providers`; they do not widen runtime eligibility until the registry is reviewed.

### AI

- `POST /api/events/{event_id}/analyze` (owner to generate)
- `GET /api/events/{event_id}/conversation`
- `POST /api/events/{event_id}/conversation` (owner)
- `GET /api/leaderboard/analysis` (owner)
- `POST /api/leaderboard/analyze` (owner)

### Settings and Maintenance

- `GET /api/settings` (owner)
- `POST /api/settings` (owner)
- `POST /api/settings/birdnet/test` (owner) — synchronously proves a mock detection can
  enter the audio-correlation buffer and complete a database insert/delete; returns `502`
  rather than a false success when persistence or cleanup fails. The synthetic row and buffer
  entry are removed so the test cannot affect history or audio confirmation.
- `GET /api/settings/birdnet/reachability` (owner) — checks that BirdNET-Go answers over
  HTTP; accepts an optional credential-free HTTP(S) `url` query override so an edited
  value can be tested without saving it.
- `POST /api/settings/mqtt/test-publish` (owner) — JSON body accepts optional `server`,
  `port`, `auth`, `username`, and `password` overrides. Send `{}` to test saved values.
  Empty/redacted passwords retain the stored secret; the probe uses an isolated,
  time-bounded MQTT client and never replaces the live ingest connection.
- `POST /api/settings/notifications/test` (owner)
- `POST /api/settings/birdweather/test` (owner)
- `POST /api/settings/llm/test` (owner) — returns structured AI diagnostic metadata (`provider`,
  `model`, `frame_count`, `failure_stage`, `retryable`, and optional `retry_after_seconds`) for the
  Settings multi-stage test panel. Provider 429 and 503 statuses are preserved.
- `GET /api/maintenance/taxonomy/status` (owner)
- `POST /api/maintenance/taxonomy/sync` (owner)
- `GET /api/maintenance/stats` (owner)
- `POST /api/maintenance/cleanup` (owner)
- `POST /api/maintenance/favorites/clear` (owner)
- `POST /api/maintenance/purge-missing-clips` (owner)
- `POST /api/maintenance/purge-missing-snapshots` (owner)
- `POST /api/maintenance/analyze-unknowns` (owner)
- `GET /api/maintenance/analysis/status` (owner)
- `DELETE /api/maintenance/feedback/clear` (owner)
- `GET /api/cache/stats` (owner)
- `POST /api/cache/cleanup` (owner)

### Backfill

- `POST /api/backfill` (owner) — synchronously imports retained Frigate bird events.
- `POST /api/backfill/async` (owner) — starts the same import as a background job.
- `GET /api/backfill/status` (owner) — returns the latest detection or weather job; `kind` can be
  `detections` or `weather`.
- `GET /api/backfill/status/{job_id}` (owner) — returns one retained in-process job status.
- `POST /api/backfill/weather` (owner) — synchronously fills historical weather fields.
- `POST /api/backfill/weather/async` (owner) — starts weather enrichment as a background job.
- `DELETE /api/backfill/reset` (owner) — irreversibly deletes all detections and cached media after
  cancelling and awaiting in-process backfill work.

Backfill accepts `day`, `week`, `month`, or `custom`. Custom `start_date` and `end_date` values are
calendar dates in the browser timezone, and the final day is inclusive. Detection import is
idempotent by Frigate event ID: a stronger image result can update classification fields, but it
preserves existing audio confirmation, weather, same-species taxonomy, the strongest Frigate score,
and sublabel evidence. A valid Frigate bird event with a classifier result below the absolute
confidence floor is persisted as `Unknown Bird` rather than counted as imported and then discarded.
For completed clean-copy snapshots, valid Frigate box/region metadata guides crop-enabled models;
already-cropped and temporally unaligned cached images do not receive those coordinates. Taxonomy
from a replaced species is cleared rather than attached to the new identity. Missing cached snapshots
can still be repaired for an existing row. Frigate history fetch or pagination failures fail the job
explicitly; partial history is never reported as a completed empty import. Job status includes
`last_progress_at`, structured skip/error reason counts, and a terminal message. A completed detection
import queues an only-missing weather pass when the maintenance lane becomes available.

### Jobs

- `GET /api/jobs` (owner) — returns the current server-owned background-work snapshot.

The response keeps each workload in its own lane: `auto_video`, `video_analysis`,
`high_quality_snapshot`, `full_visit`, `backfill`, and `weather_backfill`. Each item includes its
event ID when applicable, status, current phase, progress counters and unit, timestamps, and an
application route. Lane summaries report queued/running/terminal counts, queue capacity, configured
and effective worker concurrency, and a machine-readable blocker such as
`paused_after_failures`, `waiting_for_live_detections`, or `waiting_for_capacity`.

`include_routine=false` omits automatic per-detection media work while retaining prominent
owner-triggered work. `limit` controls returned item detail (`1`–`500`); lane totals are calculated
before that item limit so capacity reporting remains accurate. This endpoint is a no-cache status
snapshot, not a destructive queue-control API.

### Integrations

- Audio:
  - `GET /api/audio/recent`
  - `GET /api/audio/history` — persisted BirdNET detections; `matched_visual_event_id` identifies a
    completed automatic video classification that agrees by species, time window, and source mapping
  - `GET /api/audio/summary`
  - `GET /api/audio/species`
  - `GET /api/audio/context`
  - `GET /api/audio/context/event/{event_id}` — nearby BirdNET detections for one persisted visual
    event, using the configured correlation window and camera-to-audio-source mapping
  - `GET /api/audio/sources`

`GET /api/events` accepts `event_id` for an exact Frigate event lookup. It retains the same guest
history, hidden-event, and camera-privacy restrictions as the paginated event list.
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
- `GET /api/diagnostics/errors`
- `GET /api/diagnostics/workspace`
- `POST /api/diagnostics/clear`

### AI Usage Stats (owner)

- `GET /api/stats/ai/usage`
- `DELETE /api/stats/ai/usage`

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
