# Agent Overview (Start Here)

This is the single entrypoint for AI agents working on YA-WAMF.

## Critical Rules
- Never build containers locally.
- Always push changes to `dev` (CI builds dev images from `dev`).
- Release images are built from `v*` tags only (tag `vX.Y.Z` on `main`).
- Update `CHANGELOG.md` for user-facing features, fixes, and breaking changes.
- Keep GitHub Actions workflow runs human-readable with explicit `run-name:` values when touching workflow files; do not rely on GitHub's inconsistent default push titles.

## Environment (devEnvSJP)
- Primary workspace container: `code-server-sjp`
- Playwright service: `playwright-service` (ws://playwright-service:3000/)
- Supporting services: mailpit-service, spamassassin, redis-service, adminer-service
- Full details: `DEV_ENVIRONMENT.md`

## Tooling Available
- GitHub CLI: `gh` (installed in the devEnvSJP Dockerfile)
- Docker CLI + Compose + Buildx (docker socket mounted)
- Node.js 22.x, Python 3 + venv/pip, PowerShell
- Playwright (via remote browser container)

## Standard Workflow
1. Edit code.
2. Commit locally.
3. Push to `dev`.
4. Verify deployment via logs or version hash.
5. Update `CHANGELOG.md` with shipped user-facing and operationally meaningful changes.
6. When ready to release, tag `main` with `vX.Y.Z` and push the tag to publish release images.

## References
- `AGENT_TOOLS.md` (tooling procedures)
- `GITHUB_API_WORKFLOW.md` (safe GitHub issue/comment API workflow and formatting)
- `PLAYWRIGHT_TESTING_GUIDE.md` (UI testing)
- `DEV_ENVIRONMENT.md` (container/tooling inventory)
- `ARCHIVED/` (historical notes)
