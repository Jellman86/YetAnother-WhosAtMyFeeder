# YA-WAMF Roadmap

The single, forward-looking plan for YA-WAMF. This is where **planned** and
**in-progress** work lives; **completed** work moves to [`CHANGELOG.md`](CHANGELOG.md)
and is summarised in the [Delivered](#3-delivered) catalogue at the bottom.

> **YA-WAMF is already feature-rich.** This roadmap tracks what's *next*, not what
> exists — see the [README](README.md) and [Delivered](#3-delivered) for current
> capabilities.

It is anchored by two honest assessments of *where we stand*:

- [Gold-Standard Review (2026-07-07)](docs/reviews/2026-07-07-project-quality-and-gold-standard-review.md) — quality assessment and the incremental path.
- [Telemetry Health Findings (2026-07-09)](docs/reviews/2026-07-09-telemetry-health-findings.md) — what actually fails across the fleet.
- [Image Classification Pipeline Review (2026-07-20)](docs/reviews/2026-07-20-image-classification-pipeline-review.md) — evidence provenance, temporal consensus, HQ media, and runtime recovery.

---

## How to read this roadmap

- **Priority:** `P0` critical · `P1` high · `P2` nice-to-have · `P3` future.
- **Effort:** `XS` <1d · `S` 1-3d · `M` 4-7d · `L` 1-3wk · `XL` 3wk+.
- **Status markers:** ✅ done · 🔄 in progress · ☐ not started.
- **Release scope:** only work listed under [3.0 exit criteria](#30-exit-criteria) blocks the
  release. A priority describes value and sequencing, not whether an item blocks `3.0`.

**Issues first.** Before new feature work, clear anything in `ISSUES.md` and the
[GitHub issue tracker](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues).
If a section ever claims "none open", treat it as stale and check both sources.

---

## 1. The Road to 3.0

`3.0` is the next major version. It has a deliberately bounded set of exit criteria; the
P2/P3 feature and platform backlog below does not delay the release unless an item is
explicitly promoted into those criteria. The release completes the defining product work,
proves the lossless migration path, and removes deprecated runtime paths.

The sub-sections are ordered as the program runs: **exit criteria → foundations already
delivered → release-defining initiatives → non-blocking backlog → breaking removals.**

### 3.0 exit criteria

`3.0` can ship when all of the following are true:

- [ ] The UI simplification pass has made Settings and the primary owner/guest journeys coherent,
  responsive, keyboard-operable, and honest about loading, empty, error, and destructive states.
- [ ] Native editorial review is complete for locales presented as fully supported, or any residual
  language-quality limitations are labelled honestly in the release notes.
- [x] Stable installation and recovery docs match the shipped Compose defaults and first-run auth
  state machine; all user-facing pages are reachable from the docs hub.
- [ ] The split-to-monolith migration is exercised against preserved `/config` and `/data` volumes
  and documented as lossless.
- [ ] The legacy split deployment and `X-API-Key` path are removed from the recommended/runtime
  surface, with migration guidance available before users update.
- [ ] The repository Definition of Done passes, and release notes state the removals, migration
  path, hardware limits, and any remaining translation limitations.

### 1.1 Engineering foundations — ✅ met

The engineering and fleet-health gates that had to land before `3.0`. Both are complete;
kept here for traceability.

#### Gold-Standard engineering gate 🏅
**Priority:** P0 | **Effort:** M | **Status:** ✅ Gate met

The gap between the `CLAUDE.md` contract and the codebase is closed to the point that the
release ships against the full bar. Tracked assessment:
[Gold-Standard Review](docs/reviews/2026-07-07-project-quality-and-gold-standard-review.md).

- ✅ **CI enforcement** — Ruff lint + format gates, backend coverage floor ratcheted 20%→60%
  (measured ~65%), and `CONTRIBUTING.md` rewritten against the contract.
- ✅ **API contract** — build-time OpenAPI artifact (`backend/openapi.json`) with a CI drift
  check, and a generated SPA type contract (`apps/ui/src/lib/api/generated/openapi.ts`) with a
  CI freshness check, so backend/frontend drift fails review.
- ✅ **Documentation governance** — documentation standard published, governance files added
  (`AGENTS.md`, `CODE_OF_CONDUCT.md`), local links/API routes checked in CI, and the stable-install
  plus authentication-recovery paths corrected against current behaviour.

The remaining generated-type adoption is a small, non-blocking carry-over — see
[Engineering carry-overs](#16-engineering-carry-overs).

#### Fleet health: Frigate media reliability + telemetry signal 🩹
**Priority:** P1 | **Effort:** M | **Status:** ✅ Complete

All four recommendations from the
[Telemetry Health Findings](docs/reviews/2026-07-09-telemetry-health-findings.md) shipped:

- ✅ **Recording-frame classification fallback** — when snapshot, thumbnail, and cached image
  all fail, a frame is extracted from Frigate's continuous recording at the detection moment and
  classified, instead of dropping the detection (the fleet's most common real failure).
- ✅ **In-app Event-Not-Found guidance** — the Errors page surfaces the tuning guide as a calm
  advisory when the media-unavailability drop rate is genuinely elevated.
- ✅ **Cleaner telemetry signal** — expected `filter_*` drops are informational and excluded
  from health reporting; critical stage failures now carry `error_type` + `stage` context.
- ✅ **Old-build critical retired** — the `classify_snapshot` critical is confirmed
  `2.9.15`/`2.10.0`-only (resolved on `2.11`+); stale installs are nudged by the in-app update prompt.

### 1.2 Required product work

The headline work that makes `3.0` a major version: a guided first run, a cleaner product
surface, a codebase reviewed to the gold standard, and complete translations.

#### First-run setup wizard 🧭
**Priority:** P1 | **Effort:** L | **Status:** ✅ Shipped on `dev` — multi-part, hardware-validating, re-runnable from the main owner navigation ([design](docs/plans/2026-07-12-first-run-setup-wizard-design.md))

A friendly, **skippable** guided setup that configures YA-WAMF end to end and — crucially —
is **idempotent and re-runnable at any time** from **Setup wizard** in the main menu (running a step again is safe and
never clobbers unrelated config). Steps:

- **Model selection with on-hardware validation** — pick a classifier and confirm it actually
  loads and runs on the providers available to the running image. The shared provider sweep now
  intersects the image package, host probe, and selected model; tests ONNX CPU/CUDA and OpenVINO
  CPU/GPU/NPU as applicable; compares real-image output with a CPU baseline; and persists the
  fastest verified provider. The wizard validates only the selected installed model, while the
  Diagnostics surface can optionally download and test the whole registry.
- **Integrations** — Frigate, BirdNET-Go, media servers, notifications: guided connect + test.
- **Frigate settings** — cameras, recording-retention guidance, and the detection gates that
  drive the Event-Not-Found problem (`min_score` / `min_initialized` / `threshold`).
- **Common quality configs** — HQ snapshots, crop selection, verification gates.

Each step is independently re-runnable; skipping the wizard leaves the current config untouched.

#### UI simplification & polish ✨
**Priority:** P1 | **Effort:** L | **Status:** 🔄 In progress — Settings simplification complete;
primary owner and guest journeys next
([design](docs/plans/2026-07-16-settings-navigation-simplification-design.md))

Make the whole UI clean, coherent, and calm — **especially Settings**, which is currently
bloated with indistinct sections. ✅ The research-and-codify step is done: the UI/UX standard
(Nielsen's heuristics, WCAG 2.2 AA, Refactoring UI craft) is codified in `CLAUDE.md` §5 and
[`docs/standards/ui-ux.md`](docs/standards/ui-ux.md). Remaining: apply it consistently across
the owner and guest surfaces (information architecture, grouping, progressive disclosure,
empty/error states) — the "full UI refresh" half of the major-version jump.

✅ **Settings pass:** task-based navigation, semantic camera controls, and progressive disclosure
now cover every Settings tab. Optional services are toggle-first, inactive credentials and tests stay
hidden, maintenance/analytics/destructive tools no longer compete with routine policy, nested card
noise and structural emoji are reduced, and the Settings type floor is 12px. The remaining work is
the primary owner/guest journey review, including their loading, empty, error, and destructive states.

✅ **Primary observation and history pass:** Dashboard, Leaderboard, Species details, BirdNET-Go
History, Explorer filters, detection tiles, and detection details now share the calmer first-run
visual language. Repeated cards have become divided information surfaces, media and rankings lead
their records, small-screen layouts avoid horizontal overflow, technical identifiers use progressive
disclosure, and interactive controls retain touch and keyboard affordances. Remaining work is the
same treatment across the less-frequent owner journeys plus a final cross-route loading, empty,
error, and destructive-state audit.

✅ **Cross-route loading and delivery pass:** Operational pages and language catalogs now load on
demand, the entry bundle is about 94% smaller, fingerprinted assets are compressed and
cached safely, and route-download failures recover in place. Quick navigation avoids loading-state
flicker; a quiet delayed status replaces page-sized skeleton walls on genuinely slow connections.
Long-lived authenticated tabs now replace stale live connections when identity changes, use one
adaptive analysis-status poller, pause routine polling while hidden, bound background requests with
timeouts, and load live camera frames only on demand. Explorer and Leaderboard loads now cancel or
ignore superseded responses, portrait enrichment has bounded concurrency and memory, shared
detection startup is single-flight, and full-visit checks no longer accumulate recurring timers or
unbounded per-event state while browsing history. Dashboard audio, Settings maintenance status, and
model-download status refreshes are also bounded against hidden tabs, stalled requests, overlapping
ticks, and navigation cleanup. Camera health now comes from one lightweight Frigate stats poll rather
than image success, while its looping viewer fetches only the selected camera and pauses when closed
or hidden.
The remaining audit is focused on page-owned empty, error, refresh, and destructive states.

#### File-by-file code-quality review 🔬
**Priority:** P1 | **Effort:** XL | **Status:** ✅ Completed

✅ **Completed.** The code-quality standard for our stack
(Python/FastAPI + Svelte 5/TypeScript) is codified in `CLAUDE.md` §4 and
[`docs/standards/code-quality.md`](docs/standards/code-quality.md). The file-by-file review and
refactor is complete, with permanent frontend/backend source gates preventing the reviewed
contract, typing, layering, async-I/O, and hygiene failures from returning.

Completed review tranches:

- ✅ **Owner debug API** — extracted database diagnostics behind a repository, added explicit
  response models for every endpoint, made secret redaction independently testable and consistent
  with the application-wide `***REDACTED***` contract, and moved filesystem inspection off the
  async event loop.
- ✅ **Python formatting baseline** — brought the remaining backend files into the enforced Ruff
  format baseline so the repository-wide formatter check is clean before deeper review batches.
- ✅ **Frontend live-update boundary** — replaced `any` across the root SSE wiring and coordinator
  with explicit payload, health, notification, and translation contracts; normalized required
  detection fields at the untrusted JSON boundary and added regression coverage.
- ✅ **Frontend API and operational stores** — removed `any` from maintenance/system clients,
  detection state, health interpretation, incident state, diagnostics snapshots, and reclassify
  recovery; external payloads now enter as `unknown` and are narrowed before use.
- ✅ **Shared frontend components** — typed navigation, settings tabs, camera roles, health runtime
  state, event handlers, timers, translations, and notification error parsing across the reusable
  component layer.
- ✅ **Chart and map vendor boundaries** — replaced ApexCharts and Leaflet `any` usage with typed
  constructors, instances, DOM extensions, option records, maps, layers, and dynamic-import guards.
- ✅ **Events and health pages** — typed URL filter admission, naming inputs, operational health
  metrics, and user-facing error extraction across the Events and Health diagnostics surfaces.
- ✅ **Species analytics page** — typed leaderboard rows, weather buckets, comparison series, chart
  axes/tooltips/options, stable serialization, chart capture, and analysis errors end to end.
- ✅ **Audio and detection detail surfaces** — typed Audio History chart options and removed `any`
  from detection/species modals through shared naming inputs, API response fields, timers, and safe
  unknown-error extraction.
- ✅ **Settings and frontend type gate** — replaced Settings casts with domain normalizers, typed
  input attributes and timers, standardized unknown-error handling, and added a full-source Vitest
  gate that rejects explicit `any` in application TypeScript/Svelte outside generated contracts.
- ✅ **Backend endpoint contracts** — authentication, Settings, classifier, maintenance/status,
  Events, and model-evaluation JSON responses now publish explicit generated contracts; binary
  model-evaluation artifacts are explicitly classified as file responses.
- ✅ **Backend persistence boundaries** — all HTTP routers are free of direct database execution.
  Detection, OAuth-token, eBird-export, species taxonomy/cache/search, and video-share persistence
  are owned by focused repositories.
- ✅ **Classifier download I/O** — model-directory inspection, archive extraction, asset writes,
  and synchronous model reloads are dispatched off the async request loop.
- ✅ **Async blocking-I/O review** — database migration/backup work, uploaded and pipeline image
  decoding, video temp-file handling, media-cache cleanup, model-evaluation artifacts, model
  discovery/activation, and AI recording reads now run through async-native APIs or worker threads.
- ✅ **Backend architecture gates** — permanent AST-backed tests reject router-owned database
  execution, missing endpoint response contracts, incomplete repository signatures, direct blocking
  I/O inside async functions, untracked TODO/FIXME notes, and application `print()` calls.
- ✅ **Completion verification** — 1,390 backend tests pass (65 platform/model skips), backend
  coverage is 79%, 408 frontend tests pass, Svelte reports zero errors/warnings, the production UI
  builds, Ruff lint/format pass, migration smoke/path-matrix checks pass, documentation is
  consistent, and committed OpenAPI/client artifacts are current.

#### Full translation review 🌍
**Priority:** P1 | **Effort:** M | **Status:** ✅ Editorial sweep complete; independent native validation is not claimed ([design](docs/plans/2026-07-12-full-translation-review-design.md), [review](docs/reviews/2026-07-20-translation-editorial-review.md))

Review every locale against the `en.json` source of truth for completeness, accuracy, and
consistency; fix missing keys, drift, and machine-translation artefacts. Add CI checks so
translations can't silently rot.

✅ **Structural completeness** is finished: every locale now exactly matches `en.json`, including
shared controls, telemetry, update messaging, the Frigate media advisory, Dashboard audio copy,
Leaderboard source controls, and the complete Audio History surface.

✅ **Anti-rot CI is in place**: the audit rejects missing/extra keys and placeholder drift, asserts
a curated set of high-risk strings differs from English, and a baseline ratchet
(`locales.untranslated-regression.test.ts` + `locales.identical-baseline.json`) fails the build if
any *new* user-facing string lands byte-identical to English, so untranslated copy can't slip in.
The editorial gate additionally rejects encoding damage, surrounding whitespace, ASCII ellipses in
prose, known accent-loss substitutions, incorrect French double-punctuation spacing, and
sentence-length Latin-only copy in Japanese, Russian, or Chinese.

✅ **The application-wide editorial sweep is recorded**: all nine catalogs contain the same 1,981
leaf keys, interpolation tokens are preserved, and no sentence-length English copy remains in the
non-Latin catalogs outside technical examples. The pass corrected copied English enrichment copy,
accent-stripped settings and video-player text, Russian and Japanese phrasing, French punctuation
spacing, catalog whitespace, and application-wide ellipsis typography.

**Release limitation:** this was a repository-backed editorial and automated quality review, not
independent native-speaker certification. Before `3.0`, either obtain native sign-off for locales
presented as fully supported or state that limitation plainly in the release notes, as required by
the exit criterion above. No automated or structural defect remains open; independent reviewers
may still refine idiom and choose a single regional convention for the generic Portuguese catalog.

### 1.3 Candidate feature backlog — non-blocking for 3.0

Candidate features, roughly ordered by value. These can land before `3.0` when they are ready,
but otherwise remain post-3.0 backlog; they do not delay the release.

#### Finish multi-user: password reset + SSO 👥
**Priority:** P2 | **Effort:** M | **Status:** 🔄 Core shipped (v2.6.0), two gaps remain

JWT auth, registration/login/logout, Admin (Owner) + Viewer (Guest) roles, rate limiting, and
session management all shipped. Remaining:
- Self-service password reset flow (currently a manual `config.json` reset).
- Optional SSO (OAuth2: Google, GitHub).

#### Enhanced notification rules 🔔
**Priority:** P2 | **Effort:** S | **Status:** ☐ Not started

Per-platform filters, species whitelist, confidence/audio/camera filters, and delivery modes
already exist. Add a rule layer on top: time-of-day windows (e.g. only 7am–7pm), per-species
frequency limits (max 1/hr/species), weather-based rules, and custom message templates with
variables.

#### Video timeline & highlights 🎬
**Priority:** P2 | **Effort:** L | **Status:** 🔄 In progress

Automated highlight reels and time-based browsing. Shipped: video preview pipeline
(sprite/VTT + caching), expiring share links with watermark overlay + owner management, and a
day-bucket timeline strip with keyboard nav. Remaining:
- Fuller grouped-browsing timeline UI + advanced keyboard UX.
- Highlight scoring (confidence, rarity, activity) and clip stitching/preview thumbnails.

#### Analytics: insights panel + camera comparison 📊
**Priority:** P2 | **Effort:** M | **Status:** ☐ Not started

Charts (top visitors, daily histogram, seasonality, leaderboard trends, activity heatmap,
weather overlays) are shipped. Add: a confidence-distribution histogram, a camera-comparison
chart, and an insights panel (rarest sighting this week, best detection hour, weather correlation).

#### Advanced BirdNET-Go visualization 🎵
**Priority:** P2 | **Effort:** S | **Status:** 🔄 Mostly shipped; confidence fusion remains

Audio-visual correlation, buffering, camera↔sensor mapping, the recent-audio widget, spectrogram
visualization, authenticated clip playback, and the dedicated Audio History page are shipped.
Remaining: design and validate an explainable confidence-fusion score that combines visual and
audio evidence without overstating certainty.

#### Local LLM support (Ollama) 🏠
**Priority:** P2 | **Effort:** M | **Status:** ☐ Not started

Self-hosted LLMs via Ollama for privacy-conscious users: Ollama client, model selection UI,
vision-model support (LLaVA etc.), streaming responses, and clean fallback to cloud LLMs when
Ollama is unavailable.

#### Full DB backup/restore tool 💾
**Priority:** P2 | **Effort:** M | **Status:** ☐ Not started

CSV export (eBird format) is shipped. Add a first-class, safe full-database backup and restore
flow so users can snapshot and recover their detection history and config.

#### Home Assistant OS add-on 🏠
**Priority:** P3 | **Effort:** M | **Status:** ☐ Proposed ([#49](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues/49))

Wrap the monolithic image as an installable HA Supervisor add-on so HAOS users can deploy from
the add-on store without a docker-compose stack. A companion `addon-yawamf` repo would carry the
add-on manifest, a Dockerfile pulling the published image, an apparmor profile, and Ingress
config; `/data` + `/config` map to the add-on data volume so upgrades preserve data and run
migrations. The existing `custom_components/yawamf` integration keeps handling the in-HA
sensor/event surface. **Out of scope:** replacing docker-compose (both ship side-by-side) and
embedding YA-WAMF in HA core. **Risks:** Ingress path-prefix CSP/CORS under `nginx + backend`;
ARM64 depends on the RPi image being production-ready (§2); a separate repo means ongoing
maintenance.

#### App-store templates & discovery 📦
**Priority:** P2 | **Effort:** M | **Status:** 🔄 Unraid template shipped; broader distribution not started

Make YA-WAMF easy to find and install where self-hosting, NVR, and media-stack users already
look. Keep the monolithic Docker contract stable across every template: image tag, web port,
Frigate URL, `/config`, `/data`, model/cache persistence, health check, optional hardware
acceleration, update-channel guidance, and a first-run smoke test.

- **Unraid Community Applications follow-through** — the Docker template and setup guide are
  shipped (`unraid/yawamf.xml`, `docs/setup/unraid.md`). Keep them synced with image names,
  ports, volume ownership, health checks, provider-family tags, and Intel GPU/NPU plus NVIDIA CUDA
  host guidance. The template keeps provider choice in-app instead of pinning it through an
  authoritative environment override. Next, pursue the normal Community Applications discovery
  path so users do not need to paste the raw template URL.
- **TrueNAS custom-app docs, then catalog submission** — first document the low-friction
  TrueNAS Custom App path for the monolithic image so users can deploy before catalog acceptance.
  Then submit a community-train app to `truenas/apps` using the current Docker Compose catalog
  structure: `app.yaml`, `ix_values.yaml`, `questions.yaml`, `README.md`, a Jinja2
  `templates/docker-compose.yaml`, and `templates/test_values/basic-values.yaml`. The wizard
  should expose the web port, Frigate URL, storage paths, CPU/memory limits, optional
  `/dev/dri` / accelerator device settings, a portal link, and a health check against
  `/health`. Validate with the TrueNAS apps render/deploy CI before opening the PR, and open a
  draft PR early to catch catalog-review issues.
- **Container registry discoverability** — continue GHCR publishing and add Docker Hub publishing
  once release tags are stable, with matching descriptions, README snippets, labels, supported
  architectures, and copy-paste compose examples for `latest`, pinned release tags, and `dev`.
- **Additional self-hosting templates** — add a Portainer stack/app-template example and evaluate
  CasaOS/ZimaOS packaging after the TrueNAS path settles. Consider YunoHost only if install,
  upgrades, storage, and reverse-proxy behaviour can be made appliance-like enough to maintain.
- **Project directories and community launch points** — submit or announce YA-WAMF in discovery
  channels that fit the app: Awesome Selfhosted, selfh.st/apps, AlternativeTo, the Unraid and
  TrueNAS forums, and relevant communities such as r/selfhosted, r/unRAID, r/truenas, Frigate,
  Home Assistant, BirdNET-Go, and homelab spaces. Use a short positioning statement, screenshots,
  setup links, and honest hardware/support notes rather than generic promotion.

### 1.4 Performance & reliability targets — non-blocking unless promoted

These are high-value follow-ups. A measured regression can promote a specific item into the 3.0
exit criteria; the broad initiatives do not block the release by default.

#### Performance optimization 🚀
**Priority:** P1 | **Effort:** L | **Status:** 🔄 Foundations in progress

✅ Connection pooling, route/locale lazy loading, bounded frontend work, and provider-family runtime
images are delivered. The full compatibility image remains available, while additive CPU, Intel and
CUDA images isolate large hardware stacks and remove build-only tooling/layers. Image promotion is
gated by per-flavor startup checks and a shared-volume full → CPU → full integrity round trip.
Runtime hardware validation is now governed by the same per-flavor contract, including CUDA in the
full image even when OpenVINO CPU is also present. Evidence is scoped per model to the exact image
flavor, failed reruns invalidate stale passes, and activation uses only a recommendation that still
matches the current eligibility record.
Remaining: DB query optimization (indexes, optional result caching, cursor pagination), further
backend async hardening + a background task queue (ARQ/Celery), targeted virtual scrolling, and a
benchmark suite for regression testing.

#### Broader end-to-end coverage 🧪
**Priority:** P1 | **Effort:** M | **Status:** 🔄 Targeted coverage exists

Unit/integration tests, CI, coverage reporting, migration-safety checks, and startup smoke
checks are all in place. ARM64 image startup plus real model inference now run under QEMU before
mutable Raspberry Pi tags are promoted. The open work is expanding Playwright E2E coverage around
restart/recovery and GPU/provider fallback paths, plus a physical-Pi smoke/soak pass.

#### Crop-detector field benchmark 🐦
**Priority:** P1 | **Effort:** M | **Status:** 🔄 Production guard validated on Quark; broader owner-labelled promotion and replacement comparison remain

The evidence-only distant-subject threshold recovery is delivered, but a detector replacement is
not selected from one event or generic COCO AP. The production challenger now mirrors Frigate's
small-object advantage: it refines a same-frame tracked region with YOLOX, falls back from native
inference to four bounded overlapping tiles only on a miss, preserves full-frame evidence, and lets
the model crop replace Frigate only after a material downstream classifier gain. Frigate's final
clean best frame and snapshot-specific tracked-box crop are now protected completed-event baselines; bottom-centre
path geometry, end-event refresh, auditable fallback candidates, and non-duplicating temporal votes
are delivered. Build the remaining
manually labelled, visit-grouped Quark panel with near/distant birds and hard negatives; compare
Frigate, the optimized current YOLOX-Tiny path,
D-FINE-N, DEIMv2-N, RTMDet-Tiny, and PP-YOLOE+ S on downstream species correctness, crop recall/clipping,
false positives, and per-provider resource cost. D-FINE-N and DEIMv2-N have now failed the initial
varied-image localisation/negative screen: neither beat current YOLOX at a zero-field-false-positive
operating point, and both crashed inside the current Intel NPU compiler despite static batch-one
exports. They remain benchmark evidence, not runtime or release models. Promote only a reproducible
permissively licensed artifact that beats Frigate without weakening full-frame/fail-soft behaviour. See the
[candidate review and promotion gate](docs/reviews/2026-07-21-crop-detector-candidate-review.md).

The shared hardware sweep now includes both exact crop-detector artifacts, a species-diverse
round-robin image sample, deterministic hard negatives, isolated CPU/CUDA/OpenVINO compilation,
and CPU box/confidence agreement. The comparison fails closed on missing/duplicated rows and ignores
raw proposals below every production threshold. Validated crop providers activate at runtime with
CPU fallback. A private same-frame builder and initial 30-event/10-negative Quark panel now exist,
but most reference boxes and labels are still Frigate/automatic evidence rather than owner-labelled
ground truth. The reusable external-candidate probe, first D-FINE-N/DEIMv2-N CPU/Intel GPU/NPU
screens, schema-3 field manifest, and direct Frigate/model downstream win-tie-loss harness are
complete. The first optimized-path run used 24 guided, two sliced, and four fast-fallback positive
cases: the production guard promoted 7 same-identity crops with at least a two-point classifier gain
and retained Frigate for 23. The three owner-labelled cases produced one guarded improvement, two
ties, and no regression, while none of ten hard-negative regions produced a crop classification
above the active `0.40` floor.
That validates the fail-soft selection logic but is not enough owner truth to claim detector
superiority. Collecting more owner labels and comparing RTMDet-Tiny/PP-YOLOE+ S remain open.

#### High-availability setup 🏗️
**Priority:** P3 | **Effort:** M | **Status:** ☐ Not started

`/health` + Prometheus `/metrics` exist. Add example Nginx load-balancer config, session-less
multi-replica support, Grafana dashboard templates, and Kubernetes manifests.

#### Raspberry Pi hardware validation 🍓
**Priority:** P2 | **Effort:** S | **Status:** 🔄 Image ships; hardware validation remains

See [§2](#2-raspberry-pi-compatibility-best-effort) — the ARM64 image builds in CI; the open
work is real-device smoke/soak validation before declaring official support.

### 1.5 Technical debt — post-3.0 unless promoted

- **EventProcessor decomposition** (P2, M) — split `_handle_detection_save_and_notify` into
  smaller services (persistence, notification policy, media cache, auto-video trigger) to reduce
  coupling and improve testability.
- **BirdNET-Go audio backfill** (P2, M) — backfill BirdNET-Go audio detections into
  `audio_detections` so history regains audio context after a DB reset (needs a persistent
  BirdNET-Go source + importer + re-correlation).
- **Optional frontend log shipping** (P3, M) — optionally forward UI logs to a backend endpoint
  for remote debugging.
- **CSP tightening** (P3, M) — investigate moving from `unsafe-inline` to CSP nonces where feasible.

### 1.6 Engineering carry-overs — non-blocking

Small, incremental gold-standard follow-ups. They may land before `3.0`, but do not block it:

- **Frontend API contract adoption** — most SPA API modules now derive their types from the
  generated OpenAPI contract. Done: the email/iNaturalist integrations module, and the
  species module (search, eBird nearby/notable, seasonality, and the detections timeline all now
  carry backend `response_model`s and are consumed as generated types). Remaining, treated
  differently on purpose:
  - **`model_eval.ts` stays hand-written by design** — the model-eval `list_runs`/`get_run`
    endpoints return open-ended diagnostic JSON (the eval harness's `summary.json`, per-model
    metrics). A strict `response_model` would be brittle and could truncate diagnostic data, so
    `dict` is the correct contract; the module keeps a hand-written *view* type over it.
  - A few already-typed species endpoints (`stats`/`info`/`range`) still keep hand-written
    mirrors in `species.ts` — cosmetic, low priority.
- **Coverage ratchet** — raise the backend coverage floor as low-coverage modules gain focused tests.
- **Keep dated reviews current** as significant subsystems change.

### 1.7 Breaking changes & removals — required at 3.0

`3.0` is the version where deprecated paths are actually removed. These are already signalled
in-app and in docs; the release makes them final.

- **Monolith-only deployment.** The monolithic `nginx + backend` image becomes the *only*
  supported runtime shape. The legacy split `wamf-frontend` / `wamf-backend` deployment is
  removed from the default setup path and receives no further updates from `3.0`. Compose
  examples, CI, and reverse-proxy guidance assume the monolith by default.
  (Already flagged: [`docs/setup/migrate-split-to-monolith.md`](docs/setup/migrate-split-to-monolith.md).)
- **API-key auth removed.** Optional `X-API-Key` authentication is removed in favour of the
  password-based auth already available under Settings → Security. The deprecation notice is
  live today (`backend/app/auth.py`: *"API key support will be removed in v3.0"*); `3.0`
  deletes the code path.
- **Migration must be lossless.** Existing split-deployment installs must be able to move to
  the monolith with unchanged `/config` and `/data` volumes (DB, models, `config.json`), and
  the [split-to-monolith guide](docs/setup/migrate-split-to-monolith.md) stays the supported
  path through the transition.

**Acceptance:** `3.0` docs/compose/proxy guidance are monolith-first; the split path and
`X-API-Key` are gone from the recommended surface; a documented migration preserves all user
data and runs DB migrations cleanly.

---

## 2. Raspberry Pi compatibility (best-effort)

**Status:** CI-built and QEMU inference-smoked ARM64 image available; not yet hardware-validated. Full assessment:
[`docs/reviews/2026-07-21-raspberry-pi-assessment.md`](docs/reviews/2026-07-21-raspberry-pi-assessment.md).

Release builds publish a dedicated ARM64 monolith image
(`ghcr.io/jellman86/yawamf-monalithic-rpi`); the web stack, MQTT, SQLite, and Nginx run on ARM64
unmodified, and the inference layer degrades to CPU-only (no CUDA / Intel iGPU-NPU / VideoCore).

**Shipped:** ARM-safe dependency selection (CPU `onnxruntime` plus standalone LiteRT, no x86 GPU
setup), a revision-pinned/checksum-verified bundled MobileNet fallback, Pi-aware first-run model
selection and download, functional Compose pressure controls, the multi-arch build job, and an
ARM64 QEMU gate that proves startup, classifier load, labels, and one inference before mutable tags
are promoted. Pi setup docs and `.env.rpi.example` match the deployed variables.

**Remaining:** a real-hardware exit pass (cold start, migration against preserved `/config` and
`/data`, sustained inference, thermal throttling, storage endurance, camera/event throughput, and
UI responsiveness) before claiming official support. Start with
`CLASSIFIER_IMAGE_MAX_CONCURRENT=1` and an SSD over microSD; measured device results must replace
estimates before publishing performance claims.

---

## 3. Delivered

Condensed — see [`CHANGELOG.md`](CHANGELOG.md) and git history for detail. Everything below has
shipped.

**Classification & models:** multi-model support (TFLite/ONNX: MobileNetV2, ConvNeXt, EVA-02),
fast-path mode, manual reclassification with confidence override, canonical species-identity
normalization, blocked-species picker with reliable taxonomy matching, manual-tag common-name
resolution, the classifier inference-health refactor (`v2.11`, issue #33 resolved), the labeled
feeder + auto-fetch model-evaluation harnesses, and the **accurate bird-crop detector tier**
(optional YOLOX-Tiny with fast→original fallback, model-manager UI, and adapter/eval tests), plus
**automatic per-model crop policy** validated on Quark and synchronized between the runtime registry
and downloadable model sidecars. The classification pipeline now also separates Frigate object and
sublabel confidence, runs local inference before trusted fallback, recovers missed MQTT `new` events
from `update`, protects manual identity atomically, uses three-frame/60% deep-video consensus, and
compares full-frame and cropped video evidence without double-counting frames, persists the winning
input provenance, and surfaces provider failures for recovery instead of silently treating them as
empty predictions.

**Acceleration:** Intel iGPU (OpenVINO), **Intel NPU** (`intel_npu` provider, capability probe,
device picker, validated per-model), and NVIDIA CUDA — all with empirical per-model validation and
clean fallback chains. Full registry audits can probe undeclared host providers without making them
eligible, and reproducible release sidecars prevent older provider metadata from narrowing or
widening the current application contract. Crop-detector audits now use unique identities across a
round-robin clean species panel and hard negatives, fail on incomplete comparison coverage, and
test only proposals production could admit. The accurate YOLOX-Tiny tier is validated on Quark's
Intel CPU/GPU/NPU; the fast quantized SSD remains CPU-only.

**Media & detection:** full-visit recording clips, HQ event/bird-crop snapshots with conservative,
temporally independent multi-frame crop refinement for distant subjects, a protected Frigate final
best-frame baseline with correctly reconstructed bottom-centre path coordinates, recording-frame
classification fallback, media caching, and the video player with HTTP-Range seeking + expiring
watermarked share links. Playable partial recordings are retained instead of refetched forever,
corrupt media remains rejected, and HQ recovery has persistent bounded backoff across container
restarts. Manual temporal
reclassification follows the same best-available-media contract: complete cached recording →
decodable partial recording → cached event clip → Frigate event clip → snapshot fallback, with an
invalid cache entry unable to block the next usable source.

**Integrations:** Frigate NVR (MQTT + media proxy), BirdNET-Go audio correlation, multi-platform
notifications (Discord/Telegram/Pushover/Email + Notification Center), BirdWeather, eBird (sightings,
maps, CSV export), iNaturalist (taxonomy + owner-reviewed submissions + seasonality), LLM behavioural
analysis (Gemini/OpenAI/Claude) with conversation history, and the **Home Assistant proxy/sidebar
panel** (ingress-authenticated dashboard).

**UI & platform:** real-time SSE dashboard, dark mode, advanced search/filtering, statistics +
leaderboard analytics, species detail modals, PWA baseline, complete i18n (9+ languages), the
settings architecture refactor + per-tab routing, a dedicated Jobs workspace, favourites, the
Explorer audio-matches filter, route-level and locale-level lazy delivery with resilient retry,
compressed immutable frontend assets, the in-app channel-aware update prompt, and the Unraid
Docker template + setup guide.

**Backend & quality:** Alembic-only migrations, the repository pattern, opt-in anonymous telemetry
+ Cloudflare dashboard, backfill service, health checks + Prometheus metrics, weather enrichment,
password-based + optional API-key auth (timing-safe), connection pooling, global exception handling,
background-task visibility, a typed OpenAPI contract with generated SPA types, and the CI enforcement
suite (lint/format/coverage/OpenAPI-drift/type-freshness/migration-safety).

---

## Contributing

Everyday work happens on `dev`; release tags / `main` are handled separately. Every change clears
the [`CLAUDE.md`](CLAUDE.md) contract — safety, test-first, reversible migrations, clean UI, and the
Definition of Done — before it is committed. New roadmap work should land a dated design note under
[`docs/plans/`](docs/plans/) when it starts, and move to the [`CHANGELOG.md`](CHANGELOG.md) +
[Delivered](#3-delivered) when it ships.
