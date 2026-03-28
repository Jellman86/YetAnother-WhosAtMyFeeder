# Monolithic Container Migration Design

**Date:** 2026-03-28
**Branch:** `plan/monolithic-container`
**Status:** Approved design

---

## Goal

Move YA-WAMF from the current two-container deployment model (`yawamf-backend` + `yawamf-frontend`) to one published application container that runs both the UI and API internally, while preserving current behavior, persistent storage, reverse-proxy compatibility, and GPU/device support.

The first rollout must not disturb the existing `main` and `dev` deployment lines. The monolithic build should therefore publish under a separate image name: `ghcr.io/jellman86/yawamf-monalithic`.

The target is not “a different app server shape.” The target is “the same YA-WAMF behavior, packaged as one application service.”

---

## Current State

Today YA-WAMF ships:

- a backend image defined by [backend/Dockerfile](../../backend/Dockerfile)
- a frontend image defined by [apps/ui/Dockerfile](../../apps/ui/Dockerfile)
- nginx proxy rules in [apps/ui/nginx.conf](../../apps/ui/nginx.conf)
- compose files with separate `yawamf-backend` and `yawamf-frontend` services in:
  - [docker-compose.yml](../../docker-compose.yml)
  - [docker-compose.prod.yml](../../docker-compose.prod.yml)
  - [docker-compose.dev.yml](../../docker-compose.dev.yml)

This creates unnecessary user complexity:

- two service names to deploy and troubleshoot
- split health checks
- split image publishing
- split reverse-proxy upstream configuration
- more surface area for Portainer and compose drift

At the same time, the frontend nginx already contains app-specific runtime behavior that should not be thrown away casually:

- SPA routing
- `/api/*` proxying
- SSE proxy buffering rules
- clip streaming buffering/timeouts
- security headers

That makes “one container, still using nginx internally” the correct end state.

---

## Target Architecture

### Container model

End state:

- one application image
- one application service: `yawamf`
- one exposed app port
- one internal container runtime containing:
  - `nginx` on port `80`
  - `uvicorn` on `127.0.0.1:8000`

Traffic flow:

1. User or reverse proxy connects to `yawamf:80`
2. nginx serves built frontend assets directly
3. nginx proxies:
   - `/api/*`
   - `/api/sse`
   - `/api/frigate/*`
   - `/health`
   to the internal backend at `127.0.0.1:8000`

### Why this architecture

This preserves the deployed HTTP semantics that already work today while eliminating the operational cost of a split runtime. It avoids pushing static-file serving, CSP management, SSE tuning, and clip proxy buffering into FastAPI just to remove a process that is already useful.

---

## Image Strategy

### Build shape

The new image should be a top-level multi-stage build:

1. `ui-builder`
   - based on Node
   - builds the Svelte app
   - outputs static assets from `apps/ui/dist`

2. `backend-builder`
   - based on Python
   - builds Python wheels or installs backend dependencies
   - preserves existing backend system/runtime requirements

3. final runtime image
   - contains Python runtime and backend dependencies
   - contains nginx
   - contains built UI assets under nginx root
   - contains backend source under `/app`
   - contains a small init/entrypoint layer to launch and supervise both internal processes

### Runtime process model

Use `tini` plus a purpose-built entrypoint script.

The entrypoint must:

- launch `uvicorn` on `127.0.0.1:8000`
- launch `nginx` in foreground-compatible mode
- forward shutdown signals correctly
- fail the container if either critical child process exits unexpectedly
- emit readable logs from both processes to container stdout/stderr

This is lighter than adding a full supervisor while still meeting the reliability bar needed for production and Portainer users.

---

## nginx Configuration Changes

The existing nginx config should be preserved conceptually but adjusted for same-container upstreaming.

Required changes:

- replace `proxy_pass http://yawamf-backend:8000/...` with loopback upstreams such as `http://127.0.0.1:8000/...`
- keep current SSE buffering and timeout settings
- keep clip buffering/timeouts
- keep existing CSP/security headers unless a separate security review changes them
- keep `/health` proxied to backend so external health checks continue to reflect application readiness, not just static asset serving

The frontend nginx remains part of the application, not a generic sidecar.

---

## Compose And Deployment Shape

### New service model

All compose files should converge on one service:

- `yawamf`

During the canary phase, that service should use the separate monolithic image:

- `ghcr.io/jellman86/yawamf-monalithic:<tag>`

This keeps the deployment shape simple without risking existing split-image users.

The service keeps the current persistent mounts:

- `./config:/config`
- `./data:/data`

It also keeps the external Docker network attachment so it can still reach:

- Frigate
- MQTT
- optional BirdNET-Go and related services

### GPU/device passthrough

The current backend-only GPU and `/dev/dri` guidance moves directly onto the single `yawamf` service.

That includes:

- Intel `/dev/dri` mounts and `group_add`
- NVIDIA `gpus: all` guidance
- any related environment variables needed for CUDA/OpenVINO

