# YA-WAMF project quality and gold-standard review

Date: 2026-07-07
Scope: Repository-level engineering review based on local source, tests, CI
configuration, and documentation. This is not a formal security audit or a
performance benchmark.

This review is the companion to the engineering contract in
[`CLAUDE.md`](../../CLAUDE.md). The contract defines the bar; this document is an
honest assessment of where the project currently sits against it and the
prioritised path to close the gaps.

## External standards used as reference points

- Diátaxis documentation framework: https://diataxis.fr/
- Google developer documentation style guide: https://developers.google.com/style/highlights
- OpenAPI Specification: https://spec.openapis.org/oas/latest.html
- OWASP Application Security Verification Standard: https://owasp.org/www-project-application-security-verification-standard/
- OWASP API Security Top 10: https://owasp.org/www-project-api-security/
- Twelve-Factor App methodology: https://12factor.net/
- Keep a Changelog: https://keepachangelog.com/

## Executive summary

YA-WAMF is a mature, well-tested self-hosted application, already above the normal
quality bar for homelab tooling and — on database and CI discipline — ahead of many
peer projects. The core pipeline (MQTT ingest → ML classification → SQLite → SSE
UI) is backed by a broad test suite, a hardened migration workflow, and supply-chain
automation.

The gap to "gold standard" is therefore **not** a testing or CI rescue. It is
mostly about *codifying and enforcing* the quality the project already largely
practises, and closing a small number of specific, low-risk gaps:

- Codify the standards as a clearing-bar contract (done: [`CLAUDE.md`](../../CLAUDE.md)).
- Enforce Python lint and formatting in CI, matching the Definition of Done
  (done).
- Introduce a coverage floor so testing depth cannot silently regress (done in PR
  CI at the current 60% floor).
- Rewrite [`CONTRIBUTING.md`](../../CONTRIBUTING.md) into a real bar and fix its
  internal contradictions (done).
- Keep documentation and this review current as behaviour changes.

## Current strengths

### 1. Database and migration discipline is excellent

Schema is versioned with Alembic and there is no implicit `create_all` path in
committed runtime code. CI ([`.github/workflows/ci.yml`](../../.github/workflows/ci.yml))
enforces three properties most projects never check:

- a migration smoke test that runs `upgrade → downgrade → upgrade`,
- a migration path matrix
  ([`backend/scripts/ci_migration_path_check.py`](../../backend/scripts/ci_migration_path_check.py)),
- a single-Alembic-head gate.

This makes reversibility and idempotency machine-enforced, not aspirational.
Gold-standard target: keep this posture; any schema change ships its migration in
the same commit, and destructive migrations require an explicit documented reason.

### 2. Idempotent ingest and a truthful safety model

The `detections.frigate_event` column is `UNIQUE`, so reprocessing the same Frigate
event cannot duplicate history. Deletion is soft (`is_hidden`). Secrets are redacted
in settings responses and preserved on write via `should_update_secret()`, and the
API key is compared in constant time in [`backend/app/auth.py`](../../backend/app/auth.py).
These are the right instincts for a daemon that ingests untrusted external input and
stores data users care about.

Gold-standard target: keep §1 of the contract as the first architectural invariant;
reject or redesign any change that weakens it.

### 3. Test coverage is broad and risk-aligned

The suite spans 114 backend test files and 79 frontend test/layout files, covering
classification admission, canonical-species identity, config/env mapping, taxonomy,
the classifier worker/supervisor, auth/security, and API contracts. Pure decision
logic is tested without a live database, network, or model — the pattern the
contract mandates in §2.

Gold-standard target: protect this with a coverage floor (below), and keep pushing
pure business rules out of orchestration code so they stay directly testable.

### 4. Supply-chain and docs automation already exist

The project already has what many "gold-standard" reviews recommend as future work:

- CodeQL scanning for Python and TypeScript
  ([`.github/workflows/codeql.yml`](../../.github/workflows/codeql.yml)),
- Dependabot for pip, npm, Docker, and Actions
  ([`.github/dependabot.yml`](../../.github/dependabot.yml)),
- a documentation-consistency gate
  ([`.github/workflows/docs-quality.yml`](../../.github/workflows/docs-quality.yml))
  that runs
  [`backend/scripts/docs_consistency_check.py`](../../backend/scripts/docs_consistency_check.py)
  to verify doc links resolve, that documented endpoints in [`../api.md`](../api.md)
  map to real routes, and that stale compose/navigation terms are rejected.

