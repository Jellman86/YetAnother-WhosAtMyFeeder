# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [2.9.9] - 2026-04-16

### Changed
- **UI:** Species leaderboard bar chart (detections over time) no longer shows a legend. The series composition is already visible on hover; the legend was redundant visual noise alongside the chart itself.
- **UI:** Species leaderboard Rising and Most Recent highlight cards are redesigned. The blurred detection-image background is replaced with a clean icon badge (trending-up arrow for Rising, clock for Most Recent) against a tinted card background, improving legibility across all images.
- **UI:** Full Rankings table in the species leaderboard now uses the same rosette SVG badges (gold / silver / bronze) as the Top Performers section. The previous medal emoji approach was visually inconsistent between the two tables.
- **UI:** Video player now uses the browser's native `<video controls>` element directly. Plyr has been removed. All existing UI state — the playing/paused/buffering/ended status pill, the Preparing overlay, share link buttons, download button, and share manager — continues to work via native `HTMLVideoElement` events. Autoplay with muted fallback is handled programmatically; the `autoplay` HTML attribute is not used to avoid browser autoplay-policy races.

### Fixed
- **UI:** Detection modal bottom overlay (species name, sub-name, play button) no longer bleeds over the detail panel on mobile. `overflow-hidden` is applied to the media panel so the `absolute`-positioned overlay is clipped to the video area. Long species names are also truncated to keep the play button on-screen at all times.
- **UI:** Full-visit clip availability now self-corrects shortly after a detection is created. When a probe returns `available=true` but `fetched=false` (the clip exists in Frigate but the local cache has not caught up yet), the store schedules a single re-probe after 8 seconds so the UI reflects auto-caching completing without requiring any user interaction.

## [2.9.8] - 2026-04-15

### Added
- **UI:** Leaderboard species page gains a hero card at the top of the detail panel: shows the most recent detection thumbnail for the selected species, a live pulse indicator when a detection occurred in the last 60 minutes, and a colour-coded confidence badge (green/amber/red by threshold tier).
- **UI:** Species comparison chart is redesigned — the previous line chart is replaced with a donut breakdown (detection share by species) and a stacked bar timeline, giving a clearer at-a-glance picture of species proportions and activity patterns over the selected period.
- **Backend:** Model download integrity verification now reads `sha256`, `labels_sha256`, and `weights_sha256` fields from the downloaded `model_config.json` sidecar, in addition to any values in the Python registry. Config-file values take precedence, so model refreshes on the GitHub Release page are verified without requiring a code deploy. All shipped model config files on the release have been updated with verified checksums sourced from the live production container.

### Changed
- **UI:** Leaderboard weather overlay legend entries (Temperature, Wind Speed) are no longer shown as coloured label boxes — the Y-axis scale alone communicates the range. Both axes remain visible when overlays are active; only the redundant legend items are suppressed.
- **UI:** Sidebar active navigation item now has a 3px left-edge accent bar in the theme's primary colour (teal in default, blue in bluetit) so the current route is immediately legible at a glance instead of relying on the faint background tint alone.
- **UI:** Inactive sidebar navigation text is slightly brighter in dark mode (`slate-300` instead of `slate-400`) for better readability against the near-black background.
- **UI:** Bluetit theme sidebar now has a subtle blue-50 background tint so it feels cohesive with the rest of the blue theme rather than matching plain light mode.
- **UI:** Bluetit light-mode detection cards now have a stronger blue-tinted box-shadow and a more opaque border so cards are clearly distinct from the `#eef3fb` page background.

### Fixed
- **Fixed:** Leaderboard chart no longer compresses the plot area when weather overlays (temperature or wind) are active. The right-side weather axes now use `tickAmount: 4` and a capped label width so they occupy a predictable, compact column regardless of value range.
- **Fixed:** Featured "last N days" stat card on the leaderboard now uses an emerald-tinted background accent instead of a straight top border, which clashed visually with the card's rounded corners.
- **Fixed:** Heading hierarchy on Dashboard and Species pages corrected from h1→h3 jumps to h1→h2, fixing a WCAG sequential-heading-order violation flagged by Lighthouse.
- **Fixed:** Detection card overlay badges (favourite star, verified tick, audio-confirmed mic) now carry `role="img"` so screen readers do not encounter `aria-label` on an element with no accessible role.
- **Fixed:** "Last 3 days" pill text on the Dashboard discovery feed now uses `text-slate-600` instead of `text-slate-500`, bringing the contrast ratio from ~3.4:1 to ~4.7:1 and passing WCAG AA for small text.
- **Fixed:** Detection card image overlay badges now use a slightly more opaque backdrop (`bg-black/60`) so count and status labels remain legible over bright image backgrounds.
- **Fixed:** MQTT event task dictionaries (`_event_task_tails`, `_event_tail_depths`, `_event_pending_tasks`, `_event_pending_payloads`) now have orphaned entries swept out periodically. Followup tasks created inside `_run_pending` did not register done-callbacks, so if a task completed while no new MQTT activity arrived for that event the corresponding tail entries could accumulate indefinitely. The connection watchdog now calls `_sweep_stale_event_task_entries()` on each iteration to remove entries whose tasks are done and have no pending work.
- **Fixed:** SSE stream connections authenticated with a JWT token are now terminated gracefully when the token expires during a long-lived session. The event generator checks token expiry every 60 heartbeats (~20 minutes) and sends a `session_expired` event before closing the stream, instead of the previous behaviour of keeping stale sessions alive indefinitely.
- **Fixed:** Notification and service-test endpoints (`/settings/mqtt/test-publish`, `/settings/notifications/test`, `/settings/birdweather/test`, `/settings/llm/test`) now return proper HTTP status codes for error cases. External service failures (unreachable broker, failed webhook, bad token) return `502`; configuration/validation errors (missing token, disabled service, unknown platform) return `400`. Previously all error paths returned `200` with a `"status": "error"` body, which masked failures from any HTTP-aware caller.

## [2.9.7] - 2026-04-15

### Security
- **Fixed:** Rate-limit IP spoofing via `X-Forwarded-For` — the login brute-force protection now uses `request.client.host` (already normalised by `ProxyHeadersMiddleware`) instead of reading raw proxy headers directly. Previously, any client could set `X-Forwarded-For: 1.2.3.4` and bypass the 5-per-minute login limit entirely.
- **Fixed:** Git hash and branch name are no longer returned in the unauthenticated `/api/version` response, reducing reconnaissance surface. Both fields remain available in the authenticated `/api/health` endpoint.
- **Fixed:** JWT expiry `datetime` is now kept timezone-aware throughout token validation instead of stripping timezone info after decode, preventing potential naive/aware comparison bugs in downstream code.
- **Fixed:** Discord notification errors no longer risk logging the webhook URL — `httpx` exception strings could include the request URL; the error log now records only the exception type and response status.

### Fixed
- **Fixed:** Model downloads now include SHA-256 checksum verification infrastructure. When a `sha256`, `labels_sha256`, or `weights_sha256` field is present in the model registry entry, the downloaded file is verified before activation. Entries without checksums log a warning. This closes the path where a truncated or tampered download could be silently activated as the live ML model.
- **Fixed:** The three per-event lock dictionaries in the Frigate media proxy (`_preview_locks`, `_recording_clip_fetch_locks`, `_snapshot_generation_locks`) are now `WeakValueDictionary` instances. Entries are automatically removed once no coroutine holds a reference, preventing unbounded memory growth over long-running deployments with thousands of unique event IDs.
- **Fixed:** Partial video download temp files are now guaranteed to be cleaned up when an auto-video classification task is cancelled mid-download, preventing leaked `.mp4` files accumulating in the OS temp directory.
- **Fixed:** `location_temperature_unit` is no longer silently dropped when submitted alongside `location_weather_unit_system` in a settings save. Both fields are now applied independently.
- **Fixed:** Duplicate MQTT event inserts (same `frigate_event` ID, possible after service restart) are now treated as idempotent and logged at debug level instead of being recorded as pipeline stage failures.
- **Fixed:** `_table_columns()` in `DetectionRepository` now validates the table name against an explicit whitelist before executing the `PRAGMA table_info()` query. The same pattern is applied to the `GET /api/debug/db/stats` endpoint.
- **Fixed:** The taxonomy repair endpoint no longer uses a redundant `is_running` pre-check before acquiring the maintenance coordinator lock. The coordinator's `try_acquire()` is the authoritative serialiser and the pre-check was a TOCTOU race.
- **Fixed:** Taxonomy repair job progress bar now correctly shows `failed` (red) when the repair errors out. Previously `progress_state === 'failed'` fell through to `closeActiveByPrefix('stale')`, making a failed repair visually indistinguishable from a job that never ran.

## [2.9.6] - 2026-04-15

