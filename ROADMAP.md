# YA-WAMF Roadmap

This roadmap outlines planned features and improvements for the YA-WAMF bird classification system. Estimated efforts are provided to help with planning and prioritization.

> **Important:** YA-WAMF is already feature-rich! This roadmap focuses on NEW features to be developed. See the [README](README.md) for comprehensive list of existing capabilities.

## Maintenance Mode: Next Up

These are the top maintenance-mode improvements to prioritize before broader feature expansion.

### 0. Canonical Species Identity Normalization (Scientific Name / Taxa ID) 🔒
**Priority:** P0 | **Effort:** L (1-2 weeks) | **Status:** Planned

Normalize detection identity to canonical taxonomy keys to prevent localization/alias mismatches across audio correlation, filters, and stats.

**Safety-first rollout plan:**
1. **Schema + invariants**
- Treat `taxa_id` as canonical key where available; fallback to `scientific_name`.
- Add/verify indexes and guardrails for canonical lookups without changing UI-facing names yet.

2. **Backfill (idempotent + resumable)**
- Backfill historical detections missing canonical fields via taxonomy cache/lookups.
- Run in batches with progress logging and retry-safe checkpoints.

3. **Write-path hardening**
- Ensure all new/updated detections persist canonical identity fields first.
- Keep `display_name/common_name` as presentation fields only.

4. **Read/query migration**
- Move grouping/filtering/correlation paths to canonical identity matching.
- Keep localized/common name rendering at response/UI layer.

5. **Verification + rollback**
- Add regression tests for cross-language/alias cases (for example Woodpigeon vs Common Wood-Pigeon).
- Run dual-read comparison metrics during rollout, then finalize once parity is confirmed.

### 1. Favourite Detections (Owner Curation) ⭐
**Priority:** P1 | **Effort:** M (4-6 days) | **Status:** ✅ Completed (v2.8.1)

Add a first-class way to pin standout detections so users can build a curated set of highlights.

**Design Direction (project-aligned):**
- Use an owner-curated favorites model first (single curated set), with schema choices that can later support per-user favorites.
- Keep guest access read-only: guests can view favorites, but only owner/admin can toggle.
- Preserve existing event flow and avoid heavy rewrites to detection pipelines.

**Implementation Plan:**
1. **Database + API contract**
- Add a favorites table (or equivalent relation) keyed by detection/event id with timestamps and creator metadata.
- Add idempotent toggle endpoints (`POST` favorite, `DELETE` favorite) and a filtered list/query mode (`favorites=true`).
- Ensure migration is safe, reversible, and consistent with existing migration standards.

2. **Backend integration**
- Join favorite metadata into detection responses used by dashboard/explorer/video contexts.
- Keep performance predictable with indexes and lightweight joins.
- Enforce permissions at API level (owner/admin write, guest read).

3. **Frontend UX**
- Add a consistent “star/favorite” action in detection cards, modal, and relevant tables.
- Add “Favorites” filter/preset in Explorer and optional “Highlights” section on Dashboard.
- Reuse existing toast/feedback patterns for toggle success/failure.

4. **Operations + quality**
- Add unit/API tests for toggle idempotency, auth boundaries, and filter behavior.
- Add E2E coverage for mark/unmark flows and guest-mode visibility.
- Add changelog/docs updates with behavior and permissions.

**Future-safe extension path:**
- If multi-user ownership expands later, evolve uniqueness from `(detection_id)` to `(user_id, detection_id)` with minimal API change.

### 2. Settings Architecture Refactor (Stability + Maintainability) 🧱
**Priority:** P1 | **Effort:** M (3-5 days) | **Status:** Planned

Consolidate the large settings implementation into reusable modules to reduce regression risk and improve PR velocity.

**Scope:**
- Extract Settings page logic into domain-focused modules (`dirty-check`, `secret-state`, `action-feedback`).
- Standardize async button state/feedback helpers across settings panels.
- Keep current UI/behavior stable while reducing duplication.

