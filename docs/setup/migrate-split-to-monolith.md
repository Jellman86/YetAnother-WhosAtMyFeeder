# Split-to-Monolith Migration

This guide is for existing YA-WAMF installs that currently run the legacy two-container layout:

- `wamf-backend`
- `wamf-frontend`

YA-WAMF is moving toward a single-container deployment model for `v3.0`. During the `v2.x` transition window, the split deployment still works, but new migration/testing effort is focused on the monolithic container path.

## What Changes

The monolithic deployment keeps the same YA-WAMF application behavior, volumes, and integrations, but simplifies runtime structure:

- one container instead of separate frontend/backend containers
- one app port instead of split frontend/backend ports
- one reverse-proxy upstream instead of separate frontend/backend upstreams

What stays the same:

- `/config` volume
- `/data` volume
- Frigate integration
- MQTT integration
- GPU passthrough expectations
- application URLs and API paths

## Before You Start

1. Back up your current compose file.
2. Keep your existing `/config` and `/data` volumes unchanged.
3. Be ready to update your reverse proxy from:
   - `yawamf-frontend:80` and `yawamf-backend:8000`
   to:
   - `yawamf-monalithic:8080`

## Compose Shape

The monolithic image uses:

- image: `ghcr.io/jellman86/yawamf-monalithic:latest`
- one service: `yawamf`
- one exposed port: `9852:8080`

Example:

```yaml
services:
  yawamf:
    image: ghcr.io/jellman86/yawamf-monalithic:latest
    container_name: yawamf-monalithic
    restart: unless-stopped
    user: "${PUID:-1000}:${PGID:-1000}"
    ports:
      - "9852:8080"
    volumes:
      - ./config:/config
      - ./data:/data
    environment:
      - TZ=Europe/London
      - FRIGATE__FRIGATE_URL=http://frigate:5000
      - FRIGATE__MQTT_SERVER=mosquitto
      - FRIGATE__MQTT_PORT=1883
    devices:
      - /dev/dri:/dev/dri
```

## Reverse Proxy Update

If you currently proxy the split deployment, update your reverse proxy to a single upstream:

- old:
  - `/` -> `yawamf-frontend:80`
  - `/api/*` -> `yawamf-backend:8000`
- new:
  - all YA-WAMF traffic -> `yawamf-monalithic:8080`

See [Reverse Proxy Guide](reverse-proxy.md) for the full proxy examples and SSE/video requirements.

## Migration Steps

1. Stop the old YA-WAMF stack.
2. Keep the same `/config` and `/data` mounts.
3. Replace the split services with the monolithic service in your compose stack.
4. Update your reverse proxy upstream(s) to the monolith container.
5. Start the new stack.
6. Verify:
   - the dashboard loads
   - `/api/version` responds
   - live status works
   - recent clips still play
   - GPU/OpenVINO or CUDA still shows up if you use acceleration

## Rollback

Rollback should be straightforward because the monolith keeps the same persistent volumes.

To roll back:

1. Stop the monolith container.
2. Restore the old split compose file.
3. Point your reverse proxy back to the split frontend/backend upstreams.
4. Start the old stack again.

## Current Status

As of `v2.9.2+`:

- The monolithic container (`yawamf-monalithic`) is the **recommended deployment** for new installs and migrations.
- The split deployment (`wamf-backend` + `wamf-frontend`) remains functional but receives no new development effort.
- Use `:latest` or a pinned `:vX.Y.Z` tag for stable installs. The `:dev` tag tracks the development branch and may be unstable.
