# CLAUDE.md — YA-WAMF Engineering Standards

This file is the contract for everyone working in this repository, human or AI
agent. Read it before writing code. These standards are not aspirational; they
are the bar a change must clear before it is committed. When a request conflicts
with a standard here, surface the conflict instead of silently breaking the
standard.

Sections 1–10 are the contract (the *how*). The **Reference** section below is
orientation (the *what* and *where*): architecture, components, schema, and
troubleshooting. The current honest assessment of where the project sits against
this bar — and the prioritised path to close the gaps — lives in
[`docs/reviews/2026-07-07-project-quality-and-gold-standard-review.md`](docs/reviews/2026-07-07-project-quality-and-gold-standard-review.md).

---

## 1. Safety & data integrity — the non-negotiable

YA-WAMF is a long-running daemon that ingests untrusted external events and keeps
a durable history users care about. The detection history and the user's
configuration are the assets we must never damage.

- **The detections database is user data. Never lose or corrupt it.** Schema
  changes go through reversible Alembic migrations (§3); a migration must never be
  destructive without an explicit, documented reason.
- **All external input is untrusted.** Frigate MQTT events, BirdNET-Go payloads,
  Frigate/media URLs, and API request parameters are attacker-influenced. Ingest is
  idempotent (the `detections.frigate_event` column is `UNIQUE` — the same event
  processed twice must not create a second row or mutate history unexpectedly).
  Media/event identifiers used in cache or proxy paths must be sanitised against
  path traversal. Species names rendered into notification markup must be escaped.
- **Deletes are soft or clearly destructive.** Prefer `is_hidden` soft-deletion;
  when a hard delete is offered, the UI and API must be honest that it is
  irreversible (§5).
- **Conservative defaults.** When in doubt, do nothing and report why. A dropped
  detection is recoverable on the next event; a corrupted history is not.
- **Secrets never leak.** API keys, tokens, and passwords are redacted as
  `"***REDACTED***"` in API responses, are never written to logs or telemetry, and
  are preserved (not overwritten with the redaction placeholder) on settings
  writes via `should_update_secret()`. Timing-safe comparison
  (`secrets.compare_digest`) is used for the API key in `backend/app/auth.py` and
  `backend/app/ratelimit.py`.

If you are unsure whether a change is safe, it is not safe yet. Add a test that
proves the safe behaviour.

## 2. Test-driven development

We work test-first.

- Write a failing test that describes the behaviour, then write the code that makes
  it pass, then refactor. Commit only with the suite green.
- **Pure logic gets pure unit tests.** Classification admission, canonical-species
  identity, config/env mapping, taxonomy normalisation, and other decision logic
  must be testable without a live database, network, MQTT broker, or ML model. Pass
  inputs in (parsed payloads, `now`) so tests are deterministic. See
  [`backend/tests/test_classification_admission.py`](backend/tests/test_classification_admission.py),
  [`backend/tests/test_canonical_species.py`](backend/tests/test_canonical_species.py),
  and [`backend/tests/test_config_env_mapping.py`](backend/tests/test_config_env_mapping.py).
- **A bug fix starts with a test that reproduces the bug**, then the fix.
- Tests own their fixtures (temp dirs, seeded rows) and clean up; never depend on a
  developer machine, a running Frigate/MQTT, or downloaded models.
- Mock external services (Frigate, MQTT, LLM, BirdNET-Go) at their boundary.
- Test names state the behaviour, e.g. `test_audio_species_leaderboard_counts_window_and_prev`.

The full suite (`pytest`, and `npm run check` + `npm test` for the frontend) must
pass before any commit. "It builds" is not "it works".

## 3. Database excellence

- **Alembic migrations only.** Schema is versioned under
  `backend/migrations/versions/`. There is no `create_all`/implicit-schema path in
  committed runtime code, and there must not be one.
- **Every schema change ships a migration in the same commit.** Never edit an
  already-released migration; add a new one.
