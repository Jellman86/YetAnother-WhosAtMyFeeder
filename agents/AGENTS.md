# Repository Guidelines

## Project Structure & Module Organization

- `backend/`: FastAPI service (Python 3.12), DB/migrations (`migrations/` via Alembic), unit tests in `backend/tests/`.
- `apps/ui/`: Svelte 5 + Vite frontend (built assets under `apps/ui/dist/`).
- `apps/telemetry-worker/`: Cloudflare Worker (Wrangler + D1 schema in `schema.sql`).
- `custom_components/yawamf/`: Home Assistant integration.
- `docs/`: user/deployment docs (start at `docs/index.md`).
- `tests/e2e/`: pytest-driven Playwright smoke/e2e checks (connects to a remote browser via `PLAYWRIGHT_WS`).

## Build, Test, and Development Commands

```bash
# Deployment
# This repo is typically deployed via Portainer Stacks (no local compose up/build).
# In Portainer: Stacks -> (your stack) -> "Pull and redeploy" after updating tags/refs.
# Compose files live at repo root: docker-compose.yml / docker-compose.prod.yml / docker-compose.dev.yml.

# Backend (local)
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (local)
cd apps/ui
npm ci
npm run dev
npm run build
npm run check   # svelte-check + TypeScript

# Telemetry worker (optional)
cd apps/telemetry-worker
npm ci
npm run dev
```

## Coding Style & Naming Conventions

- Python: 4-space indentation, type hints where practical. Run `ruff check .` and `ruff format .` from `backend/` before PRs.
- TypeScript/Svelte: keep changes minimal and follow nearby formatting (the repo contains mixed indentation); prefer `PascalCase` for components and `camelCase` for functions/variables.
- Naming: Python modules/functions `snake_case`; tests `test_*.py`.

## Notification UX Policy (Toast vs Notification Center)

- Use `toastStore` for short-lived feedback from a direct user action in the current view (for example save/test/copy result).
- Use `notificationCenter` for lifecycle events, background jobs, SSE/system events, and progress that users may need to revisit.
- Do not mirror high-frequency progress into toasts.
- For long-running jobs, use one stable/upserted notification id per job (or one aggregate id for batch mode) instead of appending many items.
- If a terminal toast is needed for a background job, emit at most one deduped toast per `{job_id, terminal_state}`.

## Testing Guidelines

- Backend unit tests: `cd backend && pytest` (async tests use `pytest-asyncio`).
- E2E checks: `python -m pytest tests/e2e -s` (defaults to `ws://playwright-service:3000/`; override with `PLAYWRIGHT_WS=...`).
- Never install Playwright browser binaries in this environment (for example via `playwright install`), as it can break the terminal/session setup.
- For UI/E2E testing, always use the existing remote Playwright service workflow documented in `PLAYWRIGHT_TESTING_GUIDE.md`.
- Mandatory: before running any Playwright test or browser automation, read and follow `agents/PLAYWRIGHT_TESTING_GUIDE.md` for command pattern, WS endpoint, target URL, and wait strategy.

## Commit & Pull Request Guidelines

- Commits follow a Conventional-Commits style in history: `feat(scope): ...`, `fix(ui): ...`, `docs: ...`, `chore(release): ...`, `security: ...`.
- PRs: include a clear description, link issues, and add screenshots for UI changes. Keep unrelated reformatting out of the diff.
- Always update [`CHANGELOG.md`](/config/workspace/YA-WAMF/CHANGELOG.md) for user-facing features, fixes, breaking changes, and operationally meaningful behavior changes shipped to `dev` or `main`.
- If you touch GitHub Actions workflows, keep workflow runs human-readable by using an explicit `run-name:` instead of relying on GitHub's default push `displayTitle`, which is inconsistent.
- Do not leave CI workflows with only a generic workflow title when a per-run name can identify the branch/commit/change more clearly.

## Security & Configuration Tips

- Start from `.env.example`; never commit real tokens/credentials. For vulnerabilities, follow `SECURITY.md`.
