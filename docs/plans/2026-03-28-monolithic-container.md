# Monolithic Container Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace YA-WAMF’s split `yawamf-backend` + `yawamf-frontend` deployment with one published `yawamf` application container that runs internal `nginx + uvicorn`, while preserving `/config`, `/data`, reverse-proxy behavior, GPU/device support, and upgrade/rollback safety.

**Architecture:** Build a new top-level multi-stage Docker image that compiles the Svelte UI, installs backend runtime dependencies, and launches `uvicorn` behind internal `nginx` using `tini` plus a small entrypoint/healthcheck layer. Then convert compose, CI publishing, and deployment docs to the one-service model, keeping rollback safe until the split images are explicitly deprecated.

**Tech Stack:** Docker multi-stage builds, nginx, FastAPI/uvicorn, shell entrypoint scripts, Docker Compose, GitHub Actions, existing YA-WAMF docs/tests.

---

### Task 1: Add a monolith smoke harness first

**Files:**
- Create: `tests/e2e/monolith_smoke.sh`
- Create: `tests/e2e/monolith_compose_config.sh`

**Step 1: Write the failing smoke script**

Create `tests/e2e/monolith_smoke.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IMAGE_TAG="yawamf-monolith:test"
CID="yawamf-monolith-smoke"
TMP_DIR="$(mktemp -d)"
trap 'docker rm -f "$CID" >/dev/null 2>&1 || true; rm -rf "$TMP_DIR"' EXIT

mkdir -p "$TMP_DIR/config" "$TMP_DIR/data"

docker build -t "$IMAGE_TAG" "$ROOT"
docker run -d --name "$CID" \
  -p 19852:80 \
  -v "$TMP_DIR/config:/config" \
  -v "$TMP_DIR/data:/data" \
  "$IMAGE_TAG"

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:19852/health >/dev/null; then
    break
  fi
  sleep 2
done

curl -fsS http://127.0.0.1:19852/ >/dev/null
curl -fsS http://127.0.0.1:19852/health >/dev/null
curl -fsS http://127.0.0.1:19852/api/version >/dev/null
```

Create `tests/e2e/monolith_compose_config.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

for file in docker-compose.yml docker-compose.prod.yml docker-compose.dev.yml; do
  services="$(docker compose -f "$ROOT/$file" config --services)"
  echo "$services"
  test "$services" = "yawamf"
done
```

**Step 2: Run the smoke script to verify it fails**

Run:

```bash
bash tests/e2e/monolith_smoke.sh
```

Expected: fail immediately because there is no repo-root `Dockerfile` yet.

**Step 3: Run the compose config script to verify it fails**

Run:

```bash
bash tests/e2e/monolith_compose_config.sh
```

Expected: fail because current compose files still expose `yawamf-backend` and `yawamf-frontend`.

**Step 4: Commit the failing harness**

```bash
git add tests/e2e/monolith_smoke.sh tests/e2e/monolith_compose_config.sh
git commit -m "test(container): add monolith migration smoke harness"
```

**Step 5: Keep this harness as the migration gate**

Do not delete these scripts later. They become the acceptance gate for Tasks 2-4.

---

### Task 2: Build the new monolithic runtime image

**Files:**
- Create: `Dockerfile`
- Create: `docker/monolith/entrypoint.sh`
- Create: `docker/monolith/healthcheck.sh`
- Create: `docker/monolith/nginx.conf`
- Modify: `apps/ui/nginx.conf` only if you want to keep it as the source of truth; otherwise retire it after the new config is live

**Step 1: Write the root multi-stage Dockerfile**

Create `Dockerfile` with three stages:

```dockerfile
FROM node:20 AS ui-builder
WORKDIR /ui
COPY apps/ui/package.json apps/ui/package-lock.json ./
RUN npm install --legacy-peer-deps
COPY apps/ui/ .
RUN npm run build

FROM python:3.12-slim AS backend-builder
WORKDIR /app
COPY backend/requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx curl tini ca-certificates gpg sqlite3 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=backend-builder /wheels /wheels
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir /wheels/*
COPY --from=ui-builder /ui/dist /usr/share/nginx/html
COPY backend /app
COPY docker/monolith/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/monolith/entrypoint.sh /usr/local/bin/yawamf-entrypoint.sh
COPY docker/monolith/healthcheck.sh /usr/local/bin/yawamf-healthcheck.sh
ENTRYPOINT ["tini", "--", "/usr/local/bin/yawamf-entrypoint.sh"]
```

Preserve the backend’s Intel runtime package logic from `backend/Dockerfile`; do not simplify that away during the merge.

**Step 2: Write the entrypoint**