### 5. Frontend quality is gated

CI runs `svelte-check`, unit/layout tests, and a production build. TypeScript is
used throughout and the UI is built on a shared control kit (`apps/ui/src/app.css`).
Gold-standard target: keep `npm run check` at zero warnings and always compose
controls from the shared kit (§5) so the UI stays consistent across themes.

## Main gaps to gold standard

### 1. Standards were not codified as a contract

Until this pass, `CLAUDE.md` was a strong *reference* (architecture, commands,
troubleshooting) but not a *contract*: it stated no non-negotiable safety/data
invariants, no test-first mandate, no Definition of Done, and did not frame CI as
the enforcement point. That made "gold standard" a matter of memory rather than a
bar a change must clear.

Status: **addressed** — [`CLAUDE.md`](../../CLAUDE.md) now leads with a numbered
§1–10 contract. This review is its companion.

### 2. Python lint/format is not fully enforced in CI

[`CONTRIBUTING.md`](../../CONTRIBUTING.md) tells contributors to run `ruff check .`
and `ruff format .`, and the Definition of Done (§6) requires it, but nothing gates
it. Style and simple correctness lint can therefore drift.

Status: **addressed** — [`ci.yml`](../../.github/workflows/ci.yml) now runs
`ruff check backend custom_components/yawamf` and
`ruff format --check backend custom_components/yawamf`, backed by the repo-level
[`pyproject.toml`](../../pyproject.toml) Ruff configuration and an accepted
formatting baseline.

Gold-standard target: keep both lint and format gates green. Acceptance: a lint
or format violation fails CI.

### 3. Backend coverage floor is now enforced in PR CI

Coverage tooling exists and PR CI now runs the backend suite under `coverage` with
a 60% floor, so a large PR cannot quietly lower measured backend test depth below
the current minimum.

Gold-standard target: ratchet the floor upward from the current 60% baseline as
low-coverage modules gain focused tests. Keep hardware/model-dependent
paths excluded and clearly labelled rather than faked.

### 4. `CONTRIBUTING.md` now points at the contract

Status: **addressed** — [`CONTRIBUTING.md`](../../CONTRIBUTING.md) now points at
[`CLAUDE.md`](../../CLAUDE.md) as the engineering bar, targets everyday work at
`dev`, removes the Vitest hedge, and states the concrete PR expectations.

Gold-standard target: keep contributor guidance in lock-step with the Definition
of Done and CI commands.

### 5. API contract is generated; frontend adoption has started

FastAPI serves OpenAPI at `/docs`, and PR CI checks the committed
[`backend/openapi.json`](../../backend/openapi.json) artifact is up to date. The
frontend now also has a generated TypeScript contract at
[`apps/ui/src/lib/api/generated/openapi.ts`](../../apps/ui/src/lib/api/generated/openapi.ts),
with a CI freshness check. The first consumer is the auth API module, which types
`/api/auth/status` and `/api/auth/login` from the generated path contract. The
stats and events API modules now also source high-value response shapes from the
same generated contract, and settings writes now type their request payload from
the generated `/api/settings` contract. Classifier/model manager DTOs now also
use generated model metadata, installed-model, download-progress, reclassify, and
bulk manual-tag response types. Backfill request/result/job DTOs now come from
the generated contract as well. Maintenance and media-cache endpoints now expose
explicit backend response models and the frontend maintenance API client consumes
those generated response types. Classifier label/default-download and model
download/activate action endpoints now also publish explicit response models and
feed the generated frontend client types. Taxonomy sync and timezone-repair
endpoints now do the same. Version, Frigate connection/capability, and
reverse-geocode endpoints now publish explicit response models and feed the
frontend system/geocoding client types from the generated contract. Diagnostics
history, workspace, bundle, and clear endpoints now publish explicit response
models and feed the frontend diagnostics client types from the generated contract.
Audio recent, history, summary, species-leaderboard, context, and sources endpoints
now publish explicit response models and feed the frontend audio client types from
the generated contract. Visual species leaderboard and leaderboard/statistics graph
endpoints now feed the frontend leaderboard client from generated response and
request types. Media video-share, recording-clip fetch, and snapshot candidate,
status, generate, and apply flows now feed the frontend media client from generated
response and request types.

