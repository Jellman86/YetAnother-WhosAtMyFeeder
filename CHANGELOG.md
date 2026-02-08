# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [2.7.8] - 2026-02-07

- **Changed:** Default AI analysis and conversation prompt templates now prefer short paragraphs (instead of bullet-only formatting) for a more natural “field note” style.
- **Fixed:** PWA service worker updates now auto-apply; the “Update available” toast no longer appears on every refresh.
- **Fixed:** Backend tests no longer hang in this environment by replacing FastAPI `TestClient` usage with direct ASGI (`httpx.ASGITransport`) clients.
- **Fixed:** Regenerating AI analysis now clears the persisted AI conversation history for that detection (and the UI warns about this behavior).
- **Changed:** Hardened multiple Alembic migrations to be SQLite-safe and idempotent (guarded table/index/column operations and safer downgrades).
- **Changed:** AI surfaces in Detection Details modal refined in dark mode for a less stark, more cohesive look.
- **Fixed:** Detection modal “Frame Grid” (reclassification/video analysis overlay) now scrolls so action buttons aren’t cut off on smaller viewports.
- **Fixed:** Settings “Send Test Notification” now calls Telegram and Pushover notification helpers with the correct argument order (prevents Telegram confidence parsing crash).

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