Create `docker/monolith/entrypoint.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

uvicorn app.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

nginx -g 'daemon off;' &
nginx_pid=$!

shutdown() {
  kill -TERM "$backend_pid" "$nginx_pid" 2>/dev/null || true
  wait "$backend_pid" 2>/dev/null || true
  wait "$nginx_pid" 2>/dev/null || true
}

trap shutdown TERM INT

wait -n "$backend_pid" "$nginx_pid"
status=$?
shutdown
exit "$status"
```

**Step 3: Write the healthcheck and nginx config**

Create `docker/monolith/healthcheck.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
curl -fsS http://127.0.0.1/health >/dev/null
curl -fsS http://127.0.0.1:8000/ready >/dev/null
```

Create `docker/monolith/nginx.conf` by copying the current `apps/ui/nginx.conf` behavior and changing the upstreams to loopback:

```nginx
location /api/sse {
    proxy_pass http://127.0.0.1:8000/api/sse;
    ...
}

location ~ ^/api/frigate/.+/clip\.mp4$ {
    proxy_pass http://127.0.0.1:8000;
    ...
}

location /api/ {
    proxy_pass http://127.0.0.1:8000/api/;
    ...
}

location /health {
    proxy_pass http://127.0.0.1:8000/health;
    ...
}
```

Keep the existing SSE buffering, clip buffering, CSP, and security headers unless a separate change explicitly revises them.

**Step 4: Run the smoke script and make it pass**

Run:

```bash
bash tests/e2e/monolith_smoke.sh
```

Expected: pass against the new root image and confirm `/`, `/health`, and `/api/version` work through the single exposed port.

**Step 5: Commit**

```bash
git add Dockerfile docker/monolith/entrypoint.sh docker/monolith/healthcheck.sh docker/monolith/nginx.conf tests/e2e/monolith_smoke.sh
git commit -m "feat(container): add monolithic runtime image"
```

---