- **Single head, reversible, idempotent.** There is exactly one Alembic head. Each
  migration has a working `downgrade`; `upgrade → downgrade → upgrade` is a no-op
  against an up-to-date database. CI enforces all three (see §9).
- **Constraints belong in the schema**: `UNIQUE` (e.g. `frigate_event`), indexes,
  required columns, enum handling. Do not rely on application code to enforce what
  the database can enforce.
- SQLite lives under `/data` in the container (`data/speciesid.db`). It is user
  data — migrations must be backwards-safe.
- All database access is async and goes through the **repository pattern**
  (`backend/app/repositories/`), never raw SQLAlchemy in routers. Read paths use
  pagination/limits.

Add a migration:

```bash
cd backend && source .venv/bin/activate
alembic revision --autogenerate -m "describe change"   # review the generated file
alembic upgrade head && alembic downgrade -1 && alembic upgrade head   # prove reversibility
```

## 4. Self-documenting code

- Names carry the meaning. A reader should understand intent without comments.
- Comments explain **why**, not **what**. The only *what* worth a comment is a
  non-obvious one.
- Keep functions small and single-purpose. Domain logic in `services/`, data access
  in `repositories/`, HTTP composition in `routers/`. Business rules that can be
  pure should be pure and directly tested (§2).
- **Async by default, no blocking I/O.** Use `async def` for all I/O; never
  `open()`, `requests`, or synchronous DB calls — use `aiofiles`, `httpx`, and async
  SQLAlchemy.
- **Type hints everywhere**; Pydantic models for request/response DTOs. Every endpoint
  declares a `response_model` so the OpenAPI contract carries a real shape (the generated SPA
  types depend on it); use `Depends` for DB/auth/settings so handlers stay testable.
- **Structured logging**: `structlog.get_logger()` with context
  (`log.info("event", event_id=id, score=0.9)`), never bare `print`, never secrets.
- **TypeScript is strict.** `strict: true`, and `svelte-check` is clean (zero errors/warnings)
  before commit. **No `any` in application code** — prefer `unknown` at untrusted boundaries and
  narrow; if `any` is truly unavoidable, comment why. Avoid non-null assertions (`!`); give
  exported functions explicit return types. SPA types come from the generated OpenAPI contract
  (`apps/ui/src/lib/api/generated/`), not hand-written DTOs.
- **Svelte 5 reactivity is disciplined.** Reach for `$derived` before `$effect`. `$effect` is an
  escape hatch for syncing with systems *outside* Svelte (third-party libs, canvas, manual DOM) —
  never to sync one piece of state to another, and never to set state that `$derived` could
  compute. Mark reactive only what drives the view; use `$state.raw` for large immutable API
  responses.
- No dead code, no commented-out blocks, no `TODO` without a linked issue.

The full researched standard — Python/FastAPI, TypeScript, and Svelte 5, with authoritative
sources — is [`docs/standards/code-quality.md`](docs/standards/code-quality.md).

## 5. Clean, honest UI

- The UI is **operational, not marketing**. Dense, calm, and honest about state.
- A first-time user should understand what a screen does and what a click will do,
  without a manual. Label actions by their effect. Show *why* something is disabled,
  empty, or skipped.
- **The shared UI kit in [`apps/ui/src/app.css`](apps/ui/src/app.css) is the source
  of truth for controls.** Use `btn` + `btn-primary`/`btn-secondary`/`btn-ghost`,
  `input-base`, `select-base`, `tab-button`, and `card-base` rather than hand-rolled
  Tailwind, so controls stay consistent across themes. (A bare `btn-primary` without
  the base `btn` renders unstyled — the correct form is `class="btn btn-primary …"`.)
- **Guided flows share one shape.** Every test/diagnostic flow (AI model, Frigate/MQTT,
  notifications, integrations) uses the shared `DiagnosticDialog` — a staged checklist with
  honest auto-progress and a portalled full-screen overlay — and the first-run wizard shares its
  visual language. Don't hand-roll a modal for a test. The full standard is
  [`docs/standards/diagnostics-and-dialogs.md`](docs/standards/diagnostics-and-dialogs.md).
