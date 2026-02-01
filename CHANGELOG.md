# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

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
