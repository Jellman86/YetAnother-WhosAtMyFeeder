# YA-WAMF Roadmap

This roadmap outlines planned features and improvements for the YA-WAMF bird classification system. Estimated efforts are provided to help with planning and prioritization.

> **Important:** YA-WAMF is already feature-rich! This roadmap focuses on NEW features to be developed. See the [README](README.md) for comprehensive list of existing capabilities.

## Already Implemented ✅

YA-WAMF already has extensive functionality built-in:

**Core Classification:**
- ✅ Multiple ML model support (TFLite/ONNX: MobileNetV2, ConvNeXt, EVA-02)
- ✅ Svelte 5 migration
- ✅ Built-in Authentication system
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

All unresolved issues listed in `ISSUES.md` must be addressed **before** new feature work. This section is always the top priority.

**Active Issues:**
- None (all tracked issues currently resolved). See `ISSUES.md` for current testing gaps and known issues.

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
- ❌ Hourly heatmap, weekly/monthly trends, insights panel

**What to Add:**
- Hourly activity heatmap (24h x 7 days grid)
- Weekly/monthly detection trends chart
- Confidence score distribution histogram
- Camera comparison chart
- Insights panel:
  - Rarest sighting this week
  - Best detection hour
  - Weather correlation (e.g., "50% more birds when sunny")

**Breakdown:**
- Heatmap component: 2 days
- Trend charts: 2 days
- Insights algorithms: 2 days
- Testing: 1 day

### 2.3 Progressive Web App (PWA) Support 📱
**Priority:** P1 | **Effort:** M (4-5 days) | **Status:** ✅ Completed (v2.7.7)

### AI Analysis UX Polish ✨
**Priority:** P2 | **Effort:** S (1-2 days) | **Status:** ✅ Completed (v2.7.7)

Refined AI analysis and follow-up conversation rendering with markdown-aware formatting and improved dark-mode readability.

> **Note:** UI is already responsive! This adds PWA capabilities.

**Current State:**
- ✅ Responsive design works on mobile
- ✅ Dark mode support
- ✅ Mobile scrollability fixes
- ❌ PWA manifest, service worker, offline support

**What to Add:**
- PWA manifest for "Add to Home Screen"
- Service worker for offline caching
- Offline detection viewing (cached data)
- Touch gesture improvements:
  - Swipe left/right on detection cards
  - Pull-to-refresh on dashboard
- Reduced data mode toggle (thumbnails only, no video)

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

Create automated highlight reels and a time-based browsing experience that makes it easy to review activity over a day or week.

**Features:**
- Timeline view with grouped detections by time window (hour/day) and camera
- Quick-skim mode: jump between detections with keyboard shortcuts
- Highlight reels:
  - Daily summary (top confidence, rare species, most active hour)
  - Weekly recap (trend deltas, rarest sightings)
- Auto-generated "story" segments (e.g. 30-90s stitched clip)
- Clip stitching for continuous playback
- Thumbnail preview scrubbing and hover previews
- Bookmark/favorite moments with notes
- Optional public share links with expiry + watermark

**Breakdown:**
- Video processing pipeline (FFmpeg + caching): 4 days
- Timeline UI component + keyboard UX: 3 days
- Highlight scoring logic (confidence, rarity, activity): 2 days
- Clip stitching + preview thumbnails: 2 days
- Sharing & permissions + rate limits: 2 days
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
- ❌ Load balancing config, multi-replica support, K8s manifests

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
- ❌ E2E tests (Playwright coverage is currently minimal)

---

## Phase 6: Ecosystem & Community

### 6.1 Plugin System 🔌
**Priority:** P3 | **Effort:** XL (3-4 weeks)

Allow community-developed extensions.

**Features:**
- Plugin API specification
- Plugin discovery & installation UI
- Sandboxed execution environment
- Example plugins:
  - Custom notification channels
  - Alternative ML models
  - Data visualization widgets
  - Third-party API integrations
- Plugin marketplace (community repository)

**Breakdown:**
- Plugin architecture design: 4 days
- Core plugin API: 5 days
- Plugin manager UI: 3 days
- Example plugins: 3 days
- Documentation & SDK: 3 days
- Security review: 2 days

### 6.2 Community Features 🌐
**Priority:** P3 | **Effort:** L (2 weeks)

Build community engagement features.

**Features:**
- Public detection sharing (opt-in)
- Leaderboard (species diversity, rarest sighting)
- Community identification verification
- Discussion forum integration (Discourse)
- Monthly challenge events
- Species identification quiz

**Breakdown:**
- Sharing infrastructure: 3 days
- Leaderboard system: 2 days
- Verification workflow: 3 days
- Forum integration: 3 days
- Quiz/challenge features: 3 days

### 6.3 AI Model Marketplace 🤖
**Priority:** P3 | **Effort:** L (2 weeks)

Create a repository for community-trained models.

**Features:**
- Model upload & version control
- Performance benchmarking reports
- Regional model variants (e.g., North America, Europe)
- Automated model testing pipeline
- Model licensing & attribution
- Model recommendation engine

**Breakdown:**
- Model storage & metadata: 3 days
- Upload & versioning system: 3 days
- Benchmarking pipeline: 3 days
- Frontend model browser: 2 days
- Documentation: 1 day

---

## Technical Debt & Maintenance

### Harden Background Task Visibility 🔎
**Priority:** P1 | **Effort:** S (1-2 days)

Ensure fire-and-forget tasks always surface exceptions in structured logs.

**Notes:**
- Use a shared `create_background_task()` wrapper across services.
- Add task naming for easier tracing.

### Global Exception Handler 🧯
**Priority:** P1 | **Effort:** S (1 day)

Add a top-level exception handler to capture unexpected 500s with structured context.

### Complete UI Localization (i18n Phase 2) 🌍
**Priority:** P1 | **Effort:** M (4-7 days) | **Status:** ✅ Completed (v2.7.7)

Audit all UI components and remove hardcoded strings. Move all labels, errors, and chart metadata to locale files, including modal content (e.g., FirstRunWizard, Telemetry banner, Species detail modal).

### EventProcessor Decomposition 🧩
**Priority:** P2 | **Effort:** M (3-5 days)

Split `_handle_detection_save_and_notify` into smaller services (persistence, notification policy, media cache, auto-video trigger) to reduce coupling and improve testability.

### Detection Query Composite Index 📇
**Priority:** P2 | **Effort:** S (1-2 days)

Add a composite index for common event queries, e.g. `detections(camera_name, detection_time)` to speed up the Events page and exports.

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
| Phase 2: UX Improvements | ~2 weeks | PWA, Analytics |
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

**Last Updated:** 2026-02-06
**Version:** 2.7.5