- Never imply a destructive action is reversible when it isn't. The UI must reflect
  the safety model (§1) truthfully.
- **Svelte 5 runes** (`$state`, `$derived`, `$effect`) and modern events
  (`onclick={…}`, not `on:click`). TypeScript everywhere; `npm run check` is clean
  (zero errors, zero warnings) before commit.
- Show loading, empty, and error states explicitly. Empty states tell the user what
  to do next. This is **visibility of system status** — the first usability heuristic: every
  action gets timely feedback (loading/progress/saved/skipped/stale).
- **Usability follows Nielsen's 10 heuristics** as the baseline: prevent errors rather than only
  reporting them, favour recognition over recall, keep the default simple with progressive
  disclosure (basic vs. advanced), and write plain-language errors that state the cause and the
  next step — not error codes.
- **Accessibility floor is WCAG 2.2 Level AA.** Everything is keyboard-operable with visible
  focus; colour contrast meets AA and **meaning is never signalled by colour alone**; controls
  use semantic HTML first (ARIA only to fill gaps) with labelled inputs and associated error
  messaging; motion respects `prefers-reduced-motion`.
- **Visual craft follows Refactoring UI.** Build hierarchy from size, weight, *and* colour (not
  size alone); design grayscale-first; keep spacing/type/colour on the constrained Tailwind
  scale (no arbitrary values); be generous with whitespace.
- **Media/artwork is a recognition aid, not decoration.** Snapshots and spectrograms
  are proxied so no token reaches the browser, must degrade silently to a
  placeholder, must never imply state, and must never shift layout (fixed aspect,
  lazy-loaded).
- User-facing strings go through i18n (`svelte-i18n`); new keys land in
  `apps/ui/src/lib/i18n/locales/en.json` (use `{ default: '…' }` fallbacks).

The full researched standard — the 10 heuristics, WCAG 2.2 AA checklist, and Refactoring UI
craft rules, with authoritative sources — is [`docs/standards/ui-ux.md`](docs/standards/ui-ux.md).

## 6. Definition of done

A change is done when **all** of these hold:

1. `pytest` is fully green, and new behaviour has new tests (§2).
2. `npm run check` is clean and `npm test` passes if the frontend changed (§5).
3. `ruff check .` and `ruff format .` are clean (Python style).
4. Schema changes have a reversible migration, a single Alembic head, and re-running
   them is a no-op (§3).
5. The safety/data-integrity model (§1) is intact or strengthened — never weakened.
6. `CHANGELOG.md` (Unreleased section) records the change.
7. Documentation is updated when behaviour, settings, API, or UI labels change
   (`docs/`, `README.md`, and `docs/api.md` for endpoints).
8. Code is self-documenting and matches surrounding style (§4).

## 7. Commands & local environment

