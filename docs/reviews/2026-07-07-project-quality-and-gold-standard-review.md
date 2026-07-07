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
- Enforce Python lint/format (`ruff`) in CI, matching the Definition of Done.
- Introduce a coverage floor so testing depth cannot silently regress.
- Rewrite [`CONTRIBUTING.md`](../../CONTRIBUTING.md) into a real bar and fix its
  internal contradictions.
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

### 2. Python lint/format is not enforced in CI

[`CONTRIBUTING.md`](../../CONTRIBUTING.md) tells contributors to run `ruff check .`
and `ruff format .`, and the Definition of Done (§6) requires it, but nothing gates
it. Style and simple correctness lint can therefore drift.

Gold-standard target: add a `ruff` job (or a step in the backend job) to
[`ci.yml`](../../.github/workflows/ci.yml) running `ruff check .` and
`ruff format --check .`, and commit a `ruff` configuration (e.g. `pyproject.toml`
or `ruff.toml`) so local and CI runs agree. Acceptance: a lint or format violation
fails CI.

### 3. There is no coverage floor

Coverage tooling exists (`pytest --cov`) but no minimum is enforced, so a large PR
could quietly lower tested depth without failing CI.

Gold-standard target: measure coverage in CI and fail below an agreed threshold
(start at the current level and ratchet up). Keep hardware/model-dependent paths
excluded and clearly labelled rather than faked.

### 4. `CONTRIBUTING.md` is loose and internally contradictory

It currently says the guidelines are "mostly guidelines, not rules", tells
contributors to `npm run test` "(Assuming vitest is configured)" when it is, and
says to "create your branch from `main`" while the actual workflow is trunk-based on
`dev`.

Gold-standard target: rewrite `CONTRIBUTING.md` to point at the `CLAUDE.md`
contract as the bar, fix the branch guidance to `dev`, remove the "assuming"
hedge, and state the Definition of Done as the merge requirement.

### 5. API contract is documented but not generated

FastAPI serves OpenAPI at `/docs`, and the docs-quality gate checks that documented
endpoints in [`../api.md`](../api.md) exist as routes — a good drift guard. But the
`api.md` reference is still hand-maintained and the SPA maintains API types by hand.

Gold-standard target: publish a build-time OpenAPI artifact, and consider
generating (or contract-testing) the frontend's TypeScript API types against it.
This turns "the docs match the routes" into "the client matches the contract".

### 6. Documentation history and governance are thin

There is no `docs/reviews/` history before this document, no documentation-standard
page, and no `AGENTS.md`/`CODE_OF_CONDUCT.md`. The docs themselves are good and
task-oriented; the gap is in the meta-layer that keeps them that way.

Gold-standard target: keep dated reviews here as the project evolves; add a short
documentation standard (audience, Diátaxis structure, safety-claim rules,
screenshot rules) that the docs-quality gate can grow into; add the missing
governance files.

## Gold-standard implementation plan

This plan is intentionally sequenced from lowest-risk, highest-leverage first. It is
**not** part of this documentation-only change; it is the tracked follow-up.

### Phase 1: Enforce what the contract already requires
- Add a `ruff` config and a CI lint/format gate (gap 2).
- Add coverage measurement and a floor to the backend CI job (gap 3).
- Rewrite `CONTRIBUTING.md` against the contract and fix its contradictions (gap 4).

Acceptance: CI fails on lint/format violations and on coverage regressions;
`CONTRIBUTING.md` no longer contradicts the workflow.

### Phase 2: Strengthen the API contract
- Emit a build-time OpenAPI artifact.
- Generate or contract-test the SPA's API types against it (gap 5).

Acceptance: an endpoint/type mismatch is caught in CI, not in the browser.

### Phase 3: Mature documentation governance
- Add a documentation standard and the missing governance files (gap 6).
- Keep this review current; add engineering notes as significant subsystems change.

Acceptance: new settings/API/UI changes update docs in the same PR; the docs map
links to the current review.

## Gold-standard scorecard

| Area | Current state | Target |
|---|---|---|
| Safety & data integrity | Strong (idempotent ingest, soft delete, secret redaction, constant-time auth) | Preserve as the first invariant |
| Core domain design | Good; pure decision logic is tested | Keep pushing business rules to pure, tested functions |
| Migrations | Excellent; reversibility + single head enforced in CI | Preserve; migration-per-commit |
| Testing | Broad unit + API coverage | Add a coverage floor; keep hardware paths labelled |
| CI & supply chain | Strong (migration matrix, CodeQL, Dependabot, docs gate) | Add `ruff` + coverage gates |
| Security boundary | Reasonable (optional API key, redaction, guest controls) | Keep OWASP-informed endpoint review as surfaces grow |
| UI honesty | Operational and consistent (shared control kit) | Zero-warning `check`; explicit empty/error states everywhere |
| Docs | Good and gated for drift | Add documentation standard + generated API contract |
| Workflow & governance | Trunk-based on `dev`; strict commit rules | Fix `CONTRIBUTING.md`; add missing governance files |

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
database and CI discipline. Reaching gold standard is not a rewrite and not a
testing rescue — it is codifying the bar (done here), enforcing the two Definition
of Done items CI does not yet gate (`ruff` and coverage), tightening contributor
guidance, and firming up the API contract and documentation governance. Done in that
order, YA-WAMF sits comfortably in the top tier of self-hosted tooling.
