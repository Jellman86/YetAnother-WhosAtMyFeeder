# Monolith Transition Status

Date: 2026-03-28
Branch state when written: `dev`

## Current State

- The monolithic container work has been merged into `dev`.
- The implementation branch `plan/monolithic-container` has been deleted locally and on origin.
- `dev` now contains:
  - root monolith `Dockerfile`
  - `docker-compose.monolith.yml`
  - monolith nginx/entrypoint/healthcheck runtime files under `docker/monolith/`
  - monolith CI publish path in `.github/workflows/build-and-push.yml`
  - monolith smoke tests under `tests/e2e/`
- Split deployment is still present and intentionally not removed yet:
  - `docker-compose.yml`
  - `docker-compose.dev.yml`
  - `docker-compose.prod.yml`
  - `wamf-backend` and `wamf-frontend` image publish flow

## Live Deployment State

- The live `system-compose-files` YA-WAMF stack already points to:
  - `ghcr.io/jellman86/yawamf-monalithic:dev`
- The live reverse proxy was updated to use:
  - `yawamf-monalithic:8080`
- Live targeted checks already confirmed:
  - UI root path works
  - API works
  - SSE works
  - static assets load
  - canonical `/clip.mp4` serves persisted full-visit clips when available
  - Intel GPU/OpenVINO is working in the live monolith

## Important Safeguards Already Added

- README now contains a deployment transition warning on `dev`.
- A migration guide exists at `docs/setup/migrate-split-to-monolith.md`.
- Reverse-proxy docs include monolith transition guidance.
- Roadmap now includes a `v3.0` item for:
  - monolith-only deployment
  - deprecating the split deployment
  - full UI refresh
- `.dockerignore` was hardened after merge so local monolith builds do not send large local state into Docker context.

## What Still Remains

- Watch the `dev` CI after the merge and confirm the latest:
  - `Docs Quality`
  - `Build and Push Docker Images`
  runs settle green.
- Decide when to move the monolith path from `dev` to `main`.
- Keep split deployment support through the transition window unless/until the `v3.0` cutover plan is intentionally executed.
- Before `v3.0`, update stable/docs/release messaging again when the monolith becomes the primary path on `main`.

## Current Recommendation

- Treat the monolith as the forward path on `dev`.
- Do not remove split deployment support yet.
- Finish remaining roadmap work on `dev`, then prepare the `3.0` release with:
  - monolith-first deployment
  - formal split deprecation/removal from the primary path
  - full UI refresh