### Fixed
- **Fixed:** The MQTT stall watchdog no longer fires false-positive reconnects when the feeder is genuinely quiet. YA-WAMF now subscribes to the `frigate/available` retained MQTT topic (published by every Frigate instance since v0.9.0) and uses it as an availability gate: when Frigate explicitly reports `"online"`, all stall-reconnect paths are suppressed regardless of how long `frigate/events` has been silent. When `"offline"` is received, a focused `frigate_went_offline` diagnostic is recorded immediately instead of waiting 30 minutes. When the topic has never been seen, all existing stall-check behaviour is preserved unchanged as a fallback. The `/health` endpoint now exposes a `frigate_availability` dict with `status` and `last_seen_age_seconds`, and the `stall_recovery_warning_active` flag is suppressed while Frigate is confirmed online so the system no longer reports a degraded status during normal feeder quiet periods. (Issue #18 / #33 false-positive follow-up)
- **Fixed:** The taxonomy repair job progress bar now shows as completed instead of stale after the repair finishes. The Settings page was unconditionally calling `closeActiveByPrefix('taxonomy:', 'stale')` whenever `is_running` was false, which marked a just-finished job as stale on every subsequent poll. The handler now checks the backend-provided `progress_state` field and calls `markCompleted` when the job has finished, mirroring the pattern used by the batch analysis handler. (Issue #33)

## [2.9.5] - 2026-04-13

### Fixed
- Detection and events modals now force-probe full-visit clip availability when opened, clearing stale `unavailable` cache from a previous check.
- Detections list, settings, and auth feature flags now refresh automatically after tab regains focus or after SSE reconnects, catching events missed during connection gaps.

## [2.9.4] - 2026-04-13

- **Fixed:** The Errors page pipeline card no longer shows `CRITICAL` status for historical stage failures that have already resolved. The card now reflects `critical_failure_active` (which expires 300 seconds after the last failure) so the status clears automatically once the pipeline recovers, and the summary line distinguishes an active critical failure from a resolved historical one. The incident-synthesis path in the diagnostics store also now guards on the active flag, so a resolved historical failure no longer continues to produce new critical incident records on each health poll. (Issue #18 diagnostics follow-up)
- **Changed:** The MQTT Frigate-topic stall watchdog threshold (`MQTT_FRIGATE_TOPIC_STALE_SECONDS`) now defaults to 1800 seconds instead of 300. The previous 5-minute threshold caused the watchdog to fire continuously between bird visits on low-traffic feeders, producing repeated unnecessary reconnects and a small per-reconnect window where live Frigate events could be missed. The new default matches the real intent of the watchdog — detecting a genuinely stalled MQTT broker — while avoiding false-positive reconnects during normal feeder quiet periods. Note: the BirdNET-assisted stall check threshold (`MQTT_FRIGATE_TOPIC_STALE_SECONDS / 2`) moves to 900 s accordingly; on low-traffic feeders the independent 1800 s watchdog path becomes the primary stall detection path, which is the intended behavior. The env-var override remains available for operators who need a tighter threshold. (Issue #18)

## [2.9.3] - 2026-04-12

- **Fixed:** The owner-only timezone repair workflow now respects the same shared maintenance-work gate as backfill, taxonomy sync, and analyze-unknowns, so it cleanly returns a busy response instead of overlapping other maintenance jobs. The repair scan is also now bounded to legacy detections from the March 31, 2026 UTC timestamp regression window instead of sweeping the full detections table. (Issue #39 follow-up)
- **Changed:** Maintenance workflow concurrency is now controlled independently from video-analysis concurrency. A dedicated `maintenance_max_concurrent` setting defaults to `1`, so backfill, taxonomy repair, timezone repair, analyze-unknowns, and queued maintenance video work remain serialized by default even when owners raise `video_classification_max_concurrent` for clip analysis throughput. The Settings UI now explains that `1` is the recommended maintenance value and clarifies that in-process video analysis is safest at concurrency `1` unless the runtime has been explicitly validated under overlap. (Issue #33 / maintenance hardening)
- **Fixed:** Owner diagnostics bundles and workspace payloads now include taxonomy-repair status and shared maintenance-slot status, so taxonomy failures and maintenance-lane pressure are preserved in support artifacts instead of showing up only as unrelated health noise. (Issue #33 diagnostics follow-up)
- **Fixed:** Live MQTT classification now falls back more defensively when the primary Frigate cropped snapshot is temporarily unavailable. If the cropped snapshot path returns `404` or another fetch failure, YA-WAMF now retries within the normal freshness budget and then falls back through the uncropped Frigate snapshot, Frigate thumbnail, and any cached snapshot before dropping the event as `classify_snapshot_unavailable`. High-quality bird crop replacement now also prefers Frigate `box` / `region` hints before invoking the local crop detector, reducing unnecessary crop-model work when Frigate already provides a usable bird box. (Issue #18 / #33 follow-up)
- **Fixed:** YA-WAMF now includes an owner-only timezone repair workflow for legacy detections affected by the March 31, 2026 UTC timestamp normalization change. The backend can preview and apply safe repairs by validating each stored detection time against the corresponding Frigate event `start_time`, only rewriting rows whose difference is a whole-hour timezone offset. Ambiguous rows and detections whose Frigate events are no longer available are left untouched instead of being guessed. The Settings Data tab now exposes this repair flow with localized UI strings. (Issue #39)
- **Fixed:** CUDA inference capability detection now fails closed when ONNX Runtime advertises `CUDAExecutionProvider` but the provider cannot actually load inside the container. YA-WAMF now runs a safe CUDA provider probe before marking CUDA available, falls back cleanly to CPU when NVIDIA runtime libraries are missing (for example `libcublasLt.so.12`), and surfaces the probe failure in Detection settings instead of repeatedly attempting a broken CUDA path. (Issue #18 follow-up)
- **Fixed:** The official backend and monolithic images now package the CUDA 12 / cuDNN 9 userspace runtime needed by `onnxruntime-gpu`, and YA-WAMF explicitly preloads those packaged libraries before probing or creating CUDA sessions. With a normal NVIDIA container runtime on the host (`gpus: all` / NVIDIA Container Toolkit), CUDA inference should now work as a supported image path instead of depending on ad-hoc host library injection. (Issue #18 follow-up)
- **Fixed:** Live event processing now treats Frigate snapshot unavailability as a bounded recovery condition when MQTT status shows a Frigate stall or stall-recovery reconnect in progress. Instead of dropping immediately after one 2-second retry, the event processor now keeps retrying snapshot fetches for a short, freshness-bounded window so brief Frigate outages or reconnect gaps do not turn into `classify_snapshot_unavailable` drops while BirdNET and MQTT recovery are still healthy. (Issue #33 follow-up)
- **Fixed:** Issue `#33` background maintenance work is no longer allowed to starve indefinitely behind a continuously busy live pipeline. The classifier admission coordinator now grants aged background image work a bounded starvation-relief slot after a short wait, and the maintenance video queue similarly allows one aged maintenance start through under live pressure unless MQTT pressure is already critical. Status payloads now expose when starvation relief is active so diagnostics can distinguish genuine hangs from intentional prioritization. (Issue #33 follow-up)
- **Fixed:** Issue `#33` owner-triggered maintenance now exposes explicit queue-health state and applies safer admission guardrails. Maintenance video status now reports when work is merely queued, deprioritized behind live traffic, stalled under sustained pressure, or recovering from repeated failures. Repeated `Analyze Unknowns` requests now coalesce into the current in-progress batch instead of piling on more maintenance work, while taxonomy repair and historical backfill reject new starts when maintenance is already badly backlogged or a taxonomy run is active. (Issue #33 follow-up)
- **Fixed:** Top-level `/health` status now treats high MQTT handler concurrency as a pressure signal instead of an automatic degradation. YA-WAMF still reports MQTT `pressure_level`, but the service only flips to degraded for MQTT when handler-slot backlog waiting is actively blocking the message loop or a recent slot-wait exhaustion indicates real saturation. This keeps the extreme `issue33-live` hammer profile from looking unhealthy solely because the broker is busy while events are still completing normally. (Issue #33 follow-up)
- **Fixed:** MQTT status now exposes backlog composition so `#33` live-hammer saturation is diagnosable instead of opaque. `/health` now reports per-topic in-flight counts, dispatch totals, Frigate event-tail depth, and whether BirdNET audio work is being coalesced. Under sustained BirdNET bursts, YA-WAMF now keeps only the freshest pending audio payload while one audio task is already active, instead of queuing every intermediate BirdNET MQTT message as separate in-flight work. This preserves recent-audio freshness while reducing low-value MQTT backlog growth under extreme combined load. (Issue #33 follow-up)
- **Fixed:** Issue `#33` Frigate-event backlog is now bounded per event instead of growing an arbitrarily deep same-event tail under extreme load. When newer actionable MQTT payloads arrive for an event that already has active work in flight, YA-WAMF now keeps only the freshest pending Frigate payload for that event, discards superseded intermediate updates, and exposes the superseded count in MQTT health. This preserves latest event state while reducing low-value duplicate work during heavy burst conditions. (Issue #33 follow-up)
- **Fixed:** Leaderboard species rows now use canonical species names for navigation instead of leaking arbitrary variant display labels from individual detections. That means Top Performers / Full Rankings entries such as `House Finch` or `Northern Cardinal` no longer open species modals using variant labels like `House Finch (Female/immature)` that could return `Not Found`. Leaderboard AI chart analysis now also includes weather and sunrise/sunset metadata from the rendered timeline when available, so weather-correlation summaries no longer claim the chart lacks weather data when the underlying leaderboard range already has it. (Issue #40)
- **Fixed:** The frontend no longer misreports backend startup/restart failures as an authentication prompt. When `/api/auth/status` is temporarily unavailable during startup, model reloads, or crash recovery, YA-WAMF now shows a backend-unavailable/retry state instead of collapsing into the login screen. This makes issue `#36` diagnosable as service instability rather than a false auth lockout.
- **Fixed:** Split-backend Docker installs now keep downloaded models on the persistent `/data` volume instead of the container filesystem. The backend image default now points at `/data/models`, and startup will migrate non-conflicting legacy `/app/data/models` entries forward when that older baked-in default is detected, without overwriting anything already present in `/data/models`. This prevents upgrades from continuing to use stale in-container model state that disappears on backend container replacement. (Issue #36 follow-up)
- **Fixed:** The blocked-species picker now searches cached taxonomy and stored detections in addition to the active classifier label list. That means nuisance non-bird taxa such as `Zebra Mussel`, `Bank Vole`, or other previously detected wildlife can be added to the structured blocked list even when the current model no longer exposes them directly. (Issue #37 follow-up)
- **Fixed:** Runtime classifier fallback now fails safely instead of silently installing an unloaded fallback model. When OpenVINO load falls back to ONNX Runtime CPU, or ONNX Runtime falls back to OpenVINO CPU, YA-WAMF now only adopts that fallback if the replacement model actually loads. Otherwise it continues to the final TFLite fallback instead of leaving the classifier in a broken `loaded=false` state that later produced empty historical-classification results. Historical backfill now also reports `background_image_model_unavailable` instead of the misleading generic `classification_failed` when the bird model is unavailable. (Issue #33 follow-up)
- **Fixed:** Model downloads no longer fail with a cross-device rename error (`EXDEV`) when the persistent data volume is mounted on a different filesystem than the container's writable layer. `model_manager` now falls back to a copy-then-delete strategy when `os.rename` raises `EXDEV`, and the `MODELS_DIR` resolution correctly detects a mounted `/data` volume even when the `models/` subdirectory does not yet exist. Bundled model files have been removed from the Docker image entirely — all models are downloaded from GitHub Releases at runtime. (Issue #38)
- **Fixed:** Blocked video classification results are now persisted and surfaced to the user. When a video analysis result matches a blocked species the result is stored in the database (`video_result_blocked` column) but not promoted to the primary detection species. The detection modal shows an amber "Matched a blocked species — not applied" note beneath the video label so owners can see why a video result was suppressed without having to infer it from missing data. (Issue #37 suggestion 1)
- **Fixed:** The video analysis section of the detection modal now displays the resolved common name instead of the raw scientific name when a wildlife-wide model (ConvNeXt, EVA-02) stores a scientific name as the video classification label but the primary detection already has a common name resolved. (Issue #37 suggestion 1)
- **Added:** Events multi-select now includes "Reclassify Selected" and "Delete Selected" actions alongside the existing "Manual Tag Selected" action. Bulk delete calls the new `POST /api/events/bulk/delete` endpoint which removes each detection, broadcasts an SSE `detection_deleted` event per item, and returns a summary with success and failure counts. (Issue #37 suggestion 2)
- **Added:** OpenRouter.ai is now a supported AI provider alongside Gemini, OpenAI, and Claude. Configure it by selecting "openrouter" in AI settings and entering an OpenRouter API key. OpenRouter's OpenAI-compatible API is used for both vision analysis and chat, allowing access to any model available on the OpenRouter platform. (Issue #37 suggestion 3)
- **Fixed:** The Events explorer now refreshes its species and camera filter options immediately after hide/delete mutations, including deletes triggered from the detection modal. Species with no remaining detections no longer linger in the Events species list until a manual refresh or page reload. (Issue #37 follow-up)

- **Changed:** The Jobs page now keeps `Recent` history stable and easier to scan, with newest-finished jobs first and compact job-type icons. The `Active` section now reflects the real backend model instead of inventing fake thread slots: it renders actual running jobs only, keeps their order stable by start time, and treats detection/weather backfills as coordinator jobs that manage classifier worker capacity rather than pretending one backfill job is multiple parallel job cards.
- **Fixed:** Detection AI naturalist results now persist cleanly in the UI after generation. The analysis endpoint returns the saved timestamp, the detection modal writes the fresh `ai_analysis` and `ai_analysis_timestamp` back into the current detection/store state immediately, and selected-detection sync now treats AI fields as first-class state so reopening a detection no longer drops a previously generated analysis. Manual retagging also clears stale AI analysis fields in the UI at the same time it invalidates the old species analysis.
- **Fixed:** Detection AI analysis now follows the same canonical media order as the rest of the app. Owner-triggered analysis now prefers a persisted full-visit recording clip when one exists, otherwise falls back to the Frigate event clip, and finally to a snapshot. Frame sampling stays middle-biased for both clip sources, with a wider central window for full visits so long visits are analyzed more gracefully.
- **Fixed:** The Jobs page now reconciles detection and weather backfill progress independently of the Settings page, so stale synthetic backfill lanes no longer linger in `Notifications & Jobs` after a job finishes or disappears from `/api/backfill/status`. Backfill lane polling also tolerates one failed kind-specific status fetch without freezing the other lane.
- **Fixed:** Low-priority image classification now uses longer admission windows for heavy background callers instead of immediately failing with `background_image_overloaded` after the default `0.5s` queue budget. Historical backfill snapshot classification and maintenance snapshot-fallback classification now pass a larger queue timeout into the background classifier, reducing false terminal capacity errors while leaving live-image responsiveness unchanged.
- **Changed:** The Jobs page now keeps active work in stable visual lane slots instead of reshuffling cards on every poll, and backfill/weather-backfill progress now derives a scoped total from observed progress when the backend reports a running job with `total=0`. The active slots also use clearer icon-led lane and idle states for faster scanning.
- **Fixed:** Detections are no longer reported as “missing in Frigate” when YA-WAMF still has cached media. The Events API now reports cache-backed snapshots and manually fetched full-visit clips honestly even after Frigate event metadata ages out, and the detection modal now uses a softer icon-only Frigate state instead of a hard red badge when media is still recoverable.
- **Fixed:** Maintenance video-classification timeouts for issue `#33` now degrade more safely. When an owner-triggered maintenance job times out and snapshot fallback is allowed, YA-WAMF now records richer timeout diagnostics (source, frame budget, clip probe data, provider/runtime context) and retries that item through snapshot classification instead of immediately treating the timeout as an unrecoverable failure. The video-classifier health payload now also exposes per-source timeout counters plus the latest live and maintenance timeout context.
- **Fixed:** Video-classification jobs are now source-aware for `#33` hardening. Owner-triggered maintenance/bulk analysis uses a separate maintenance breaker, so repeated batch `video_timeout` failures no longer open the live auto-video circuit that guards normal detections. Timeout diagnostics now also record the job source, camera, clip byte size, and runtime/provider context for easier root-cause analysis in exported bundles.
- **Changed:** Desktop navigation is now sidebar-only. The old horizontal desktop nav/layout mode has been removed, legacy stored `layout=horizontal` preferences are migrated back to `vertical`, the appearance layout picker is gone, and the current mobile menu/top-bar behavior stays unchanged.
- **Fixed:** Replacing a cached canonical snapshot now also invalidates the derived card thumbnail, so Events/Explorer cards cannot keep serving a stale pre-HQ image after snapshot regeneration or high-quality replacement.
- **Fixed:** Cleaned dead imports and an unused local from active backend runtime modules so `ruff` output is higher-signal again on the current media/species/auth work.
- **Fixed:** Detection-card thumbnail requests now prefer a derived thumbnail from the canonical cached snapshot when one exists, so Events/Explorer cards visibly benefit from HQ snapshot generation instead of continuing to show Frigate's tiny low-resolution thumbnails.
- **Fixed:** Backfilled detections now participate in the same high-quality snapshot pipeline as live ingest. YA-WAMF caches the backfill snapshot, queues HQ replacement without silently dropping overflow during large backfills, and when the original Frigate event clip is gone it now falls back to the best available full-visit recording clip instead of leaving the raw snapshot in place.
- **Changed:** Completed a broad UI translation pass across all supported locales (`de`, `es`, `fr`, `it`, `ja`, `pt`, `ru`, `zh`) for previously fallback-heavy active strings. Public-view badges, explorer controls, full-visit/video labels, diagnostics copy, leaderboard analytics controls, and new settings/debug/full-visit capability copy now resolve through locale files instead of inline English defaults.
- **Added:** Blue Tit color theme — a selectable accent palette inspired by the app icon that remaps teal/emerald accents to cobalt blue and golden yellow across cards, buttons, gradients, navigation, and focus rings. Selectable in Appearance settings alongside the existing font and layout options, with full i18n support.
- **Changed:** Detection cards redesigned for clarity. Image overlay reduced to confidence badge, time/play controls, and icon-only favorite/verified/audio badges. Audio details, weather breakdown, classification source, and Frigate score moved to the detection modal only. Weather now shown as a compact condition icon with temperature. Camera and date collapsed to a single metadata line.
- **Changed:** Dashboard hero card streamlined to show time, camera, weather condition, and temperature in a single compact row with SVG icons instead of emoji. Detailed weather pills (rain, snow, cloud cover, wind speed) removed from the hero overlay — full weather breakdown remains accessible in the detection modal. Discovery Feed section divider now uses a bottom border, bolder typography, and bordered badge for clearer visual separation from the hero area.
- **Added:** Frigate object-detection score now displayed in the detection modal metadata grid so it remains accessible after removal from the card overlay.
- **Changed:** Leaderboard page redesigned for clarity and visual polish. Removed duplicate hero stat pills, added accent borders and color-coding to summary cards (emerald/amber/sky), consolidated chart controls into a single toolbar row, collapsed weather overlays into an expandable section with active-state toggle styling, replaced chart stat badges with a compact inline summary, redesigned top-3 podium cards with gradient rank badges and proportional detection count bars, upgraded species table with larger rounded thumbnails, inline count bars, striped rows, and color-coded trend values, and added section wayfinding labels.
- **Fixed:** MQTT stall-recovery reconnects are now capped at a configurable maximum (default 5) consecutive no-Frigate reconnects. When the cap is reached, YA-WAMF stops the reconnect loop and records a focused `frigate_recovery_abandoned` diagnostic directing the user to check their Frigate MQTT topic configuration, instead of reconnecting endlessly when Frigate is permanently unreachable or misconfigured (Issue #33 hardening).
- **Fixed:** Video classifier temporary file cleanup now suppresses `OSError` so a secondary cleanup failure cannot mask the actual classification result or error.
- **Fixed:** eBird CSV export now annotates the species comment and submission comment columns with `common name unavailable` when a row falls back to the scientific name because no English common name could be resolved. This makes scientific-name-only rows visually identifiable before eBird import (Issue #23 hardening).
- **Added:** Deploy-recovery now tracks a cumulative recovery-attempt counter in local storage (`getRecoveryCount()`). Diagnostics bundles can inspect this to determine whether a user's tab has been stuck in a repeated reload loop versus a one-time recovery event (Issue #35 hardening).
- **Added:** Regression coverage for circuit-breaker auto-close after cooldown expiry, MQTT stall-recovery reconnect cap and abandoned-diagnostic recording, `MqttError`-path intentional-reconnect flag clearing, and Home Assistant coordinator resilience to malformed `latest_detection` payloads (missing `frigate_event`, non-string `detection_time`, non-integer `total_count`).
- **Fixed:** Automatic video-analysis state now truly takes over detection cards. While a card is being analyzed, the analysis overlay sits above all other card chrome, the timestamp/play/full-visit/action controls are suppressed, and the card border shifts to an analysis accent so hidden controls no longer bleed through above the progress UI.
- **Fixed:** Thumbnail and full snapshot cache behavior are now separated. `thumbnail.jpg` no longer poisons the canonical event snapshot cache, the detection details modal now uses `snapshot.jpg` instead of the low-resolution thumbnail route, and the full snapshot proxy self-heals obviously thumbnail-sized cached "snapshots" by evicting and refetching them.
- **Fixed:** Manual tagging in the Events explorer is now consistently owner-only. The UI no longer exposes multi-select tagging or modal retag/reclassify/delete controls until auth status has loaded successfully and owner access is confirmed, and auth-status load failures now fail closed instead of leaking owner controls.
- **Changed:** The Events explorer multi-select cards now use a full selected-card veil instead of the old in-image `Select` / `Selected` pill or a weak corner selector. Selected cards now get a bolder cyan card border, a frosted cyan-blue overlay above the card content, and a centered checkmark so bulk selection reads clearly from the grid while intentionally masking the underlying card details.
- **Changed:** Full-visit playback now uses a single canonical clip contract in the UI. The player always opens `/api/frigate/{event_id}/clip.mp4`, promoted full visits replace the canonical clip automatically for both authenticated and guest/public viewers, and the old event-vs-full toggle has been removed in favor of a passive full-visit indicator.
- **Fixed:** MQTT stall recovery now stays armed across reconnect boundaries for the `#33` live-ingest failure mode. If a Frigate-topic stall triggers a reconnect and BirdNET remains active in the next MQTT session, YA-WAMF can now detect that Frigate still never resumed and force another recovery reconnect instead of going blind because the new session had zero Frigate messages.
- **Added:** MQTT health now raises a focused stall-recovery warning when Frigate still has not resumed after a prior BirdNET-assisted recovery reconnect. `/health` now exposes the consecutive no-Frigate reconnect count and degrades status while that post-reconnect blind spot is still active, making issue `#33`-style live-ingest regressions visible before users have to infer them from missing detections.
- **Added:** A dedicated `scripts/run_issue33_harness.py` soak harness now exercises the live-ingest and batch-video symptoms seen in issue `#33`. It can stop synthetic Frigate traffic while BirdNET keeps flowing, optionally add unknown-analysis pressure, and fails on missing MQTT recovery reconnects, video-circuit openings, or excessive video-queue backlog.
- **Fixed:** The issue `#33` harness now treats its own induced Frigate stall as test stimulus rather than an automatic failure. A run now passes when BirdNET stays active, the required MQTT liveness reconnect occurs, and the video queue stays healthy, instead of inheriting issue-22 semantics that always fail on the intentionally created stall window.
- **Changed:** The issue `#33` harness can now log in with owner username/password directly instead of requiring a manually copied JWT. Credential-based runs fail with clearer login errors, and the run summary records whether authenticated owner pressure was exercised without writing the password into artifacts.
- **Fixed:** Auto-generated full-visit clips no longer cache prematurely truncated recording windows. YA-WAMF now waits until the requested Frigate recording span should be complete before fetching, validates cached `_recording.mp4` clips against the expected window duration, and evicts stale short recording clips plus their preview assets so later requests can self-heal from Frigate instead of serving a permanently shortened “full visit”.
- **Fixed:** The Home Assistant integration no longer treats `Last Bird Detected` as a plain species-name-only state for repeated detections. The sensor now only emits when a new detection event arrives, so repeat visits from the same species do not get silently swallowed by unchanged coordinator polls.
- **Added:** Home Assistant now exposes `Last Detection Event` and `Last Detection Time` sensors. These provide stable automation triggers for every new detection and a proper timestamp entity instead of relying on raw string attributes.
- **Fixed:** `/api/stats/daily-summary` now computes its 24-hour window using the same naive-UTC basis as persisted detections. This prevents Home Assistant and other clients from lagging behind recent detections when the host local timezone is offset from UTC.
- **Fixed:** Rolling-summary follow-on contracts are now aligned with that UTC window. The Home Assistant count sensor now models the API value as a rolling 24-hour measurement instead of a monotonic "today" total, daily-summary species cards now choose their representative `latest_event` by newest `detection_time` instead of lexicographic event id, and nearby AI/video-share timestamp responses now use the same explicit-UTC serialization contract as the main detection API.
- **Fixed:** The Home Assistant polling coordinator now normalizes malformed `latest_detection`, `top_species`, and `total_count` fields from `/api/stats/daily-summary` instead of leaking invalid payload shapes into sensor state.
- **Added:** Owner diagnostics workspace exports now preserve raw backend diagnostic events and a focused `video_classifier` summary in downloaded issue bundles. Circuit-breaker incidents now carry the latest `video_circuit_opened` context, likely last error, and recent video-classifier events so support bundles retain the root-cause evidence instead of only the grouped health symptom.
- **Changed:** The `Error Bundles` section on the owner `Errors` page now highlights the newest captured bundle in a dedicated availability card and presents saved bundles as clearer cards with a pinned `Newest` state, notes preview, and stronger empty-state copy.

- **Changed:** Browser E2E smoke tests now accept `YAWAMF_BASE_URL` for monolith runs instead of assuming the legacy split-stack `yawamf-frontend` hostname, and the leaderboard inspection smoke test now expects the raw histogram default instead of the old area-chart default.
- **Fixed:** MQTT stall-recovery reconnects no longer get stuck in a clean reconnect loop. When the watchdog intentionally disconnects a stalled MQTT session, the client now clears its pending reconnect flag on the normal post-loop path as well as the `MqttError` path, preventing the monolith from reconnecting endlessly without ever consuming new Frigate or BirdNET messages. This restores recent-audio freshness and normal MQTT topic counters after a stall-recovery event.
- **Changed:** The leaderboard page now opens the `Detections over time` chart in raw histogram mode by default, with smoothing disabled until the user opts in through the existing chart controls.
- **Fixed:** Stale tabs now recover more cleanly after deploys. The app shell classifies chunk-load and dynamic-import failures as likely stale-bundle errors, performs a guarded one-shot reload per frontend build, and falls back to a warning toast instead of looping if the same stale-bundle condition persists after reload.
- **Fixed:** Owner health checks now treat a backend/frontend build mismatch as a deploy-recovery signal instead of only a diagnostics signal. When the backend version moves ahead of the current bundle, the app uses the same guarded reload path to refresh an old tab before its stale UI state drifts further.
- **Added:** Pure deploy-recovery regression coverage now locks in the stale-bundle classifier, one-shot reload guard, warning fallback, and backend/frontend version-drift handling.
- **Fixed:** Batch-analysis progress cards now recover cleanly after a backend redeploy or restart. When owner health checks detect a new backend `startup_instance_id`, the frontend clears only the synthetic `reclassify:progress` batch state and lets the next successful queue-status poll recreate it if work is still running, preventing old tabs from showing a stale `Working...` batch card indefinitely after `/api/maintenance/analysis/status` returned transient `502` errors during a deploy.
- **Fixed:** Owner queue-status polling now explicitly bypasses browser/proxy caches and also self-heals orphaned synthetic `Batch Analysis` jobs. If a tab misses the terminal batch update but later receives a fresh zero-queue `/api/maintenance/analysis/status` response, the stale `reclassify:progress` card is settled automatically instead of lingering at states like `0 / 21 · 1 stale` until a manual refresh.
- **Added:** Live-update regression coverage now asserts that backend instance changes clear orphaned synthetic batch-analysis state without removing per-event reclassify jobs or per-event progress notifications.
- **Fixed:** Detection and stats timestamps now follow an explicit UTC API contract instead of leaking naive server-local datetimes. New detections, notification/update timestamps, SSE payloads, daily summary latest-detection cards, leaderboard species `first_seen` / `last_seen`, species stats, and related nested detection responses now serialize datetimes with an explicit `Z` suffix so browsers render the correct local wall time instead of treating UTC values as already-local timestamps.
- **Added:** Regression coverage now asserts explicit UTC serialization on live detection broadcasts, `/api/events` rows, `/api/stats/daily-summary` latest detections, and species stats `first_seen` / `last_seen` / `recent_sightings` payloads, including legacy naive timestamps already stored in SQLite.
- **Fixed:** The species leaderboard no longer throws `500 Internal Server Error` when `Unknown Bird` rows are present. The canonical unknown-species leaderboard window query now binds the correct rolling-window parameters for the aggregate camera-count and outer `WHERE` clauses, fixing the live SQL binding error on `/api/leaderboard/species`.
- **Fixed:** Timeline compare-series queries on the leaderboard page now include the canonical taxonomy join they rely on when resolving selected species names. This fixes the live `no such column: tc_filter.taxa_id` failure on `/api/stats/detections/timeline` when the page requests compare lines for real species.
- **Added:** Leaderboard regression coverage now exercises both `/api/leaderboard/species` with hidden noncanonical detections and `/api/stats/detections/timeline` with canonical compare-species selections, so the page’s top-species and detections-over-time sections cannot silently regress independently.

- **Changed:** YA-WAMF now documents the coming deployment transition more explicitly. `v2.x` continues to support the legacy split frontend/backend stack, but `v3.0` is now planned around a monolithic single-container deployment with a dedicated split-to-monolith migration path in the docs.
- **Fixed:** Species-name normalization for Issue #26 is now hardened across all major backend surfaces instead of only the Explorer lists. Broad and non-species model labels such as `Life (life)` and `... and allies` are now treated as `Unknown Bird` consistently for live snapshot saves, video reclassification promotion, SSE/live-update payloads, species search/catalogue pages, daily summary cards, timeline compare overlays, and maintenance unknown-detection selection.
- **Added:** A shared canonical-species helper now centralizes hidden-label handling and user-facing masking for `display_name`, `category_name`, and taxonomy fields. This preserves raw classifier labels in storage for diagnostics while ensuring normal UI/API responses only expose canonical species or `Unknown Bird`.
- **Changed:** `Unknown Bird` matching is now repository-backed and canonical. Query/filter paths no longer depend solely on exact configured unknown labels; they also include hidden noncanonical labels across `display_name`, `category_name`, `scientific_name`, and `common_name`, which keeps filtering, stats, and maintenance jobs aligned with the new masking rules.
- **Fixed:** Blocking `Unknown Bird` now also blocks hidden noncanonical model outputs that would be surfaced as `Unknown Bird` to users, preventing a policy gap where broad labels bypassed the owner’s blocklist.
- **Fixed:** Auto/video classification can no longer reintroduce hidden noncanonical labels as the primary stored species. Video results now refuse to downgrade a known species to a broad/noncanonical label and only promote such labels back to `Unknown Bird` when the existing detection is already unknown.
- **Fixed:** Species and stats aggregates for `Unknown Bird` now include historical hidden noncanonical labels, so leaderboard totals, species-detail counts, recent sightings, daily summary latest-detection cards, and timeline compare series all remain internally consistent after the canonical masking change.

- **Added:** Canonical species identity normalization is now completed end to end. YA-WAMF now treats species identity as `taxa_id` first, then `scientific_name`, instead of relying on raw `display_name` equality for key repository filters and historical rollups.
- **Added:** The maintenance taxonomy-repair action now runs an explicit canonical-identity repair flow that backfills missing taxonomy on historical detections and rebuilds species rollups afterward, so repaired rows immediately collapse into the correct canonical species stats.
- **Changed:** `species_daily_rollup` now stores canonical identity fields (`canonical_key`, `scientific_name`, `common_name`, `taxa_id`) and is rebuilt on canonical keys instead of display name alone, which prevents common/scientific alias variants from splitting leaderboard windows and recent metrics.
- **Fixed:** Canonical taxonomy lookups can now resolve localized common names even when no language hint is available, which hardens maintenance repair and other backend-only reconciliation paths against historical localized labels.
- **Fixed:** Canonical identity repair now uses a safer maintenance policy: it backfills missing canonical taxonomy fields and rebuilds canonical rollups without rewriting already-populated localized `common_name` values just because they are non-ASCII.
- **Fixed:** Species-rollup rebuilds now use an atomic staging-table swap instead of deleting the live rollup table first. A failed maintenance repair can no longer leave `species_daily_rollup` empty, and the normal incremental rollup path retains its original idempotent `ON CONFLICT` upsert behavior.
- **Fixed:** Species detail endpoints no longer double-count canonical species aliases after the repository helpers were normalized. Species stats now query canonical species once per request, while the explicit multi-label aggregation path remains reserved for `Unknown Bird` handling.
- **Fixed:** Canonical identity repair no longer treats a localized stored `common_name` as damaged just because it is non-ASCII. Repairs remain additive for `common_name`, which preserves localized rows such as Cyrillic species names while still backfilling missing canonical taxonomy fields and serving localized read paths through `taxonomy_translations`.
- **Changed:** Manual video reclassification now prefers the persisted full-visit recording clip when one is already cached for the same Frigate event, instead of falling back to the shorter event clip or re-downloading unnecessary media.
- **Changed:** Video frame sampling is now clip-aware. Normal Frigate event clips bias their sampled frames toward the center while still covering the edges, and persisted full-visit clips use a broader whole-visit sampling pattern with lighter center emphasis.
- **Fixed:** The video player now treats already-persisted full-visit clips as the canonical `/clip.mp4` path instead of trying to reload them through the separate recording route, which fixes stale short-clip labeling and the stuck `Loading...` state when toggling to `Full visit` for previously fetched events. The mobile video-action row now wraps cleanly instead of overflowing its buttons.
- **Changed:** Delayed notifications now derive their effective video wait from the actual video-classification pipeline timing, including the clip polling backoff budget, so `delay_until_video` cannot silently time out before video analysis has a real chance to complete. The existing notification timeout now acts only as a larger manual override instead of a smaller cutoff.
- **Fixed:** Manual tag updates now preserve full-visit readiness for the same Frigate event. When a persisted full-visit clip already exists, renaming a detection refreshes that event-based clip state instead of re-offering a redundant `Fetch full clip` action.
- **Changed:** HQ Event Snapshots section in Settings > Data has been reworked for clarity. The toggle is now a dedicated card with a persistent amber **Beta** label, a description line always visible, and an animated sub-panel for the bird-crop and JPEG quality options that only appears when HQ snapshots are enabled. The basic snapshot and video clip cache toggles remain as a compact 2-column grid above it.
- **Changed:** Blue Tit is now the default colour theme for new installs. Existing installs keep their stored preference; this only affects first-run or cleared-storage scenarios. The backend `config.json` default has also been updated to match.
- **Fixed:** The default (teal) colour theme swatch in Appearance settings now renders as a solid teal block instead of a gradient. Only the Blue Tit swatch uses a gradient; each theme now has its own correctly styled swatch.
- **Changed:** Documentation updated for monolith-first deployment. All user-facing docs now lead with `yawamf-monalithic` examples, container command references updated from `yawamf-backend` to `yawamf-monalithic`, Swagger/OpenAPI access clarified (not proxied through monolith nginx), `canary` framing removed, and `:dev` tag in stable-use examples replaced with `:latest`.
- **Changed:** Legacy split deployment (`wamf-frontend` + `wamf-backend`) now carries an explicit end-of-updates notice: no bug fixes, new features, or compatibility guarantees will be provided for the split stack starting with v3.0. Documented in README and the split-to-monolith migration guide.

## [2.9.1] - 2026-03-27

- **Added:** When recording clips and the media cache are enabled, YA-WAMF now auto-generates a persisted full-visit clip for eligible completed detections after the Frigate `end` event instead of requiring manual fetch for each event.
- **Added:** A bounded background reconciler now revisits recent detections that are old enough to have a complete full-visit window and backfills any missing persisted full-visit clips when the original MQTT `end` event was missed or recordings were briefly unavailable.
- **Changed:** YA-WAMF's canonical `/api/frigate/{event_id}/clip.mp4` route now prefers the persisted `{event_id}_recording.mp4` full-visit file when one exists, so the longer clip transparently replaces the short Frigate event clip inside YA-WAMF without modifying Frigate itself.
- **Changed:** The full-visit ready indicator now uses a compact icon-only treatment beside the play button with hover text, and the video player collapses the old short-vs-full toggle once the persisted full-visit clip has replaced the canonical event clip.
- **Changed:** Locale coverage has been expanded again across active settings and jobs surfaces, and a new locale audit test now guards against untranslated English carryover in the highest-traffic non-English UI paths.

## [2.9.0] - 2026-03-26

- **Added:** YA-WAMF can now serve a first-class `Full visit` clip variant from Frigate continuous recordings. Owners can enable it in Settings → Connection → Frigate, choose how many seconds before/after the detection to include, and switch between the original event clip and the longer recording window in the VideoPlayer without leaving the modal.
- **Added:** The Frigate settings panel now includes a recording-clip capability check that inspects the saved Frigate config, reports whether continuous recordings appear usable for the selected cameras, and shows the detected retention window before allowing the feature to be turned on.
- **Added:** Full-visit clips now work through the same access paths as normal event clips, including share links and public-access playback, using the new `/api/frigate/{event_id}/recording-clip.mp4` proxy route and a distinct media-cache key of `{event_id}_recording.mp4`.
- **Added:** Detection Settings now uses a species-search picker for blocked species. New selections are stored as structured `blocked_species` entries with taxonomy identifiers, while unresolved legacy `blocked_labels` continue to render as removable `Legacy` chips for backward compatibility.
- **Added:** A small manual-tag search policy helper now centralizes when the picker should request taxonomy hydration for typed queries, making the modal behavior explicit and regression-testable.
- **Fixed:** The blocklist now matches against both legacy raw labels and structured blocked-species entries across live detection filtering, post-taxonomy save paths, auto video classification writes, and manual reclassification. Blocking a species via the picker now reliably catches common-name, scientific-name, and `taxa_id` matches instead of depending on a fragile exact raw-label string.
- **Fixed:** The manual tag / reclassify picker now hydrates missing taxonomy data for meaningful typed searches instead of only during the initial empty-query load. Species that have never previously been detected can now show a clean common-name primary label and scientific-name subtitle while searching.
- **Fixed:** Species search hydration now strips trailing classifier parentheticals before taxonomy lookup, so labels like `"Cassin's Finch (Adult Male)"` resolve through `"Cassin's Finch"` instead of failing iNaturalist/common-name hydration.
- **Fixed:** Full-visit fetching is now available from the detection details modal as well as the event card. When a recording span is available, owners can fetch the full clip directly from the modal, and detections that have already fetched it show a `Full visit` badge in the media header.
- **Fixed:** Fetched full-visit clips now persist correctly across modal reopen and page reload instead of falling back to the short default clip. The recording-clip probe now reports when a cached full visit already exists, the frontend remembers fetched full visits per event, and the `Fetch full clip` action has been moved out of the snapshot center overlay to sit below the detection timestamp.
- **Fixed:** Detection source badges and confidence panels now reflect the current visible classification source instead of blindly mirroring the historical `manual_tagged` feedback flag. Manual tags that were later superseded by a completed video result no longer leave stale `Manual` pills behind on cards, the hero, or the details modal.
- **Fixed:** Full-visit availability probes now handle streamed Frigate `404` responses safely and use the current camera-recording route shape that Frigate actually exposes. This prevents the fetch button from being hidden behind a probe-side `500` and restores full-visit availability detection for live installs using Frigate's `/api/{camera}/start/{start_ts}/end/{end_ts}/clip.mp4` endpoint.
- **Fixed:** Authentication setup and settings now enforce the same password policy client-side as the backend and surface readable validation failures instead of `[object Object]` or a generic `Failed to save settings` banner. FastAPI/Pydantic validation payloads are normalized into user-facing messages, so username/password setup errors now explain the real problem.
- **Changed:** Locale coverage has been expanded again across the highest-traffic owner flows. Full-visit video controls, detection AI conversation copy, Frigate connection state, shared error-boundary text, and the entire `Settings → Data` section now have localized strings in all supported UI languages instead of falling back to English.
- **Changed:** `ROADMAP.md` and `ISSUES.md` were refreshed to match the current GitHub tracker state: issue `#16` and issue `#21` are closed, the issue-first section no longer points at stale open work, and roadmap item 7 is marked complete on `dev`.
- **Changed:** Roadmap item 1, `Blocked Species — Species Picker + Reliable Matching`, is now completed on `dev`.
- **Changed:** Roadmap item 0, `Full-Visit Recording Clip ("Bird Lifecycle View")`, is now completed on `dev`.

## [2.8.7] - 2026-03-26

- **Fixed:** Blocked labels did not suppress detections where the model outputs a parenthetical plumage or age suffix — for example, `medium_birds` produces `"Cassin's Finch (Adult Male)"` and `"Cassin's Finch (Female/immature)"`, neither of which matched a blocklist entry of `"Cassin's Finch"`. The blocked-label check in the real-time detection pipeline, the post-taxonomy enrichment check, and the manual-tag guard now all strip trailing parentheticals before comparing against the blocklist. The auto video classifier path, which previously had no blocked-label check at all, now also applies the same logic — and always writes the video classification result to the database before returning so that the stale-video watchdog cannot cause an infinite re-queue loop for blocked species (Issue #31).
- **Fixed:** Classifier health remained `degraded` after downloading the active model via the Model Manager. Downloading a model never triggered a classifier reload; only clicking Activate did. The model manager now automatically calls `reload_bird_model()` after a successful download if the downloaded model matches the currently active selection, recovering health without any manual action or container restart. Reload failures are caught and logged as warnings so a transient error cannot affect the download status (Issue #30).
- **Fixed:** Bundled TFLite fallback path in `_resolve_active_bird_model_spec` passed the configured model ID (e.g. `"medium_birds"`) to `_get_model_paths` instead of `"model.tflite"`, causing the fallback to look for a directory rather than the bundled model file and fail. The fallback now correctly searches for `model.tflite`.
- **Fixed:** ONNX models expecting `uint8` input (e.g. the bird-crop detector) received `float32` tensors, causing `INVALID_ARGUMENT` errors at inference time. The ONNX classifier now reads the model's declared input dtype from session metadata after load and returns raw `uint8 NHWC` tensors for quantized models, keeping the existing normalized `float32 NCHW` path for all others.
- **Fixed:** `small_birds_eu` (MobileNet V4 Large) is now correctly listed as GPU not supported. The model passes isolated OpenCL probes but consistently corrupts the GPU context with `CL_EXEC_STATUS_ERROR_FOR_EVENTS_IN_WAIT_LIST` when run after other GPU models in the same inference session — matching the same non-deterministic failure seen on `small_birds_na`. Intel GPU is no longer offered as a provider for this variant.

## [2.8.6] - 2026-03-24

- **Added:** Scheduled cleanup actions are now individually configurable. Three new toggles in Settings → Data allow "Remove Detections Without Clips", "Remove Detections Without Snapshots", and "Analyze Unknown Species" to run automatically as part of the existing 24-hour cleanup cycle. All default to off (opt-in). Manual action buttons are unchanged.
- **Added:** Pushover notifications now support device targeting. A new "Device(s)" field in notification settings accepts one or more comma-separated Pushover device names. Leave blank to send to all active devices (existing behaviour).
- **Added:** Notification language is now configurable in Settings → Notifications. A new "Notification Language" dropdown controls the language used for message text sent to Discord, Telegram, Pushover, and Email — independent of the UI language.
- **Added:** Gmail and Outlook OAuth app credentials (Client ID and Client Secret) are now configurable directly in Settings → Notifications → Email. Previously these could only be set via environment variables; they can now be entered and saved through the UI, unblocking the OAuth "Connect Gmail" / "Connect Outlook" flow for users without direct container access.
- **Added:** Reduced Motion and Zen Mode accessibility toggles are now wired in Settings → Accessibility. Both settings persist to the backend config and apply their respective CSS classes (`reduced-motion`, `zen-mode`) on load.
- **Fixed:** eBird CSV export now resolves English common names for species whose taxonomy cache only contains a localised name (e.g. Russian-locale users whose `taxonomy_cache` was populated with non-ASCII common names). A pre-enrichment pass runs before formatting rows: for each distinct scientific name where no English name was found via the existing SQL COALESCE chain, the exporter calls `get_localized_common_name(taxa_id, 'en')` which checks `taxonomy_translations` first (a single SQLite read per species when warm) and falls back to iNaturalist with `locale=en` only for species never previously exported or viewed in English. Concurrent lookups are capped at 5 to avoid thundering the iNat API on a first export.
- **Fixed:** MQTT stall detection now works for all deployments, including those without BirdNET-Go. Previously, the Frigate topic stall check required active BirdNET traffic as a liveness witness, so visual-only users had no self-healing mechanism if Frigate silently stopped publishing events. A new independent time-based watchdog task now runs alongside the MQTT message loop and periodically checks whether the Frigate topic has been silent for longer than `MQTT_FRIGATE_TOPIC_STALE_SECONDS` (default 5 minutes). When a stall is detected the watchdog disconnects the MQTT session immediately without exponential backoff, allowing fast recovery. The BirdNET-assisted check is preserved as a higher-confidence path that still triggers during the message loop for BirdNET users. Additionally, `_wait_for_handler_slot` now enforces a maximum total wait of `MQTT_MAX_HANDLER_WAIT_SECONDS` (default 120 s) so a flood of permanently-hung tasks can no longer block the MQTT message loop indefinitely. Both new limits are configurable via environment variables (Issue #22).
- **Fixed:** Video analysis failures caused by a Frigate timing race condition. When a Frigate `end` MQTT event fires before the event is committed to the Frigate API database, the auto video classifier's precheck (`GET /api/events/{id}`) received a transient 404 and immediately marked the detection as `video_analysis_failed`, counting toward the circuit breaker. After five such failures the circuit breaker opened and blocked all further video analysis. The precheck now retries up to 3 times with 2-second delays when a 404 is returned, resolving without error in the next poll once Frigate commits the event. All other error types (timeouts, 5xx, connection errors) still fail fast. Similarly, the MQTT-path snapshot fetch now retries once after 2 seconds before dropping the event as `classify_snapshot_unavailable`.
- **Fixed:** Safari/WebKit autofill crash on the login form. The `autofillFieldData.autoCompleteType.includes` null-reference error, which blocked login entirely when autofill was active, is resolved by adding explicit `autocomplete="username"` and `autocomplete="current-password"` attributes so WebKit can identify field types without hitting its internal null path.

## [2.8.5] - 2026-03-22

- **Added:** Three new ONNX models exported from the [Birder](https://github.com/birder-project/birder) pretrained model library and published to the GitHub models release, now downloadable and activatable via the Model Manager:
  - **FocalNet-B EU Medium** (`eu_medium_focalnet_b`) — 707 European bird species, 384px input, 338 MB. Strong birds-only accuracy for European feeders.
  - **HieraDeT DINOv2 Small Wildlife** (`hieradet_dino_small_inat21`) — 10,000-species iNat21 wildlife model, 256px, 159 MB. Lighter alternative to RoPE ViT or ConvNeXt for CPU-constrained setups.
  - **FlexiViT Global Birds** (`flexivit_il_all`) — 550 worldwide bird species, 240px, 85 MB. Fast and compact; good for regions without a dedicated regional model.
- **Added:** `scripts/export_and_config_birder_model.py` — utility script to download any Birder pretrained model, extract its preprocessing stats (`rgb_stats`, input resolution) from the checkpoint, export to ONNX, and write a `model_config.json` sidecar alongside `labels.txt`.
- **Added:** `scripts/eval_model_accuracy.py` — accuracy evaluation harness for ONNX bird classifiers. Supports CUB-200-2011 and labelled-directory datasets, threshold sweeping, per-class breakdown, inference timing, and JSON/CSV output.

- **Changed:** Default classification model changed from `MobileNet V2 (Fast)` (2019-era 960-class Google Coral TFLite) to `RoPE ViT-B14` for new installs. Users who have not changed their model setting were silently using a severely underpowered baseline; any install that already has a model selected is unaffected.
- **Fixed:** North America birds-only models (EfficientNet-B0 NA small, Binocular/DINOv2 NA medium) were configured with `direct_resize` preprocessing, which squashes Frigate's landscape-orientation snapshots into a square without cropping, significantly distorting bird shapes. Both are now set to `center_crop` with `crop_pct: 0.875`, matching the standard preprocessing used during training. When the bird-crop detector is active the effect is minimal (crops are already roughly square); on uncropped full-frame inference this is a meaningful accuracy improvement.
- **Fixed:** MobileNet V2 letterbox padding colour changed from grey (128) to black (0) to match the original Google Coral training preprocessing.
- **Added:** Each model in the registry now exposes a `recommended_threshold` field (0.45 for 10,000-class wildlife-wide models, 0.65 for birds-only families, 0.70 for the legacy MobileNet V2). Wildlife-wide models like ConvNeXt Large and EVA-02 naturally produce lower per-class scores due to competing against ~8,500 non-bird classes; the default 0.70 threshold was causing excessive "Unknown Bird" outcomes for these models. The recommended threshold is shown as an inline hint in the Model Manager detail panel so users know when to adjust it.

- **Fixed:** Frigate "clip not retained" stub responses (~78 bytes) are no longer cached as valid clip files. Every media-cache boundary now enforces a `512`-byte minimum (`_MIN_VALID_CLIP_BYTES`); sub-threshold bodies are rejected at write time, and any stub files already on disk are evicted at read time. This eliminates `icvExtractPattern` OpenCV crashes that surfaced as HTTP 500 errors when requesting video thumbnails for expired recordings.
- **Fixed:** The video thumbnail proxy endpoint (`/api/proxy/clip/…/preview`) now returns a clean HTTP 404 when Frigate returns a stub clip body instead of crashing inside the preview generator. The stub check mirrors the media-cache threshold so the two paths stay consistent.
- **Fixed:** Video classification could unconditionally override an "Unknown Bird" detection with any video result regardless of confidence, causing low-signal scores (e.g. 0.05) to replace a pending unknown label. A `_UNKNOWN_UPGRADE_MIN_SCORE = 0.10` floor is now enforced for the unknown-upgrade branch; the video classification columns are still written for UI display, only the primary label promotion requires the minimum score.
- **Fixed:** Image classification admission timeouts logged a `WARNING` for every queued request that timed out during bulk backfill, flooding logs when many workers raced the single background admission slot simultaneously. The first timeout per service instance is still logged at `WARNING`; all subsequent ones are demoted to `DEBUG`.
- **Fixed:** Workers waiting for a clip-not-retained snapshot classification slot could all fire at exactly the same instant during backfill, causing thundering-herd admission pressure. A random jitter (`0–500 ms`) is now inserted before the first snapshot admission attempt to spread the load.
- **Fixed:** Switching from the dev image back to the live image no longer breaks startup when the database contains Alembic revision identifiers unknown to the live migration tree. `init_db` now creates a timestamped pre-migration backup before every migration run, detects the "DB ahead of codebase" case when `alembic upgrade head` fails with an unknown-revision error, logs a clear recovery warning (including the backup path), and allows the backend to start safely. `_verify_schema` applies the same additive-schema tolerance so the ahead-case is handled consistently whether it is detected at migration time or schema-verification time.

- **Fixed:** `_resolve_color_space` in the classifier pipeline had inverted conditional logic that always returned `"RGB"` regardless of the value in the model spec, making it impossible to use any other color space (e.g. `"L"` for grayscale models). The function now correctly returns the spec value when it is a valid PIL classification mode and falls back to `"RGB"` otherwise. All current models use `"RGB"` so there is no runtime behavior change, but future models requesting a different color space will now be handled correctly.
- **Fixed:** TFLite float32 model normalisation was hardcoded to the MobileNet-style `(x - 127.5) / 127.5` formula regardless of the model spec. The classifier now reads `mean` and `std` from the preprocessing block and applies ImageNet-style per-channel normalisation when those values are present, falling back to the corrected MobileNet constant (`127.5 / 127.5`, previously the slightly-off `127.0 / 128.0`) for legacy float32 TFLite models without explicit stats. The only current TFLite model (`mobilenet_v2_birds`) is `uint8`-quantised and is not affected.
- **Fixed:** Taxonomy background sync was unconditionally forwarding `force_refresh=False` to `get_names` even when a forced refresh was not required. `AsyncMock` captured the keyword argument and caused two CI test assertions to fail. The kwarg is now only passed when `must_refresh` is `True`.

- **Added:** Reclassification overlay UI now dynamically displays the active inference provider icon and real-time backend RAM usage.
- **Changed:** Regional birds-only model variants now use generic functional names ("Small Birds", "Medium Birds") instead of strict geographic labels in the model manager.
- **Changed:** Removed the generic "Tiered model lineup" explanatory block from Detection Settings to reclaim vertical space.
- **Fixed:** Removed the absolute close button from the Reclassification overlay to prevent conflict with the primary modal close controls.
- **Fixed:** eBird CSV export date column now uses the eBird-standard `MM/DD/YYYY` format. Common names that were stored as scientific names (e.g. "Parus major" in the Common Name column after a manual tag by scientific name) are now correctly resolved to English common names; the taxonomy cache lookup additionally filters out entries where `common_name` equals `scientific_name` at the database level (Issue #23).
- **Fixed:** Species filters and the manual-tag dropdown in the Explorer no longer show duplicate entries for the same species under different name formats (e.g. "Great tit", "Great tit (Parus major)", "Parus major (Great tit)"). The species query now groups by canonical identity (`taxa_id` → `scientific_name` → display name) using the taxonomy cache to enrich missing IDs, and the Python deduplication layer also falls back through `scientific_name` before using the raw display value (Issue #26).
- **Fixed:** Weather unit system (`metric`, `imperial`, `british`) now applies correctly across all detection cards, the detection modal, the latest-detection hero, and the species chart for all users. Previously, when the owner settings were not yet loaded or the user was a non-owner, `"british"` was silently downgraded to `"metric"` because the legacy temperature-unit fallback maps `british → celsius → metric`; the fix inserts `authStore.locationWeatherUnitSystem` (correctly resolved from `/api/auth/status` for all users) as the primary fallback before the legacy field (Issue #24).

- **Fixed:** Explorer now keeps the desktop `Time`, `Species`, and `Camera` filters in a compact three-column layout instead of stretching each control full width, and the page-level bulk-tagging toggle is labeled `Multi Select` to better communicate its purpose.
- **Fixed:** Clicking the Dashboard navigation item while already on `/` now forces the dashboard view to remount and refresh, preventing stale summary content from lingering across repeated nav clicks.
- **Fixed:** Batch/manual video analysis snapshot fallback now uses the low-priority background image-classification path instead of the generic image path, retries temporary background-capacity pressure, and records overload as `background_image_overloaded` instead of incorrectly collapsing it into `snapshot_no_results`.
- **Fixed:** Snapshot-fallback video analysis now only records success when snapshot classification actually succeeds. Failed snapshot fallback no longer clears the video-classifier failure state by calling the success path unconditionally.
- **Fixed:** The classification admission coordinator now handles queue-timeout races more defensively and cancels rejected queued result futures instead of leaving unconsumed timeout exceptions behind, eliminating the noisy `Future exception was never retrieved` warnings seen during overloaded batch fallback runs.
- **Added:** The roadmap now puts a labeled feeder model evaluation harness at the top of the maintenance queue so crop defaults and model choices can be decided from real ground-truth feeder data instead of plausibility checks.
- **Added:** Detection Settings now lets owners override crop behavior and crop-source preference per model family and per regional variant, with shipped model-config defaults preserved underneath and high-quality snapshot preference available where crop generation is enabled.
- **Added:** YA-WAMF now manages the bird crop detector as a first-class downloadable artifact instead of assuming a manually placed local file. The detector has its own install status in the model manager, reuses the normal global download progress system, and crop controls stay blocked in the UI until the detector is installed.
- **Fixed:** Installed `model_config.json` crop settings now merge with registry defaults instead of replacing them wholesale, so newly added defaults like `source_preference=high_quality` survive older sidecars that only specify `enabled` or input-context fields.
- **Changed:** Downloaded model payloads are being standardized around a per-artifact `model_config.json` sidecar so preprocessing and provider metadata can travel with the installed model instead of relying on partially duplicated registry defaults.
- **Added:** Bird-crop generation is now model-config-driven. Classification entrypoints pass `is_cropped` source context end-to-end, the classifier can run a shared fail-soft crop stage before preprocessing, and the current North America birds-only manifests explicitly opt into that stage while Frigate `crop=True` paths skip double-cropping.
- **Added:** The bird-crop stage now autodiscovers a local ONNX detector from the standard models directory (for example `/data/models/bird_crop/model.onnx`) and still honors `BIRD_CROP_MODEL_PATH` as an override. If the detector is missing, unloadable, or returns unusable detections, classification falls back to the original image without breaking crop-enabled models.
- **Fixed:** Snapshot and video classification entrypoints now preserve `event_id` in classification input context through live MQTT handling, backfill, manual reclassification, and auto video fallback paths, so crop-source resolution can consistently locate higher-quality event snapshots when cropping is enabled on uncropped flows.
- **Fixed:** Video classification now preserves classification input context all the way through direct and subprocess worker paths, so batch analysis no longer drops `event_id` before crop-source resolution and crop-enabled models can actually use high-quality event snapshots during video/frame classification.
- **Fixed:** Event-driven video reclassification now forwards Frigate’s normalized `data.box` and `data.region` into classification input context, allowing crop-enabled models to use the original Frigate detection box as a reliable crop hint before falling back to the local crop detector.
- **Fixed:** `high_quality` crop-source preference now only upgrades the source used for crop generation. If no crop is found, YA-WAMF falls back to the original image/frame instead of silently classifying the full high-quality still image as a replacement input.
- **Changed:** The local bird-crop detector parser is intentionally strict: by default it only accepts simple detection tensors, rejects unsupported multi-class row layouts instead of guessing, and allows `cxcywh` coordinates only when `BIRD_CROP_BOX_FORMAT=cxcywh` is set.
- **Added:** The local bird-crop runtime now understands SSD-style ONNX detector signatures with `NHWC uint8` input and named `detection_boxes` / `detection_classes` / `detection_scores` outputs, which makes ONNX Model Zoo `ssd_mobilenet_v1_12-int8` a viable local crop-detector candidate.
- **Fixed:** Classifier preprocessing is now manifest-driven for ONNX/OpenVINO models, with explicit support for `letterbox`, `center_crop`, and `direct_resize` so models like Birder, timm iNat21, and Binocular no longer all inherit the same generic square-letterbox path.
- **Fixed:** Registry preprocessing metadata has been corrected for the currently known mismatch cases, including ConvNeXt Large iNat21, RoPE-ViT iNat21, Europe small/medium birds models, and EVA-02 Large.
- **Added:** Birds-only ONNX export tooling now writes `model_config.json` next to `model.onnx` and `labels.txt`, capturing source model preprocessing defaults for release-backed artifacts.
- **Changed:** Small and medium ONNX model slots are being reworked toward birds-only replacement artifacts published via GitHub Releases, with validation tracked in [`docs/plans/2026-03-19-birds-only-model-validation-matrix.md`](docs/plans/2026-03-19-birds-only-model-validation-matrix.md).
- **Changed:** The experimental wildlife-wide small and medium ONNX placeholders (`hieradet_small_inat21` and `rope_vit_b14_inat21`) now live in the advanced overflow instead of the default recommended lineup.
- **Added:** Detection Settings now includes a `Bird model region` override (`Auto`, `Europe`, `North America`) wired end-to-end through the UI settings payload so regional birds-only families can be selected manually while location-based auto-selection remains the default.
- **Added:** New backend exporter [`backend/scripts/export_binocular_model.py`](backend/scripts/export_binocular_model.py) supports converting the North America `jiujiuche/binocular` NABirds checkpoint into ONNX plus labels for release-backed artifact testing.
- **Added:** Candidate birds-only release assets have been uploaded for Europe small (`MobileNetV4`), Europe medium (`ConvNeXt V2 Tiny 256px`), North America small (`n2b8/birdwatcher` EfficientNet-B0 NABirds), and North America medium (`Binocular` / `DINOv2 ViT-B/14`) under the `models` release for side-by-side validation before any registry swap.
- **Changed:** The `models` GitHub release notes now document the regional `small_birds` / `medium_birds` candidate assets and their label behavior so release-backed testing matches the current birds-only replacement plan.
- **Added:** Classifier runtimes now support optional grouped-label collapse strategies, allowing NABirds-style North America checkpoints with `555` visual categories to be surfaced as deduplicated species results by collapsing trailing parenthetical variants into `404` species labels.
- **Changed:** Regional birds-only model families are now resolved end-to-end through the model manager. `small_birds` and `medium_birds` can install as multi-variant family directories, expose the correct active regional artifact based on `Auto | Europe | North America`, and pass variant-specific runtime metadata like `input_size`, `weights_url`, and `label_grouping` through to the classifier service.
- **Changed:** Container-backed validation in the running `yawamf-backend` image now confirms the Europe small and medium birds-only candidates produce finite outputs on ONNX Runtime CPU, OpenVINO CPU, and OpenVINO GPU, while the current North America small and medium NABirds candidates still fail the OpenVINO GPU correctness gate by returning non-finite outputs after successful GPU compilation.
- **Fixed:** North America regional birds-only candidates no longer advertise or auto-select `intel_gpu`. The registry now marks those artifacts as `cpu`/`intel_cpu` only, and runtime selection honors that constraint so `auto` stays on OpenVINO CPU instead of loading known-bad GPU paths.
- **Added:** Detection Settings now presents a tiered model lineup with downloadable small, medium, large, and advanced wildlife models, plus guidance that keeps advanced options collapsed by default for most installs.
- **Added:** Model downloads now appear in the global progress system so owners can track long-running ONNX artifact downloads from anywhere in the UI.
- **Changed:** The new model picker, download progress messaging, and adjacent Detection Settings guidance are now localized across all supported UI languages instead of falling back to English outside the default locale.
- **Fixed:** Birder wildlife model labels are now normalized to canonical scientific names instead of leaking raw taxonomy-path strings like `04853_Animalia_...` into detections, video analysis, and release label assets.
- **Fixed:** Taxonomy repair and manual species updates now backfill canonical scientific/common names more robustly by preferring stored taxonomy identifiers and scientific names over localized display labels.

- **Fixed:** Selecting a new classification model (e.g., EVA-02 Large) now immediately restarts the subprocess worker pool. Previously, workers would continue using the old model until they crashed or were manually restarted, causing a mismatch between the UI and actual inference results.
- **Fixed:** Removed legacy "safety" remapping that automatically downgraded EVA-02 Large to ConvNeXt Large when not explicitly flagged. The system now strictly respects the user's active model selection.
- **Fixed:** Improved system stability when using large models (EVA-02) by increasing default classification timeouts to 60s (from 30s) and worker ready timeouts to 60s (from 20s). This prevents "classify_snapshot_timeout" errors during the initial heavy model load phase and reduces unnecessary OOM-related worker restarts.
- **Fixed:** Added a global initialization lock to the classifier supervisor. This ensures that only one worker across all pools (Live, Video, Background) can load its model at a time, eliminating massive RAM and GPU spikes that previously led to system-wide OOM crashes and GPU resource exhaustion errors when starting up with "Elite" models.
- **Fixed:** Prevented API timeouts (504 Gateway Timeout) when switching to heavy models by moving the worker pool restart process into FastAPI background tasks, ensuring the UI remains responsive even if workers take minutes to load the new model into GPU memory.
- **Fixed:** Resolved a race condition where the supervisor watchdog loop could attempt to replace a crashed worker simultaneously with an intentional pool restart, which previously resulted in "zombie" leaked worker processes running in the background.
- **Fixed:** Increased the `asyncio` subprocess stream reader limit to 512KB. This hardens worker communication against oversized stdout protocol messages and large stderr bursts, reducing `LimitOverrunError` risk when workers emit large result payloads or runtime error output.
- **Changed:** The Video Classifier now stops starting new batch analysis jobs whenever live detections are running or queued, while allowing any already-running video analysis to drain normally. This prioritization reduces GPU and RAM contention for immediate detections when using heavy "Elite" models under sustained load.
- **Changed:** `In-Process` is now the default image execution mode for fresh installs and unset configurations. This substantially reduces RAM usage with larger models by sharing model weights in one backend process, while `Subprocess` remains available for users who prefer stronger isolation.
- **Changed:** Optimized memory usage in the main process by preventing it from loading the bird classification model into RAM when configured for `subprocess` execution mode. Model loading is now deferred entirely to the dedicated worker processes.
- **Fixed:** eBird CSV export now robustly falls back to scientific names in the "Common Name" column if no English common name is available in the taxonomy cache. This ensures better compatibility with eBird's strict import validation.
- **Fixed:** Corrected a bug in the taxonomy service where localized species names (e.g., Russian) were incorrectly overwriting canonical English names in the main cache, which previously broke English-only exports like eBird. Localized names are now correctly stored only in the translation table.
- **Added:** New **Execution Mode** toggle in Settings -> Detection. This allows users to switch between `Subprocess` (isolated and stable) and `In-Process` (shared RAM) classification. Switching to In-Process can reduce backend RAM usage by up to 60% (from ~11GB to ~4GB) when using "Elite" accuracy models by sharing a single model instance across all inference tasks.
- **Fixed:** Video classification progress now accurately reaches 100% in the UI overlay even for short videos or when some frames are skipped due to inference errors.
 The frontend now correctly trusts the backend's frame total instead of sticking to the configured maximum, and progress callback signatures were hardened to prevent internal reporting mismatches.
- **Fixed:** Concurrent manual video reclassifications now correctly track their progress independently in the UI. Previously, triggering multiple manual reclassifications simultaneously caused their progress bars to violently overwrite each other in the notification center.
- **Fixed:** The global progress banner during Batch Analysis will no longer jump backward or display misleading totals. The UI previously confused per-worker video frame ticks with overall queue item counts, causing the progress denominator to fluctuate dynamically as workers picked up new events. Batch progress now correctly stabilizes on "Items" using the authoritative backend queue status.
- **Fixed:** Resolved a critical pre-assignment deadlock in the subprocess classifier supervisor that could permanently stall live Frigate MQTT ingestion (Issue #22). If a worker process crashed during startup (e.g. GPU initialization failure) and the pool was previously active, the supervisor would block incoming classification requests indefinitely waiting for an idle worker, preventing the admission coordinator from shedding load and wedging the pipeline at 0% capacity.
- **Fixed:** Subprocess classification requests now actively track unassigned futures and fail immediately if 0 active workers are available after a recovery attempt. This enables rapid failure propagation, correctly triggering the supervisor's circuit breaker and unblocking upstream admission queues to recover live event flow.
- **Changed:** eBird export now follows the reopened issue-23 follow-up contract: protocol is `Stationary`, duration is populated per exported date window, submission comments include available runtime metadata and confidence, export uses explicit location `state` / `country` settings when provided, and the UI now supports inclusive `From` / `To` export dates instead of a single-date picker.
- **Changed:** The eBird export range UI now has an explicit `Export everything` toggle that clears and disables the `From` / `To` pickers when enabled, making full-export state obvious instead of relying on blank date fields.
- **Changed:** The Notifications `Errors` tab now surfaces backend-recorded failures only in its live incident list and grouped diagnostics. Frontend/client polling issues remain available in captured diagnostic bundles, but no longer clutter the live error workspace.
- **Changed:** eBird export is now stricter and importer-safer: `Unknown Bird` rows are always excluded, localized/non-English fallback names are suppressed unless the exporter can resolve an English-safe common name, and the route remains a single 19-column Record Format path.
- **Added:** Location settings now include optional `state` / `country` values so eBird export can fill those columns without guessing from coordinates.
- **Changed:** Notifications jobs surfaces are now much more compact. The global progress banner and Jobs view default to short, direct status text and only show extra detail when a job is blocked, stale, or otherwise needs explanation.
- **Fixed:** `/api/ebird/notable` no longer returns `500 Internal Server Error` when optional taxonomy thumbnail enrichment fails. The route now imports its enrichment dependencies correctly and treats thumbnail lookup as best-effort so notable observations still load.
- **Changed:** Notifications Jobs and the global progress banner now explain what background work is actually doing. Active rows show explicit activity, determinate vs indeterminate progress, freshness, and blocker text instead of unlabeled bars.
- **Added:** Reclassification queue telemetry now surfaces truthful capacity details in the UI, including worker-slot usage, queue-slot availability, and MQTT-pressure throttling context where available.
- **Added:** Deep Video Analysis now persists the model id used for completed video-classification results, exposes a backend-derived friendly model name in event APIs, and shows both provider (`CPU` / `GPU`) and model chips in the Detection Details video-analysis card.
- **Fixed:** Intel iGPU OpenVINO stability now uses `openvino==2024.6.0` as the last verified working runtime line for the live ConvNeXt bird model on this host. Earlier investigation showed `2026.x` broke GPU device discovery and `2025.4.1` still produced non-finite GPU outputs for the live ConvNeXt path despite `f32`, cache, and stream hardening.
- **Changed:** The repo now treats OpenVINO runtime drift as a first-class regression risk. The durable incident backstory, misleading intermediate symptoms, and final runtime findings are documented in [docs/plans/2026-03-13-openvino-gpu-regression-retrospective.md](docs/plans/2026-03-13-openvino-gpu-regression-retrospective.md) so future debugging does not repeat the same archaeology.
- **Fixed:** Backfill/unknown-analysis GPU regressions are now understood: the earlier `already_exists` skip symptom on the restored branch was actually a non-finite-score path hidden by SQLite `INSERT OR IGNORE`; the investigation now documents why that happened and why it was not a true duplicate-event condition.
- **Fixed:** Subprocess-mode live and background bird image classification now runs behind the same `ClassificationAdmissionCoordinator` used by in-process execution. This restores bounded admission, fast overload shedding, and lease-expiry recovery for the default `subprocess` runtime instead of letting requests wait indefinitely behind busy or wedged worker slots.
- **Fixed:** When a coordinated subprocess image-classification lease expires, YA-WAMF now aborts the matching supervised worker assignment using coordinator-owned `work_id` and `lease_token`, forcing prompt worker replacement. This prevents stale subprocess work from holding the only live slot after the coordinator has already recovered logical capacity.
- **Added:** Regression coverage now asserts subprocess-mode fast live overload behavior, truthful live in-flight status reporting, stale-capacity reclaim, and supervisor-side abort semantics for matching vs stale lease tokens.
- **Fixed:** GPU inference stability on Intel hardware is now significantly improved by forcing `f32` (FP32) precision. This prevents OpenVINO from defaulting to FP16, which caused mathematical overflows (`NaN`/`inf` logits) on un-quantized bird models, resulting in "produced no finite probabilities" errors and triggering unnecessary CPU fallbacks.
- **Fixed:** GPU concurrency is now limited to a single stream per worker via `NUM_STREAMS: 1` (corrected from `GPU_THROUGHPUT_STREAMS`). This prevents Intel OpenCL driver race conditions and resource exhaustion during concurrent batch reclassification tasks.
- **Fixed:** Subprocess classifier workers now forward their `stderr` logs to the main backend log. This ensures that GPU initialization errors, driver warnings, and OpenVINO startup failures are now visible in standard `docker logs` for better troubleshooting.
- **Fixed:** OpenVINO GPU shader compilation is now cached in `/tmp/openvino_cache` via the `CACHE_DIR` property. This prevents worker processes from timing out during heavy initial model loads and avoids the `worker startup timed out` errors previously seen during large batch jobs.
- **Fixed:** The Svelte global `ErrorBoundary` now filters out harmless, non-fatal exceptions (including `Cloudflare connection failed`, `Failed to fetch`, and `ResizeObserver loop limit exceeded`), preventing browser extensions or transient network drops from hijacking the UI with full-screen crash cards.
- **Fixed:** The `GlobalProgress` bar and `Jobs` view are now consistent during batch reclassifications. The main "Batch Analysis" job card no longer disappears when individual video classification sub-jobs start, and the global percentage no longer jumps erratically by excluding individual frame progress from the overall event-queue sum.
- **Fixed:** OpenVINO runtime exceptions (like `CL_OUT_OF_RESOURCES`) are now properly raised as `InvalidInferenceOutputError` instead of being silently swallowed as empty results. This allows the supervisor to accurately detect crashed workers and reboot them, preventing permanent hangs in the batch processing queue.
- **Added:** Detection backfill jobs now broadcast their started status to the UI immediately. Users now receive instant feedback (e.g. "Querying Frigate API...") during the expensive initial data-sync phase before the first event is processed.
- **Added:** The Detection Details video-analysis card now displays explicit `GPU` or `CPU` badges. This provides owners with real-time verification of the hardware acceleration path used for each verified detection.
- **Changed:** Historical note: `openvino==2025.4.1` was an intermediate compatibility pin that restored GPU device enumeration versus `2026.x`, but it was later found to remain numerically unstable for the live ConvNeXt Intel iGPU path on this host.

- **Fixed:** Video classification now rejects degenerate near-uniform confidence outputs (for example top score near `1 / class_count`) as `video_no_results` instead of reporting a misleading `completed` result with ~`0%` confidence, and uses deterministic full-clip stratified frame sampling with best-frame aggregation to improve transient-bird recovery.
- **Added:** Detection video results now persist per-event inference runtime evidence (`video_classification_provider`, `video_classification_backend`) through DB/API/UI so GPU vs CPU execution is attributable on each classified event instead of inferred from process-global status.
- **Fixed:** Frontend `svelte-check` now passes for the strict non-finite debug toggle by adding `strict_non_finite_output` to the UI `Settings` API type, aligning typed settings reads/writes with the backend-exposed field.
- **Added:** Experimental strict-non-finite classifier toggle is now configurable end-to-end: backend setting `classification.strict_non_finite_output` (env override `CLASSIFICATION__STRICT_NON_FINITE_OUTPUT`, with legacy `CLASSIFIER_STRICT_NON_FINITE_OUTPUT` fallback) is exposed in `Settings > Debug`, persisted via `/api/settings`, and surfaced in `/api/classifier/status` as `strict_non_finite_output` so active policy is explicit during controlled GPU/CPU behavior tests.
- **Fixed:** Detection Details video-analysis inference markers now use inline SVG GPU/CPU icons instead of font-dependent glyph characters, so provider markers render consistently across browsers/platform fonts.
- **Fixed:** Subprocess classifier supervision now supports a dedicated background worker hard deadline (`classification.background_worker_hard_deadline_seconds`, env `CLASSIFICATION__BACKGROUND_WORKER_HARD_DEADLINE_SECONDS`, default `120s`) instead of forcing background/backfill jobs to share the shorter live deadline; this prevents long-running historical classification work from repeatedly tripping `hard_deadline` restarts and opening the background worker circuit while preserving strict live-request deadlines.
- **Added:** Detection Details video-analysis card now shows a live inference-provider badge (`GPU` / `CPU`) during active analysis by polling classifier status, so owners can immediately see whether current processing is running on accelerated or fallback compute.
- **Added:** Auto video-classifier diagnostics now include classifier runtime context (`inference_backend`, `active_provider`, `selected_provider`, and latest runtime-recovery snapshot when available), so exported incident evidence shows which inference path was active when failures occurred.
- **Changed:** GPU runtime recovery policy is now more robust: on invalid OpenVINO GPU output, YA-WAMF now retries once on a freshly reloaded GPU model before demoting to CPU fallback, and workers that fell back to OpenVINO CPU now auto-attempt GPU restoration after a cooldown (when GPU is configured/available) instead of staying on CPU indefinitely.
- **Added:** Classifier status telemetry now includes GPU recovery counters (`runtime_gpu_retries`, restore attempts/success/fail, and restore cooldown marker) so owner diagnostics can verify whether the system is actually recovering back to GPU over time.
- **Changed:** Backend dependency pinning now treats the OpenVINO version as host-sensitive and regression-prone; the newer investigation found `2024.6.0` to be the last verified working Intel iGPU runtime line for the live ConvNeXt model on this host, replacing the earlier assumption that `2025.4.1` was the stable baseline.
- **Added:** New backend regression test (`backend/tests/test_dependency_pins.py`) asserts the OpenVINO pin remains fixed, preventing accidental drift back to an unbounded OpenVINO version range.
- **Fixed:** Subprocess video-classification progress callbacks now accept both keyword and positional callback signatures (`current_frame`/`total_frames` and legacy positional args), restoring reliable `reclassification_progress` SSE emission for frame-strip UI updates during reclassify/auto-video runs.
- **Added:** Location weather units now support a third `british` mode (`°C`, `mph`, `mm`) across backend settings/auth payloads and frontend weather rendering/helpers, so UK-style mixed units can be selected globally without temperature/speed/precipitation mismatches.
- **Fixed:** OpenVINO GPU runtime failures (for example `CL_OUT_OF_RESOURCES`) are no longer silently treated as empty classifier output. OpenVINO classify/classify_raw paths now surface these as invalid-runtime errors so classifier runtime recovery can immediately fail over to a safer backend/provider (typically Intel CPU) instead of cascading into repeated `video_no_results` failures and circuit-breaker opens.
- **Fixed:** Auto video analysis no longer collapses into `video_no_results` when progress delivery is slow: worker-side progress emission is now best-effort, video classification no longer treats progress callback failures as fatal, and supervisor progress callbacks no longer block worker result consumption behind slow SSE/broadcast handling.
- **Fixed:** Owner incident detail now shows grouped diagnostics for the selected incident even when the evidence exists only in backend diagnostics; backend-only incidents like `video_no_results` no longer render an empty “Grouped Diagnostics” panel just because no matching local frontend group exists.
- **Changed:** GitHub Actions now opts JavaScript actions into Node 24, uses the newer checkout/setup-node actions, gives workflow runs explicit commit-based run names, and always builds/publishes the frontend and backend images together on `dev` so both `:dev` containers share the same git hash for deployment tracking.
- **Added:** Owner Errors workspace now has a real “Clear Live Errors” path: the backend exposes an owner-only diagnostics clear endpoint, the frontend clears persisted local diagnostics and resets correlated incidents, and the page refreshes against empty backend history instead of leaving stale evidence with no way to reset it.
- **Fixed:** Supervised video OpenVINO startup is now less fragile on GPU hosts: worker pools warm sequentially instead of compiling multiple video workers in parallel during cold start, and video workers get a larger ready timeout than live/background workers so heavy OpenVINO initialization does not fail under the short image-worker startup budget.
- **Fixed:** Detection backfill now treats classifier worker transport loss and transient background-worker restarts as bounded retryable failures instead of leaking raw connection-reset errors or immediately losing the event; send-time worker transport failures are normalized into worker-unavailable errors, dead workers are replaced before reuse, and backfill gets a larger per-event budget with one transient retry for background worker timeout/startup/unavailable conditions.
- **Fixed:** Owner incident correlation now resolves stateful health incidents against the latest backend health snapshot instead of leaving them permanently open; cleared video/classifier circuit-breaker incidents move to recent history, and active root-cause incidents like `video_no_results` remain visible in Current Issues after recovery.
- **Added:** Global weather measurement units setting for issue `#24`: `Settings > Integrations > Location` now uses a single `metric`/`imperial` preference, older `location.temperature_unit` configs auto-migrate on load, and auth/settings payloads expose the canonical unit-system field while keeping the legacy temperature alias for compatibility.
- **Changed:** Weather rendering now uses one shared frontend unit helper across detection cards, the latest-detection hero, the detection modal, and species weather charts so temperature, wind, and precipitation stay consistent instead of mixing `°F` with `km/h` or `mm`.
- **Fixed:** Auto video classification now uses a video-specific supervised worker deadline instead of the shorter live-image worker deadline, preserves worker failure reasons (deadline/startup/exit/circuit) instead of flattening them into generic “no results”, and records canonical backend diagnostics for video failures/circuit-open events so the owner Errors workspace can surface them.
- **Added:** Owner incident workspace in Notifications > Errors now correlates backend diagnostics into current/recent incidents, preserves richer evidence in exported bundles, and generates issue-ready report text with optional owner notes for GitHub reporting.
- **Changed:** OpenVINO/GPU bird inference is now fully supervisor-oriented in subprocess mode: the main backend no longer eagerly loads a duplicate bird model, status probes are cached instead of re-running OpenVINO device detection on every refresh, and owner bird test/debug routes use subprocess-safe behavior instead of assuming an in-process bird runtime.
- **Fixed:** Classifier self-healing is more robust under worker replacement failures: failed restarts no longer kill the watchdog loop, unavailable slots are tracked explicitly, restart budgets still trip circuit breakers, and recovery telemetry now includes worker-reported runtime fallback events.
- **Added:** Supervised video bird classification now uses a dedicated worker pool and protocol support for progress events, isolating clip analysis from live/background snapshot workers while preserving progress callbacks and worker-side runtime recovery reporting.
- **Fixed:** Batch reclassification UI now self-heals from the authoritative owner queue status: the app shell polls `/api/maintenance/analysis/status` globally, recreates a synthetic batch job for the global progress bar after refresh/SSE loss, settles stale `Batch Analysis` process notifications when the queue drains, and avoids duplicate batch-vs-event progress counting when per-event reclassification jobs are already active.
- **Changed:** eBird CSV export now targets the strict eBird record-format workflow: it emits headerless 19-column rows, accepts an optional single-day `date` filter, prefers English taxonomy names for species labels, and no longer requires eBird API enablement or credentials just to export local detections.
- **Fixed:** eBird export now validates the `date` query before streaming begins, avoids duplicate rows when taxonomy cache aliases share a `taxa_id`, and treats corrupt score metadata as best-effort provenance so one bad historical row cannot break the full CSV download.
- **Fixed:** Classifier subprocess workers no longer let bootstrap/runtime logs corrupt the stdout protocol stream: normal worker logs are redirected to stderr, the client tolerates stray stdout noise defensively, and live/backfill classification no longer fails startup with misleading `exited before ready` errors when TensorFlow/OpenVINO emits initialization chatter.
- **Fixed:** Background classifier subprocesses now accept large historical snapshot payloads during detection backfill by raising the worker stdin stream limit above the default asyncio line cap, preventing `Separator is not found, and chunk exceed the limit` crashes on base64-encoded Frigate snapshots.
- **Fixed:** Classifier supervisor cold-start no longer drops the first live/backfill requests while OpenVINO workers are still loading: worker pools now start lazily per priority instead of booting every pool on first use, workers in the requested pool start in parallel, startup-ready waits are configurable and mapped to explicit worker-unavailable handling, and backfill error logs now preserve exception type/details instead of empty `TimeoutError` strings.
- **Fixed:** Detection/weather backfill is now more truthful and more complete: historical Frigate event fetches paginate beyond the previous 100-event cap, historical filtering now uses Frigate score parity with live processing, async backfill jobs track structured `error_reasons`, and diagnostics now capture snapshot/classifier/job failure reasons instead of collapsing them into generic backfill errors.
- **Added:** Issue `#22` classifier resilience hardening: a live/background admission coordinator with lease reclaim and stale-completion rejection, recovery-aware ML/event-pipeline health reporting, richer diagnostics export, and truthful paused/throttled backfill progress messaging.
- **Added:** New subprocess classifier-supervisor foundation behind `classification.image_execution_mode`, including worker config/settings, a framed worker protocol, worker-process and worker-client primitives, supervised live/background pools, watchdog-based worker replacement, restart-budget circuit breaking, and initial `ClassifierService` routing hooks for subprocess image execution.
- **Changed:** Subprocess classifier execution can now boot a real worker entrypoint via `python -m app.services.classifier_worker_process`, and supervisor failure modes are translated back into existing live-pipeline semantics so circuit-open conditions surface as explicit overload and worker heartbeat/deadline failures surface as lease expiry instead of leaking raw supervisor exceptions.
- **Changed:** Event processing now coalesces duplicate in-flight live Frigate event IDs and sheds stale live events before snapshot classification, reducing wasted live-classifier capacity during replay storms or delayed MQTT delivery.
- **Fixed:** Live-event shedding now keys off MQTT receipt age rather than raw Frigate event start time, and duplicate-event coalescing is limited to the classification section so reconnect backlogs are not discarded and downstream save/notify stalls do not suppress legitimate retries.
- **Fixed:** Non-finite classifier scores are now sanitized or rejected before thresholding/persistence, preventing OpenVINO `NaN` outputs from being misreported as “already exists” during detection backfill and unblocking downstream weather backfill when historical detections are rebuilt.
- **Fixed:** Classifier runtime recovery now treats non-finite model outputs as backend failure, automatically falling back off broken providers (for example OpenVINO GPU to CPU/ONNX/TFLite), surfacing recovery in health/status telemetry, and using the correct TFLite asset paths if an ONNX/OpenVINO fallback chain reaches TFLite.
- **Changed:** Image classification now defaults to supervised `subprocess` execution instead of in-process threads, so issue `#22` worker replacement/circuit-breaker self-healing is active by default unless a deployment explicitly opts back into `in_process`.
- **Fixed:** Subprocess classifier workers now drain and retain a bounded stderr tail, preventing pipe backpressure from wedging workers and surfacing recent worker stderr in supervisor metrics/startup failures for easier diagnosis.
- **Changed:** Health/backfill/diagnostics now surface subprocess worker-pool recovery state end-to-end: `/health` includes worker-pool circuit data, backfill progress messaging distinguishes worker recovery from ordinary live throttling, and exported diagnostics bundles preserve worker restart/circuit evidence plus ignored late worker results.
- **Changed:** App shell refactor extracted mobile top-bar UI and stale reclassification recovery orchestration into dedicated modules, reducing `App.svelte` to a slimmer route/layout coordinator.
- **Changed:** Legacy API-key fallback auth helpers were consolidated into `app/auth.py`, and router/main imports now use the unified auth module.
- **Removed:** Deprecated `backend/app/auth_legacy.py`; legacy API-key behavior remains supported via `get_auth_context_with_legacy` in `app/auth.py`.
- **Added:** Jobs page now includes a top pipeline flow view (`Queued → Running → Outcomes`) with per-kind stage counts so background work is visible at a glance.
- **Changed:** Jobs pipeline now uses real queue telemetry for auto video reclassification (`pending`/`active`) and explicitly marks queue depth as “not reported” for job kinds that do not expose queue metrics yet.
- **Fixed:** Jobs queue telemetry polling now keeps retrying after transient failures and preserves previously known queue data instead of downgrading to “not reported.”
- **Changed:** Notifications workspace heading now reads “Notifications & Jobs” to better match the combined page purpose.
- **Added:** Notifications workspace now has a dedicated `Errors` tab (alongside Notifications and Jobs) with grouped anti-spam diagnostics, severity tagging, and drill-down metadata for troubleshooting.
- **Added:** Client-side diagnostics bundle capture/archive in the `Errors` tab so multiple support bundles can be stored and downloaded independently as JSON.
- **Added:** Diagnostics export payloads now include app version/branch/hash metadata plus captured health snapshots with event-pipeline latest timeout/failure/drop details.
- **Fixed:** Ongoing process notifications now auto-settle when no active backing job is tracked, preventing Notifications/Jobs drift after reconnects or missed terminal updates.
- **Fixed:** Taxonomy repair now skips `Unknown Bird`/unknown-label detections so unresolved catch-all labels no longer appear as perpetual taxonomy work items on every sync run.
- **Changed:** Completed locale-key coverage pass for the Notifications/Jobs/Errors workspace additions (pipeline labels, Errors tab strings, bundle controls), including updated localized Notifications page headings.
- **Added:** New UI locale regression test (`locales.jobs-errors.test.ts`) to enforce key coverage for Notifications/Jobs/Errors strings across all supported languages.
- **Added:** Settings polling failures for analysis status and backfill status are now captured into the Errors diagnostics store for exportable troubleshooting context.
- **Added:** New owner-only backend diagnostics history endpoint `GET /api/diagnostics/errors` with bounded in-memory retention, plus structured event capture for event-pipeline drops/timeouts/failures and notification-dispatcher queue/job failures.
- **Fixed:** Jobs pipeline no longer shows idle reclassification queue rows after local clear actions when queue depth is `0` and no job activity exists.
- **Fixed:** Reclassification fallback handling now treats `pending` as queued (not active running), preventing phantom extra active reclassify jobs beyond configured concurrency during batch analysis.
- **Fixed:** Jobs/Global Progress active counts now exclude stale reclassification entries, so displayed running concurrency aligns with backend-reported active workers instead of stale UI remnants.
- **Changed:** Auto video `trigger_classification` now uses the same bounded/deduped queue path as batch analysis (instead of direct task spawn), preventing concurrency oversubscription races between trigger and queue workers.
- **Changed:** Video-analysis queue hardening: pending queue is now truly bounded (`asyncio.Queue(maxsize)`), enqueue dedupe is guarded by an async lock for concurrent safety, pending-id lifecycle avoids dequeue/start race windows, and status snapshots prune completed tasks before reporting active counts.
- **Fixed:** Live MQTT snapshot classification now runs on a dedicated live-image executor instead of the shared non-live image pool, preventing user-initiated or batch snapshot work from queueing ahead of real-time Frigate events under load.
- **Changed:** Event-pipeline health status is now recovery-aware: cumulative critical-failure counters remain available for diagnostics and soak analysis, while `/health` can return to `ok` after the configured recovery window if no new critical failures occur.
- **Fixed:** Backend app shutdown now explicitly tears down classifier executors, preventing unmanaged image/video worker threads from lingering across process teardown or test/service reinitialization.
- **Changed:** Event-pipeline recovery now stays `degraded` while unresolved incomplete events remain after a critical failure, avoiding overly optimistic `/health` recovery during partial pipeline drain.
- **Added:** High-quality event snapshots now have a configurable derived JPEG quality setting (default `95`) in Data Settings, so users can trade off snapshot detail against file size without changing image format compatibility.
- **Fixed:** Reclassification recovery now also reconciles older `running` jobs (not just `stale`) against backend classification status, reducing phantom Active entries when SSE terminal events are missed.
- **Added:** Dedicated frontend background-job telemetry store (`jobProgressStore`) with explicit lifecycle states (`running`, `stale`, `completed`, `failed`), rate-per-minute estimation, and ETA tracking.
- **Changed:** Notifications now hosts a unified tabbed workspace for both notification history and jobs (`/notifications` + `/notifications/jobs`), with `/jobs` retained as a legacy canonical redirect to the Jobs tab.
- **Changed:** Global progress UI now reads from dedicated job telemetry (not notification `process` items), supports determinate/indeterminate rendering, exposes stale/update-age indicators, and links directly to the Notifications Jobs tab.
- **Changed:** Backfill and reclassification SSE/polling paths now update both notification history and job telemetry in parallel, improving resilience when terminal SSE events are missed.
- **Fixed:** Backfill progress reconciliation no longer treats `null` status as implicit completion; matching jobs are now marked `stale` defensively to avoid false-finished states during restarts/auth races.
- **Fixed:** Job telemetry updates now preserve prior counters when sparse payloads omit `current`/`total`, enforce monotonic progress, and prevent `N/0` terminal-state regressions.
- **Changed:** Added locale-key coverage for new Jobs/global-progress/navigation/shortcut strings across all supported UI languages.
- **Added:** Frontend unit tests for job telemetry edge cases (sparse payloads, monotonic counters, stale transitions, idempotent prefix-close behavior, terminal counter normalization) via Vitest.
- **Added:** Owner API endpoint `GET /api/events/{event_id}/classification-status` for authoritative per-event video-classification state (`status`, `error`, `timestamp`) during client recovery flows.
- **Fixed:** iOS PWA stale-reclassification drift now self-heals by reconciling stale `reclassify:*` jobs against backend classification status on app resume/reconnect/interval, aligning PWA behavior with Safari fresh-session state.
- **Added:** Frontend + backend regression tests for reclassification fallback terminal transitions and classification-status API behavior.

- **Changed:** Refactored backend configuration internals into segmented modules: `app/config.py` (orchestration), `app/config_models.py` (settings models/defaults), and `app/config_loader.py` (env/file merge logic), reducing `config.py` from 1,032 lines to 95 lines while preserving `from app.config import settings` compatibility.
- **Added:** New backend regression tests for env-to-settings mapping coverage (`backend/tests/test_config_env_mapping.py`).
- **Fixed:** Restored env override support for `CLASSIFICATION__VIDEO_CLASSIFICATION_TIMEOUT_SECONDS`, `CLASSIFICATION__VIDEO_CLASSIFICATION_STALE_MINUTES`, and `NOTIFICATIONS__NOTIFICATION_COOLDOWN_MINUTES`.

- **Added:** New `classification.write_frigate_sublabel` setting (API + config + env: `CLASSIFICATION__WRITE_FRIGATE_SUBLABEL`) to control whether YA-WAMF writes species labels back to Frigate event sublabels.
- **Added:** Detection Settings now includes a visible toggle for `write_frigate_sublabel`, with localization coverage across all supported UI languages.
- **Changed:** Event processing now honors `write_frigate_sublabel`; Frigate write-back is skipped when disabled while local YA-WAMF detections still persist normally.
- **Changed:** Snapshot classification now applies a stricter confidence gate when Frigate sublabel disagrees and Frigate trust is disabled, reducing overconfident cross-species mislabels (for example long-tailed tit drift) by demoting low-confidence disagreements to `Unknown Bird`.
- **Changed:** Legacy `active_model.json` entries that reference `eva02_large_inat21` without explicit user selection now auto-remap to `convnext_large_inat21` on load; explicit EVA selections remain supported.
- **Fixed:** Frontend nginx now serves `/assets/*` with strict file lookup (`404` if missing) instead of SPA fallback to `index.html`, preventing module MIME errors (`text/html` returned for JavaScript chunks) after rolling updates.

- **Fixed:** MQTT ingestion now dispatches Frigate/BirdNET message handling through bounded concurrent workers so long-running event processing no longer blocks topic intake in a single serial loop.
- **Changed:** Real-time Frigate event handling now ignores routine `update`/`end` chatter and processes actionable bird events (`new` and false-positive cleanup), reducing duplicate classification passes per Frigate event ID.
- **Fixed:** MQTT worker handlers now enforce per-message timeouts, preventing stalled Frigate/BirdNET processing tasks from occupying all worker slots indefinitely.
- **Changed:** Frigate MQTT payloads are now pre-filtered before task scheduling, so non-actionable update chatter no longer consumes in-flight queue capacity.
- **Changed:** MQTT queue-pressure diagnostics now emit explicit saturation warnings (in-flight count + wait duration), making ingestion bottlenecks visible in backend logs instead of appearing silent.
- **Fixed:** Detection backfill now wraps per-event processing in a timeout guard, preventing a single slow/hung historical event from stalling the entire async backfill job indefinitely.
- **Fixed:** `ClassifierService` now uses separate thread pools for snapshot (`classify_async`) and video (`classify_video_async`) inference, preventing heavy background video analysis from starving real-time MQTT event classification.
- **Fixed:** Snapshot image inference now uses bounded admission control before executor dispatch; when workers are saturated, requests fail fast instead of piling up behind stuck/slow classifications.
- **Added:** MQTT service now exposes pressure telemetry (`pressure_level`, in-flight utilization, and threshold-based `under_pressure`) for diagnostics and adaptive scheduling.
- **Changed:** Auto video-classification queue now adaptively throttles effective concurrency when MQTT ingest pressure rises, prioritizing live `new/end` event processing during bursts.
- **Changed:** Detection backfill now uses a dedicated low-priority image inference executor so backfill classification no longer competes directly with live MQTT snapshot inference workers.
- **Changed:** `/health` now includes MQTT and video-classifier queue-pressure snapshots and marks health as `degraded` when MQTT pressure is high/critical.
- **Added:** New bounded async notification dispatcher service with configurable worker count, queue size, per-job timeout, and dropped-job accounting (`backend/app/services/notification_dispatcher.py`).
- **Changed:** Event ingestion now queues notification orchestration work instead of awaiting remote notification I/O inline, so notification slowness no longer blocks Frigate/BirdNET event processing.
- **Changed:** Notification queue saturation now fails safe by dropping excess notification jobs (with explicit warning logs and counters) rather than spawning unbounded fallback tasks in the ingest path.
- **Added:** MQTT topic-liveness watchdog for Frigate/BirdNET traffic asymmetry, including automatic MQTT session recycle when Frigate topic activity stalls while BirdNET remains active.
- **Added:** MQTT status telemetry now includes per-topic message counters, message-age metrics, connection uptime, liveness reconnect count, and last reconnect reason.
- **Changed:** `/health` now includes `notification_dispatcher` status and reports `degraded` when notification jobs have been dropped, surfacing notifier backpressure explicitly.
- **Added:** Backend regression tests covering queued notification dispatch, MQTT topic-stall reconnect detection, health degradation on notification drops, and MQTT-pressure throttling behavior for auto video classification.

- **Changed:** Clicking the bell notification icon now navigates directly to the full Notifications page instead of opening a dropdown menu.
- **Added:** A global progress bar now appears at the top of the application when background jobs (like backfills or batch analysis) are running, providing system-wide visibility into ongoing processes.
- **Changed:** Updated the global progress bar styling to match the emerald gradient theme used in the Notifications view.
- **Fixed:** Global progress aggregate calculations now sanitize and clamp malformed progress metadata, preventing invalid percentages or overflowed progress widths.
- **Changed:** Global progress multi-job summary text is now localized across supported UI languages instead of hard-coded English.
- **Fixed:** Global progress expand/collapse control now uses native button semantics with `aria-expanded`/`aria-controls` for better keyboard and screen-reader accessibility.

- **Fixed:** Dashboard Discovery Feed now correctly displays an empty state instead of continuous loading skeletons when there are no recent detections in the past 3 days.

- **Added:** Explorer filter toggle to show only detections with an "Audio Match".
- **Added:** Frigate logo asset for third-party integration representation (via acceptable use policy).
- **Changed:** Leaderboard and analytical statistics now group species queries using resilient canonical identities (`taxa_id` and `scientific_name`), making the UI immune to language switching and speeding up analytical database paths.
- **Added:** Single-image ONNX acceleration provider selector (`auto`, CPU, NVIDIA CUDA, Intel OpenVINO CPU/GPU) with runtime fallback reporting and Intel GPU auto-detection in the Settings UI.
- **Added:** Expanded classifier/OpenVINO diagnostics in Detection Settings and `/api/classifier/status` (OpenVINO version/import path, `/dev/dri` visibility, process UID/GID/groups, device list, and GPU probe errors) to make Intel iGPU setup failures debuggable in-container.
- **Added:** New non-interactive, movement-first video-analysis progress visualization for reclassification overlays (bottom thumbnail strip that advances with real analysis progress and scales to configurable frame counts), with a blurred current-frame/snapshot backdrop for clearer visual context.
- **Added:** `backend/scripts/patch_convnext_openvino_model.py` utility to patch `convnext_large_inat21` ONNX exports that fail OpenVINO compile with unsupported sequence ops (`SequenceEmpty`, `SequenceInsert`, `ConcatFromSequence`), with backup-on-replace behavior for in-place model remediation.
- **Added:** Personalization feedback persistence (`classification_feedback`) and manual-tag feedback capture during species corrections, including camera name, model ID, predicted label, corrected label, and original score.
- **Added:** Optional Personalized Re-ranking setting in Detection Settings, plus per-camera/per-model readiness diagnostics in `/api/classifier/status` and Detection Settings.
- **Changed:** Reclassification overlay progress presentation refined: larger bottom progress strip, centered progress/result stack, and a visible 30-second auto-close countdown after completion.
- **Changed:** Reclassification overlays now surface an `Auto Video` source badge for automatic video reclassification jobs (including the Analyze Unknowns pipeline), making batch/background runs distinguishable from manual reclassify actions.
- **Changed:** Detection Settings now surfaces ONNX inference provider/GPU acceleration controls in a dedicated panel (with an in-UI link to the repo GPU setup/diagnostics guide), and the bird naming style preference has been moved to Appearance Settings.
- **Changed:** Camera-aware inference paths now pass camera context into snapshot/video classification so personalized re-ranking can be applied consistently in live processing and manual/background reclassification flows.
- **Added:** AI Models settings cards now display model runtime and supported inference providers (CPU, NVIDIA CUDA, Intel OpenVINO CPU/GPU) so users can see which installed models can use each acceleration path.
- **Changed:** Active model cards now show only host-verified dynamic acceleration pills (CPU/CUDA/OpenVINO) and no longer duplicate static capability labels.
- **Fixed:** Added missing `ai_pricing_json` field to the backend settings update schema, resolving an issue where custom AI pricing inputs were not saved and reset to `[]`.
- **Fixed:** Corrected the AI Cost Estimation Reference link in the AI Settings UI to properly point to the reference documentation hosted on the project's GitHub repository.
- **Fixed:** CUDA availability detection now requires both the ONNX Runtime CUDA provider and a real NVIDIA CUDA device, preventing false-positive "CUDA available" status on Intel-only hosts.
- **Fixed:** OpenVINO runtime import compatibility now supports both legacy `openvino.runtime.Core` and OpenVINO 2026+ `openvino.Core`.
- **Fixed:** OpenVINO capability probing no longer risks backend startup crashes on unstable GPU plugin/driver combinations; GPU and device probes now run in isolated subprocesses and report diagnostics instead of crashing the API process.
- **Fixed:** Backend image now bundles Intel GPU userspace runtime dependencies (OpenCL + Level Zero via Intel graphics repo) for OpenVINO Intel iGPU support, and sets writable XDG cache/config paths to avoid OpenVINO telemetry/shader-cache warnings under non-root container users.
- **Fixed:** Detection Details now replaces the left media/video slot with the video-analysis progress UI during active analysis (`pending`/`processing`) instead of rendering a duplicate progress banner above the details panel.
- **Fixed:** Detection Details no longer shows the underlying video play button while the reclassification overlay is active.
- **Fixed:** Personalized re-ranking is fail-open with bounded score shifts; if feedback data is unavailable or errors occur, YA-WAMF falls back to base classifier scores.
- **Changed:** Updated the application icon set (including PWA assets, Apple Touch icon, and favicon) across the UI with a newly generated high-quality source image.
- **Fixed:** Explorer event-card weather summaries now use a two-tier layout with wrapping secondary metrics to prevent overflow in precipitation-heavy cases, and no longer duplicate temperature when freezing conditions are shown.
- **Changed:** Explorer event-card weather summaries now visually separate the primary weather summary from secondary weather details with labeled sub-rows for clearer hierarchy.
- **Changed:** Explorer event-card top weather row now shows only a generalized condition + temperature (with precipitation amounts/details kept in the Details row), and inner weather sub-panels use tighter horizontal padding.
- **Changed:** Explorer event-card top weather summary row no longer repeats a "Weather" label/icon header, reducing visual noise while preserving the labeled Details row.
- **Changed:** Explorer event-card weather sub-panels now use identical inner padding so summary/details cards align uniformly.
- **Fixed:** "Process Unknown Birds" now includes detections that are still labeled `Unknown Bird` even if a previous video classification run completed, allowing manual batch retries after model/config changes.
- **Fixed:** Explorer event cards now stay in sync more reliably during batch reclassification bursts; live updates no longer depend solely on the capped recent-detections list, and completed reclassifications trigger a debounced list refresh fallback to prevent stale `Unknown Bird` cards.
- **Changed:** Explorer pagination controls are now available at both the top and bottom of the event list to reduce extra scrolling during page-by-page review.
- **Changed:** Explorer now includes a manual "Refresh options" control for species/camera filters, and the page triggers a debounced metadata refresh after reclassification completions so newly introduced species appear in filter dropdowns without a full page reload.
- **Added:** `/api/events/filters` now supports `force_refresh=true` to bypass the short-lived filter-options cache when clients need immediate freshness.
- **Fixed:** BirdNET camera-audio mapping matching is now more resilient in correlation paths: comparisons are normalized for whitespace/case and accept legacy source IDs from raw payload metadata, reducing false mismatches after `nm` migration or mixed payload formats.
- **Added:** BirdNET camera-audio mappings now support multiple source names per camera (comma-separated), allowing multi-stream camera setups to correlate audio across multiple BirdNET sources.
- **Changed:** Detection cards and detection modal audio badges now show `No Audio Match` when audio does not confirm the visual species, and display nearby heard species instead of the previous generic `Heard` wording.
- **Added:** Events API now includes `audio_context_species` for unmatched-audio detections so cards can surface nearby BirdNET species without per-card fetches.
- **Fixed:** Manual-tag species options now hydrate missing taxonomy metadata on demand, improving common/scientific name coverage in locale-aware species pickers without requiring a full reload.
- **Fixed:** Active model capability pills now wrap cleanly on small/mobile cards to prevent overflow and clipped labels.
- **Fixed:** Dashboard "Recent Visitors" click-through now prefers stable `taxa:<id>` filters and no longer forces `date=today`, avoiding false "No events" results when sightings fall outside the local-day window.
- **Changed:** OpenVINO version pin raised from `>=2025.0.0,<2026.0` to `>=2025.4.0,<2026.0`. The 2025.4 release introduced a confirmed LayerNorm scale/bias reshape fix required for correct ViT-based model inference on Intel iGPU; 2026.0.0 is excluded because EVA-02 triggers a fatal `clWaitForEvents -14` process crash under that runtime, and 2026.0.1 is not available on PyPI.
- **Fixed:** Preprocessing registry metadata corrected for `small_birds` and `medium_birds` North America variants: both use `direct_resize` (not `center_crop`) with bilinear interpolation and no `crop_pct`, matching the actual `model_config.json` shipped with those artifacts. The `small_birds` Europe variant mean/std values have also been corrected to the CAPI/RoPE training statistics `[0.5248, 0.5372, 0.5086]` / `[0.2135, 0.2103, 0.2622]` (all values verified against released model config files).
- **Added:** OpenVINO GPU NaN fix probe test (`test_gpu_nan_fix_probe`) that runs every NaN-failing model through three recovery strategies — `HETERO:GPU,CPU`, SDPA-optimisation disabled, and both combined — and prints a comparison table. Results on this Intel iGPU with 2025.4.1: all three strategies still produce NaN for `rope_vit_b14_inat21` and `flexivit_il_all`; `hieradet_small_inat21` CPU inference is stable in isolation (the probe failure was a GPU-session-pollution artifact). No runtime fix is available for these models on this hardware without ONNX graph surgery.
- **Fixed:** `hieradet_small_inat21` registry `recommended_for` text removed an incorrect "Intel GPU" reference; the model is CPU and Intel CPU (OpenVINO) only.
- **Fixed:** `eva02_large_inat21` registry notes updated to confirm the fatal Intel GPU crash (`CL_OUT_OF_RESOURCES`) persists on OpenVINO 2025.4 — previously the note said "not retested on 2025.4."
- **Changed:** `eu_medium_focalnet_b` promoted to `GPU_VALIDATED` and `intel_gpu` added to its registry `supported_inference_providers`. With OpenVINO 2025.4.1 the model produces correct finite output (range ratio ≈1.0) in an isolated GPU context. Spearman correlation degrades when the GPU has been exercised by prior back-to-back model runs (a test-isolation artifact, not a production issue).
- **Fixed:** `eu_medium_focalnet_b` registry notes updated to reflect confirmed GPU support (was incorrectly marked "Intel GPU not supported"). GPU inference requires static-batch reshape (already applied by both the classifier service and the test harness).
- **Fixed:** `hieradet_dino_small_inat21` GPU_NOT_SUPPORTED failure reason corrected from "Compile error — HieraDeT architecture fails to load" to "NaN output — model compiles on GPU but produces non-finite values." The model uses standard `LayerNormalization` (fused to MVN by OpenVINO), so the NaN originates elsewhere — likely attention-scaling Sqrt ops or RoPE computations — and persists even after static-batch reshape.
- **Fixed:** `hieradet_dino_small_inat21` registry notes updated to match: "Intel GPU fails to compile" replaced with "Intel GPU produces non-finite outputs (NaN), confirmed on OpenVINO 2025.4."
- **Removed:** `hieradet_small_inat21` (ViT Reg4 M16 RMS Avg I-JEPA) and `hieradet_dino_small_inat21` (HieraDeT-D-Small + DINOv2) removed from the registry and GitHub release. Both are wildlife-wide small-tier models with confirmed GPU NaN and no unique niche — the wildlife-wide medium slot is covered by `rope_vit_b14_inat21` and large by `convnext_large_inat21`.
- **Kept:** `flexivit_il_all` (FlexiViT Global Birds) retained — unique global birds-only niche for users outside EU/NA (Asia, South America, Africa) with no dedicated regional model. CPU and Intel CPU validated.
- **Research:** Exhaustive ONNX graph surgery investigation for `hieradet_small_inat21` and `flexivit_il_all` GPU NaN. Root cause confirmed: Birder's custom RMSNorm decomposes to `Pow → ReduceMean(axes-as-tensor-input, opset 20) → Add(eps) → Sqrt → Reciprocal → Mul → Mul(scale)`. OpenVINO's MVN fusion pass pattern-matches only the standard `LayerNormalization` ONNX op; decomposed RMSNorm is not fused and produces NaN on GPU due to floating-point precision loss in the Sqrt chain. Approaches exhausted: (1) HETERO:GPU,CPU — NaN persists; (2) SDPA disabled — NaN persists; (3) ORT `SimplifiedLayerNormalization` fusion — OpenVINO rejects ORT custom ops; (4) Dynamo re-export at opset 20 — still decomposed; (5) Axes-to-attribute ONNX surgery at opset 17 — OpenVINO does not fuse the pattern even with attribute axes; (6) ONNX opset 23 `RMSNormalization` op — ORT 1.24.4 supports it but OpenVINO 2025.4 does not. Intel GPU support for these models requires either a future OpenVINO release that supports ONNX opset 23 `RMSNormalization`, or upstream Birder adoption of standard `LayerNormalization` export.
- **Added:** Comprehensive OpenVINO GPU diagnostic test suite (`backend/tests/test_model_openvino_gpu.py`) covering: ground-truth preprocessing validation against every installed `model_config.json`, NCHW float32 tensor shape/range checks, CPU-vs-GPU logit comparison (Spearman rank correlation ≥0.90, range ratio ≥0.5, top-5 overlap ≥1), a documented GPU support matrix with failure reasons for each known-unsupported model, and an always-passing diagnostic report test that prints a full comparison table across all installed models.

## [2.8.3] - 2026-02-23

- **Added:** New **AI Usage Dashboard** in Settings, providing real-time tracking of token consumption and estimated API costs for Gemini, OpenAI, and Claude.
- **Added:** Dynamic **AI Cost Estimation** with support for manual pricing overrides via a configurable JSON registry in the new AI tab.
- **Added:** **CUDA Acceleration** support for ONNX-based high-accuracy models (ConvNeXt, EVA-02) with a configurable UI toggle and real-time environment detection.
- **Added:** New **"AI" Settings Tab** to centralize LLM provider configuration, usage metrics, and prompt templates.
- **Added:** Configurable **Video Classification Frames** setting, allowing users to control the number of frames sampled for temporal ensemble analysis.
- **Added:** Refreshed **Application Icon Set** generated from a new high-quality source image.
- **Fixed:** Resolved species statistics grouping issues by prioritizing scientific name aggregation, ensuring accurate counts across different localized labels (e.g., Russian vs. English names).
- **Fixed:** Enhanced **Audio Correlation** to match against both scientific and common names, resolving "zero detection" issues when using localized BirdNet-Go instances.
- **Fixed:** Unified manual and background **Reclassification Logic** to ensure consistent display name updates and robust audio re-correlation.
- **Fixed:** Added `scientific_name` column to `audio_detections` table via a robust, idempotent migration following the Excellence Standard.
- **Fixed:** Resolved frontend build errors related to Svelte syntax in settings placeholders and missing interface properties.
- **Fixed:** Corrected backend test environment initialization so that Alembic migrations run automatically on temporary test databases, ensuring all tables are present during CI runs.
- **Changed:** Refactored AI usage logging to run as a non-blocking background task, improving API responsiveness.
- **Changed:** Fully localized all new UI elements and settings across all 9 supported languages.

## [2.8.2] - 2026-02-19

- **Fixed:** Detection-time email notifications now send reliably alongside Discord: corrected invalid Jinja in `bird_detection.html`, fixed snapshot fallback fetch handling, and added channel-level dispatch result logging so email skip/failure reasons are visible in backend logs.
- **Fixed:** Email notifications with "Only send on event end" now trigger on Frigate `end` events even when other channels already notified earlier in `standard`/`realtime`/`custom` modes; `silent` mode still suppresses all notifications.
- **Fixed:** Species enrichment matching is now more robust across languages for non-Wikipedia providers: iNaturalist taxon lookup now uses scored bird-only candidate selection (search + autocomplete + optional scientific-name hints), and eBird taxonomy matching now uses Unicode-safe normalization with locale resolution/fallback to avoid bad matches for localized names.
- **Fixed:** Species Wikipedia link resolution is now more robust across non-English locales (including Russian), using scored multilingual candidate selection plus scientific-name hints to avoid selecting similarly named but incorrect species pages.
- **Fixed:** Leaderboard species-info cache is now locale-aware, preventing stale cross-language external links/thumbnails after UI language switches.
- **Added:** Backend regression tests for multilingual Wikipedia article scoring and short-token boundary matching (`backend/tests/test_species_wikipedia_matching.py`).
- **Fixed:** Request middleware now handles client-disconnect cancellation paths gracefully, preventing noisy `RuntimeError: No response returned.` 500 traces during long-running calls such as event reclassification.
- **Fixed:** Detection modal manual-tag flow now provides explicit success/error toast feedback, sets pending state while saving, and hardens mobile interaction/scroll-lock behavior so species selection completes reliably and the picker closes cleanly after update.
- **Fixed:** Frigate `sub_label` values are now normalized when payloads arrive as arrays/objects, preventing SQLite binding crashes (`type 'list' is not supported`) during detection upserts/backfill/event processing.
- **Fixed:** Reclassification UI progress overlays now recover cleanly after failed requests; the backend emits a completion event on unexpected reclassification failures so clients do not remain stuck in pointer-blocking "in progress" state.
- **Fixed:** Date preset filtering in Events and initial detections loading now uses deterministic local-calendar `YYYY-MM-DD` formatting (via shared `toLocalYMD` utility) instead of UTC `toISOString()` splitting, preventing "today/week/month" drift around UTC day boundaries.

## [2.8.1] - 2026-02-14

- **Added:** Owner-curated favorite detections with idempotent API endpoints (`POST/DELETE /api/events/{event_id}/favorite`) and guest-safe read behavior.
- **Added:** Favorites filtering support on Events APIs (`favorites=true` on `/api/events` and `/api/events/count`) and Explorer UI toggle.
- **Changed:** Detection payloads now include `is_favorite` across list responses and SSE update flows so Dashboard/Explorer/Modal stay in sync.
- **Changed:** Retention cleanup now preserves favorited detections, and scheduled/manual media-cache cleanup now exempts favorite event media (snapshots, clips, previews).
- **Added:** Settings Data tab now includes an owner-only "Delete All Favorites" action with confirmation, API support, and localized UI copy across all supported languages.
- **Changed:** Email test-send flow now emits structured step-level SMTP/OAuth diagnostics (connect, STARTTLS, auth, send, timeout mode) to make delivery failures and timeouts debuggable from container logs.
- **Added:** New `detection_favorites` migration with guarded DDL, FK cascade semantics, and downgrade safety checks.
- **Fixed:** Resolved test-email template rendering error (`unexpected '\\'`) by correcting escaped quotes in the Jinja `font_family` default expression used by `POST /api/email/test`.
- **Changed:** Settings action feedback is now consistent across tabs: test/connect/disconnect/export actions route through unified status handling and toast notifications instead of mixed banner-only, inline-only, and `alert()` paths.
- **Fixed:** Settings dirty-state detection now includes `notifications_email_only_on_end` and `notifications_notification_cooldown_minutes`, so the unsaved-changes bar reliably appears for those edits.
- **Changed:** Secret handling in Settings is now consistent for redacted values (MQTT password, BirdWeather token, eBird key, iNaturalist credentials, LLM API key, and notification secrets) with unified “Saved” indicators and stable dirty-state behavior.
- **Changed:** Clarified Raspberry Pi support messaging in documentation; Pi compatibility is now explicitly described as best-effort ARM64 work in progress until physical-device validation is completed.
- **Added:** Roadmap now includes a detailed Raspberry Pi compatibility plan (multi-arch images, ARM dependency strategy, CI validation path, and real-hardware exit criteria).

## [2.8.0] - 2026-02-13

- **Fixed:** Owner system health notifications no longer reappear on every browser refresh when backend `/health` reports `status: ok`; stale health/cache system notices are now cleared when status is healthy.
- **Fixed:** Video player share-link manager now prevents mobile scroll bleed (background page scrolling behind the modal) and keeps long active-link lists scrollable within the overlay.
- **Changed:** About page was refactored for stronger accessibility and maintainability (semantic sections, in-page jump links, safer link rendering without `{@html}`, and translated About metadata keys across all supported locales).
- **Changed:** Documentation polish pass completed: README redundancy reduced, docs links standardized with icons, and docs index navigation made visually consistent.
- **Changed:** AI diagnostics clipboard controls now default to disabled (`localStorage` opt-in) and are only rendered when backend debug UI mode is enabled.
- **Added:** Public Access settings now include an optional "Share link base URL" used for generated video-share links in reverse-proxy/multi-domain deployments.
- **Changed:** Video share-link creation now uses the configured public share base URL when valid, with safe fallback to request host when unset/invalid.
- **Changed:** Locale key coverage pass completed across `de/es/fr/it/ja/pt/ru/zh` so frontend locale files now match English key coverage.
- **Fixed:** Hardened multiple Alembic migrations for SQLite-safe idempotency and downgrade reliability (guarded index/table drops, resilient recreation of missing indexes, and deterministic rollback of multilingual species cache rows).
- **Changed:** Documentation accuracy pass completed: API reference now reflects current route structure, setup/troubleshooting commands now use canonical compose service names, and Security-tab navigation wording is consistent across README/docs.
- **Added:** Docs CI guardrail (`backend/scripts/docs_consistency_check.py` + `docs-quality` workflow) to validate markdown links, detect stale doc terminology, and catch API endpoint drift in `docs/api.md`.

- **Fixed:** Leaderboard weather/toggle overlay updates now harden Apex options normalization (annotation bucket defaults + resilient y-axis series mapping) to prevent `Cannot read properties of undefined (reading 'push')` runtime crashes.
- **Fixed:** Apex chart update handling now catches both synchronous and async `updateOptions` failures and recreates the chart instance safely to avoid unhandled promise rejections.
- **Changed:** Dashboard/Species/Detections fetch failure logging now classifies transient network/abort errors and records them as warnings instead of noisy hard errors.
- **Fixed:** Mobile header action buttons now provide explicit/fallback accessible names, and key dashboard/list badges were adjusted for stronger light-mode contrast.

- **Added:** Leaderboard now includes two additional analytics panels beneath the main detections chart:
  - Species comparison trend chart for the top species in the selected window.
  - Activity heatmap chart (hour x weekday) for the selected window.
- **Added:** New stats API endpoint `GET /api/stats/detections/activity-heatmap` for 7x24 detection activity aggregation by weekday/hour.
- **Changed:** Leaderboard timeline loading now fetches compare-series data and heatmap data in parallel with graceful partial-failure handling.
- **Changed:** Added i18n keys/translations for new leaderboard analytics cards and weekday labels across supported locales.

- **Changed:** Removed the mobile-only Bottom Navigation bar to avoid duplicate navigation patterns with the existing mobile sidebar/menu.
- **Fixed:** Owner "system status" startup notifications are now emitted once per backend startup instance (using a startup instance marker), instead of being re-created on every page refresh.
- **Changed:** Leaderboard range controls now default to **Month** and are ordered **Month → Week → Day → All Time** for a more useful first view.
- **Changed:** Leaderboard chart header metadata was compacted into icon chips (range/grouping/metric) to reduce visual noise and long range strings.
- **Added:** Leaderboard chart now supports metric modes (`Detections`, `Unique species`, `Avg confidence`) plus trend modes (`Raw`, `Smooth`, `Both`).
- **Added:** Leaderboard chart now supports multi-species compare overlays (up to 3 species) and anomaly spike markers.
- **Added:** Timeline API now returns per-bucket `unique_species`, `avg_confidence`, and optional `compare_series` for selected species.
- **Fixed:** Safari dark-mode overscroll/root paint now consistently matches the active theme (including startup theme bootstrap) instead of flashing/lightening to white.
- **Changed:** Refined Leaderboard visual aesthetic with asymmetrical thumbnail overlaps for a bespoke "field journal" feel.
- **Changed:** Refined global color palette: deeper "Midnight" dark mode and warmer "Parchment" light mode for improved atmosphere and character.
- **Added:** Staggered entrance animations for Dashboard and Explorer cards to improve perceived performance and polish.
- **Fixed:** Standardized badge and chip styles across the UI for better visual consistency.
- **Fixed:** Video modal now includes a subtle zoom-in entrance transition and themed Plyr playback controls.
- **Fixed:** Leaderboard sunrise/sunset ranges now use local timezone data from weather APIs (instead of forced UTC), improving real-world day/week/month display accuracy.
- **Fixed:** Leaderboard sunrise/sunset range formatting now parses and sorts by clock-time values for stable ascending ranges (for example `07:28–08:13`).
- **Changed:** Leaderboard detections chart now defaults to histogram-style bars on Week/Month views while preserving line/area trend rendering for shorter ranges.
- **Changed:** Video modal mobile controls now use stronger contrast, larger touch targets, and explicit labels on preview/download actions for clearer visibility.
- **Changed:** Keyboard shortcuts modal is now grouped into clearer sections with improved key-description hierarchy.
- **Added:** Leaderboard chart-mode toggle (`Auto`, `Line`, `Histogram`) so users can override the default visualization mode per preference.
- **Changed:** Leaderboard chart subtitle/config metadata now include the active chart mode for clearer context and AI analysis consistency.
- **Added:** Backend regression tests for local-time sun fetch and sunrise/sunset range formatting behavior.
- **Fixed:** Detection modal mobile “Play video” interaction now uses a dedicated high-priority touch target and explicit event handling to avoid pointer interception.
- **Fixed:** Events/Dashboard video open flow now uses an explicit `videoEventId` handoff, closing detection details before opening the video modal to prevent modal-stacking race conditions.
- **Fixed:** Video autoplay startup no longer gets interrupted by timeline-preview attachment; preview activation is deferred until player startup settles.
- **Changed:** Timeline preview notifications now suppress transient `checking/deferred` noise and dedupe final state updates to avoid per-open notification spam.
- **Fixed:** Detection repository write-result checks now use per-statement SQLite `changes()` semantics (not cumulative `total_changes`), preventing false positives on pooled DB connections.
- **Fixed:** iNaturalist token deletion now returns accurate success/failure based on the last DELETE statement instead of cumulative connection write history.
- **Changed:** Notification delay-until-video flow now waits on an in-process video-classification completion signal, removing DB polling loops while preserving timeout fallback behavior.
- **Changed:** Video autoplay startup now accepts explicit user play intent and coordinates first playback with player readiness, with safer muted-first fallback for non-user-initiated starts.
- **Fixed:** Video modal playback-status chip no longer sticks on `Paused`; state now tracks the active media element even when player internals swap the underlying `<video>` node.
- **Fixed:** Timeline preview WebVTT cues now emit path-based sprite URLs instead of host-bound absolute URLs, so previews remain functional behind reverse proxies and non-default host headers.
- **Added:** E2E guard in `tests/e2e/test_video_player.py` to fail if playback is active while the status chip still renders the paused style.
- **Added:** Video modal now includes a dedicated share action that uses native share sheets when available and falls back to copying a deep link (`/events?event=<id>&video=1`) to clipboard.
- **Added:** Events page now supports video deep links via `?event=<frigate_event>&video=1`, opening the video modal directly.
- **Fixed:** Deferred timeline-preview activation now updates the active Plyr instance in place instead of recreating the player, preventing interaction-triggered fallback to native controls.
- **Added:** Events page now supports share-token deep links via `?event=<frigate_event>&video=1&share=<token>`, including direct modal open and token-aware playback URLs.
- **Added:** Owner-only expiring video-share API endpoints (`POST /api/video-share`, `GET /api/video-share/{event_id}`) backed by hashed tokens and expiry checks.
- **Added:** Owner share-link management APIs (`GET /api/video-share/{event_id}/links`, `PATCH /api/video-share/{event_id}/links/{link_id}`, `POST /api/video-share/{event_id}/links/{link_id}/revoke`) for active-link lifecycle control.
- **Changed:** Video-share creation now has explicit anti-abuse rate limits (`10/minute;60/hour`) and emits structured share-audit logs for create/update/revoke actions.
- **Changed:** Maintenance cleanup now purges expired/revoked video-share links on the scheduled cleanup cycle.
- **Added:** Video modal now includes an owner share-management panel to create links with TTL/watermark presets, list active links, and revoke/update links in place.
- **Added:** Backend proxy tests now cover share-link create/list/update/revoke endpoint behavior.
- **Added:** Shared video playback now renders a watermark label/expiry context in the modal and disables direct clip downloads for shared-link sessions.
- **Added:** Events now include a grouped day timeline strip with keyboard navigation (`[`, `]`, `0`) for faster time-based browsing.
- **Fixed:** Notification Center no longer emits noisy per-video "Timeline previews enabled" updates when opening clips.
- **Fixed:** Event processor error logging now captures event ID deterministically without `locals()` fallback hacks.
- **Changed:** CSP policy now removes `script-src 'unsafe-inline'` and adds `object-src 'none'`/`base-uri 'self'` hardening.
- **Changed:** Remaining hardcoded UI copy in key components (header/sidebar/video modal/toasts/top visitors/mobile shell) has been routed through i18n keys/defaults.

- **Added:** Video modal clip download action (`download=1`) with backend enforcement that allows owners always and guests only when explicitly enabled.
- **Added:** New public-access setting to control guest clip downloads (UI + API + auth status propagation): `public_access_allow_clip_downloads` / `PUBLIC_ACCESS__ALLOW_CLIP_DOWNLOADS`.
- **Changed:** Public-access settings now include an explicit “Allow clip downloads” toggle for guest users.
- **Changed:** Troubleshooting and setup docs now include step-by-step non-root permission remediation with exact `PUID`/`PGID`, compose snippets, and verification commands.
- **Changed:** Video playback UI migrated to Plyr for a more compact, familiar control surface with robust keyboard support and cleaner modal behavior.
- **Added:** Server-generated timeline preview thumbnails (sprite + WebVTT) via new media proxy endpoints:
  - `GET /api/frigate/{event_id}/clip-thumbnails.vtt`
  - `GET /api/frigate/{event_id}/clip-thumbnails.jpg`
- **Changed:** Timeline preview generation now uses the backend media-cache lifecycle (retention, orphan cleanup, empty-file cleanup, and cache stats integration).
- **Changed:** Timeline previews are now explicitly disabled when media cache is disabled (backend returns `503`; UI shows a clear disabled state).
- **Added:** Video modal now shows an indeterminate progress-bar notification while timeline previews are being checked/generated.
- **Added:** Prometheus metrics for timeline preview request outcomes and generation duration.
- **Changed:** Video player E2E coverage now validates Plyr controls, close button visibility, explicit preview-state messaging, and hover-preview rendering when preview tracks are available.
- **Fixed:** Video modal initialization watchdog no longer uses reactive timer state, preventing Svelte `effect_update_depth_exceeded` loops and full-UI hangs when opening playback.
- **Fixed:** Video player initialization now waits for the bound `<video>` element and uses bounded probe timeouts so modal startup cannot stall indefinitely on media probe requests.
- **Fixed:** Video player now initializes Plyr immediately after clip availability checks and probes preview thumbnails asynchronously, preventing controls from stalling while preview assets are generated.
- **Fixed:** Explorer and Leaderboard now surface backend load failures instead of silently rendering empty views, and leaderboard fetches the table and timeline independently (so one failing request does not blank the whole page).
- **Changed:** Release builds now derive `APP_VERSION` from the git tag and avoid embedding tag names as “branch” identifiers, preventing malformed version strings in telemetry and `/api/version`.
- **Changed:** Backend startup now logs explicit lifecycle phases with timing and marks non-fatal startup failures as `startup_warnings`.
- **Added:** New readiness endpoint `GET /ready` for orchestration health checks; returns `503` with details when startup is not ready.
- **Changed:** Health endpoint `GET /health` now includes `startup_warnings` and reports `degraded` when startup had non-fatal phase failures.
- **Changed:** Classifier/event-processor initialization is now deferred to runtime startup (not module import), improving startup failure attribution and resilience.
- **Fixed:** Leaderboard weather/temperature/wind/precip controls now remain visible even when overlay data is unavailable; controls are disabled with explicit hints (no weather data yet vs range limitation).
- **Added:** Video modal now includes hover timeline previews (sprite + WebVTT) when preview assets are available.
- **Changed:** Video modal now supports compact Plyr controls, keyboard seek/play shortcuts, and clearer preview-state messaging.
- **Changed:** Video modal bottom-bar now uses icon-only controls for preview status and clip download (with accessible labels/tooltips).
- **Fixed:** Video modal now attaches deferred timeline previews when playback pauses/ends instead of leaving preview state deferred indefinitely.
- **Added:** Timeline preview generation/availability now appears in Notification Center as process/update events for owner sessions.
- **Changed:** Video modal shortcut hint now uses compact keyboard/icon chips instead of plain text.
- **Fixed:** Video modal close button no longer overlays playback controls/content on mobile; close action is now in the modal header.
- **Changed:** Video modal bottom-bar chips and action icons now use larger touch targets and improved mobile spacing.
- **Fixed:** Video modal mobile action buttons (preview/download) now remain clearly visible with explicit labels and consistent icon sizing.
- **Changed:** Video modal keyboard shortcut hint now uses simpler text (mobile-friendly) instead of dense icon chips.
- **Changed:** Video modal now shows a touch-device-only timeline preview hint when previews are enabled, clarifying scrub behavior on mobile.
- **Changed:** Notification Center now includes source metadata, supports click-through deep links to relevant pages, and uses stronger dedupe/throttle logic for noisy SSE-driven updates.
- **Added:** Notification lifecycle hardening for owner sessions: stale in-progress items are auto-settled, SSE disconnect warnings are surfaced, and startup health/media-cache checks can raise actionable system notifications.
- **Changed:** Events page now supports `?event=<frigate_event>` deep links, allowing notification click-through to open the matching detection modal when present in the current result set.
- **Added:** Settings updates now broadcast a `settings_updated` SSE event so owner sessions receive real-time notification updates after configuration changes.
- **Changed:** Backend startup/shutdown CI smoke test now verifies `/health` and `/ready` responses under real lifespan startup.
- **Changed:** CI now runs a sampled Alembic upgrade-path matrix (multiple historical revisions → head), with SQLite integrity/FK checks and app-level `init_db()` validation on each path.

## [2.7.9] - 2026-02-08

- **Fixed:** Detection modal “Frame Grid” (reclassification/video analysis overlay) now scrolls so action buttons aren’t cut off on smaller viewports.
- **Fixed:** Settings “Send Test Notification” now calls Telegram and Pushover notification helpers with the correct argument order (prevents Telegram confidence parsing crash).
- **Changed:** Email notifications now use the configured UI font theme for their HTML templates (email clients may fall back to system fonts).
- **Changed:** Overscroll background and PWA/mobile browser chrome (`theme-color`) now track the active theme (light/dark/high-contrast).
- **Fixed:** Settings route now prompts for login and blocks rendering for unauthenticated users when Public Access is enabled (prevents guests directly navigating to `/settings` and generating noisy 403s).
- **Fixed:** Leaderboard ranking now defaults to **Total** (all-time), and “Unknown Bird” can be toggled on/off from the leaderboard table.
- **Fixed:** Leaderboard “Detections over time” chart now reacts to the Day/Week/Month selection (bucketed timeline), and shows an explicit range/grouping label (with optional weather overlays when location data is available).
- **Fixed:** Leaderboard chart weather-unit labels and species summary source attribution labels are now localized.
- **Fixed:** Leaderboard “All Species” summary now shows explicit date ranges for the 7-day and 30-day totals.
- **Fixed:** Traditional SMTP email now uses STARTTLS on port 587 when “TLS/STARTTLS” is enabled (and implicit TLS on 465).
- **Fixed:** Telegram notifications now truncate long bodies to respect Telegram length limits, and disable link previews in the text-only path.
- **Changed:** Email OAuth (Gmail/Outlook) connect/refresh logic hardened for SMTP XOAUTH2 flows (still needs end-to-end testing).
- **Changed:** Renamed the font picker “Default” label to “Modern” (Classic remains the actual default).
- **Changed:** Added `INTEGRATION_TESTING.md` and moved `ISSUES.md` to the repo root to make untested integrations and testing requests easier to find.
- **Fixed:** Home Assistant integration options flow no longer crashes on newer Home Assistant versions (prevents “Config flow could not be loaded: 500”).
- **Security:** Removed hardcoded MQTT credentials from a debugging script.
- **Changed:** Marked Email OAuth (Gmail/Outlook), Telegram Bot API, and iNaturalist submission flows as “needs testing” in `ISSUES.md`.

## [2.7.8] - 2026-02-07

- **Changed:** Default AI analysis and conversation prompt templates now prefer short paragraphs (instead of bullet-only formatting) for a more natural “field note” style.
- **Fixed:** PWA service worker updates now auto-apply; the “Update available” toast no longer appears on every refresh.
- **Fixed:** Backend tests no longer hang in this environment by replacing FastAPI `TestClient` usage with direct ASGI (`httpx.ASGITransport`) clients.
- **Fixed:** Regenerating AI analysis now clears the persisted AI conversation history for that detection (and the UI warns about this behavior).
- **Changed:** Hardened multiple Alembic migrations to be SQLite-safe and idempotent (guarded table/index/column operations and safer downgrades).
- **Changed:** AI surfaces in Detection Details modal refined in dark mode for a less stark, more cohesive look.

## [2.7.7] - 2026-02-07

- **Added:** AI conversation threads per detection with persisted history.
- **Added:** PWA service worker for offline caching and installability.
- **Added:** PWA update notifications and refresh prompt.
- **Added:** LLM connection test endpoint and Settings UI action for validating API keys.
- **Added:** Telemetry transparency details in Settings (installation ID, platform, flags, frequency).
- **Changed:** EventProcessor notification flow decomposed into a dedicated orchestrator.
- **Added:** Composite index on detections (`camera_name`, `detection_time`) for faster queries.
- **Changed:** AI analysis rendering now uses a cleaner markdown layout and improved dark-mode contrast.
- **Changed:** Settings panels now align cards to consistent heights and widths.
- **Changed:** Settings tooltips and aria-labels are fully localized.
- **Changed:** Default font theme is now Classic.
- **Fixed:** AI analysis text now renders brighter in dark mode and avoids over-eager list formatting.
- **Fixed:** Detection modal AI analysis panel now boosts dark-mode contrast for headings, body text, and code blocks.
- **Fixed:** Notification settings cards now size per row instead of matching the tallest card on the page.
- **Fixed:** Integration and authentication settings cards now size per row instead of matching the tallest card on the page.
- **Fixed:** AI analysis markdown now correctly applies dark-mode text colors for injected content.
- **Changed:** AI analysis markdown now promotes uppercase section lines to headings and restores dark-mode input contrast for follow-up questions.
- **Changed:** AI markdown now uses a unified Markdown parser, and prompt templates are configurable from Settings → Debug.
- **Added:** Localized prompt templates with selectable styles and a reset option in Settings → Debug.
- **Fixed:** CI errors by adding markdown-it typings and associating prompt editor labels with inputs.
- **Fixed:** Normalized AI markdown formatting for headings and bullet lists across analysis and conversation views.
- **Changed:** Unified AI analysis and conversation surfaces for consistent typography and contrast in light/dark modes.
- **Fixed:** Detection modal AI text now uses bright dark-mode colors and tighter heading/paragraph spacing.
- **Changed:** Expanded AI markdown styling coverage (lists, quotes, code blocks, tables, links) for light/dark modes.
- **Fixed:** AI conversation markdown now inherits panel colors correctly in dark mode and uses tighter heading/list spacing.
- **Changed:** Security reporting now accepts public GitHub issues for vulnerability reports.
- **Added:** Debug-only AI diagnostics panel in the detection modal for collecting markdown/theme contrast details.
- **Fixed:** AI markdown dark-mode styles now apply even when the modal is outside the global `.dark` tree.
- **Added:** AI diagnostics panel now supports copying raw AI content and prompt templates.
- **Added:** AI diagnostics panel can copy a full diagnostics bundle in one click.
- **Changed:** AI markdown styling now uses a dedicated surface class for stronger specificity in all themes.
- **Added:** Debug setting to toggle the AI diagnostics clipboard button on detection modals.

## [2.7.6] - 2026-02-06

- **Added:** First-run language picker with persisted preference.
- **Changed:** First-run setup, telemetry banner, and eBird sections in detection/species modals now use i18n keys.
- **Changed:** Settings tab labels fully localized (including Enrichment).

## [2.7.5] - 2026-02-04

- **Fixed:** Authenticated media (snapshots/clips/thumbnails) now include query tokens so owner access is honored even when public access limits are enabled.
- **Added:** Public access settings now include a separate media history window (snapshots/clips) from the detections list.
- **Fixed:** eBird nearby sightings now render even when species code resolution fails (warning no longer suppresses results).
- **Added:** Configurable date formats (US/UK/JP-CN) with consistent formatting across the UI.
- **Added:** Detection details now display the detection/event ID.
- **Added:** Range map zoom controls in the species detail view.
- **Changed:** Range map panel grows taller when eBird is disabled.
- **Fixed:** Species cards now respect enrichment summary/seasonality settings and avoid fetching disabled sources.
- **Fixed:** Species card labels and empty summary messaging now use localized translations.
- **Changed:** Enrichment sources are now automatic: eBird API key enables eBird-first enrichment with iNaturalist seasonality fallback; without a key, Wikipedia + iNaturalist are used.
- **Changed:** Enrichment settings UI is now read-only and reflects the effective source selection.
- **Fixed:** Added missing seasonality labels for species detail translations across locales.
- **Added:** Species detail modal now includes a GBIF-based global range map under seasonality.
- **Fixed:** Detection details now distinguish between confirmed audio matches and merely detected audio.
- **Fixed:** Detection cards and hero badge now distinguish audio detected vs confirmed.
- **Changed:** Range map now defaults to a wider zoom and includes interaction hints.
- **Fixed:** eBird usage now respects the integration toggle; disabled eBird no longer drives enrichments.
- **Changed:** Species detail activity charts now match the modal card styling for a more consistent look.
- **Changed:** Refined UI cohesion with unified navigation, button, and form-control styling.
- **Changed:** Refined Species Detail modal styling for consistent cards, headers, and recent sightings layout.
- **Changed:** Events species filter now uses taxonomic normalization and respects naming preferences.
- **Added:** Data settings now include cleanup actions for detections missing clips or snapshots.
- **Added:** Detection cards now show classification source (manual, video, snapshot).
- **Changed:** Media purge endpoints guard against Frigate outages and disabled clips.
- **Added:** Events page now includes a legend for classification source badges.
- **Changed:** eBird integration docs now recommend enabling eBird and clarify enrichment behavior.
- **Added:** Appearance settings now include a font switcher with multiple typography presets.
- **Fixed:** Mobile navigation now always uses the vertical layout for reliable menu access.
- **Changed:** Appearance settings now clarify that font changes apply immediately.
- **Fixed:** Font switcher now consistently applies across the UI.
- **Added:** Appearance settings now show language coverage hints for each font preset.

## [2.7.4] - 2026-02-03

- **Added:** eBird integration as a primary enrichment source for Species Info and Taxonomy (Common Names).
- **Changed:** Taxonomy lookup now respects the configured "Taxonomy Source" in settings. If set to eBird, the system prefers eBird common names (e.g., "Eurasian Blackbird") while still maintaining iNaturalist links for seasonality data.
- **Fixed:** eBird CSV export now fully complies with the "eBird Record Format (Extended)" specification (19 columns), ensuring successful imports without "Unknown species" or "Invalid date" errors.
- **Fixed:** eBird CSV export now uses the database's normalized `common_name`, resolving import mismatches (e.g., matching "Turdus merula" to "Eurasian Blackbird").
- **Changed:** UI Enrichment Settings now include eBird as a valid source for Summary and Taxonomy.
- **Changed:** Source attribution pills in detection details now always reflect the actual source of the displayed information.
- **Fixed:** Added a fallback note in Enrichment Settings to clarify that eBird taxonomy falls back to iNaturalist for missing IDs.

## [2.7.3] - 2026-02-03

- **Fixed:** Restored `taxa_id` lookup flow to ensure seasonality and localized names load when taxonomy cache entries exist or recent detections provide the ID.
- **Fixed:** Filled missing Detection settings translation keys across all supported locales.
- **Fixed:** Localized retention duration labels instead of relying on hardcoded language checks.
- **Fixed:** Added a generic localized fallback for test email failures.
- **Fixed:** Resolved eBird API 400 error caused by invalid `genus` category and added backend error handling for eBird service failures.
- **Fixed:** Expanded Wikipedia bird validation to support higher taxonomic ranks (Family, Genus, Order) and multiple languages (DE, FR, ES, IT, NL, PT, PL, RU).
- **Fixed:** Improved UI error states for eBird sightings in species and detection modals.
- **Fixed:** Aligned eBird CSV export with the standard 16-column Record Format (Extended) and removed the header row to prevent import parsing errors.

## [2.7.2] - 2026-02-03

- **Fixed:** Resolved issue where enrichments (eBird sightings, iNaturalist seasonality) were hidden in guest mode due to missing configuration state and restricted endpoints.
- **Added:** Public configuration state is now synchronized to guests via the auth status endpoint, enabling correct localized naming and feature toggles without requiring owner login.
- **Changed:** eBird taxonomic lookups now include Genus, Spuh, Slash, and ISSF categories, enabling lookups for broader groups like "Siskins and New World Goldfinches" (genus `Spinus`).
- **Changed:** eBird resolution now automatically falls back to scientific names if common name lookups fail.
- **Fixed:** Resolved issue where Seasonality chart would not appear in modals due to missing `taxa_id` in some API responses.
- **Added:** Comprehensive translation sync across all 9 supported languages, ensuring all settings panels (Data, Integrations, Enrichment) are fully localized.
- **Fixed:** Corrected multiple TypeScript and syntax issues in the frontend, resulting in a clean `npm run check`.
- **Fixed:** Accessibility live announcements now respect user settings even in guest mode.
- **Fixed:** Resolved JSON syntax error in German locale file (`de.json`).
- **Fixed:** Added missing `AuthStatusResponse` type handling in frontend API service.

## [2.7.1] - 2026-02-02

- **Added:** New dedicated Enrichment tab in Settings for centralizing all species data source configurations.
- **Added:** Interactive Map visualization for eBird sightings in species and detection modals (user location hidden in guest mode).
- **Changed:** Map visualization in guest mode now centers on a random sighting rather than the geometric center to prevent location inference.
- **Added:** eBird Notable Nearby sightings now include species thumbnails powered by iNaturalist.
- **Added:** Local Seasonality chart in Species Details (replacing Notable Nearby), showing monthly observation frequency from iNaturalist.
- **Changed:** Dashboard "Top Visitor" stat card now has a cleaner layout without the numeric visit count.
- **Fixed:** Resolved issue where Seasonality chart would appear blank due to missing taxonomy ID.
- **Added:** Expanded telemetry collection to include feature usage (notifications, integrations, enrichment settings) for better development insights.
- **Changed:** Refined Species Info, Recent Sightings, and Notable Nearby sections in Detection and Species modals with a new structured "beautiful" card-based layout.
- **Fixed:** Resolved mobile scrollability issue in the Detection Details pane.
- **Fixed:** Critical iNaturalist token expiration bug by implementing automatic refresh logic.
- **Fixed:** Multiple TypeScript and accessibility issues across frontend components, resulting in a clean build check.
- **Added:** Visual headers and icons for all enrichment sources (Wikipedia, eBird, iNaturalist) in modals.
- **Changed:** Centralized enrichment provider selection logic to ensure consistent data presentation across the UI.

## [2.7.0] - 2026-02-01

- **Added:** Notification Center now separates ongoing actions with pinned progress bars for long-running jobs.
- **Added:** Notification Center expand button opens a full notifications page.
- **Added:** Camera selection now includes a snapshot preview in Connection settings (auto-refreshing).
- **Fixed:** iNaturalist settings now correctly mark the Settings page dirty so changes can be saved.
- **Fixed:** Common "Show/Hide" labels now translate correctly in detection detail expanders.
- **Fixed:** Background tasks now log unhandled exceptions instead of failing silently.
- **Added:** Global exception handler now logs unhandled 500s with structured context.
- **Fixed:** Camera preview now uses a backend proxy (avoids CSP/mixed-content issues and supports auth).
- **Changed:** Database reset now pauses ingestion and cancels long-running jobs for a clean slate.
- **Fixed:** Notification Center popout aligns correctly in horizontal navigation and uses stronger shadows.
- **Changed:** Camera preview is now an accordion toggle (mobile-friendly, no popout clipping).
- **Fixed:** Camera preview works with unauthenticated Frigate endpoints and owner-auth mode.
- **Fixed:** Settings updates no longer overwrite unrelated fields on partial updates.
- **Added:** Auto video classification queue now has a safety cap with cleanup to prevent unbounded growth.
- **Changed:** EventProcessor flow refactored for clearer, more robust handling.
- **Added:** Leaderboard chart AI analysis with persisted insights and rerun support.
- **Changed:** AI analysis responses now respect the configured UI language.
- **Changed:** Leaderboard AI analysis always includes all weather overlays for richer insights.
- **Changed:** Leaderboard AI analysis now includes sunrise/sunset ranges in the prompt and chart capture.
- **Fixed:** Leaderboard chart analysis now correctly passes PNG mime types for Claude.
- **Fixed:** ApexCharts subtitle no longer throws errors when analysis banners toggle.
- **Changed:** Added render delays to ensure all chart overlays are captured before AI analysis.
- **Fixed:** Camera list now fills the available height in Connection settings.

## [2.6.8] - 2026-01-31

- **Changed:** Dashboard summary stats now use a rolling last-24-hours window for detections, species, top visitor, and audio confirmations.
- **Added:** Top Visitor stat now uses species thumbnail imagery (iNaturalist/Wikipedia) when available.
- **Changed:** Detection cards now show compact weather icons; audio context and detailed weather expanders now live in the detection details panel.
- **Changed:** Audio badges now only show when audio confirms the visual detection.
- **Added:** Audio detections are now persisted in the database so audio context survives in-memory buffer expiry.
- **Added:** Detection details now include expandable weather summaries (wind, cloud cover, precipitation).
- **Added:** Weather backfill action in Settings → Data to populate missing weather fields for historical detections.
- **Added:** Detections over time chart now shows subtle AM/PM rain/snow bands per day with a small legend, plus a temperature line series.
- **Added:** Detections over time chart now supports toggling weather bands/temperature/wind, shows average wind speed, and displays sunrise/sunset ranges.
- **Added:** Detections over time chart now supports a precipitation toggle with mm values.
- **Changed:** Adjusted precipitation chart styling and removed the native chart legend to use the custom legend.
- **Fixed:** Unknown Bird modal now correctly loads aggregated stats even when the underlying label is background/unknown.
- **Fixed:** Species detail modal close buttons now use explicit click handlers to avoid stuck modals.
- **Added:** Backfill jobs now run in the background with progress tracking so you can navigate away and return safely.
- **Added:** iNaturalist submission panel can be previewed without OAuth by enabling preview mode.
- **Fixed:** Test email failures now surface readable error feedback instead of an unhandled promise rejection.
- **Fixed:** Unknown Bird species modal now shows reclassification actions and a link to review detections in Explorer instead of a blank panel.
- **Changed:** Notifications now require a confirmed snapshot (confidence threshold or audio-confirmed) or confirmed video result before sending.
- **Fixed:** Email notifications now include Date/Message-ID headers and toned-down HTML sizing to reduce spam flags.
- **Added:** iNaturalist submission integration (owner-reviewed), with OAuth settings UI, connection flow, and detection-detail submission panel.
- **Added:** iNaturalist integration documentation and About page feature entry (marked untested pending App Owner credentials).
- **Fixed:** Leaderboard weather overlay removed wind/cloud bands; temperature plotted alongside detections for clarity.
- **Added:** Notification Center bell with persistent detection, reclassification, and backfill status updates.
- **Added:** Backfill async runs now broadcast start/progress/completion events for real-time UI updates.
- **Fixed:** Settings updates no longer overwrite existing secrets when placeholders or empty values are sent.
- **Changed:** Telegram notifications now use HTML escaping to prevent Markdown injection.
- **Changed:** Notification status icon now uses a chat bubble to avoid confusion with the Notification Center bell.
- **Added:** Reclassification progress now updates a pinned notification while batch analysis runs.
- **Changed:** Notifications settings now use a mode selector (Final-only / Standard / Realtime / Silent) with advanced overrides.
- **Added:** Notification mode is now stored in settings and respected by the backend dispatcher.
- **Added:** Optional Debug tab in Settings (gated by config) with iNaturalist preview toggle.

## [2.6.7] - 2026-01-29

- **Fixed:** Refined Audio/Video correlation logic: Audio detections can no longer "upgrade" the species name of a visual detection. Audio is now strictly for verification and metadata ("also heard").
- **Fixed:** High-confidence Video Analysis results now intelligently override the primary species identification and score if they provide a better match than the initial snapshot.
- **Fixed:** Automated re-evaluation of audio confirmation badges when video analysis corrects or updates a species identification.
- **Added:** Application versioning now includes the current git branch name (e.g., `2.6.7-dev+abc1234`) across the UI, Backend, and Telemetry.
- **Added:** Nginx Reverse Proxy guide updated with dynamic DNS resolution (resolver) to prevent "System Offline" (502) errors when container IPs change.
- **Changed:** Removed all references to the defunct generic wildlife classifier from documentation, the About page, and architectural diagrams.
- **Changed:** Standardized project documentation tone to use first-person singular ("I/me/my") throughout all Markdown files.
- **Fixed:** Resolved "System Offline" errors caused by stale DNS cache in Nginx Proxy Manager.
- **Fixed:** Resolved multiple TypeScript and Svelte compilation errors across settings components.
- **Fixed:** Corrected i18n interpolation usage and aria-label type mismatches in UI components.
- **Fixed:** Improved `onMount` async handling in `App.svelte` to prevent type mismatches.
- **Fixed:** Updated `Settings` interface to include missing notification and cooldown properties.
- **Added:** New `Reverse Proxy Configuration Guide` with detailed Cloudflare Tunnel and Nginx Proxy Manager examples.
- **Added:** Standardized trusted proxy configuration to automatically support RFC1918 private subnets (Docker/K8s) by default.
- **Added:** Module declaration for `svelte-apexcharts` to fix missing type definitions.
- **Fixed:** Enforced guest access checks for Frigate media proxies to prevent access to hidden or out-of-range events.
- **Fixed:** Added guest rate limiting to classifier status/label endpoints.
- **Fixed:** Added security headers to frontend Nginx responses.
- **Fixed:** Updated CSP to allow Cloudflare Insights script and beacon endpoints.
- **Fixed:** Allowed external image hosts in frontend CSP to prevent leaderboard thumbnail blocking.
- **Changed:** Disabled frontend production sourcemaps by default.
- **Fixed:** Added FastAPI request args to rate-limited classifier endpoints to satisfy SlowAPI.
- **Fixed:** Allowed media proxy access checks to fall back gracefully when the detections table is unavailable (test DB).
- **Changed:** Updated language utility tests to recognize Portuguese as supported.
- **Added:** Portuguese, Russian, and Italian UI translations.
- **Added:** Playwright-based console capture and Lighthouse runner scripts for external audits.
- **Added:** Leaderboard image inspection script for troubleshooting missing thumbnails.
- **Fixed:** Mark stale video analysis tasks as failed and added a timeout to prevent indefinite "in progress" states.
- **Changed:** Render AI naturalist analysis as paragraphs instead of bullet lists.
- **Fixed:** Persist deep video analysis label/score on manual reclassification so the UI shows the species.
- **Fixed:** Added missing language options to the header language selector.

## [2.6.6] - 2026-01-25

- **Added:** Standardized AI Naturalist responses to structured Markdown headings (`Appearance`, `Behavior`, `Naturalist Note`, `Seasonal Context`).
- **Added:** AI analysis can prefer clip frames (`use_clip`, `frame_count`) and falls back to snapshots.
- **Added:** Leaderboard hero now shows species blurb and “Read more” link (Wikipedia/iNaturalist).
- **Added:** Guest mode documentation in README and docs, plus About page feature entry.
- **Added:** BirdNET status exposed to guests so the Recent Audio panel can show in public view.
- **Changed:** Leaderboard chart now uses fixed dimensions to avoid NaN sizing/overlap issues.
- **Fixed:** `docker-compose.dev.yml` restored and aligned with prod/base configuration.
- **Fixed:** Added missing error boundary translation keys across non-English locales.
- **Fixed:** Removed stray `common.edit` key from Chinese locale.

## [2.6.5] - 2026-01-24

- **Changed:** Version bump to 2.6.5.
# 2.8.5

- Fixed Explorer manual-tag species search so alias-style labels like `Great tit`, `Great tit (Parus major)`, and `Parus major (Great tit)` collapse to a single canonical selectable species entry instead of showing duplicates.
- Added bulk manual tagging in the Explorer with multi-select support and a shared backend bulk-tag endpoint that reuses the existing taxonomy/audio/manual-feedback flow.