**Acceptance Criteria:**
- No behavior regressions in save/dirty/secret indicators/feedback.
- Reduced repeated logic in component files.
- Existing `npm run check`, unit tests, and settings E2E flows remain green.

### 3. Explorer Filter: Show Audio Matches Only 🎧
**Priority:** P1 | **Effort:** S (1-2 days) | **Status:** Planned

Add an Explorer filter toggle to show only detections with direct BirdNET audio confirmation.

**Scope:**
- Add `audio_confirmed_only` support to `/events` and `/events/count`.
- Thread filter through API client and Explorer page state/URL params.
- Add a clear UI toggle next to existing filter controls.
- Keep behavior consistent with pagination, count, and SSE refresh flows.

**Acceptance Criteria:**
- Explorer list and total count stay in sync when filter is enabled/disabled.
- Filter composes correctly with date/species/camera/favorites/hidden filters.
- Guest/public access constraints remain unchanged.
- Regression tests cover backend list+count filtering and basic frontend flow.

---

## Raspberry Pi Compatibility (Best-Effort Plan)

**Status:** Planned, not yet hardware-validated.

YA-WAMF currently does **not** have verified Raspberry Pi support based on direct device testing.  
At the moment, no physical Raspberry Pi test hardware is available in this project environment, so Pi compatibility is being treated as **best effort** until real-device validation is complete.

### Current Reality

- Published release images are currently focused on existing CI build targets and should not be treated as confirmed Raspberry Pi-ready.
- Documentation language has been corrected to avoid claiming confirmed Pi support.
- Objective remains to support **64-bit Raspberry Pi deployments** (Pi 4/Pi 5 class devices) for the Fast model profile.

### Implementation Plan

1. **Multi-Arch Image Publishing**
- Update image build pipeline to publish `linux/amd64` and `linux/arm64` manifests.
- Keep existing release flow (`dev` for `:dev`, `v*` tags for release tags/`latest`) unchanged.

2. **ARM-Safe Dependency Strategy**
- Review backend ML/runtime dependencies for `arm64` wheel availability and install stability.
- Separate heavyweight optional runtimes from baseline runtime to reduce ARM installation failures.
- Ensure default model/runtime path on ARM uses the lowest-friction inference stack.

3. **Pi-Oriented Runtime Profile**
- Provide a documented low-resource profile for Pi:
  - Fast model default (MobileNet/TFLite path).
  - Conservative defaults for expensive enrichments/features.
  - Clear guidance on optional features that may be too heavy on Pi 4-class hardware.

4. **CI Validation Without Physical Pi**
- Add ARM64 container smoke tests in CI (emulated where needed):
  - Container startup (`/health`, `/ready`).
  - Fresh DB migration + idempotency.
  - Basic inference path smoke check.
- Treat these as compatibility guards, not performance certification.

5. **Real Hardware Exit Validation (When Available)**
- Run a final acceptance pass on a physical Raspberry Pi before claiming full support:
  - Cold start time.
  - Sustained inference behavior and thermal stability.
  - End-to-end detection + UI responsiveness under realistic load.

### Support Statement Until Hardware Validation Exists

- Raspberry Pi support is **planned best effort**.
- ARM64 compatibility improvements are in progress.
- Official “supported” status will only be declared after successful real-device validation.

## Already Implemented ✅

YA-WAMF already has extensive functionality built-in:

**Core Classification:**
- ✅ Multiple ML model support (TFLite/ONNX: MobileNetV2, ConvNeXt, EVA-02)
- ✅ Svelte 5 migration
- ✅ Fast path mode (trust Frigate sublabels)
- ✅ Manual reclassification with confidence override