Backend (Python 3.12, from `backend/`):

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000   # dev server + OpenAPI at /docs
pytest                                                     # full suite
pytest tests/test_audio_api.py -v                          # one file
ruff check . && ruff format .                              # lint + format
alembic upgrade head                                       # apply migrations
```

Frontend (from `apps/ui/`):

```bash
npm install
npm run dev        # dev server; proxy target is set in vite.config.ts
npm run check      # svelte-check: zero errors, zero warnings
npm test           # vitest unit/layout tests
npm run build      # production build
```

The dev proxy target in `vite.config.ts` points at the container service host; set
it to your local backend when running the two directly.

## 8. Project layout & dependency direction

```
backend/app/routers/        HTTP composition: FastAPI endpoints, request/response DTOs.
backend/app/services/       Domain + orchestration: MQTT, classifier, taxonomy, audio, AI, notifications.
backend/app/repositories/   Data access: async SQLAlchemy behind a repository API.
backend/app/models/         Pydantic models.
backend/migrations/         Alembic versioned schema.
backend/tests/              pytest (unit + API via TestClient).
apps/ui/src/lib/pages/      Svelte 5 pages.
apps/ui/src/lib/components/ Reusable components.
apps/ui/src/lib/api/        Typed API client (the only place fetch happens).
docs/                       Product, setup, integrations, API, reviews.
.github/workflows/          CI (see §9).
```

Dependency direction: `routers → services → repositories → SQLite`. Keep business
rules out of routers and pure where possible. On the frontend, all API calls go
through `apps/ui/src/lib/api/`, never inline `fetch`.

## 9. CI is the enforcement point

CI is where the Definition of Done is enforced. Keep CI and the local commands in
§7 in lock-step; if you change how the app is built or tested locally, update the
workflow in the same commit. CI is allowed to be stricter than a local run, never
looser.

- [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — **backend**: Alembic
  migration smoke (`upgrade → downgrade → upgrade`), migration path matrix
  ([`backend/scripts/ci_migration_path_check.py`](backend/scripts/ci_migration_path_check.py)),
  single-Alembic-head check, and `pytest`. **frontend**: `npm ci` → `npm run check`
  → `npm test` → `npm run build`. **telemetry worker**: dependency check.
- [`.github/workflows/codeql.yml`](.github/workflows/codeql.yml) — CodeQL scanning
  for Python and TypeScript.
- [`.github/workflows/docs-quality.yml`](.github/workflows/docs-quality.yml) — runs
  [`backend/scripts/docs_consistency_check.py`](backend/scripts/docs_consistency_check.py):
  local doc links resolve, documented endpoints in `docs/api.md` map to real routes,
  and stale compose/nav terms are rejected.
- [`.github/dependabot.yml`](.github/dependabot.yml) — dependency updates for pip,
  npm, Docker, and Actions.

**Anything in the Definition of Done that can be machine-checked should be a CI
gate.** Ruff lint, Ruff format, backend coverage, OpenAPI artifact freshness, and
frontend OpenAPI type freshness are all CI gates. Do not treat a missing or future
gate as permission to skip the local Definition of Done command.

## 10. Workflow & commit rules

- **Everyday work happens on `dev`.** Release tags / `main` are handled separately.
- **Write GitHub Releases for the person updating their feeder, not for the commit
  history.** Follow [`docs/development/releasing.md`](docs/development/releasing.md)
  and start from [`.github/RELEASE_NOTES_TEMPLATE.md`](.github/RELEASE_NOTES_TEMPLATE.md).
- **Git commit rules (unchanged, and strict):**
  - **Never** add `Co-Authored-By:`, `Co-authored-by:`, or any AI attribution
    trailer to commit messages.
  - **Never** reference Claude, Gemini, or any AI tool in commit messages, PR
    descriptions, or issue comments.
  - Commit messages should read as if written by the project owner.

---

# Reference

Orientation only. Behaviour is defined by code and tests (§2); when this section
disagrees with the code, the code wins — fix the doc.

## Project overview

YA-WAMF (Yet Another WhosAtMyFeeder) is a bird classification system that
integrates with Frigate NVR to identify birds visiting feeders using machine
learning. It receives MQTT events from Frigate, classifies species with local ML
models (TFLite/ONNX), correlates with audio detections from BirdNET-Go, and serves
a real-time web dashboard with notifications.

**Tech stack:** Python 3.12 + FastAPI + SQLite + Alembic (backend); Svelte 5 +
TypeScript + Tailwind + Vite (frontend); ONNX Runtime / TensorFlow Lite (ML);
MQTT (aiomqtt) for ingest, SSE for the frontend; Docker Compose deployment.

## Architecture

### Data flow

```
Frigate (MQTT) → MQTTService → EventProcessor → ClassifierService → DetectionRepository → SQLite
                                     ↓                                      ↓
                              FrigateClient (snapshot)              Broadcaster (SSE)
                              WeatherService                               ↓
                              AudioService (BirdNET)                  Frontend (realtime)
                              TaxonomyService
                              NotificationService
