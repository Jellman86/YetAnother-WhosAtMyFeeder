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
docker exec yawamf-monalithic curl -fsS http://127.0.0.1:8000/openapi.json | python3 -m json.tool | head -40
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

Guest media requests return `503` with `Retry-After: 5` when a database error prevents checking
the owner's visibility rules. No cached or upstream media is served before that check succeeds.

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
curl -fsS -H "Authorization: Bearer <token>" http://localhost:9852/api/events
# Legacy split deployment (backend exposed on 8946):
# curl -fsS -H "Authorization: Bearer <token>" http://localhost:8946/api/events
```

### Common responses

| Status | Meaning |
|---|---|
| `401` | Authentication is missing, invalid or expired. |
| `403` | The authenticated role cannot perform this action. |
| `404` | The accessible resource or retained artifact does not exist. |
| `409` | The action conflicts with current state, for example an active model, an incomplete install or an already running evaluation. |
| `422` | The request does not match its schema or allowed values. |
| `429` | A rate limit or upstream AI quota was reached; respect `Retry-After` when present. |
| `503` | Startup, database admission or a required upstream/runtime is temporarily unavailable. |

See each endpoint for additional statuses. A `200` response can still carry a documented
`no_result` or test failure state; automation must inspect the body rather than infer
that an identification was accepted.

### Session cookie for media

`<img>`, `<video>` and `<audio>` cannot set an `Authorization` header. The app uses a session
cookie for media requests to keep the session token out of URLs and proxy request logs.

Instead, `POST /api/auth/login` (and first-run setup) also sets an `HttpOnly`, `SameSite=Lax`
cookie named `yawamf_session`, scoped to `/api`, `Secure` when the request arrived over HTTPS,
with the session's own lifetime. **Only read-only media routes and the live stream honour it**:
snapshots, thumbnails, clips, recording clips, clip-thumbnail sprites and VTT, snapshot
candidates, the camera live frame, audio spectrograms and clips, Garden snapshots and saved
crops, manual-observation media, showcase images and videos, and `GET /api/sse`. The cookie
cannot authorise other routes or state-changing requests. Use a Bearer header for authenticated
API calls. `POST /api/auth/logout` clears the cookie.

- `POST /api/auth/session-cookie` (owner, **Bearer only**) — attaches the caller's existing session
  as the cookie. The app calls it once on load for a browser that signed in before the cookie
  existed. The cookie itself is not accepted here, so a media-scoped cookie can never widen its
  own reach.
- The deprecated `api_key` query parameter still works on media routes until it is removed in 3.0.

### Stream ticket

`EventSource` cannot set an `Authorization` header. The app exchanges its session for a
single-use stream ticket, keeping the session token out of the URL. A client can open the
stream with a ticket as follows:

```bash
TICKET=$(curl -fsS -X POST -H "Authorization: Bearer <token>" \
  http://localhost:9852/api/auth/stream-ticket | python3 -c 'import sys,json; print(json.load(sys.stdin)["ticket"])')
curl -N "http://localhost:9852/api/sse?ticket=$TICKET"
```

- A ticket is **single-use** and expires **60 seconds** after issue. An unredeemed ticket
  exposed in a log remains usable until it expires.
- It inherits the session's expiry, so the stream still ends when the session would have.
- Only a signed-in session is issued one (`403` for a guest, `401` with no session). A guest does
  not need one: with public access on, the bare `/api/sse` already opens as a guest.
- The server keeps only a hash of each outstanding ticket, bounded to 256 at a time.
- Clients that can send a Bearer header may skip the exchange. The stream also accepts the
  session cookie described above.

### Auth status

- `GET /api/auth/status`: returns auth/public-access capability flags used by the frontend.
  For the owner it also carries `avatar_version` (null without a profile picture).
- `GET /api/auth/avatar` (owner): the profile picture, a 256 px square JPEG; 404 without one.
- `PUT /api/auth/avatar` (owner, multipart `image`): replaces it. The upload is decoded, turned
  upright, centre-cropped and re-encoded, so no metadata (location included) is kept; 400 for a
  file that is not an image, 413 above 8 MB or 40 megapixels. Returns `avatar_version`.
- `DELETE /api/auth/avatar` (owner): removes it; the account shows its initial again.

## Health, Readiness, Version, Streaming

- `GET /health`: process + classifier health. The response is not cacheable.
  `video_classifier` includes `pending_by_source`, `oldest_pending_age_seconds_by_source`,
  `active_by_source`, and `active_by_phase`. Source maps
  distinguish `live`, `manual`, and `maintenance`; an empty source has a `null` waiting age.
  `scheduler_pressure` reports cumulative observed pressure/wait seconds and start, relief-start,
  and finish counts. Counters reset with the process and update independently of health polling.
  A finish can include failure or cancellation. These are scheduler observations, not exact
  accelerator utilization or live-request latency; short bursts between checks can be missed.
  Existing maintenance-specific fields remain available. See [video queue behaviour](features/video-analysis.md#settings).
- `GET /ready`: startup readiness (returns `503` until ready). This exact public path is proxied
  through both monolithic and split frontend deployments and is not cacheable.
- `GET /api/version`: app version metadata.
- `GET /api/update-status`: whether a newer YA-WAMF release exists. A notification only —
  YA-WAMF never updates itself, and the check honours the `system.update_check_enabled` opt-out.
- `GET /api/system-telemetry`: one live host-utilization sample (the sidebar's rolling CPU/NPU
  graph). Guest rate limits apply; the response is not cacheable. The UI samples every 2.5 s for
  the owner and, for a visitor, at a fifth of the public rate limit (every 10 s at the default 30
  a minute). It pauses while the tab is hidden and backs off after failed samples.
- `GET /api/system-telemetry/history` (owner): the last thirty minutes of host CPU and accelerator
  load, sampled every five seconds while the app runs, with what this container's own processes
  (the app, each classifier worker, any ffmpeg it spawned) took of it by CPU and memory. Anything
  else on the host is reported only as the remainder and is never named. Not cacheable.
  `accelerators` lists every device that was found, each with a `scope` saying what its number
  covers: `device` is every user of it (an Intel NPU busy counter), `app` is only the work this
  app submitted (GPU engine time, which a container can read for its own processes and no
  others). A device that is present but publishes no readable counter carries `unreadable`
  instead of a number. Each point's `accelerators` map holds one percentage per device id;
  `accelerator` and `accelerator_percent` remain as the single series the sidebar graph draws.
- `GET /api/sse`: Server-Sent Events stream. Opens with a Bearer header, with a single-use
  `?ticket=` from `POST /api/auth/stream-ticket`, or as a guest when public access is on. The
  session token is **not** accepted in the query string; see [Stream ticket](#stream-ticket).

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
- `POST /api/auth/stream-ticket` (owner) — single-use, 60-second ticket that opens `GET /api/sse`; see [Stream ticket](#stream-ticket).
- `POST /api/auth/session-cookie` (owner, Bearer only) — sets the media session cookie for an already-signed-in browser; see [Session cookie for media](#session-cookie-for-media).

### Guided setup

- `GET /api/setup/state` (owner; also reachable before auth is enabled) — returns
  deterministic `ok`, `attention`, or `optional` states for account, connection,
  cameras, classifier, snapshot quality, and integrations. This is saved
  configuration/credential readiness, not a live external-service health check.

### Events

Public event-history and media windows use UTC calendar days. Custom `0` starts at
00:00 UTC and excludes the next midnight; custom `N` starts at midnight UTC `N` days
ago. Public audio, AI access, filter counts, About photographs and leaderboard portraits
use the corresponding shared history/media bounds. Owner date filters are unchanged.
One UTC calendar day is captured per HTTP response, so nested queries, totals and audio
projection cannot switch to another day's evidence midway through a request. The calendar
is released when the response body completes; later requests and background work use a
fresh day. This does not cache sharing preferences.

- `GET /api/events`
- `GET /api/events/count`
- `GET /api/visits` Groups the accessible history before pagination. Accepts `limit`, `offset`,
  `start_date`/`end_date` or UTC `start_time`/`end_time`, `species`, `camera`, `favorites`,
  `audio_confirmed_only`, `only_hidden`, `multiple_species_only` and `sort` (`newest`, `oldest`,
  `confidence`). Returns `visits`, `total` and `gap_seconds`. Each visit includes
  `visit_id` (its first accessible capture ID), start/end, full `capture_count`, best score, review/audio/owner-confirmation
  state, representative/latest records and owner-only busiest counted capture. Grouping uses
  canonical species, actual camera and a 60-second inactivity gap after the running latest
  verified event end; historical captures without bounds use capture time. Unknown and manual
  records remain separate. It does not identify individual birds. `owner_confirmed`
  aggregates explicit owner species confirmations from accessible visit members,
  independently of model confidence and matching audio. Another favourite may represent
  the visit. Unresolved names and captures excluded by the active visibility filters
  do not establish confirmation. Access/date/hidden scope is
  applied before grouping; species, favourite, audio and multiple-species matching selects the
  whole accessible visit. A sharing window or correction can change membership and the first id.
- `GET /api/visits/{visit_id}/captures` Rechecks access and history window on every read. Accepts
  the same date/time and hidden scope, plus `limit` (20 by default, maximum 50) and `offset`.
  Returns chronological `captures` and `total`; unavailable visits return 404.

Fresh databases return an empty visit list until captures are saved. Live ingest and backfill
retain valid Frigate event bounds. Backfill can arrive out of order: visit membership and totals
are calculated from saved captures, so earlier captures or longer verified ends can join groups
as an import progresses. Repeated imports preserve original capture IDs and valid stored bounds.
Visit IDs can change when an earlier capture arrives or groups join during backfill.
Grouping and filtering add no model inference. Upgrading existing history does not rescan media;
captures without verified bounds continue to use their stored capture time.

`GET /api/events`, `GET /api/events/count` and `GET /api/visits` accept the owner-only
`multiple_species_only=true` filter. It matches at least two distinct resolved, named species
among visible counted birds in a capture. Aliases of one species and unknown/excluded birds do
not satisfy it. A visit matches if one of its captures qualifies. Guest requests ignore the flag.

- `GET /api/events/filters` Species and camera options, each with a detection count, plus totals
  for the favourites, audio-matched and video-analysed facets. Counts exclude hidden detections;
  for public guests, they also use the configured public-history window so filter metadata cannot
  reveal older private visits.
- `GET /api/events/hidden-count` (owner)
- `GET /api/events/new-species` (owner) — species that appeared recently with no confirmed
  history, each represented by its latest sighting, for the dashboard's review queue.
  `max_sightings` (default 3) and `window_days` (default 14) bound what still counts as new.
- `GET /api/events/{event_id}/classification-status` (owner)
- `PATCH /api/events/{event_id}` (owner)
- `PATCH /api/events/bulk/manual-tag` (owner)
- `DELETE /api/events/{event_id}` (owner)
- `POST /api/events/{event_id}/hide` (owner)
- `POST /api/events/{event_id}/favorite` (owner)
- `DELETE /api/events/{event_id}/favorite` (owner). Both return `archive_state`.
- `GET /api/events/{event_id}/archive` (owner). What the favourite's archive holds: `state`,
  `snapshot_state`, `clip_state`, `bytes`, `error`, `retry_at`.
- `POST /api/events/{event_id}/archive/retry` (owner). Retries a failed archive now.
- `POST /api/events/{event_id}/reclassify` (owner)
- `POST /api/events/{event_id}/classify-wildlife` (owner)

For owners, each event row from `GET /api/events` (default, `fields=detail`, `fields=list`, or a
custom field list naming it) carries `bird_summary`: the localized birds stored for that capture,
read in one batched query per page. `counted` excludes birds the owner excluded, `unknown` counts
counted birds classified as unknown under the configured label policy (including noncanonical taxa),
`excluded` counts exclusions, `species` groups
the counted named birds by their stored (owner-corrected) species, and `hint_only` is true when
every bird came from Frigate's tracked box. Repeated species stay separate observations; they are
birds located in one analysed frame, not unique animals. `null` means no observations are stored,
which is not a measured zero. Guests never receive the field. Other routes that return detections
leave it unset.

`PATCH /api/events/{event_id}` accepts `{"display_name": "Blue Tit"}`. A successful response
always includes `manual_tagged: true` and the retained taxonomy fields. If the requested name is
the current species or another known name for the same taxon, `status` is `unchanged`: YA-WAMF
records the human confirmation but preserves the stored display, scientific and common names and
does not create correction feedback. A different species returns `status: "updated"` after the
canonical taxonomy and manual tag have been committed.

Event rows and `GET /api/events/{event_id}/classification-status` expose
`video_classification_input_source` when YA-WAMF knows which representation produced the retained
analysis result. Current video values are `full_frame`, `frigate_hint_crop`, `model_crop`, or
`provided_crop`. Snapshot fallbacks use their cache/media source, such as `high_quality_snapshot`,
`high_quality_bird_crop`, `frigate_snapshot`, or `frigate_snapshot_cropped`; an additional
model-driven crop is reported as `snapshot_model_crop` or `snapshot_frigate_hint_crop`. The field is
`null` for historical results that predate provenance tracking; clients must not infer crop state
from image dimensions. A trusted upstream label that won because local image evidence did not
clear policy is reported as `frigate_sublabel` rather than as snapshot or video inference.

For current video runs, event rows and the classification-status endpoint can also expose
`video_classification_diagnostics`. Version 3 records sampled/decoded frame counts, the number of
temporally independent moments, minimum per-frame confidence, final outcome/reason, and per-source
evaluated/confident counts, `confident_coverage_ratio`, `required_supporting_frames`, confident
`top_candidates`, and separate all-score `top_observations`. It also identifies the sparse top-k
median aggregation, five-moment pool limit, and 250 ms de-correlation interval. The matching
requirement is calculated from confident independent votes, not every decoded frame. It is `null`
while work is pending, after a successful result, and for historical runs that predate retained
diagnostics. Candidate evidence explains an abstention; clients must not present it as an accepted
identification. Clients should continue to tolerate version 1 and 2 summaries already stored in the
detections database.

An HQ baseline built from Frigate's regular ended-event snapshot because the clean copy was absent
uses `hq_candidate_frigate_snapshot_fallback`. It is treated conservatively as already cropped: the
ended-event API ignores crop query overrides, so YA-WAMF must not run localisation a second time.

`POST /api/events/{event_id}/reclassify` returns `status: "success"` and `updated: true` only after
the selected result has been persisted. A snapshot strategy with no promotable species returns HTTP
200 with `status: "no_result"`, `updated: false`, and a bounded reason such as
`no_confident_result`, `below_threshold`, `low_confidence`, `blocked_label`, `abstention_label`, or
`invalid_score`, or `non_bird`; the existing species and score are returned unchanged. Media-fetch, decode, and
inference faults remain non-2xx errors.

With `strategy=video`, the request performs temporal analysis whenever a usable video exists. The
source order is complete cached recording, decodable partial cached recording, cached event clip,
then the live Frigate event clip. A snapshot does not short-circuit an available video, but becomes
the final evidence route when video is unavailable, temporal sources abstain, or the consensus
candidate does not clear the configured promotion threshold. The SSE stream emits
`reclassification_strategy_changed` before that fallback.

Video `reclassification_completed` events are emitted after photograph work settles. A successful
run can include `photo_outcome`, such as `replaced`, `matching_photo_preserved`,
`manual_selection_preserved`, `owner_identification_preserved`, `primary_identity_preserved`,
`storage_evicted`, `blocked_species`, `media_cache_disabled`, `snapshot_caching_disabled`,
`media_cache_unavailable`, `bird_presence_unconfirmed`, `detector_error`, `classifier_error`,
`inference_deferred`, `frame_extract_failed`, or
`snapshot_replace_failed`. Owner, identity, storage and failure outcomes also enter processing
diagnostics; routine replacements and matching photographs do not. Species success does not imply
a photograph was replaced; existing owner choices remain protected. `bird_presence_unconfirmed`
means no suitable photo had sufficiently confident detector localization inside its bounds.
The current photo remains available, including when the crop detector is absent or disabled.
Species confidence alone is not bird-presence evidence. Photographs are always kept, so
`media_cache_unavailable`, a media folder that cannot be written, is the one storage outcome. Builds
before #622 also reported `media_cache_disabled` and `snapshot_caching_disabled` for the retired
switches, and older builds the combined `disabled_or_no_evidence`, which alone cannot identify the
cause.

A prior photograph retained during replacement can appear among snapshot candidates with
`source_mode: "retained_photo"`, `clip_variant: "retained_snapshot"`, and no frame offset or
classifier prediction. Its `frame_index: 0` is a storage placeholder, not evidence of clip timing.
Regular proxy-fetched JPEGs use `frigate_snapshot_unverified` provenance because camera settings
can change their framing. Full-frame Frigate coordinates must not be reapplied to those bytes.

- `POST /api/events/bulk/delete` (owner) — **irreversibly** deletes several detections by Frigate
  event ID in one request. Duplicate and empty IDs are dropped, and an empty list is a `400`. The
  response separates the IDs actually deleted from those that did not exist. This is a hard delete:
  the rows and their cached media are gone. Use `POST /api/events/{event_id}/hide` when you want a
  recoverable soft delete instead.

### Garden animal review

Garden routes use `private, no-store`. All of them require owner access except the read-only
history and photo routes (`visits`, `visits/{visit_id}/captures`, `timeline`, `{capture_id}/snapshot`
and `{capture_id}/crop`). With public access on, a guest reads those under the bird detection rules.
A guest sees confirmed captures only, within the public history window. Camera names read `Hidden`
when they are not shared. `review_token` and `automatic_check` are null. Snapshot, crop and
`clip_event` are null outside the public media window or when photographs or video are not shared.
Photo requests outside those rules return `404`, and guest requests are rate-limited. `GET
/api/auth/status` reports `garden_animals_enabled`. The Frigate clip proxy admits a confirmed Garden
capture's event as it does a bird detection's, and serves its kept clip first when one exists. A
pending or dismissed Garden capture's clip is streamed from Frigate and never written to the clip
cache. Capture responses include `photo_kept` and `clip_kept`: whether YA-WAMF holds its own
checksummed copy of the full photograph or Frigate clip (false for a guest when that media is not
shared). See [Kept photographs and clips](features/garden-animals.md#kept-photographs-and-clips). Presence and
species identification have separate reviews; `frigate_label` remains an upstream suggestion.

- `GET /api/garden` — `status=pending|confirmed|dismissed`, `limit=1..128` (default 20),
  `offset>=0`; returns `items`, `total`, `limit`, `offset`. Pending items and totals
  omit captures whose photos are known to be unavailable, without changing their
  stored reviews. Confirmed and dismissed history still include them.
  `automatic_check` records a new capture's automatic SpeciesNet assessment:
  `animal|bird|non_animal|uncertain|unavailable`, check time, model/package/photo
  checksums, exact normalized crop, actual CPU device and complete probability
  mass for birds, non-human/non-bird animals, humans, blank/vehicle and other.
  Confident bird or blank/vehicle checks move an untouched pending capture to
  dismissed; person evidence removes it under the existing privacy rules.
  Unknown results and failures stay pending. Owner review/restore overrides
  automation permanently for that capture (`automatic_check_overridden=true`).
  Pre-update captures are not rechecked. With `garden_automatic_naming` on, an
  `animal` check whose top crop prediction reaches `garden_naming_threshold` also
  confirms the capture and saves an accepted `identification` with `automatic=true`,
  in one transaction. `reviewed_at` stays `null` because no owner reviewed it.
- Garden capture responses name a standing identification from the species catalogue in the
  `Accept-Language` language, falling back to English. A lowercase model name is cased like a
  catalogue name (`domestic dog` becomes `Domestic Dog`); an owner's cased rename is kept as written.
  `scientific_name` is the catalogue's scientific name for that identification, or null.
- `GET /api/garden/visits` returns Garden entries, grouped before pagination.
  `start`/`end`, `camera` and `status` (`reviewable`, `pending`, `confirmed`, `dismissed`)
  scope eligible captures. `order` is `newest` or `oldest`; `limit` (1–200) and `offset`
  count groups. The response has `visits`, group `total`, `capture_total`, `limit` and
  `offset`. Each visit includes `id`, `kind` (`visit` or `position`), start/end,
  `capture_count` and its latest `representative`. Canonical identity, camera and
  review state separate timed stays; gaps over 60 seconds start another stay.
  Pending motion proposals retain fixed-anchor position stacks instead of joining by time.
  Optional `page_start`/`page_end` select whole groups by latest capture time after grouping,
  for mixed bird pages. Newest order uses [start,end); oldest order uses (start,end].
- `GET /api/garden/visits/{visit_id}/captures` rechecks the same history scope and
  returns capture `items`, `total`, `limit` and `offset`, newest photo first. `limit`
  is 1–128. Membership is recomputed after reviews, expiry and privacy revocation;
  an unavailable group returns 404. Reads never change reviews. Visit identifiers
  are the first eligible capture and can change when membership changes.
- `GET /api/garden/timeline` — the Explorer's Garden view and review states. Optional `start` and `end` (ISO 8601;
  a time without an offset is UTC; `422` when `start` is after `end`), `camera`,
  `status=reviewable|pending|confirmed|dismissed` (default `reviewable`, meaning confirmed plus
  pending with an available photo; blocked captures are never listed),
  `order=newest|oldest` (default newest), `limit=1..200` (default 48) and `offset>=0`. Returns
  the same `items`, `total`, `limit`, `offset` page as `GET /api/garden`. Read-only.
- `POST /api/garden/review-batch` — explicit `ids` (1..128 hexadecimal capture IDs)
  and `action` (`dismiss` or `restore`). Dismiss changes only pending captures;
  Restore changes only dismissed captures with available photos. Returns `updated_ids`
  in request order and `skipped_count` (unique IDs not changed). Confirmed, blocked,
  missing or concurrently changed reviews are skipped. Never confirms presence or
  identification, deletes photos, or applies to future captures.
- `POST /api/garden/{capture_id}/confirm` — move to confirmed history; no body.
  A known unavailable photo returns `409` without changing the review.
- `POST /api/garden/dismiss-captures` — owner-only explicit dismissal, including confirmed
  captures. Send `captures: [{"id": "<32 hex characters>", "review_token": "<64 hex characters>"}]`,
  with 1–128 unique IDs and the opaque `review_token` from each capture response.
  Only unchanged pending or confirmed reviews are dismissed; changed, blocked, missing
  and already-dismissed captures are skipped. Returns `updated_ids` in request order and
  `skipped_count`. Later arrivals are unaffected. History and original model results
  remain, with species review marked dismissed; saved crop previews are removed as on
  single-capture dismissal. A successful change refreshes other owner sessions after commit.
  Returning these captures through `review-batch` with `restore` means pending review,
  not reconfirmed presence or species. No batch confirmation is offered.
- `POST /api/garden/{capture_id}/dismiss` — dismiss a false detection; no body.
- `POST /api/garden/{capture_id}/restore` — return to pending review; no body.
  Frigate captures require an advertised snapshot; motion captures require an
  unexpired stored photo. Known unavailable photos return `409`.
- `GET /api/garden/{capture_id}/snapshot` — a confirmed capture's kept photograph when its bytes
  still match the recorded checksum, otherwise the Frigate or retained motion photograph, `404` when
  missing or rejected. The exact read-only route accepts the owner session cookie
  and uses `private, no-store`; review writes still require an authorization header.

- `GET /api/garden/species?q=fox` — owner-only, beta-gated local species search.
  `q` is 1–120 characters; returns up to 20 `{species_id, name, scientific_name}`
  choices. Searches common/scientific names with the reader's locale and English
  fallback. No model or external service runs. Only complete animal species from
  the pinned Garden catalogue are offered; human/background/higher taxa are excluded.
- `PUT /api/garden/{capture_id}/species` — save an owner correction for one confirmed
  capture. Body: `{"species_id": 123, "review_token": "<64 hex characters>"}`.
  Use the opaque token from the capture response. A stale token or non-confirmed
  record returns `409`; missing/blocked returns `404`; an unsupported species returns
  `422`; an unavailable catalogue returns `503`. Retained crops or an expired original
  do not prevent correction. The response includes nullable `owner_identification`
  (`species_id`, `name`, `scientific_name`, `changed_at`) separately from unchanged
  model `identification`; `scientific_name` describes the current owner identity.
  No score, model or execution is assigned to the owner's choice. The new identity
  controls visit grouping, marks automation overridden and emits the private history
  refresh after commit. No alert is scheduled or replayed by this action.
- `DELETE /api/garden/{capture_id}/species?review_token=<64 hex characters>` — remove
  the correction using the current token, returning to the stored model identity
  without inference. Automation remains overridden. Both write routes require header
  authentication; the media cookie cannot authorize them. Ordinary dismissal retains
  owner identity with history, while person revocation and retention purge it.

- `GET /api/garden/notifications` — owner-only, beta-gated delivery status. Returns
  `enabled`, `use_bird_channels`, the explicitly chosen `channels`, `delivery_channels`
  (where an alert would go now from the saved settings), `include_photo`,
  credential-presence booleans in `configured`, and aggregate `attempts` counts
  (`attempted`, `sent`, `failed`, `skipped`). No secrets or message contents are
  returned; private/no-store headers apply. `sent` means provider acceptance, not
  recipient acknowledgement. Reading status sends nothing.
- `GET /api/garden/captures/{capture_id}` — one capture's record, as a Garden alert
  links to it (`capture_id` is 32 hexadecimal characters; anything else returns `422`).
  The owner reads any capture that is not blocked. A visitor reads a confirmed capture
  inside the public history window only, with the same redactions as the timeline;
  anything else returns `404`, and `403` once public access is off. Rate-limited for
  guests; private/no-store headers apply.
- `GET /api/garden/motion` — enabled cameras, catalogue and detector availability,
  shared busy state, `animal_confidence`, collection state/message, last attempted scan/outcome and
  interval/photo limits. `interval_seconds` reports the selected minimum spacing between scan starts:
  five seconds after a completed window with more footage queued, otherwise ten seconds.
  Processing is included, long scans leave at least one second of rest and failures back off
  thirty seconds. This is not a promised capture rate. `catchup_seconds` bounds recording age; `queue_limit`
  caps each rebuilt camera queue. `queued_windows`, `queue_camera` and
  `queue_checked_at` describe the latest inspected camera, not a live total across
  all cameras. More footage may remain when the queue is full. Refresh to read
  progress; it does not initiate a scan.
- `POST /api/garden/motion/install` — atomically download and checksum-verify the
  101 MB Cedar ONNX detector; no body. `409` if another garden operation is running,
  `503` if the catalogue, download or worker cleanup is unavailable.

- `GET /api/garden/identification` — catalogue availability, normalised ISO-3 country,
  per-variant model download status, busy state, `automatic_message` and any worker cleanup error.
  Automatic checks download/verify the tracked-crop model when needed and run
  on the Detection device preference after a host-bound CPU agreement check, with
  CPU fallback and bird/camera priority. Missing boxes never use whole-image inference
  to reject a capture. Unavailable checks retry no sooner than five minutes later.
- `POST /api/garden/models/{variant}/install` — atomically download and verify
  `4.0.3a` or `4.0.3b`; no body. Both files are about 224 MB.
- `POST /api/garden/{capture_id}/check-photo` — body
  `{"image_sha256":"<displayed motion photo SHA-256>","provider":"intel_npu"}`.
  Uses installed `4.0.3a` on an enabled camera's pending retained motion photo;
  no country is required and no download or review write is performed. Returns
  a `bird`, `mammal`, `uncertain` or `unavailable` advisory bound to the photo,
  normalized XYWH crop, model/package checksums, provider, actual devices and
  frame size. Complete bird/non-human-mammal/human/blank/other probability mass
  accompanies usable assessments; human evidence returns `unavailable` with
  `mass: null`. Stale/reviewed/expired/disabled captures and bird priority return
  `404` or `409`; model/provider/deadline/cleanup failures return `503`.
- `POST /api/garden/{capture_id}/identify` — body `{"variant":"4.0.3b","provider":"cpu"}`.
  Providers: `cpu`, `intel_cpu`, `intel_gpu`, `intel_npu`, `cuda`. Requires confirmed
  animal presence, an enabled garden camera, installed model and recognised country.
  Returns the capture with an unreviewed suggestion or unknown result. `409` covers
  bird priority, unavailable prerequisites or a changed capture; `503` covers
  a failed provider, model verification, timeout or worker cleanup.
- `POST /api/garden/{capture_id}/identification/{action}` — `accept` or `dismiss`,
  no body. Acceptance requires an unreviewed identity and the unchanged source photo.
  Group-level identities retain their rank; unknown results cannot be accepted.

Identification metadata includes the canonical `species_id`, model/package/photo
checksums, raw winning `output_index`, country, requested provider, actual devices,
input kind, optional normalized XYWH box, frame size and review state. This belongs
only to garden history. Manual suggestions require acceptance; automatic naming
confirms a bound animal identity at the configured threshold without an owner click.
It does not change the owner's provider preference.


Completed model execution evidence uses `model_id`, `provider`, optional
`requested_provider`, `devices`, `checked_at` and optional `fallback_reason`.
Finder evidence is exposed as `crop_detector.last_execution` in classifier status
and comes from successful in-process inference or an accepted worker result bound
to its current lease. Records for another selected finder are withheld. Garden
checks include optional `execution`, `policy_version`, `decision_reason`,
`naming_score` and `naming_threshold`; old stored JSON remains readable. A
`below_threshold` decision soft-dismisses the capture without marking it as an
owner review. Owner overrides, person vetoes and atomic result comparisons remain
in force.


Captures include `source_kind=frigate_event|motion`. Motion captures have no Frigate
event ID. Their `motion_source` binds the requested recording window, returned frame
index/offset, model/input/frame/clip/photo hashes and normalized detector box. The
windows describe the requested Frigate interval; the returned clip can include up
to five seconds of keyframe padding. Samples stay within its first ten seconds,
person checks include the padded interval and displayed observation times are approximate. These
are detector proposals, including possible birds and false positives. Confirmation
requires an unexpired stored photo. The 128-photo budget is capped at 512 KiB per
photo. A new candidate at capacity reclaims the oldest dismissed photos in the same
transaction as storage; duplicate or failed writes preserve them. Pending and
confirmed photos are protected. Reclaimed captures retain dismissed metadata until
expiry and return `snapshot_url=null`; confirm and restore return `409` without
changing the review or identification. Restore remains available while the photo is stored.
The photo budget remains 64 MiB. Clips are temporary; photos expire after three
days and unconfirmed motion captures are removed. Confirmed history survives photo expiry.

`garden_motion_confidence` is a saved settings value from 0.5 to 0.95 (default 0.5).
The equivalent environment override is `FRIGATE__GARDEN_MOTION_CONFIDENCE`.
`garden_automatic_naming` (default `true`, `FRIGATE__GARDEN_AUTOMATIC_NAMING`) and
`garden_naming_threshold` (0.7 to 0.99, default 0.8, `FRIGATE__GARDEN_NAMING_THRESHOLD`)
control automatic naming. Successful results below the species threshold are soft
dismissed and restorable; failures remain pending for retry. Older pending results
without owner overrides are reconsidered once under this policy. Bird and person
thresholds remain separate.
It affects new Cedar animal proposals only, leaving bird and person thresholds intact.
`motion_source.animal_confidence` records the threshold used; legacy photos default
this provenance value to the previous fixed 0.5. A changed threshold interrupts a
pending scan before its proposal or completion cursor is saved.

Settings use `garden_cameras` (default `[]`), `garden_motion_cameras` (default `[]`) and `garden_labels` (default
`["cat", "dog"]`), persisted under `frigate` in the configuration. These are
independent of `cameras`, `camera_roles` and bird `frigate_ingest_labels`.
Motion cameras must also be enabled garden cameras; otherwise they are inactive. When a settings
write includes `garden_cameras` or `garden_motion_cameras`, the server drops any motion camera that
is not a Garden camera before saving.
Motion collection ignores animal event labels and does not perform species identification.
Garden notification settings use flat settings API fields
`garden_notifications_enabled` (default `false`),
`garden_notifications_use_bird_channels` (default `true`: send on the bird channels
that are switched on and configured), `garden_notification_channels` (default `[]`;
`discord`, `telegram`, `pushover`, `email`; used while
`garden_notifications_use_bird_channels` is `false`) and
`garden_notifications_include_photo` (default `true`). A saved configuration without
`garden_notifications_use_bird_channels` keeps its explicit channels when it chose
some and follows the bird channels when it chose none. Only confirmed captures whose
name was accepted in the last five minutes, for sightings up to two hours old,
qualify. See [Garden notification rules](features/garden-animals.md#send-garden-notifications)
for freshness, photos, privacy and durable per-visit attempt semantics.

Garden captures have no bird detection ID and cannot be submitted by bird export APIs.
See [Garden animals](features/garden-animals.md) for retention and prototype limits.

### Manual observations

- `POST /api/manual-observations` (owner; multipart `media`; images up to 25 MiB, videos up to
  250 MiB; returns `202`)
- `GET /api/manual-observations/{draft_id}` (owner)
- `POST /api/manual-observations/{draft_id}/retry` (owner; returns `202`)
- `POST /api/manual-observations/{draft_id}/confirm` (owner)
- `DELETE /api/manual-observations/{draft_id}` (owner; unsaved drafts only)
- `GET /api/manual-observations/{draft_id}/preview` (owner; also supports `HEAD`)
- `GET /api/manual-observations/{draft_id}/media` (owner; also supports `HEAD` and byte ranges)
- `GET /api/manual-observations/{draft_id}/species/{position}/{view}` (owner; `view` is `photo` or
  `scene`; also supports `HEAD`; `404` when no frame localised that suggestion)

These exact read routes accept the owner HttpOnly session cookie so browser image and
video elements can load the draft without tokens in their URLs. Draft identifiers must be
32 lowercase hexadecimal characters. Cookie authentication does not authorize draft status,
upload, retry, confirmation or deletion. Guests cannot read draft media. Preview responses
are private; original media sends `Cache-Control: private, no-store`.

Upload and retry responses expose durable status, progress, model alternatives, inference
provider/model/input provenance, common/scientific taxonomy names, optional extracted GPS
coordinates, and local preview/media URLs. For a video, each suggestion the analysis localised in
a frame also carries `photo_url` (that species' best frame, cropped to the bird), `scene_url` (the
whole frame) and `frame_offset_seconds`; they are null otherwise. The confirmation body accepts optional `latitude` and
`longitude` together plus `location_source` (`image_metadata`, `manual_pin`, or `none` to clear an
extracted location).

Draft responses also carry `captured_at` (UTC ISO-8601, or null) and `captured_at_source`
(`exif`, `video_metadata`, or `none`): when the file itself says it was taken. A photo's time comes
from EXIF `DateTimeOriginal`, then `DateTime`, using `OffsetTimeOriginal`/`OffsetTime` when present.
An EXIF time with no offset is read as local time in the server's configured `TZ` (UTC when unset).
An MP4 or MOV time comes from the movie header's creation time, which the format defines as UTC.
Times before 1990 or more than ten minutes in the future are ignored. The confirmation body's
optional `observed_at` wins; without it the detection uses `captured_at`, and only then the save
time.

Uploading a file the server already holds returns `409` with
`detail: { message, draft_id, event_id }`. `event_id` is the saved observation's ID (open it at
`/events?event={event_id}`), or null while the earlier upload is still an unsaved draft that can be
continued with `GET /api/manual-observations/{draft_id}`.

Confirmation creates a normal
detection with `observation_source: "manual_upload"`; its owner-confirmed species stays distinct
from the retained top classifier result. A saved video's photo is the confirmed species' best frame
when the analysis localised one, and the video's first frame otherwise. A later species correction
through `PATCH /api/events/{event_id}` moves the photo the same way and reports `photo_changed`. Detection responses expose confirmed location as
`observation_latitude`, `observation_longitude`, and `observation_location_source`. Manual media is
served through the canonical snapshot, thumbnail, and clip routes but is excluded from Frigate
reconciliation and BirdNET-Go context lookup.

Reverse proxies must permit a 256 MiB request envelope on the exact upload route to accommodate
multipart overhead and should stream the request body. The backend remains authoritative for the
per-file limits above.

Owner event responses expose nullable `classification_input` and `initial_classification_input`.
Each records `source`, optional `is_cropped`, pixel LTRB `box`, `frame_size` (width, height),
`frame_time` (recording timestamp), `frame_sha256` and `supporting_frames` when known. The current
input follows an accepted replacement; the initial input is immutable. A photograph choice never
rewrites either. Old records remain null. `fields=list` includes current input and `manual_tagged`;
guest projections exclude input evidence. Whole-view names follow the same confidence threshold as
other identifications for `needs_review`, and are excluded from personalization feedback and reranking.

### Media Proxy and Share Links

- `GET /api/frigate/{event_id}/snapshot.jpg`
- `GET /api/frigate/{event_id}/snapshot/status` (owner; reports the effective best-available policy)
- `GET /api/frigate/{event_id}/snapshot/candidates` (owner)
  - `image_url` and `thumbnail_url` are nullable independently when the corresponding cached
    file is missing or empty. Candidate choices and counted bird records remain available.
    Retained media URLs use stable file revisions: reading an unchanged image does not
    change its URL, while replacing it changes its revision. A file can still expire between
    listing and loading; clients must keep a working saved photo and handle media failures.
  - Candidate rows include optional `crop_strategy` provenance (`native`, `frigate_guided`,
    `sliced_2x2`, or `fast_native`) for model-generated crops, and `frigate_final_box` for the
    completed-track clean-snapshot baseline.
  - `birds` lists the individual observations counted from one analyzed full frame. Each row
    includes its box, suggested or corrected species, detector confidence when available, and
    `is_hidden`, and server-derived `is_unknown`. The unknown decision uses the same configured
    label and noncanonical-taxon policy as `bird_summary`, including after an owner correction.
    Names include optional `common_name` and `scientific_name`. `identity_source` is `crop`,
    `visit`, or `manual`; `identity_score` describes that identification and is null for an
    owner-named identity. `classifier_score` describes the retained candidate crop used for that bird.
    A successful contextual retry references its own candidate with `source_mode: model_observation`;
    its `crop_box` describes the classified image, while the bird's box remains the localized detector box.
    An uncertain bird can use the accepted visit identification
    only when its own species guess agrees and the persisted classifier box uniquely matches
    it in the exact retained source frame. Known whole-view input cannot supply this association.
    Legacy records without input evidence retain their existing Frigate-hint association. Known common/scientific aliases share one effective species count;
    ambiguous names remain unresolved. Reads do not rewrite stored crop evidence.
    The eight classified photo crops per frame do not limit the number of counted
    detector boxes. In Intensive scan mode, large high-resolution frames are also scanned in overlapping tiles so distant
    birds occupy more detector pixels. Frigate supplies one tracked-object hint per event; a
    hint-only count can miss other birds, and local detector results can include false positives.
    A fresh snapshot scan can make up to four serial regional detector rechecks for weak crops
    supported by a matching, confidently identified crop within ten seconds in the same clip.
    Rechecks reuse existing frames. Only new same-frame detector evidence changes the count.
    Each confirmed uncertain bird can receive one serial contextual classification attempt, with
    an 80% margin on each side and no overlapping distinct localized bird. The result must agree
    with the original canonical bird species and meet the 65% naming threshold. Its exact scored
    crop is retained under a separate candidate ID. A timeout or disagreement preserves the
    original crop identity and recovered count. These evidence candidates cannot be applied as
    photograph choices or change the main visit identification; original photo scores stay unchanged.
- `GET /api/frigate/{event_id}/birds/scan?candidate_id=...` (owner) — scan state for one
  retained whole-frame candidate. Returns `status` (`not_scanned`, `queued`, `running`,
  `completed`, `failed`), `available`, `unavailable_reason`, `error`, nullable `result_count`,
  `retained_previous` and `updated_at`, with `event_id` and `candidate_id`. Reading status does
  not start inference. `completed` with `result_count: 0` means the scan finished without usable
  birds; `not_scanned` is not a zero count. Existing observations may remain after an empty retry.
  Conflicting whole-bird and bird-part regions return `failed` with
  `error: "ambiguous_localization"` and `result_count: null`, preserving all existing
  observations. A species prediction from shared crop context does not resolve that count.
- `POST /api/frigate/{event_id}/birds/scan` (owner) — body
  `{"candidate_id": "retained-whole-frame-id", "expected_media_version": "image-revision", "force": false}`. Returns 202 with the same
  status shape. `expected_media_version` is the `v` query value in that candidate's `image_url`;
  an outdated displayed image is rejected rather than scanning replacement pixels. Identical active requests are coalesced; completed identical input is reused
  unless `force` is true. One worker processes the durable queue, capped at 100 pending scans.
  Requires an available bird detector and the exact retained whole frame, never a thumbnail
  or cropped Frigate fallback. The photo and primary species are unchanged; owner-corrected and
  excluded birds keep their existing protection. Returns 404 for a missing capture, 409 for
  unavailable/changed media, a conflicting active scan or reviewed birds on another frame, and
  429 when the queue is full. Changed media is rechecked before publication. Interrupted jobs
  resume after restart. Automatic scans use `media_cache_automatic_multi_bird_scan` (default
  `false`); manual scans work while it is off. Both use `media_cache_bird_scan_mode` effort.
- `PATCH /api/frigate/{event_id}/birds/{bird_id}` (owner) — correct one counted bird's `species`
  or set `is_hidden` to exclude or restore it. Send exactly one field per request. A correction
  stays attached to the matched box when HQ candidates are regenerated.
  A species must be a complete known common or scientific name. Partial or ambiguous names return
  HTTP 400. Send the selected `id` from `/api/species/search` to preserve canonical identity.
- `PATCH /api/frigate/{event_id}/snapshot/candidates/{candidate_id}` (owner). Body:
  `{"dismissed": true}` removes a photo choice; `false` restores it. Returns the updated candidate
  list with `photo_hidden` flags. Source images and bird evidence remain intact. The current chosen
  photo returns 409 until another is chosen; missing choices return 404. Applying a removed choice
  returns 409 until restored. Dismissals are tied to image content, so regeneration keeps an
  unchanged removed image excluded while a genuinely changed image can become a new choice.
- `GET /api/frigate/{event_id}/snapshot/candidates/{candidate_id}/thumbnail.jpg` (owner) — the
  small chooser thumbnail for one candidate.
- `GET /api/frigate/{event_id}/snapshot/candidates/{candidate_id}/image.jpg` (owner) — the retained
  full-resolution candidate, for the large preview.
- `POST /api/frigate/{event_id}/snapshot/apply` (owner) — marks the chosen candidate or original
  photo as an owner selection, protected from later automatic snapshot writes.
- `GET /api/frigate/{event_id}/snapshot/original.jpg` (owner)
- `POST /api/frigate/{event_id}/snapshot/hq-bird-crop` (owner; legacy route name, generates the best available HQ image)
  accepts `regenerate=true` to rebuild frame choices even when an HQ crop already exists. It also recounts localized birds when
  `media_cache_automatic_multi_bird_scan` is enabled. A
  successful replacement releases the previous protected owner photo choice. A newer choice
  made while regeneration runs stays protected. Empty regeneration preserves saved candidates
  and the chosen photo; unavailable media returns an error rather than claiming success.
- `GET /api/frigate/{event_id}/clip.mp4`
- `GET /api/frigate/{event_id}/recording-clip.mp4`
- `GET /api/frigate/{event_id}/hls/{asset}`
- `GET /api/frigate/{event_id}/recording-hls/{asset}`
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
explicit or automatic generation clears the failure state. Queue intent is saved before admission;
overflow is recovered from disk, and a final-event revision cannot be consumed by an older live
pass finishing later. `durable_pending` reports saved pending/retry work, and the owner Jobs view
includes disk overflow. Missing historical selected/count-scene files can be recovered in bounded
pages. Media deliberately evicted by retention or limits stays evicted until explicit regeneration.

Snapshot-candidate `frame_offset_seconds` values are temporal evidence, not presentation metadata.
Automatic crop selection/refinement requires supporting offsets to be at least 250 ms apart;
neighbouring decode fallbacks never become additional votes. Event-clip Frigate boxes are translated
to the nearest timestamped path point. Recording clips never reuse one static event box across
sampled frames; a Frigate crop is available only when `path_data` aligns it within the 0.75-second
tolerance. Full-frame and detector-crop evidence remain available when tracking data is absent.

Notes:
- Browser playback first requests `hls/master.m3u8`, or `recording-hls/master.m3u8` for a promoted
  full visit. YA-WAMF proxies only Frigate's expected relative playlist, init-fragment and media-
  fragment names; it carries a share token or legacy API key into those relative asset URLs but
  never forwards browser query strings to Frigate. A Frigate version without VOD HLS returns 404
  and the player falls back to the canonical MP4 route.
- `GET /api/frigate/{event_id}/clip.mp4` is the canonical YA-WAMF clip route. When a persisted recording exists for the event, this route serves it before falling back to the shorter Frigate event clip. Recording responses expose `X-YAWAMF-Clip-Variant: recording`, `X-YAWAMF-Recording-Clip-State: complete|partial`, and the measured `X-YAWAMF-Recording-Clip-Duration` when available.
- `GET` and `HEAD /api/frigate/{event_id}/recording-clip.mp4` remain available as explicit full-visit routes and use the same persisted `{event_id}_recording.mp4` cache file. `X-YAWAMF-Recording-Clip-Ready` is `cached` for a complete file and `partial` for a usable shorter file.
- `POST /api/frigate/{event_id}/recording-clip/fetch` remains available as a manual recovery/warm endpoint. Its response reports `status: ready|partial` and `recording_state: complete|partial`; with recording clips enabled and writable local media storage, YA-WAMF also generates and upgrades full-visit clips automatically for eligible completed detections.

### Species and Leaderboard

- `GET /api/species`
- `GET /api/species/search`
- `GET /api/species/{species_name}/stats`
- `GET /api/species/{species_name}/info` returns cached reference metadata. Known Wikimedia
  JPEG/PNG originals and oversized reference thumbnails use a supported 960-pixel rendition;
  smaller renditions and other providers retain their URLs. This also applies to older cache
  rows without a catalogue refresh or database write.
  An optional `scientific_name` (1–200 characters) binds a reference to that exact
  taxon. Garden uses this to avoid ambiguous common-name bird searches. These
  lookups use Wikipedia and iNaturalist, require the scientific identity in the
  article or exact active taxon name, and have a separate language/identity cache.
  They never reuse name-only cached articles. If neither source matches, text
  and photographs stay unavailable. `refresh=true` bypasses either cache.
  `extract` and `description` are readable plain text: provider HTML, comments,
  scripts and styles are removed, entities are decoded and paragraph breaks are
  retained. This also applies when reading older cached summaries, without a
  cache refresh or database rewrite.
- `GET /api/species/{species_name}/range`
- `GET /api/species/common-name-override?scientific_name=...` (owner)
- `PUT /api/species/common-name-override` (owner; preserves the provider name separately)
- `DELETE /api/species/common-name-override?scientific_name=...` (owner; restores the provider name)
- `DELETE /api/species/{species_name}/cache` (owner)
- `GET /api/leaderboard/species` (per species: window and previous-window counts, confirmed and
  call-matched detections in the window; `history_start` and `previous_window_complete` say whether
  the previous window was fully recorded; with eBird configured, `reported_nearby` per species and
  the `nearby_radius_km` / `nearby_days_back` of that check; `window_visit_count` and
  `window_prev_visit_count` fold captures of one canonical species on one camera with a 60-second inactivity gap, as the
  dashboard does, while `window_count` stays frames)

### Taxonomy

Catalogue data only, the same for every reader. Birds take order, family and genus from the pinned
IOC World Bird List release and the ranks above Aves from Catalogue of Life; each taxon says which
in `source`. Intermediate ranks a source records (subphylum, infraphylum, parvphylum, megaclass) are
returned with `principal: false` so a view may collapse them. A taxon id is the catalogue identity:
for a species it is the same `species_id` detections carry.

- `GET /api/taxonomy/{taxon_id}/lineage` — the taxon and every taxon above it, root first, each with
  rank, scientific name, common name in the reader's language where one exists, source and
  `species_count`, the species beneath it. 404 when the catalogue does not hold the taxon.
- `GET /api/taxonomy/lineage?scientific_name=` — the same lineage for a species named by its
  scientific name, as a detection carries it. Only species resolve; 404 for a name the catalogue
  does not hold.
- `GET /api/taxonomy/{taxon_id}/children` — the taxa directly beneath one in the source's order
  (IOC sequence for birds), each with `species_count`. Query: `limit` (1 to 5000, default 500).

Every taxon in these responses also carries what this feeder has seen beneath it: `seen_species`
(distinct species) and `seen_count` (visible detections). The owner sees the whole history; a
guest sees the window public access allows, as everywhere else.

### Statistics

- `GET /api/stats/daily-summary` — includes `counted_birds` (visible child observations) and
  `counted_captures` (captures with at least one stored bird observation) for the same daily
  window. These counts cover analyzed captures and may count the same bird in later captures.
  Visits for the same last-24-hours window use the leaderboard's rule (a frame opens a visit unless the
  same canonical species was on the same camera within 60 seconds of the running latest verified event end, or capture time when the end is unavailable): `visit_count`, `hourly_visits`
  (24 local-hour buckets by when each visit began), `camera_visits` (visits and last sighting per
  camera; `null` for a guest who may not see camera names) and `visit_count` on each `top_species`
  entry, which is now ordered by visits. `total_count` and `hourly_distribution` still count frames.
- `GET /api/stats/detections/daily`
- `GET /api/stats/detections/timeline`
- `GET /api/stats/detections/activity-heatmap` (optional `species` limits the grid to one species)
- `GET /api/stats/uptime` (owner) Availability over a recent window, derived from heartbeat rows
  written every 5 minutes. Buckets with no heartbeat report `down`; buckets from before the first
  heartbeat ever recorded report `unknown`, because a fresh install has no history and that is not
  an outage. Query: `hours` (1 to 168, default 24), `bucket_minutes` (5 to 240, default 60).

### Classifier and Models

- `GET /api/classifier/quarantine/revalidation` (owner only, no-store): current exact profile, eligibility and latest process-local attempt.
- `POST /api/classifier/quarantine/revalidation/prepare` (owner only): reserve a client UUID `attempt_id` with a current 64-character `profile_fingerprint`. No native work starts; the upload reservation expires after five minutes.
- `POST /api/classifier/quarantine/revalidation/{attempt_id}/inputs` (owner only): multipart `images` (exactly three distinct photos, each up to 25 MiB) and `video` (one clip up to 32 MiB). Total stream limit includes 1 MiB multipart overhead. A current reservation, unchanged profile and unchanged incidents are required. Starts one bounded disposable-process diagnostic; returns status immediately after input acceptance.
- `POST /api/classifier/quarantine/revalidation/{attempt_id}/cancel` (owner only): cancels a reservation or waits for diagnostic child cleanup. Never clears retained crash evidence. States are `idle`, `uploading`, `checking`, `running`, `restoring`, `succeeded`, `failed`, `cancelled`, `superseded`. Approval lasts only in the current application process and only for matching isolated workers; restart requires explicit revalidation again. See [the safety contract](reviews/2026-10-19-owner-native-profile-revalidation.md).

Native quarantine retains a stable primary model/provider/runtime block across
video-frame and crop/wildlife artifact changes; process-local approval remains
bound to the full checked profile. Existing incident files are retained. Failure
status/audit messages use allow-listed input, output, crop, provider or device
causes where available, with recognised GPU device codes only. Raw child stderr,
exception details and uploaded paths are not returned. Unreadable/malformed or
excessive saved evidence makes the profile ineligible for owner revalidation.
See the [evidence identity and failure-report contract](reviews/2026-10-21-native-quarantine-evidence-and-failure-reports.md).

- `GET /api/classifier/provider-validation` (owner only): automatic accelerator recovery state, model, provider, reason and check time. States are `idle`, `running`, `succeeded`, `failed`, `interrupted` and `superseded`.
- `GET /api/classifier/status`
- `GET /api/classifier/labels`
- `GET /api/classifier/wildlife/status`
- `GET /api/classifier/wildlife/labels`
- `GET /api/classifier/debug` (owner)
- `POST /api/classifier/test` (owner) — upload limits below apply
- `POST /api/classifier/classify` (owner)
- `POST /api/classifier/probe` (owner)

Image uploads to the test, classify, probe and wildlife test endpoints are
bounded: files over 25 MB, or images over 80 megapixels once decoded, are
refused with `413` before any classification work runs.
- `GET /api/classifier/wildlife/debug` (owner)
- `POST /api/classifier/wildlife/test` (owner)
- `POST /api/classifier/wildlife/download` (owner)
- `POST /api/classifier/download` (owner)
- `GET /api/models/available` (owner)
- `GET /api/models/installed` (owner)
- `GET /api/models/families/resolved` (owner)
- `POST /api/models/{model_id}/download` (owner)
- `GET /api/models/download-status/{model_id}` (owner)
- `POST /api/models/{model_id}/validate` (owner) — trial-activates a classifier, validates every globally safe or reviewed candidate provider in the running image/host/model intersection in isolated processes, compares accelerator output with a CPU baseline, records schema-4 artifact/runtime/hardware-bound eligibility and median inference latency, orders passing providers by measured latency, and restores the previously active model. Crop-detector artifacts are rejected with `409`.
- `POST /api/models/{model_id}/activate` (owner) — rejected with `409` if the artifact is a crop detector or the classifier has not been validated for this artifact/runtime/install (unless it is bundled or already active); after activation succeeds, applies the first still-eligible provider and never carries an explicit provider from the previous model.
- `DELETE /api/models/{model_id}` (owner) — removes an installed model's files and reports `bytes_freed`. Irreversible: the model must be downloaded again. Refused with `409` when the model is active or mid-download, and `404` when it is not installed. The id may contain a slash for a region variant, for example `medium_birds/eu`.

MogaNet-S EU, ConvNeXt-V1 Tiny EU, RegNet-Y-8G EU, and UniFormer-S EU are retired from the
current catalogue. Download, validation, and activation requests for those IDs return `410 Gone`.
Their existing release files remain available to pre-3.0 application versions during the
compatibility window; current releases neither list nor run them.

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
| `active_model_candidate_providers` | Reviewed global candidates that this model's isolated compatibility sweep may probe. A candidate is not automatically selectable. |
| `active_model_validated_providers` | Providers that passed current artifact/runtime/install validation for the active model. |
| `validated_provider_preference_order` | Passing providers ordered by this installation's measured latency. |
| `selected_provider` | Saved preference from configuration. An image mismatch does not rewrite it. |
| `active_provider` / `inference_backend` | Provider and backend resolved for the runtime; inspect `runtime_source` before claiming a loaded worker. |
| `runtime_source` | `worker` is a worker-reported loaded session; `in_process` or `in_process_fallback` describes a loaded parent session. `planned` and `default` do not prove inference has run. |
| `labels_count` | Number of ordered catalogue outputs for this artifact, or legacy label-file entries if no complete catalogue mapping is available. It is independent of whether the parent process holds the model. |
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
Each compatibility summary row has `requested_provider: "validation_sweep"`. Its accuracy fields
are zero placeholders, not measurements, and its `mean_latency_ms`, `p50_latency_ms` and
`p95_latency_ms` all hold the best provider's median inference latency. Clients should use the
marker, not a zero score, to tell such a row from a measured one.
Compatibility-only clients should label the run **Compatibility check only**, omit accuracy/mean/p95
claims, and read measured provider medians from `device_matrix.json`.
Compatibility summaries also expose `validated_providers` and `failed_providers` per model; the
measured passing order becomes the current-install activation and `Auto` recommendation.
`discover_providers=true` additionally probes packaged, host-visible providers omitted by current
model metadata. Passing undeclared rows are reported as `declared: false` and under
`discovered_providers`; they do not widen runtime eligibility until the registry is reviewed.

### AI

- `POST /api/events/{event_id}/analyze` (owner to generate)
- `GET /api/events/{event_id}/conversation`
- `POST /api/events/{event_id}/conversation` (owner)
- `GET /api/leaderboard/analysis` (owner)
- `POST /api/leaderboard/analyze` (owner)

All supported providers use the same failure contract for analysis, charts and chat.
Provider rate limits and temporary unavailability preserve `429`/`503` and a numeric
`Retry-After` header when supplied. Timeouts, malformed replies and empty answers return
an error rather than successful analysis text. Failed replies are not cached or added as
assistant conversation turns, and do not replace an existing successful analysis. A failed
chat request retains the owner's question. Retrying requires a new explicit request.

Forced analysis regeneration clears the conversation only when the new analysis is
successfully saved, in the same database transaction. A changed analysis or new
conversation turn during provider work returns `409` and preserves the newer state.
A late chat reply also returns `409` if its question was cleared or its analysis
changed. The prompt and its revision are read together; a concurrent change to the
stored capture identity, displayed species, time, temperature or weather also
returns `409`. Unrelated favourite changes do not reject completion. Refresh before
retrying; the server does not repeat a paid provider call.

### Range filter

Owner only; guests receive `401` or `403`. See [Range filter](features/range-filter.md) for the
rules. The switch itself is `range_filter_enabled` and the finest region is
`range_filter_region_level` (`county`, `state` or `country`) on `GET`/`POST /api/settings`.

- `GET /api/range-filter/status` — whether new detections are being range-checked right now
  (`filtering`) and, in one `reason`, why not: `active`, `ready` (list present, switch off),
  `needs_location`, `needs_ebird_key`, `waiting_for_list`, `lookup_failed`, `location_changed`,
  `list_stale` or `list_unusable`, with `problem` naming the failure. Also the region used and
  why it is coarser than the setting (`region.note`), the species counts, BirdNET-Go species heard
  in the last year, when the list was refreshed and goes stale, and how the active model's labels
  fall against the list (`model.out_of_range`, `model.unmatched`).
- `POST /api/range-filter/refresh` — starts a background fetch of the regional list and returns
  the status with `refreshing: true`. Poll the status to see it finish.
- `GET /api/range-filter/preview` — read-only: species recorded here in the last 90 days that the
  list treats as out of range, with detection counts, then how many species the active model can
  name that would be set aside, with examples. `available` is false without a current list.
- `GET /api/range-filter/skips?limit=` — detections set aside as out of range, newest first
  (`limit` 1–100, default 20), so a vagrant can be found and recorded by hand.
- `GET /api/range-filter/decisions/{frigate_event}` — what the filter changed for one detection:
  `{"decision": null}` when nothing, or the original label and score and the in-range label kept.

A detection set aside is dropped with reason `filter_out_of_range`, and `POST
/api/events/{event_id}/reclassify` can answer `no_result` with reason `out_of_range`.

### Settings and Maintenance

- `GET /api/settings` (owner)
- `GET /api/settings/public` — the display preferences a viewer needs, served identically to a
  guest and to an owner. Deliberately unauthenticated, and an allowlist rather than a filtered
  copy: a setting is public because it is named in `backend/app/models/public_settings.py`, so a
  new one is public or owner-only by decision rather than by whether anyone remembered.
  `bird_counting_enabled` says whether new captures are analysed to count birds (high-quality
  snapshots on, with clips available), so the Dashboard can hold its counted-birds figure while
  the day loads.
- `POST /api/settings` (owner)

Settings writes are partial and use the flat API field names, rather than the nested
`config.json` layout. Omitted fields stay unchanged. Empty or redacted secrets retain
the saved value; they do not clear it. A provider or execution-mode change reloads
the classifier, as does a saved-coordinate change. For example:

```http
POST /api/settings
Authorization: Bearer <token>
Content-Type: application/json

{
  "classification_threshold": 0.7,
  "inference_provider": "auto",
  "location_latitude": null,
  "location_longitude": null
}
```

Here both explicit `null` coordinates clear the saved feeder location; omitting them
keeps it. Location-aware DINOv2 receives either a complete valid coordinate pair or
neutral metadata, including in subprocess workers. It receives no date or uncertainty.
Use `/api/classifier/status` after reload to distinguish saved preference from the
worker-reported runtime.

`bird_crop_inference_provider` independently selects the accurate bird finder's
device: `auto` (default), `cpu`, `intel_cpu`, `intel_gpu`, `intel_npu`, or `cuda`.
New explicit accelerator choices require current validation for the selected finder,
artifact and host; otherwise the write returns 409 before changing settings. Send
both fields together to select RF-DETR on an already validated NPU without first
activating its automatic recommendation:

```json
{"bird_crop_accurate_detector": "rfdetr_nano", "bird_crop_inference_provider": "intel_npu"}
```

Changing either field reloads the classifier workers. If a saved explicit device
later loses its validation or fails, the accurate finder uses CPU instead of another
accelerator. An unchanged stale preference can remain in an unrelated settings save.
The fast fallback finder still chooses its own validated device automatically.

`recording_frame_delay_seconds` is an owner-only number from 1 to 120 (default 12).
It controls the initial wait for new `classification_image_source: recording_snapshot`
events, including when notifications can first be sent. Later tracked snapshot metadata
received during the wait is used. Omitted values stay unchanged; invalid or null values
return 422. It does not reclassify saved detections or wait indefinitely for an event end.

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
- `POST /api/settings/ha-weather/test` (owner) — fetches a live reading from the configured
  Home Assistant weather source so the settings page can prove the URL, token, and entities work.
- `POST /api/settings/llm/test` (owner) — returns structured AI diagnostic metadata (`provider`,
  `model`, `frame_count`, `failure_stage`, `retryable`, and optional `retry_after_seconds`) for the
  Settings multi-stage test panel. Provider 429 and 503 statuses are preserved.
- `GET /api/settings/export` (owner) — downloads the whole persisted configuration as one JSON
  file. **This export contains your secrets in the clear** (API keys, tokens, MQTT and SMTP
  passwords) because it has to restore them. Treat the file like a password.
- `POST /api/settings/import` (owner) — restores a configuration backup. The payload is validated
  before anything is written (`422` on a bad shape), and enabling authentication without a password
  hash is refused. A successful import replaces the current configuration and broadcasts the
  changed fields. It keeps this installation's `auth.session_secret` and `auth.oauth_token_secret`,
  which sign current logins and decrypt OAuth tokens stored in this database, and it applies the
  same follow-up as a settings save: a classifier reload when the model, provider, execution
  mode or saved feeder coordinates change, and forgetting the telemetry installation when telemetry is turned off.
- `GET /api/maintenance/taxonomy/status` (owner)
- `POST /api/maintenance/taxonomy/sync` (owner)
- `GET /api/maintenance/stats` (owner) — total detections, the oldest one, the saved
  `retention_days`, and `detections_to_cleanup`: how many the saved retention deletes at the next
  cleanup. `kept_newest_per_species` is the per-species floor and `automatic_cleanup` says whether
  the scheduled cleanup runs (on start, then every 24 hours). The optional `retention_days` query
  parameter (0 to 36500) previews another window without changing anything:
  `preview_detections_to_cleanup` is how many detections that window would delete, counted with the
  cleanup's own rule (hidden detections count; favourites and the per-species floor are kept), and
  `preview_retention_days` echoes the window. Both are `null` without the parameter.
- `POST /api/maintenance/cleanup` (owner)
- `POST /api/maintenance/favorites/clear` (owner)
- `POST /api/maintenance/purge-missing-clips` (owner)
- `POST /api/maintenance/purge-missing-snapshots` (owner)
- `POST /api/maintenance/purge-missing-media` (owner) — applies your configured missing-media
  policy to every detection whose Frigate event or media has gone. With the policy set to `delete`
  this **permanently removes** those detections; `mark_missing` and `keep` do not.
  All three missing-media scan endpoints return an `errors` count for unsuccessful event checks.
  Timeouts, authentication/server errors and unusable responses leave the existing detection
  and its media state unchanged. Only confirmed absence applies the missing-media policy.
- `GET /api/maintenance/timezone-repair/preview` (owner) — reports which legacy detections have a
  timestamp shift, validated against Frigate, and changes nothing.
- `POST /api/maintenance/timezone-repair/apply` (owner) — applies those repairs. Requires
  `{"confirm": true}`; anything else is a `400`. Returns `409` while another maintenance job holds
  the lane.
- `POST /api/maintenance/video-classification/reset-circuit` (owner) — reopens the live and
  maintenance video-analysis circuit breakers after a transient Frigate outage. Queued and running
  jobs are preserved, not discarded.
- `POST /api/maintenance/analyze-unknowns` (owner)
- `GET /api/maintenance/analysis/status` (owner)
- `DELETE /api/maintenance/feedback/clear` (owner)
- `GET /api/cache/measurement` (owner, `no-store`). Without `measurement_id`,
  starts a read-only storage measurement or joins the one already running.
  Returns `id`, `status` (`running`, `completed`, `failed`), `started_at`,
  `completed_at`, `stats` (the cache-stats shape only on success), and `error`.
  Poll with the returned `measurement_id`; polling never starts a new scan.
  Up to 16 process-local results are retained. A missing/expired id or restart
  returns `404`; start a new measurement to recover. The UI bounds each request
  to ten seconds and the polling session to ten minutes, retaining the pending
  id for Retry. Slow filesystem I/O continues independently of the request.
- `GET /api/cache/stats` (owner). Includes `storage_available` (false when the media folder cannot
  be written, so nothing is being kept), `archive_count`, `archive_size_bytes` and the favourite
  counts by archive state. `garden_count`, `garden_size_bytes` and `garden_size_mb` describe the kept
  photos and clips of confirmed Garden animals; they are included in `total_size_bytes`. `cache_enabled` and `cache_snapshots` were removed with their settings.
- `GET /api/leaderboard/portraits?span=&limit=` (guest-rate-limited). This feeder's newest stored
  crop of each leading species, for the leaderboard's reel and spotlight; a species without one is
  absent. `film_url` is set once a film of that visit is made; for the six leading species a film
  not made yet is asked for in the background. Guests get films only when clips are shared.
- `GET /api/about/showcase?limit=` (guest-rate-limited). One recent crop per species, newest first;
  guests see the public media window, and nothing when snapshots are not shared.
- `GET /api/about/showcase/{event_id}.jpg` (guest-rate-limited). The stored photograph at card
  size, under the same access rules as `snapshot.jpg`.
- `GET /api/about/showcase/{event_id}.webm` (guest-rate-limited). A visit film: four silent seconds
  of 640x360 VP8 WebM cut from Frigate's recording around the visit's best snapshot and framed on
  the bird, under the same access rules as the clip. Answers byte ranges and is never cached. A film
  not made yet is asked for and answered 404 with `X-Film-Status: pending`; a full work queue also
  returns `pending` so a later request can try again. `unavailable` means the film cannot be made
  now, including an unwritable media folder, expired recording, non-Frigate visit or a retry delay.
  Generation admits at most eight jobs and renders one at a time. Missing recordings for active
  or very recent visits can be retried after 30 seconds; other temporary failures wait six hours.
  Failure records are bounded to 256 entries. The newest 40 films are kept under the media cache
  directory in `films/`. Each photo revision has an immutable film filename, so a delayed
  response cannot read a different revision published after its access check.
  A film requires image-bound recording timing and crop coordinates. New crops from Frigate's
  final snapshot retain this alignment, including a manually selected crop of another bird in
  that snapshot. Historical photos and video-derived choices without a proven recording moment
  keep their photograph. Each film is bound to its photo revision; changing the photograph
  invalidates it, including when that change happens during rendering. Legacy films without
  matching provenance are not served.
- `GET /api/about/portrait?utc_offset_minutes=` (guest-rate-limited). This feeder in a few facts:
  `started_at`, `visits` (the shared 60-second visit rule), `detections`, `species`,
  `busiest_day` (the viewer's calendar day, from the offset), `newest_arrival` (seen at least three
  times or confirmed) and `latest_visit` (with `film_url` once made). `scope` is `shared` for a
  guest, whose facts cover only the shared window of `shared_days`.
- `GET /api/about/community` (guest-rate-limited). The telemetry service's active install count,
  cached for an hour; `enabled` is false when update checks are off.
- `POST /api/cache/cleanup` (owner) — applies age retention, removes orphaned media and enforces
  optional `media_cache_per_species_maximum` and `media_cache_max_size_mb` limits. Garden's kept
  media follows the same age retention and storage limit. Limits preserve
  detection history and favourites. `media_cache_bird_scan_mode` accepts `standard` or `intensive`.

Published ordinary cache files left after a capture deletion are retried every five
minutes independently of optional limits. Photographs and generated visit media no
longer have an enable/disable cache switch. Active media
writers and current parent records protect their files; failed local cleanup is retried
on the next pass. Favourite archives and hidden temporary files are outside this sweep.
Local atomic publication/deletion finishes before cancellation releases its coordination;
a stalled filesystem can therefore delay shutdown.

Archived favourite media is resolved before Frigate availability/context checks for MP4 and HEAD
requests. Byte ranges and the existing access/download permissions apply. HLS requests for
archived videos return 404 so the player uses the retained MP4; no archive transcoding is required.

### Backfill

- `POST /api/backfill` (owner) — synchronously imports retained Frigate bird events.
- `POST /api/backfill/async` (owner) — starts the same import as a background job.
- `GET /api/backfill/status` (owner) — returns the latest detection or weather job; `kind` can be
  `detections` or `weather`.
- `GET /api/backfill/status/{job_id}` (owner) — returns one retained job status, including persisted summaries after restart.
- `POST /api/backfill/weather` (owner) — synchronously fills historical weather fields.
- `POST /api/backfill/weather/async` (owner) — starts weather enrichment as a background job.
- `DELETE /api/backfill/reset` (owner) — irreversibly deletes all detections and cached media after
  cancelling and awaiting in-process backfill work.

Backfill accepts `day`, `week`, `month`, or `custom`. Custom `start_date` and `end_date` values are
calendar dates in the browser timezone, and the final day is inclusive. Detection import is
idempotent by Frigate event ID: a stronger image result can update classification fields, but it
preserves existing audio confirmation, weather, same-species taxonomy, the strongest Frigate score,
and sublabel evidence. Backfill applies the same confidence, abstention, blocked-species, and trusted-
sublabel rules as live ingest. Completed snapshots are requested explicitly without a crop and valid,
aligned Frigate box/region metadata restores Frigate's tracked-object crop locally before that shared
gate, independent of the selected classifier's own detector-crop policy. Already-cropped and
temporally unaligned cached images do not receive those coordinates. Taxonomy from a replaced species
is cleared rather than attached to the new identity. Missing cached snapshots can still be repaired
for an existing row. Frigate history fetch or pagination failures fail the job explicitly; partial
history is never reported as a completed empty import. The `new_detections` count includes only
inserted rows; `updated` counts existing detections whose automatic classification improved.
Skipped and error counts are separate. Job status includes `last_progress_at`,
structured skip/error reason counts, and a terminal message. A completed detection import queues an
only-missing weather pass when the maintenance lane becomes available.

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
  - `GET /api/audio/heard-groups?start_date=&end_date=` — BirdNET-Go calls in a window of at most
    93 days. A call that supports a visit the pipeline confirmed (same species, a microphone mapped
    to that camera, within the visit widened by the correlation window) is counted on that visit in
    `matched_visits`, call by call. The rest fold per species into bouts across silences of up to
    `gap_seconds` (300): first and last call, call count, strongest confidence and the BirdNET-Go id
    of the strongest servable call for the spectrogram. Guests get the public window, no visit older
    than it, and no source names when camera names are private; `truncated` says the window held
    more than 20,000 calls
  - `GET /api/audio/species`
  - `GET /api/audio/context`
  - `GET /api/audio/context/event/{event_id}` — nearby BirdNET detections for one persisted visual
    event, using the configured correlation window and camera-to-audio-source mapping. Both retain
    their established array response. The `X-YAWAMF-Audio-Suppressed-By-Mapping` response header
    counts detections that fell inside the correlation window but were excluded by the mapping, so
    clients can distinguish "nothing was heard" from "something was heard on an unmapped microphone"
    without breaking consumers of the response body. Event-scoped rows expose `scientific_name` and
    `matches_visual`; the latter is true when the row independently confirms the persisted visual
    species, including audio that arrived after initial event processing.
  - `GET /api/audio/sources`
  - `GET /api/audio/spectrogram/{birdnet_id}` — proxies the BirdNET-Go spectrogram PNG so no
    BirdNET-Go host or token reaches the browser. `width` is `64`–`1600` (default `400`).
  - `GET /api/audio/clip/{birdnet_id}` — proxies the matched audio clip, forwarding the client's
    `Range` header so `<audio controls>` can seek.

  Both honour **Share audio with visitors**: with it off, a guest gets no audio at all.

`GET /api/events` accepts `event_id` for an exact Frigate event lookup. It retains the same guest
history, hidden-event, and camera-privacy restrictions as the paginated event list.
- eBird:
  - `GET /api/ebird/export` (owner only; guests receive `403`). Exports precise configured location, camera names and non-hidden history in the selected date range. Local CSV export does not require enabling eBird or configuring its API key. Supported legacy owner authentication and auth-disabled owner-equivalent access are preserved.
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
- Location:
  - `GET /api/location/reverse-geocode` — resolves `lat` and `lon` to a state, country, and place
    guess, used to fill the location fields the eBird export needs. Returns `502` when the upstream
    geocoder cannot be reached.
- Email OAuth and testing:
  - `GET /api/email/oauth/gmail/authorize`
  - `GET /api/email/oauth/gmail/callback`
  - `GET /api/email/oauth/outlook/authorize`
  - `GET /api/email/oauth/outlook/callback`
  - `DELETE /api/email/oauth/{provider}/disconnect`
  - `POST /api/email/test`

OAuth authorization, disconnection and submission require owner authentication. Only the three
exact GET callback routes accept a provider redirect without a login header. They require a
provider-bound, single-use state issued by the owner authorization route, expiring after ten
minutes. Invalid, expired or replayed state returns `400` before contacting the provider.
Pending flows are held in memory (at most 256); after a restart, start the connection again.
The callback exception grants no owner role and does not expand cookie authentication.

### Debug (owner)

- `GET /api/debug/config` — the full settings dump with secrets hidden. Passwords,
  tokens, signing and encryption secrets and password hashes are replaced by
  `***REDACTED***`; keys whose names look secret-bearing are hidden too, so a
  newly added secret cannot appear in the dump.
- `GET /api/debug/db/stats`
- `GET /api/debug/connectivity`
- `GET /api/debug/fs/models`
- `GET /api/debug/system`
- `GET /api/diagnostics/errors`
  Diagnostic entries redact credential-shaped fields, known configured secret values
  and common credential URLs at collection and export. Context is copied and bounded
  (2,048 characters per string, 64 items per collection, depth eight and 512 nodes
  per payload field); truncation is marked. Source/correlation fields remain present.
  Failed redaction-context lookup drops details rather than interrupting ingestion.

- `GET /api/diagnostics/workspace` — focused video failure candidates include
  warning, error and critical events, excluding circuit summaries and successful
  CPU recovery or successful snapshot fallback. Routine photo updates and cache
  reuse remain in recent activity.
  Failure candidates are selected from the bounded diagnostic snapshot before
  recent activity is limited to eight events; an older failure can remain visible.
  The newest failure or circuit cause supplies `likely_last_error`, so an older
  circuit cannot override a newer failure. CPU recovery events identify their
  worker pool at the top level.
- `GET /api/diagnostics/bundle` — the whole owner diagnostics bundle as one exportable JSON
  payload; this is what **Settings → Health → Diagnostics export** downloads. `limit` is `1`–`1000`
  (default `200`). Each request gathers fresh server health, classifier, queues and
  bounded recent diagnostics even when no local UI error exists. The response includes
  `generated_at`, `schema_version` and `server.startup_instance_id` to identify its capture.
  It is a support snapshot, not a restorable configuration/history backup.
  Workspace and bundle responses also include optional `system_telemetry` evidence
  in the `/api/system-telemetry/history` response shape. The owner-only `drm_diagnostics`
  field retains the last two timestamped probe summaries: read/error and client-turnover
  counts, and at most 64 allow-listed counter observations each. Counter observations
  include current/previous busy and total values, units and measurement-state codes;
  arbitrary driver/engine text, raw procfs, client IDs and exception messages are excluded.
  It reads the existing bounded history without sampling or inference; unmeasured accelerator values remain null.
- `POST /api/diagnostics/clear`

### Model evaluation (owner)

Runs labelled-image accuracy evaluation or a compatibility-only device sweep.
Installed classifiers are the default accuracy scope. A compatibility run also
checks installed crop detectors. `model_ids` narrows both groups to the requested
installed, ready artifacts; crop-only requests require both `compat_only=true`
and `sweep_devices=true`. A missing requested artifact fails rather than checking
an unrelated model. `sweep_all_models=true` can download the registry. Evaluation temporarily switches the
active model and attempts to restore it afterwards. Avoid competing model changes
during a run and verify the selected model/provider when it finishes.
See [Model evaluation](features/model-evaluation.md).

- `POST /api/diagnostics/model-eval/runs` — start a run.
- `GET /api/diagnostics/model-eval/runs` — list runs.
- `GET /api/diagnostics/model-eval/runs/{run_id}` — one run's status and results.
- `GET /api/diagnostics/model-eval/runs/{run_id}/{artifact}` — download an existing run
  artifact with owner authorization. Compatibility-only runs normally write `summary.json`
  and `device_matrix.json`; accuracy/per-image files are not implied. An allowed filename
  that this run did not write returns `404`. The media-only session cookie does not authorize
  these downloads; browser clients use the owner API client, then download the fetched blob.
- `POST /api/diagnostics/model-eval/runs/{run_id}/cancel` — stop a run in progress.
- `DELETE /api/diagnostics/model-eval/runs/{run_id}` — delete a run and its artifacts.

A minimal compatibility-only request for one installed classifier is:

```http
POST /api/diagnostics/model-eval/runs
Authorization: Bearer <token>
Content-Type: application/json

{
  "sweep_devices": true,
  "compat_only": true,
  "model_ids": ["dinov2_b14_inat21_metadata_336"]
}
```

The response is `{"run_id": "<run-id>"}`. Poll that run's status, then fetch the
artifacts appropriate to its mode. A successful sweep proves compatible execution on the tested
inputs, not accuracy at a new feeder. Deleting a run permanently removes its evidence
and files; download evidence you need before deleting it.

To check only RF-DETR Nano without activating an identification model, use:

```json
{
  "sweep_devices": true,
  "compat_only": true,
  "model_ids": ["bird_crop_detector_accurate_rfdetr_nano"]
}
```

This still fetches the evaluation image panel and runs disposable native probes.
It records host-specific crop eligibility and recommendations. Loaded crop
sessions adopt a changed recommendation on their next use; an unchanged failed
accelerator keeps its CPU fallback rather than retrying every frame.

### AI Usage Stats (owner)

- `GET /api/stats/ai/usage`
- `DELETE /api/stats/ai/usage`

## Rate Limiting

- Login endpoint has strict per-IP limits.
- Guest/public endpoints are rate-limited by public-access settings.
- Video share-link creation is rate-limited.

The public `/api/auth/status` response advertises `public_access_rate_limit_per_minute`
so clients can pace history refreshes. Limits apply per endpoint and client address;
the field is pacing metadata and grants no extra access.

## Compression

The bundled nginx gzips `application/json` responses of 1 KiB or more under `/api/`, including
`GET /api/classifier/labels` (about 214 kB uncompressed and 72 kB compressed). Compression is
off for `/api/sse`, video clips and HLS, and images and audio are never compressed. JSON
responses carry no secret beside reflected request input, and JSON reads authenticate with a
Bearer header that a cross-site page cannot send, so compression does not create a BREACH
length oracle.

## Best Practices

1. Prefer JWT auth over legacy API key.
2. Use HTTPS in production.
3. Put YA-WAMF behind a reverse proxy with explicit trusted proxy hosts.
4. Treat Swagger/OpenAPI as canonical for integration code generation.

5. Use SSE (`/api/sse`) for realtime UI updates instead of short polling. Owner streams
   carry detailed messages. `garden_history_changed` is an owner-only invalidation
   emitted after an automatic Garden result is committed, including removal for person
   evidence. It contains no capture ID or metadata; reread the owner-only Garden history
   with the current filters. Guest streams carry only `public_history_changed` and
   `public_access_changed` invalidations, in addition to connection/heartbeat frames;
   fetch allowed data through the public HTTP API and refresh sharing preferences.

## See Also

- [Getting Started](setup/getting-started.md)
- [Configuration](setup/configuration.md)
- [Authentication & Access](features/authentication.md)
- [Troubleshooting](troubleshooting/diagnostics.md)

### Local audio visibility

- `PATCH /api/audio/history/{detection_id}` (owner): set `{ "hidden": true }` to hide a local
  audio detection, or `false` to restore its history row. Returns `{ "id": 123, "hidden": true }`;
  unknown IDs return 404. Hiding removes buffered evidence and excludes the row from history,
  summaries and future correlation. This does not write to BirdNET-Go.


### Saved Garden animal crops (owner)

Garden capture responses include nullable `crop_url` and `crop` evidence alongside
`snapshot_url`. A crop is a separate saved preview, never a replacement for the full
photo used by identification. `crop_url` is emitted only for a confirmed capture with
saved pixels. Its evidence records source kind/checksum, frame and crop dimensions,
normalized XYWH box, source time window, aligned Frigate frame time when applicable,
and the saved JPEG checksum.

- `GET /api/garden/{capture_id}/crop` returns the private JPEG, `404` when unavailable
  or no longer confirmed, and `409` if its checksum differs from the evidence.
  Signed-in browsers may use their owner media session cookie for this read-only
  image request. Guest cookies are refused; storage statistics and review actions
  still require API authentication.
- `GET /api/garden/crops/storage` returns `count`, `bytes`, `limit` and
  `max_bytes_per_crop` for the bounded preview store.

Both endpoints require owner authentication and the Garden beta. Media responses
use `Cache-Control: private, no-store` and `X-Content-Type-Options: nosniff`.
Person revocation, dismissal and history cleanup remove saved pixels. Preview
reclamation retains capture/name metadata; crops do not make expired originals
confirmable, restorable or usable as full-frame model input.