**Integrations:**
- ✅ Frigate NVR integration (MQTT events, media proxy)
- ✅ BirdNET-Go audio correlation (visual + audio matching)
- ✅ Multi-platform notifications (Discord, Telegram, Pushover)
- ✅ BirdWeather community science reporting
- ✅ Home Assistant custom integration
- ✅ LLM behavioral analysis (Gemini, OpenAI, Claude)
- ✅ iNaturalist taxonomy normalization
- ✅ iNaturalist submission integration (owner-reviewed)
- ✅ iNaturalist seasonality visualization (histogram data)
- ✅ eBird integration (nearby sightings, map visualization)
- ✅ eBird CSV export (bulk import support)
- ✅ Multiple Language Support (i18n) - Translations for 9+ languages
- ✅ Built-in Authentication system (Admin/Owner & Guest roles)

**User Interface:**
- ✅ Real-time dashboard with SSE updates
- ✅ Global progress bar hardening (sanitized aggregate progress math, localized multi-task summary text, improved accessibility semantics)
- ✅ Dark mode support
- ✅ Detection filtering (species, camera, date, confidence, audio)
- ✅ Advanced Search & Filtering UI
- ✅ Video playback with seeking (HTTP Range support)
- ✅ Statistics dashboard (top visitors, daily histogram, recent audio)
- ✅ Species detail modals with Wikipedia & iNaturalist info
- ✅ Interactive sightings map (eBird)
- ✅ Local Seasonality charts (iNaturalist)
- ✅ Settings management UI
- ✅ Model download & management

**Backend Services:**
- ✅ Media caching (snapshots & clips)
- ✅ Telemetry service (opt-in, anonymous, feature usage tracking)
- ✅ Backfill service (reprocess historical events)
- ✅ AI Integration Persistence (Caching) - Avoid redundant LLM API calls
- ✅ Health checks & Prometheus metrics
- ✅ Optional API key authentication
- ✅ Weather data enrichment

See [DEVELOPER.md](DEVELOPER.md) for architectural details.

---

## Table of Contents

