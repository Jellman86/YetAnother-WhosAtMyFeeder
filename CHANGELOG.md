# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

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
