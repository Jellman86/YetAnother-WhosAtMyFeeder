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
- ✅ iNaturalist submission integration (owner-reviewed, currently untested)
- ✅ Multiple Language Support (i18n) - Translations for 9+ languages
- ✅ Built-in Authentication system (Admin/Owner & Guest roles)

**User Interface:**
- ✅ Real-time dashboard with SSE updates
- ✅ Dark mode support
- ✅ Detection filtering (species, camera, date, confidence, audio)
- ✅ Advanced Search & Filtering UI
- ✅ Video playback with seeking (HTTP Range support)
- ✅ Statistics dashboard (top visitors, daily histogram, recent audio)
- ✅ Species detail modals with Wikipedia info
- ✅ Settings management UI
- ✅ Model download & management

**Backend Services:**
- ✅ Media caching (snapshots & clips)
- ✅ Telemetry service (opt-in, anonymous)
- ✅ Backfill service (reprocess historical events)
- ✅ AI Integration Persistence (Caching) - Avoid redundant LLM API calls
- ✅ Health checks & Prometheus metrics
- ✅ Optional API key authentication
- ✅ Weather data enrichment

See [DEVELOPER.md](DEVELOPER.md) for architectural details.

---

## Table of Contents

- [🎯 Top Priority Features](#-top-priority-features)
  - [1. Multiple Language Support (i18n)](#1-multiple-language-support-i18n-) - **2.5 weeks**
  - [2. AI Integration Persistence](#2-ai-integration-persistence-) - **1.5 weeks**
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

## 🎯 Top Priority Features

These are the highest-impact features planned for the next major release.

### 1. Technical Debt Cleanup Sprint 🧹
**Priority:** P0 | **Effort:** L (1-2 weeks)

Focus the next release cycle on resolving outstanding technical debt and stability improvements.

**Scope (examples):**
- Finish background task hardening across all services
- Audit and tighten CSP (nonce-based where possible)
- Complete remaining Svelte 5 state migration
- Consolidate logging + error handling patterns
- Remove legacy/dead code paths and document any breaking changes

### 2. eBird Integration 🐦
**Priority:** P1 | **Effort:** M (4-7 days)

Add eBird integration for taxonomy lookup and optional submission/links.

**Notes:**
- Use eBird taxonomy for name normalization/links where configured.
- Optional submission flow should be owner-reviewed like iNaturalist.

### 3. iNaturalist Photo Submission 🌿 (Completed)
**Status:** ✅ Implemented (owner-reviewed, currently untested due to App Owner approval limits)

---

## Phase 1: User Experience & Enhancements

### 1.1 Conversation History for AI Analysis 💬
**Priority:** P2 | **Effort:** M (4-5 days)

Allow users to have follow-up conversations about specific detections with the AI.

**Implementation:**
- Extend `ai_analyses` table to support conversation threads
- Add `conversation_turns` table:
  ```sql
  CREATE TABLE conversation_turns (
    id INTEGER PRIMARY KEY,
    analysis_id INTEGER REFERENCES ai_analyses(id) ON DELETE CASCADE,
    role VARCHAR(20), -- 'user' or 'assistant'
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  ```
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
- ❌ Export filtered results to CSV/JSON

### 2.2 Enhanced Analytics Dashboard 📊
**Priority:** P2 | **Effort:** M (5-7 days)

> **Note:** Basic charts already exist! This adds more advanced visualizations.

**Current State:**
- ✅ Top Visitors bar chart
- ✅ Daily histogram
- ✅ Recent audio detections widget
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
**Priority:** P1 | **Effort:** M (4-5 days)

> **Note:** UI is already responsive! This adds PWA capabilities.

**Current State:**
- ✅ Responsive design works on mobile
- ✅ Dark mode support
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

Create automated highlight reels and timeline views.

**Features:**
- Automatic daily/weekly highlight compilation
- Timeline view showing all detections across clips
- Multi-clip stitching for continuous viewing
- Thumbnail preview scrubbing
- Bookmark/favorite specific moments
- Share clips with public links (optional)

**Breakdown:**
- Video processing pipeline (FFmpeg): 4 days
- Timeline UI component: 3 days
- Clip stitching logic: 2 days
- Sharing & permissions: 2 days
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

### 4.3 eBird Integration 🐦
**Priority:** P2 | **Effort:** M (6-7 days)

Integrate with eBird for species validation and community science.

**Features:**
- eBird API integration:
  - Validate detections against regional checklists
  - Suggest likely species based on location/date
  - Submit notable detections to eBird (with user consent)
- Regional species probability scoring
- Rareness alerts
- Import eBird personal observations for comparison

**Breakdown:**
- eBird API client: 2 days
- Validation logic: 2 days
- Submission flow with consent: 1.5 days
- UI integration: 1.5 days
- Testing: 1 day

### 4.4 Backup & Export Tools 💾
**Priority:** P1 | **Effort:** M (4-5 days)

Add robust backup and data portability features.

**Features:**
- One-click full database backup (SQLite → ZIP)
- Scheduled automatic backups (cron-based)
- Selective export (date range, species filter)
- Import detections from backup
- Cloud backup integration (S3, Dropbox)
- Disaster recovery documentation

**Breakdown:**
- Backup/export logic: 2 days
- Scheduled backup service: 1.5 days
- Import/restore tool: 1 day
- Testing: 0.5 days

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
  - Connection pooling (database, HTTP clients)
  - Async optimization (remove blocking I/O)
  - Background task queue (Celery or ARQ)
- Frontend optimizations:
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

### Finish Frontend State Migration (Svelte 5 Runes) ⚙️
**Priority:** P2 | **Effort:** M (4-6 days)

Complete the migration of remaining global state (theme/layout/stores) to Svelte 5 runes to simplify subscriptions.

### Optional Frontend Log Shipping 📡
**Priority:** P3 | **Effort:** M (3-5 days)

Allow UI logs to be optionally sent to a backend endpoint for better remote debugging.

### CSP Tightening (Nonce-based) 🛡️
**Priority:** P3 | **Effort:** M (3-5 days)

Investigate moving from `unsafe-inline` to CSP nonces where feasible.

### High Priority Fixes

> See [DEVELOPER.md](DEVELOPER.md) for comprehensive technical debt tracking.

| Issue | Effort | Priority | Notes |
|-------|--------|----------|-------|
| Settings update secret clearing bug | S (1 day) | P0 | Redacted fields get cleared on PUT |
| Blocking I/O in config save | S (1 day) | P0 | `config.py` blocks event loop |
| TypeScript type errors (bool → boolean) | S (0.5 days) | P0 | In `api.ts` |
| EventProcessor refactoring | M (3-4 days) | P1 | 200+ line method needs decomposition |
| Memory leak in auto video classifier | M (2 days) | P1 | Unbounded task dict |
| Telegram markdown injection | S (1 day) | P1 | Escape special chars in species names |
| Missing database connection pooling | M (2 days) | P1 | Use SQLAlchemy async pool |
| Video analysis schema mismatch | M (1 day) | P1 | Ensure columns exist in db_schema.py |

**Total Effort for High Priority Fixes:** ~2 weeks

### Already Fixed ✅

- ✅ API auth timing attack - Already uses `secrets.compare_digest()`

---

## Estimated Total Effort by Phase

> **Note:** Effort estimates updated to reflect features already implemented!

| Phase | Total Effort | Duration (if sequential) |
|-------|--------------|--------------------------|
| **Top Priority** | ~3.5 weeks | Multi-language + AI Persistence |
| Phase 1: UX Enhancements | ~1 week | Conversation history |
| Phase 2: UX Improvements | ~2 weeks | Filters, Analytics, PWA |
| Phase 3: Advanced Features | ~8 weeks | Multi-user, Alerts, Video, Ollama |
| Phase 4: Data & Integration | ~3.5 weeks | Audio viz, eBird, PostgreSQL, Backups |
| Phase 5: Performance & Reliability | ~4.5 weeks | Optimization, HA, Testing |
| Phase 6: Ecosystem & Community | ~10 weeks | Plugins, Community, Marketplace |
| Technical Debt | ~2 weeks | High priority fixes |
| **Grand Total** | **~35 weeks** | **8.75 months** |

**Note:** These are rough estimates assuming a single full-time developer. Parallelization, community contributions, and prioritization can significantly reduce time to delivery for critical features.

### Quick Wins (High Impact, Low Effort)

These features provide excellent user value with minimal development time:

1. **AI Integration Persistence** - 1.5 weeks - Save $$$ on API costs
2. **Advanced Search UI** - 1 week - Backend already done!
3. **Enhanced Notification Rules** - 0.5 weeks - Time/frequency limits
4. **Backup & Export Tools** - 1 week - Data safety
5. **Technical Debt Fixes** - 2 weeks - Stability & security

---

## Recommended Implementation Order

For maximum user impact with minimum effort, consider this order:

### Sprint 1: Critical Fixes & Quick Wins (3 weeks)
1. **Technical Debt Fixes** (P0 items) - 2 weeks
2. **AI Integration Persistence** - 1.5 weeks

### Sprint 2: Accessibility & UX (4 weeks)
3. **Multiple Language Support (i18n)** - 2.5 weeks
4. **Advanced Search & Filtering UI** - 1 week
5. **PWA Support** - 1 week

### Sprint 3: Data Safety & Performance (3 weeks)
6. **Backup & Export Tools** - 1 week
7. **Performance Optimization** - 2 weeks

### Sprint 4: Advanced Features (4 weeks)
8. **Enhanced Analytics Dashboard** - 1 week
9. **Conversation History for AI** - 1 week
10. **Ollama Local LLM Support** - 1 week
11. **Testing Infrastructure** - 2 weeks

### Future Sprints
12. *Multi-user support, eBird integration, PostgreSQL, etc. based on user feedback*

---

## How to Contribute

Interested in helping build any of these features? Check out [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

Have a feature idea not on this list? Open an issue on [GitHub](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues) to start a discussion!

---

**Last Updated:** 2026-01-29
**Version:** 2.6.7