Gold-standard target: continue migrating high-value frontend API modules to the
generated path contract so "the docs match the routes" becomes "the client matches
the contract" across the whole SPA.

### 6. Documentation history and governance are thin

There is now a documentation standard page plus `AGENTS.md` and
`CODE_OF_CONDUCT.md`. The remaining work is to keep dated reviews current as the
project changes and to grow the docs-quality gate around the standard.

Gold-standard target: keep dated reviews here as the project evolves and grow the
docs-quality gate around the documentation standard.

## Gold-standard implementation plan

This plan is intentionally sequenced from lowest-risk, highest-leverage first. It is
**not** part of this documentation-only change; it is the tracked follow-up.

### Phase 1: Enforce what the contract already requires
- Add a `ruff` config and CI lint/format gates (done).
- Add coverage measurement and a floor to the backend CI job (done at 60%; ratchet
  upward as coverage improves).
- Rewrite `CONTRIBUTING.md` against the contract and fix its contradictions (done).

Acceptance: CI fails on lint violations and coverage regressions;
`CONTRIBUTING.md` no longer contradicts the workflow.

### Phase 2: Strengthen the API contract
- Emit a build-time OpenAPI artifact (done).
- Generate frontend TypeScript types from the artifact and check freshness in CI
  (done).
- Migrate remaining high-value frontend API modules to generated path-level
  response/request types.

Acceptance: an endpoint/type mismatch is caught in CI, not in the browser. Initial
auth, stats, events, classifier/model, classifier/model actions, backfill,
maintenance/cache, taxonomy/timezone repair, system/geocoding, diagnostics, and
audio, leaderboard/statistics graphs, media/share/snapshot flows, and
settings-write coverage is in place; broader SPA adoption remains.

### Phase 3: Mature documentation governance
- Add a documentation standard and the missing governance files (done).
- Keep this review current; add engineering notes as significant subsystems change.

Acceptance: new settings/API/UI changes update docs in the same PR; the docs map
links to the current review.

## Gold-standard scorecard

| Area | Current state | Target |
|---|---|---|
| Safety & data integrity | Strong (idempotent ingest, soft delete, secret redaction, constant-time auth) | Preserve as the first invariant |
| Core domain design | Good; pure decision logic is tested | Keep pushing business rules to pure, tested functions |
| Migrations | Excellent; reversibility + single head enforced in CI | Preserve; migration-per-commit |
| Testing | Broad unit + API coverage; 60% backend coverage floor in PR CI | Ratchet the floor upward; keep hardware paths labelled |
| CI & supply chain | Strong (migration matrix, CodeQL, Dependabot, docs gate, Ruff lint/format, coverage floor) | Keep gates green |
| Security boundary | Reasonable (optional API key, redaction, guest controls) | Keep OWASP-informed endpoint review as surfaces grow |
| UI honesty | Operational and consistent (shared control kit) | Zero-warning `check`; explicit empty/error states everywhere |
| Docs | Good and gated for drift; documentation standard exists | Continue generated API contract adoption |
| Workflow & governance | Trunk-based on `dev`; strict commit rules; CONTRIBUTING aligned; governance files present | Keep contributor guidance current |

## Suggested agent prompt

Use this when pointing an agent at the project:

```text
Read CLAUDE.md and docs/reviews/2026-07-07-project-quality-and-gold-standard-review.md
before changing code.

Improve YA-WAMF toward gold-standard quality without weakening the safety and
data-integrity model in CLAUDE.md §1. Work test-first, keep domain rules pure and
tested, ship a reversible Alembic migration in the same commit as any schema change,
and keep the UI honest and built from the shared control kit. Update CHANGELOG.md and
docs when behaviour, settings, API, or UI labels change.

Before finishing: run pytest; run ruff check . and ruff format .; run npm run check
and npm test if the UI changed; run python3 backend/scripts/docs_consistency_check.py
for docs changes; and git diff --check.
```

## Bottom line

YA-WAMF is already a high-quality, well-tested project with unusually strong
database and CI discipline. The standards contract, Ruff lint/format gates,
coverage floor, OpenAPI artifact, generated frontend contract, and governance
files are now in place. The remaining gold-standard work is incremental: continue
migrating frontend API clients to generated path types, ratchet coverage as
low-coverage modules gain focused tests, and keep dated reviews and user-facing
docs current as behaviour changes.