Nothing about GPU support should depend on the old service split.

### External interface simplification

The migration should simplify the external deployment shape to one service/one app port. The optional localhost-only backend port should be removed from default deployment docs and compose examples.

If direct backend access is still useful for advanced operators, it can exist only as an opt-in debug override, not as part of the default deployment story.

---

## CI And Image Publishing

The GitHub Actions pipeline in [.github/workflows/build-and-push.yml](../../.github/workflows/build-and-push.yml) should add a separate published monolithic runtime artifact.

Target outcome for phase one:

- one separate monolithic canary image published for `main`, `dev`, SHA, and release tags:
  - `ghcr.io/jellman86/yawamf-monalithic:<tag>`
- current split images remain untouched:
  - `ghcr.io/jellman86/wamf-backend:*`
  - `ghcr.io/jellman86/wamf-frontend:*`

Target outcome for a later promotion phase:

- decide whether `yawamf-monalithic` becomes the canonical app image
- only then deprecate and remove the split frontend/backend image lines

Recommended rollout:

1. add monolith build path first
2. publish only `yawamf-monalithic:*`
3. prove it in CI and local compose
4. switch canary docs and test stacks to `yawamf-monalithic`
5. only after confidence, decide whether to promote and deprecate split images

This keeps rollback easy while avoiding accidental disruption of current users.

---

## Development Workflow

The migration must cover both production and local/dev usage.

### Development target

`docker-compose.dev.yml` should also move to the one-service model.

That does not necessarily mean “single-stage dev image.” It means the developer-facing compose entry point should still be one service. If dev-specific bind mounts or hot-reload shortcuts are needed, they should remain inside that single-service shape rather than preserving the two-container topology.

### Practical dev stance

For the first migration pass, correctness is more important than hot-reload cleverness. It is acceptable if dev compose rebuilds the monolith image rather than providing perfect split-service frontend hot reload, as long as:

- local development remains usable
- docs say what changed
- the path to run the app locally is unambiguous

If a better monolith-friendly dev loop is needed later, it can be iterated separately.

---

## Migration Plan For Existing Users

The migration must be safe for existing YA-WAMF installs.

### Compatibility guarantees

- `/config` remains unchanged
- `/data` remains unchanged
- database path remains unchanged
- model storage remains unchanged
- media cache remains unchanged
- app URL path structure remains unchanged

### User migration expectation

An existing two-container install should be upgradable by:

1. replacing the compose file
2. pulling the new image
3. recreating the stack

No data migration should be required for this packaging change.

### Rollback

Rollback must remain possible by restoring the previous compose file and old split images against the same volumes.

That rollback story is important enough to be explicitly documented.

---

## Risks And Mitigations

### Risk 1: one internal process dies while the other remains up

If `uvicorn` dies but nginx stays up, the container can appear superficially alive while the app is broken.

Mitigation:

- entrypoint must terminate the container if either child exits unexpectedly
- health checks should probe the full app path through nginx and/or a backend loopback probe script

### Risk 2: nginx still points at old service names

The current config proxies to `yawamf-backend:8000`.

Mitigation:

- replace all internal upstreams with loopback
- add regression checks for `/`, `/health`, `/api/*`, `/api/sse`, and clip playback under the monolith

### Risk 3: GPU/runtime behavior regresses

The backend currently owns GPU/device guidance in a dedicated service.

Mitigation:

- preserve backend runtime packages in the monolith image
- move device configuration directly onto the new `yawamf` service
- verify OpenVINO and CUDA diagnostics through the monolith

### Risk 4: documentation drift causes bad installs

This migration touches a lot of docs:

- [README.md](../../README.md)
- [docs/setup/getting-started.md](../setup/getting-started.md)
- [docs/setup/docker-stack.md](../setup/docker-stack.md)
- [docs/setup/reverse-proxy.md](../setup/reverse-proxy.md)
- [docs/features/authentication.md](../features/authentication.md)
- [docs/api.md](../api.md)

Mitigation:

- update docs as part of the same migration branch
- treat docs as release-blocking, not cleanup

---

## Verification Criteria

The migration is only complete when all of the following are verified:

- the app root loads through the single service
- `/api/*` works through nginx-to-backend loopback proxying
- `/api/sse` remains stable
- clip playback and clip downloads still work
- guest/public mode still works
- health checks reflect real application readiness
- Intel OpenVINO guidance still works on the single service
- NVIDIA guidance still works on the single service
- existing `/config` and `/data` volumes survive upgrade unchanged
- existing reverse-proxy users can point to one upstream instead of two without losing features

---

## Recommendation

Proceed with a staged migration to a single published monolithic image using internal `nginx + uvicorn`, but ship it first as a separate canary line, `ghcr.io/jellman86/yawamf-monalithic`, delivered on a fresh branch/worktree and rolled out first in CI/compose/docs, then to users, with rollback preserved throughout.