```

### Key components

**Backend services** (`backend/app/services/`):
- `mqtt_service.py` — subscribes to the `frigate/events` MQTT topic
- `event_processor.py` — orchestrates the detection pipeline
- `classifier_service.py` — ML inference engine (ONNX/TFLite load + predict)
- `frigate_client.py` — fetches snapshots and clips from the Frigate API
- `audio/audio_service.py` — correlates visual detections with the BirdNET-Go buffer
- `taxonomy/taxonomy_service.py` — iNaturalist scientific ↔ common name mapping
- `ai_service.py` — LLM integration (Gemini/OpenAI) for behavioural analysis
- `broadcaster.py` — Server-Sent Events for real-time frontend updates
- `notification_service.py` — Discord, Telegram, Pushover notifications
- `auto_video_classifier_service.py` — background video-frame analysis
- `model_manager.py` — model download and management
- `telemetry_service.py` — anonymous, opt-in usage metrics

**Backend routers** (`backend/app/routers/`): `events`, `species`, `settings`,
`proxy` (Frigate media proxy with HTTP Range), `stream` (SSE), `classifier`, `ai`,
`audio`, `backfill`, `stats`, `models`.

**Frontend pages** (`apps/ui/src/lib/pages/`): `Dashboard`, `Events`, `Species`,
`AudioHistory`, `Settings`, and others. **Components**
(`apps/ui/src/lib/components/`): `DetectionCard`, `VideoPlayer`,
`SpeciesDetailModal`, `RecentAudio`, `Header`, and more.

### Database schema

**Primary table `detections`** — all bird detections with classification scores,
Frigate event IDs, camera names, weather, and audio correlation.
- `frigate_event` is `UNIQUE` (idempotent ingest); `is_hidden` for soft deletion.
- `audio_confirmed`, `audio_species` for BirdNET-Go correlation.
- `scientific_name`, `common_name`, `taxa_id` for taxonomy enrichment.
- Video fields: `video_analysis_done`, `video_top_species`, `video_avg_score`.

**`audio_detections`** — persisted BirdNET-Go detections (species, scientific name,
confidence, timestamp, sensor, raw payload); indexed on `timestamp` and
`scientific_name`.

**`taxonomy_cache`** — caches iNaturalist lookups to reduce external calls.

**Migrations:** Alembic under `backend/migrations/versions/` (§3).

### Configuration system

Priority (highest to lowest): environment variables (section-prefixed, e.g.
`FRIGATE__FRIGATE_URL`) → `config/config.json` (persisted runtime config) → code
defaults in `backend/app/config.py`. Settings are read/written through Pydantic
Settings; the `/api/settings` endpoint redacts secrets in GET and preserves stored
secrets on PUT via `should_update_secret()`.

### Authentication & access

Optional API-key authentication via the `YA_WAMF_API_KEY` environment variable.
When set, all API requests require the `X-API-Key` header, SSE streams authenticate
via query parameter, and the frontend shows a login screen. Public/guest access and
privacy controls live under **Settings → Security**. Comparison is timing-safe
(`secrets.compare_digest`).

## External integrations

- **Frigate NVR** — MQTT events on `frigate/events`; HTTP API for media.
- **BirdNET-Go** — audio detections; persisted history + spectrogram/clip proxy.
- **iNaturalist** — taxonomy normalisation (cached in `taxonomy_cache`).
- **Weather APIs** — local weather enrichment.
- **LLMs** — Gemini or OpenAI for behavioural analysis.
- **BirdWeather / eBird / Home Assistant** — optional reporting and integration
  (`custom_components/yawamf/`).

## Troubleshooting

**No detections appearing:**
- Check the MQTT connection in the backend logs.
- Verify Frigate is publishing to `frigate/events` and the camera is in the
  configured list (Settings).
- Confirm the model is loaded: `GET /api/classifier/status`.

**Frontend not loading:**
- Verify the backend is healthy (`/api/classifier/status`); check CORS in
  `backend/app/main.py`; inspect the browser console.

**Database errors:**
- Apply migrations (`alembic upgrade head`); check permissions on
  `data/speciesid.db`; look for schema mismatches.

**Classification failures:**
- Verify model files exist under `data/models/`; confirm the format matches the
  classifier type; review classifier logs for shape/type mismatches.