- [Maintenance Mode: Next Up](#maintenance-mode-next-up)
- [Raspberry Pi Compatibility (Best-Effort Plan)](#raspberry-pi-compatibility-best-effort-plan)
- [🚨 Issues First](#-issues-first)
- [🎯 Top Priority Features](#-top-priority-features)
- [Phase 1: User Experience & Enhancements](#phase-1-user-experience--enhancements)
- [Phase 2: User Experience Improvements](#phase-2-user-experience-improvements)
- [Phase 3: Advanced Features](#phase-3-advanced-features)
- [Phase 4: Data & Integration](#phase-4-data--integration)
- [Phase 5: Performance & Reliability](#phase-5-performance--reliability)
- [Phase 6: Ecosystem & Community](#phase-6-ecosystem--community)
- [Technical Debt & Maintenance](#technical-debt--maintenance)
- [Recommended Implementation Order](#recommended-implementation-order)

---

## Legend

- **Effort Estimates:**
  - **Small (S):** 1-3 days of development
  - **Medium (M):** 4-7 days of development
  - **Large (L):** 1-3 weeks of development
  - **Extra Large (XL):** 3+ weeks of development

- **Priority:**
  - **P0:** Critical - Should be addressed immediately
  - **P1:** High - Important for user experience
  - **P2:** Medium - Nice to have, improves functionality
  - **P3:** Low - Future enhancement

---

## 🚨 Issues First

Prioritize fixes for anything listed in `ISSUES.md` (known issues, testing gaps) and any open GitHub Issues before new feature work.

If this section ever claims "none", treat it as stale: always check `ISSUES.md` and the GitHub issue tracker.

### Current Execution Focus (Issue Triage + Validation)
- Snapshot as of **March 3, 2026**: prioritize open GitHub issues before new feature work (`#16`, `#21`).
- ✅ `#17` (batch reclassify issue) closed after triage confirmed the remaining symptom belonged in `#19`.
- ✅ `#20` (weather conditions panel text alignment) fixed and reporter-confirmed, then closed.
- ✅ `#19` follow-up fixes shipped (`76433eb`, `419818f`) and issue closed after filter/state hardening and click-through correction.
- 🔄 `#16` BirdNET-Go mapping improvements (source-name / `nm` mapping) are in `dev`; reporter sees audio figures again and is validating long-running stability.
- 🔄 `#21` OpenVINO ConvNeXt load failure has `dev` remediation (patched model + safe re-download flow + clearer capability diagnostics) and is awaiting reporter retest.
- 🔄 Latest detection-pipeline hardening (snapshot disagreement guard + optional Frigate sublabel write-back + legacy EVA default remap) is in `dev` and awaiting field validation against misclassification-heavy feeds.
- 🔄 Continue reliability work in parallel: expand E2E coverage around restart/recovery scenarios and GPU/provider fallback paths.

---

## 🎯 Top Priority Features

These are the highest-impact features planned for the next major release.

### 1. Technical Debt Cleanup Sprint 🧹 (Completed)
**Status:** ✅ Resolved 100% of frontend TypeScript/Svelte-check errors.

### 2. eBird Integration 🐦 (Completed)
**Status:** ✅ Implemented nearby sightings, interactive maps, and CSV export.

### 3. iNaturalist Photo Submission 🌿 (Completed)
**Status:** ✅ Implemented (owner-reviewed, with auto-token refresh for reliability).

---

## Phase 1: User Experience & Enhancements

### 1.1 Conversation History for AI Analysis 💬
**Priority:** P2 | **Effort:** M (4-5 days) | **Status:** ✅ Completed (v2.7.7)

Allow users to have follow-up conversations about specific detections with the AI.

**Implementation:**
- Persist per-detection threads via an `ai_conversation_turns` table keyed by `frigate_event` (detection ID)
- Update AI service to maintain context across turns
- Add chat interface in detection modal
- Implement streaming responses for better UX
- Token usage tracking and limits

**Breakdown:**
- Database schema: 0.5 days
- Backend conversation logic: 2 days
- Frontend chat UI: 1.5 days
- Testing: 1 day

---

## Phase 2: User Experience Improvements

### 2.1 Advanced Search & Filtering UI 🔍
**Priority:** P1 | **Effort:** M (3-4 days)

> **Note:** Backend filtering already exists! Just needs a better UI.

Enhance the detection search interface with an intuitive filter panel.

**Current State:**
- ✅ Backend supports filtering by species, camera, date, confidence, audio confirmation
- ✅ Visual filter panel implemented (date presets, species, camera, sort)

**Breakdown:**
- ✅ Frontend filter panel UI
- ❌ Saved filter presets (save favorite filters)
- ✅ Export filtered results to CSV (eBird format)

### 2.2 Enhanced Analytics Dashboard 📊
**Priority:** P2 | **Effort:** M (5-7 days)

> **Note:** Basic charts already exist! This adds more advanced visualizations.

**Current State:**
- ✅ Top Visitors bar chart
- ✅ Daily histogram
- ✅ Recent audio detections widget
- ✅ Seasonality histogram (local/global via iNaturalist)
- ✅ Leaderboard analytics expansion shipped (detections trend modes, species compare trend chart, hour x weekday activity heatmap, weather overlays)
- ❌ Dedicated insights panel and camera-comparison analytics are still pending

**What to Add:**
- Confidence score distribution histogram
- Camera comparison chart
- Insights panel:
  - Rarest sighting this week
  - Best detection hour
  - Weather correlation (e.g., "50% more birds when sunny")

**Breakdown:**
- Confidence distribution chart: 1 day
- Camera comparison chart: 1 day
- Insights algorithms + UI: 2 days
- Testing: 1 day

### 2.3 Progressive Web App (PWA) Support 📱
**Priority:** P1 | **Effort:** M (4-5 days) | **Status:** ✅ Completed (v2.7.7)

### AI Analysis UX Polish ✨
**Priority:** P2 | **Effort:** S (1-2 days) | **Status:** ✅ Completed (v2.7.7)

Refined AI analysis and follow-up conversation rendering with markdown-aware formatting and improved dark-mode readability.

> **Status note:** PWA baseline is shipped (manifest + service worker + update flow). Further mobile UX ideas should be tracked as separate enhancements, not PWA core.

---

## Phase 3: Advanced Features

### 3.1 Multi-User Support & Roles 👥
**Priority:** P2 | **Effort:** XL (3-4 weeks)

✅ **Implemented in v2.6.0**

- ✅ User authentication system (JWT tokens)
- ✅ User registration/login/logout
- ✅ User roles: Admin (Owner) and Viewer (Guest)
- ✅ Rate limiting and session management
- ❌ Password reset flow (currently manual reset via config.json)
- ❌ SSO support (OAuth2: Google, GitHub)

### 3.2 Enhanced Notification Rules 🔔
**Priority:** P2 | **Effort:** S (2-3 days)

> **Note:** Basic notification filtering already exists! This adds custom rules.

**Current State:**
- ✅ Per-platform filters (Discord, Telegram, Pushover)
- ✅ Species whitelist
- ✅ Minimum confidence threshold
- ✅ Audio-confirmed only filter
- ✅ Camera filters
- ✅ Detailed notification modes (Silent, Final, Standard, Realtime)
- ❌ Custom rule builder, time-of-day conditions, frequency limits

**What to Add:**
- Time-based rules (only notify between 7am-7pm)
- Frequency limits per species (max 1 notification per hour per species)
- Weather-based rules (only notify when sunny, etc.)
- Custom message templates with variables

**Breakdown:**
- Time/frequency logic: 1.5 days
- Settings UI enhancements: 1 day
- Testing: 0.5 days

### 3.3 Video Timeline & Highlights 🎬
**Priority:** P2 | **Effort:** L (1.5-2 weeks)

**Status:** 🔄 In Progress (core player and timeline preview foundation shipped)

Create automated highlight reels and a time-based browsing experience that makes it easy to review activity over a day or week.

**Features:**
- ✅ Quick-skim mode foundations in player (keyboard seek/play controls)
- ✅ Expiry-limited share links now supported (`/events?event=<id>&video=1&share=<token>`) with backend token validation.
- ✅ Shared-link watermark overlay now enforced in player UI (label + expiry context).

**Breakdown:**
- ✅ Video preview processing pipeline + caching: shipped (sprite/VTT generation, retention integration, metrics)
- 🔄 Timeline UI component (grouped browsing) + advanced keyboard UX: initial day-bucket timeline strip + `[ ] / 0` navigation shipped; further expansion pending.
- Highlight scoring logic (confidence, rarity, activity): 2 days
- Clip stitching + preview thumbnails: 2 days
- ✅ Sharing & permissions: owner-issued expiring tokens, owner management controls (list/update/revoke), create-rate limiting, and scheduled stale-link cleanup are implemented.
- Testing: 1 day

### 3.4 Local LLM Support (Ollama) 🏠
**Priority:** P2 | **Effort:** M (4-5 days)

Add support for self-hosted LLMs via Ollama for privacy-conscious users.

**Implementation:**
- Ollama client integration
- Model selection UI (pull models from Ollama registry)
- Vision model support (LLaVA, etc.)
- Streaming response handling
- Fallback to cloud LLMs if Ollama unavailable
- Performance benchmarking tools

**Breakdown:**
- Ollama client integration: 2 days
- UI for model management: 1.5 days
- Testing with various models: 1 day
- Documentation: 0.5 days

---

## Phase 4: Data & Integration

### 4.1 Advanced BirdNET-Go Visualization 🎵
**Priority:** P2 | **Effort:** M (3-4 days)

> **Note:** BirdNET-Go integration already works! This adds visualization.

**Current State:**
- ✅ Audio-visual correlation (matches detections by timestamp)
- ✅ Audio buffer with configurable window
- ✅ Camera-to-audio-sensor mapping
- ✅ Recent audio detections widget
- ✅ Audio-confirmed badge on detections
- ❌ Audio spectrogram visualization, audio clip playback

**What to Add:**
- Audio spectrogram visualization in detection modal
- Audio clip playback widget (if BirdNET-Go provides clips)
- Confidence fusion algorithm (combine visual + audio scores)
- Audio detection history page (separate from visual detections)

**Breakdown:**
- Spectrogram rendering: 2 days
- Audio playback widget: 1 day
- History page: 1 day
- Testing: 0.5 days

### 4.3 eBird Integration 🐦 (Completed)
**Status:** ✅ Implemented. Nearby sightings, interactive maps, and CSV export for bulk import are fully operational.

### 4.4 Backup & Export Tools 💾 (Partially Completed)
**Status:** ✅ CSV Export for eBird added. ❌ Full DB backup/restore tool pending.

---

## Phase 5: Performance & Reliability

### 5.1 Performance Optimization 🚀
**Priority:** P1 | **Effort:** L (1.5-2 weeks)

Optimize system performance for large installations.

**Tasks:**
- Database query optimization:
  - Add missing indexes
  - Implement query result caching (Redis optional)
  - Pagination cursor optimization
- Backend improvements:
  - ✅ Connection pooling (database, HTTP clients)
  - Async optimization (remove blocking I/O)
  - Background task queue (Celery or ARQ)
- Frontend optimizations:
  - ✅ Resolve TypeScript/Svelte strict typing issues
  - Lazy loading for images/videos
  - Virtual scrolling for large lists
  - Bundle size reduction
  - Service worker caching
- Benchmark suite for regression testing

**Breakdown:**
- Database optimization: 3 days
- Backend async refactor: 4 days
- Frontend optimization: 3 days
- Benchmarking: 2 days

### 5.2 High Availability Setup 🏗️
**Priority:** P3 | **Effort:** M (1 week)

> **Note:** Health checks and Prometheus metrics already exist!

**Current State:**
- ✅ `/health` endpoint
- ✅ `/metrics` Prometheus endpoint

**What to Add:**
- Nginx load balancer configuration example
- Multi-replica backend support (session-less architecture)
- Grafana dashboard templates for metrics
- Kubernetes deployment manifests (Deployment, Service, Ingress)
- Database replication guide (for PostgreSQL when implemented)

**Breakdown:**
- Nginx config & docs: 1 day
- Grafana dashboards: 2 days
- K8s manifests: 2 days
- Documentation: 1 day

### 5.3 Testing Infrastructure 🧪
**Priority:** P1 | **Effort:** L (1.5-2 weeks)

✅ **Implemented**

- ✅ Unit tests for Service layer, repositories, and utilities
- ✅ Integration tests for API endpoints and MQTT flow
- ✅ CI/CD pipeline (GitHub Actions) with automated testing
- ✅ Code coverage reporting
- ✅ DB migration safety checks (fresh/idempotent/downgrade-upgrade + sampled historical upgrade paths)
- ✅ Startup/readiness smoke checks in CI
- ⚠️ Playwright E2E coverage is improving but still targeted; broader end-to-end regression coverage remains a priority

---

## Technical Debt & Maintenance

### Harden Background Task Visibility 🔎
**Priority:** P1 | **Effort:** S (1-2 days) | **Status:** ✅ Completed

Ensure fire-and-forget tasks always surface exceptions in structured logs.

**Notes:**
- Use a shared `create_background_task()` wrapper across services.
- Add task naming for easier tracing.

### Global Exception Handler 🧯
**Priority:** P1 | **Effort:** S (1 day) | **Status:** ✅ Completed

Add a top-level exception handler to capture unexpected 500s with structured context.

### Complete UI Localization (i18n Phase 2) 🌍
**Priority:** P1 | **Effort:** M (4-7 days) | **Status:** ✅ Completed (v2.7.7)

Audit all UI components and remove hardcoded strings. Move all labels, errors, and chart metadata to locale files, including modal content (e.g., FirstRunWizard, Telemetry banner, Species detail modal).

### EventProcessor Decomposition 🧩
**Priority:** P2 | **Effort:** M (3-5 days)

Split `_handle_detection_save_and_notify` into smaller services (persistence, notification policy, media cache, auto-video trigger) to reduce coupling and improve testability.

### Detection Query Composite Index 📇
**Priority:** P2 | **Effort:** S (1-2 days) | **Status:** ✅ Completed (v2.8.0)

Composite index for common event queries (`detections(camera_name, detection_time)`) is in place to speed up Events and export queries.

### Optional Frontend Log Shipping 📡
**Priority:** P3 | **Effort:** M (3-5 days)

Allow UI logs to be optionally sent to a backend endpoint for better remote debugging.

### CSP Tightening (Nonce-based) 🛡️
**Priority:** P3 | **Effort:** M (3-5 days)

Investigate moving from `unsafe-inline` to CSP nonces where feasible.

### BirdNET-Go Audio Backfill 🐦🎧
**Priority:** P2 | **Effort:** M (3-5 days)

Backfill BirdNET-Go audio detections into `audio_detections` so historical detections can regain audio context after a DB reset.

**Notes:**
- Requires a persistent BirdNET-Go data source (SQLite/JSON logs/API).
- Add an importer + mapping to camera IDs, then re-correlate detections.

### High Priority Fixes (Completed)

> See [DEVELOPER.md](DEVELOPER.md) for comprehensive technical debt tracking.

| Issue | Effort | Priority | Notes |
|-------|--------|----------|-------|
| Settings update secret clearing bug | S (1 day) | P0 | ✅ Fixed |
| Blocking I/O in config save | S (1 day) | P0 | ✅ Fixed |
| TypeScript type errors (bool → boolean) | S (0.5 days) | P0 | ✅ Fixed |
| iNaturalist Token Refresh | S (1 day) | P0 | ✅ Fixed: Auto-rotation implemented |
| Blank seasonality chart | S (0.5 days) | P0 | ✅ Fixed: Taxa ID propagation |
| Frontend compilation warnings | S (1 day) | P1 | ✅ Fixed: 0 errors/warnings |
| EventProcessor refactoring | M (3-4 days) | P1 | ✅ Partial refactor |
| Memory leak in auto video classifier | M (2 days) | P1 | ✅ Mitigated |
| Missing database connection pooling | M (2 days) | P1 | ✅ Implemented |
| Persist UI font theme to backend (used by emails) | S (1 day) | P2 | ✅ Implemented |
| Leaderboard span chart weather overlays | S (1 day) | P2 | ✅ Implemented |
| Remove legacy theme/layout subscribe wrappers from Settings | S (0.5 day) | P2 | ✅ Implemented |
| Guard Settings route for guests (public access) | S (0.5 day) | P1 | ✅ Implemented |
| Remove hardcoded credentials from debug scripts | S (0.5 day) | P1 | ✅ Implemented |

**Total Effort for High Priority Fixes:** ~2 weeks (Completed)

### Already Fixed ✅

- ✅ API auth timing attack - Already uses `secrets.compare_digest()`

---

## Estimated Total Effort by Phase

> **Note:** Effort estimates updated to reflect features already implemented!

| Phase | Total Effort | Duration (if sequential) |
|-------|--------------|--------------------------|
| **Top Priority** | **Completed** | Technical Debt + eBird + iNat |
| Phase 1: UX Enhancements | ~1 week | Conversation history |
| Phase 2: UX Improvements | ~1-2 weeks | Saved filters, analytics expansion |
| Phase 3: Advanced Features | ~8 weeks | Multi-user, Alerts, Video, Ollama |
| Phase 4: Data & Integration | ~2 weeks | Audio viz, PostgreSQL |
| Phase 5: Performance & Reliability | ~4 weeks | Optimization, HA, Testing |
| Phase 6: Ecosystem & Community | ~10 weeks | Plugins, Community, Marketplace |
| **Grand Total** | **~27 weeks** | **6.75 months** |

**Note:** These are rough estimates assuming a single full-time developer. Parallelization, community contributions, and prioritization can significantly reduce time to delivery for critical features.

---

## How to Contribute

Interested in helping build any of these features? Check out [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

Have a feature idea not on this list? Open an issue on [GitHub](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues) to start a discussion!

---

**Last Updated:** 2026-02-27
**Version:** 2.8.3-dev
