# Contributing to YA-WAMF

Thanks for helping improve YA-WAMF.

The engineering bar for this repository is defined in [`CLAUDE.md`](CLAUDE.md).
Read it before opening a pull request. In short: protect user data, work
test-first, keep migrations reversible, avoid blocking I/O in async code, and
leave the relevant test and lint commands green.

## Development Setup

### Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd apps/ui
npm install
npm run dev
```

The Vite development proxy is configured in `apps/ui/vite.config.ts`. Adjust it
locally if your backend is not reachable at the default development target.

## Required Checks

Use the [shared regression gate](docs/development/testing.md), which defines the complete
backend, frontend, telemetry and browser checks. From the repository root with the backend
virtual environment active:

```bash
python -m ruff check .
python -m ruff format --check .
python backend/scripts/run_regression_gate.py
npm --prefix apps/ui run check
npm --prefix apps/ui run lint:dead
npm --prefix apps/ui test
npm --prefix apps/ui run build
npm --prefix apps/telemetry-worker test
python backend/scripts/docs_consistency_check.py
```

For documentation, follow the [documentation standard](docs/documentation-standard.md),
read changed pages top to bottom, check links and commands against their implementation,
and visually inspect every changed screenshot. Keep examples free of credentials and
private location data. Capture screenshots from current components or a matching build.

If you change schema, add an Alembic migration in the same commit and prove the
migration can upgrade, downgrade, and upgrade again.

## Branches and Pull Requests

Start from current `dev` and create a short-lived branch for one reviewable
behaviour change or tightly related maintenance slice. Open the pull request
into `dev`; release pull requests alone target `main`.

Use the repository pull request template to:

- describe the useful outcome and exact included/excluded scope;
- record focused and full checks with their real results;
- include tests for new or changed behaviour;
- add one [`changelog.d/`](changelog.d/README.md) fragment for implemented user/operator behavior changes instead of editing `CHANGELOG.md` directly; documentation-only maintenance does not need a new behavior entry;
- update docs when settings, APIs, integrations, or user-visible behaviour change;
- identify data-integrity, migration, security, or operational risk and recovery;
- keep required checks green and resolve blocking review conversations.

A pull request is delivery evidence, not a substitute for tests or a place to
accumulate unrelated roadmap work.

## UI Notification Rules

- Toasts (`toastStore`) are for short-lived feedback from a direct user action in
  the current view.
- Notifications (`notificationCenter`) are for persistent background or system
  events and progress users may revisit.
- Do not send high-frequency progress updates to toasts.
- For long-running jobs, update one stable notification id (`upsert`) instead of
  creating many cards.
- If a completion/error toast is shown for a background job, emit only one
  deduped terminal toast per job/state.

## Reporting Bugs

Bugs are tracked as GitHub issues. Please include:

- a clear title and description,
- steps to reproduce,
- backend logs (`docker compose -f docker-compose.monolith.yml logs yawamf`, or
  `docker compose logs yawamf-backend` for the legacy split deployment),
- browser console errors for UI issues,
- a fresh support bundle from **Settings → Health** when requested, reviewed for private details before sharing. Include the running build and what happened around the failure; a healthy later capture cannot prove an earlier incident did not occur.

## Security Issues

Follow the [Security Policy](SECURITY.md) for responsible disclosure and
supported versions.