### Task 3: Convert compose files to the one-service model

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`
- Modify: `docker-compose.dev.yml`
- Optionally create: `.env.example` updates if service/image names are referenced there

**Step 1: Replace split services with one `yawamf` service**

Convert each compose file to:

```yaml
services:
  yawamf:
    image: ghcr.io/jellman86/wamf:latest   # use :dev in docker-compose.dev.yml
    container_name: yawamf
    restart: unless-stopped
    user: "${PUID:-1000}:${PGID:-1000}"
    networks:
      - yawamf_network
    volumes:
      - ./config:/config
      - ./data:/data
    ports:
      - "9852:80"
    environment:
      - TZ=${TZ:-UTC}
      - PUID=${PUID:-1000}
      - PGID=${PGID:-1000}
      - FRIGATE__FRIGATE_URL=${FRIGATE_URL:-http://frigate:5000}
      - FRIGATE__FRIGATE_AUTH_TOKEN=${FRIGATE_AUTH_TOKEN:-}
      - FRIGATE__MQTT_SERVER=${MQTT_SERVER:-mqtt}
      - FRIGATE__MQTT_PORT=${MQTT_PORT:-1883}
      - FRIGATE__MQTT_AUTH=${MQTT_AUTH:-false}
      - FRIGATE__MQTT_USERNAME=${MQTT_USERNAME:-}
      - FRIGATE__MQTT_PASSWORD=${MQTT_PASSWORD:-}
      - SYSTEM__DEBUG_UI_ENABLED=${DEBUG_UI_ENABLED:-false}
```

Move any existing backend GPU/device examples directly onto `yawamf`.

**Step 2: Replace health checks**

Use the new health script or an equivalent app-port health check:

```yaml
healthcheck:
  test: ["CMD", "/usr/local/bin/yawamf-healthcheck.sh"]
  interval: 30s
  timeout: 10s
  retries: 3
```

**Step 3: Remove the default direct backend port**

Do not expose `8946:8000` in the default compose files. If you decide to preserve it for advanced users, add it only as a commented-out opt-in note with explicit warning text.

**Step 4: Run the compose config harness**

Run:

```bash
bash tests/e2e/monolith_compose_config.sh
docker compose -f docker-compose.yml config
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.dev.yml config
```

Expected: all three compose files resolve cleanly and expose only the `yawamf` service.

**Step 5: Commit**

```bash
git add docker-compose.yml docker-compose.prod.yml docker-compose.dev.yml tests/e2e/monolith_compose_config.sh
git commit -m "refactor(compose): collapse app to one service"
```

---

### Task 4: Switch CI publishing to one canonical image

**Files:**
- Modify: `.github/workflows/build-and-push.yml`

**Step 1: Collapse change detection and image outputs**

Remove the backend/frontend publish split and replace it with one monolith output, for example:

```yaml
outputs:
  app: ${{ steps.compute.outputs.app }}
...
run: |
  echo "app=true" >> "$GITHUB_OUTPUT"
```

**Step 2: Build and publish one runtime image**

Replace the separate `wamf-backend` / `wamf-frontend` build-push jobs with one build using the repo-root `Dockerfile`, tagging:

```text
ghcr.io/${OWNER_LC}/wamf:${IMAGE_TAG}
ghcr.io/${OWNER_LC}/wamf:${GITHUB_SHA}
ghcr.io/${OWNER_LC}/wamf:latest   # main/tags path
ghcr.io/${OWNER_LC}/wamf:dev      # dev path
```

Use the same branch/tag semantics that the current workflow already applies.

**Step 3: Add a CI monolith smoke step**

Add a workflow step that runs:

```bash
bash tests/e2e/monolith_smoke.sh
bash tests/e2e/monolith_compose_config.sh
```

If CI runner limitations require adapting published ports or temp directories, change the scripts once, not the workflow repeatedly.

**Step 4: Remove split-image publish references**

Delete or retire steps that publish:

- `ghcr.io/.../wamf-backend:*`
- `ghcr.io/.../wamf-frontend:*`

If you want a temporary compatibility window, add a clearly-commented short-lived transition section and put a removal TODO in the same commit.

**Step 5: Commit**

```bash
git add .github/workflows/build-and-push.yml
git commit -m "ci(container): publish monolithic app image"
```

---

### Task 5: Update docs, migration guidance, and operator examples

**Files:**
- Modify: `README.md`
- Modify: `MIGRATION.md`
- Modify: `docs/setup/getting-started.md`
- Modify: `docs/setup/docker-stack.md`
- Modify: `docs/setup/reverse-proxy.md`
- Modify: `docs/features/authentication.md`
- Modify: `docs/api.md`
- Modify: `CHANGELOG.md`

**Step 1: Replace the deployment story everywhere**

Update all install/upgrade examples to use:

- one image
- one service
- one app upstream

Examples that currently refer to `yawamf-backend` and `yawamf-frontend` must be rewritten to `yawamf`.

**Step 2: Update reverse-proxy docs**

Replace dual-upstream examples with single-upstream examples, for example:

```nginx
set $app_upstream yawamf;

location /api/sse {
    proxy_pass http://$app_upstream:80;
    ...
}

location /api/ {
    proxy_pass http://$app_upstream:80;
    ...
}

location / {
    proxy_pass http://$app_upstream:80;
    ...
}
```

Keep the SSE and clip-specific guidance. The point is to simplify upstream topology, not erase the proxy requirements.

**Step 3: Write the user migration section**

Expand `MIGRATION.md` with a dedicated section for this release:

```md
## Upgrading to vX.Y.Z (Monolithic Container)

1. Replace your compose file with the new one-service version.
2. Pull `ghcr.io/jellman86/wamf:<tag>`.
3. Recreate the stack.
4. Keep the same `config/` and `data/` mounts.

Rollback:
1. Restore the previous compose file.
2. Pull the previous split-image tags.
3. Recreate the stack against the same volumes.
```

**Step 4: Update changelog**

Add a release note describing:

- one-container packaging
- no volume/data migration required
- reverse-proxy simplification
- split image deprecation/removal status

**Step 5: Commit**

```bash
git add README.md MIGRATION.md docs/setup/getting-started.md docs/setup/docker-stack.md docs/setup/reverse-proxy.md docs/features/authentication.md docs/api.md CHANGELOG.md
git commit -m "docs(container): document monolithic deployment"
```

---

### Task 6: Run the full migration verification set

**Files:**
- No new files unless verification reveals a missing helper script

**Step 1: Re-run the monolith smoke checks**

```bash
bash tests/e2e/monolith_smoke.sh
bash tests/e2e/monolith_compose_config.sh
```

Expected: both pass.

**Step 2: Run backend and frontend sanity checks**

Run:

```bash
/config/workspace/YA-WAMF/backend/venv/bin/python -m pytest -q --collect-only
npm --prefix apps/ui run check
```

Expected:

- backend tests still collect cleanly
- frontend typecheck passes

If the worktree has no frontend dependencies, run `npm --prefix apps/ui install --legacy-peer-deps` once in the worktree before rerunning `npm --prefix apps/ui run check`.

**Step 3: Do a real compose bring-up**

Run:

```bash
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:9852/health
curl -fsS http://127.0.0.1:9852/api/version
```

Expected: the single `yawamf` service becomes healthy and answers through the app port only.

**Step 4: Verify operator-critical behaviors**

Manually verify or script-check:

- UI root loads
- login/auth status works
- `/api/sse` connects
- clip playback route still works
- guest/public mode still works if enabled
- OpenVINO/CUDA diagnostics still report through the single service

Record any environment-specific exceptions in the PR/commit notes; do not silently skip them.

**Step 5: Commit the final verification-ready state**

```bash
git status --short
git add .
git commit -m "feat(container): migrate app to monolithic deployment"
```

Only do this commit after all checks above are green and the docs are aligned.
