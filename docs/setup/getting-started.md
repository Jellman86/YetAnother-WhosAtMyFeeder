# Getting Started

This guide will walk you through the basic installation of YA-WAMF using Docker Compose.

## Prerequisites
- **Docker & Docker Compose** installed on your host.
- **Frigate NVR** already running and accessible.
- **MQTT Broker** (e.g., Mosquitto) configured and connected to Frigate.
- **Optional GPU acceleration (ONNX models):**
  - **NVIDIA CUDA:** NVIDIA driver on the host + NVIDIA Container Toolkit installed + GPU passed into the backend container (`gpus: all` or equivalent).
  - **Intel iGPU (OpenVINO):** `/dev/dri` passed into the backend container + correct `/dev/dri` numeric `group_add` values for your host.

## Quick Install

### 1. Download the core files
Create a directory for YA-WAMF and download the latest compose and example environment files:

```bash
mkdir ya-wamf && cd ya-wamf
curl -O https://raw.githubusercontent.com/Jellman86/YetAnother-WhosAtMyFeeder/main/docker-compose.yml
curl -O https://raw.githubusercontent.com/Jellman86/YetAnother-WhosAtMyFeeder/main/.env.example
```

> Note: If you want to run the bleeding-edge `:dev` images, download `docker-compose.dev.yml` and use:
> `docker compose -f docker-compose.dev.yml up -d`. For production/stability, prefer `docker-compose.prod.yml` or pin a version tag.

### 2. Configure Environment
Copy the example environment file and edit it with your details:

```bash
cp .env.example .env
nano .env
```

**Key variables to set:**
- `DOCKER_NETWORK`: The name of the Docker network Frigate is using.
- `FRIGATE_URL`: The full URL to your Frigate instance (e.g., `http://192.168.1.10:5000`).
- `MQTT_SERVER`: Your broker's hostname or IP.
- `PUID` & `PGID`: Your host user's UID and GID (run `id` to find them). This ensures the container has permission to write to your `config/` and `data/` folders.

### 2.1 Non-root permissions (required) 🔐
YA-WAMF runs as non-root. If host directory ownership is wrong, startup fails or data/model writes fail.

Use these exact commands from your stack directory:

```bash
mkdir -p config data
PUID=$(id -u)
PGID=$(id -g)
echo "PUID=$PUID"
echo "PGID=$PGID"
sudo chown -R "$PUID:$PGID" config data
sudo chmod -R u+rwX,g+rwX config data
```

Put these values in `.env`:

```env
PUID=1000
PGID=1000
```

Compose/Portainer stack values should match:

```yaml
services:
  backend:
    user: "${PUID}:${PGID}"
    environment:
      - PUID=${PUID}
      - PGID=${PGID}
    volumes:
      - ./config:/config
      - ./data:/data
```

Quick verify:

```bash
docker compose exec yawamf-backend sh -lc 'id && ls -ld /config /data && touch /data/.perm_test && rm -f /data/.perm_test'
```

If this fails with `Permission denied`, re-run `chown` on the host path that is actually mounted in your stack.

### 3. Launch
Start the containers in detached mode:

```bash
docker compose up -d
```

### 3.1 (Optional) Enable GPU acceleration for ONNX models

If you want ConvNeXt/EVA-02 acceleration:

- **Intel iGPU (OpenVINO):**
  - Mount `/dev/dri` into `yawamf-backend`
  - Add `group_add` entries for the host's `/dev/dri` GIDs (check with `ls -ln /dev/dri`)
- **NVIDIA CUDA:**
  - Install/configure the NVIDIA Container Toolkit on the host
  - Pass through the NVIDIA GPU to `yawamf-backend` (`gpus: all` in Compose, or your platform's NVIDIA runtime equivalent)
  - Optional quick check after startup:
    ```bash
    docker compose exec yawamf-backend python -c "import onnxruntime as ort; print(ort.get_available_providers())"
    ```
    You should see `CUDAExecutionProvider` in the list when the CUDA-capable runtime is available in the container.

After startup, go to **Settings > Detection** and check the provider diagnostics:

- `OpenVINO` / `CUDA` availability badges
- `Selected provider` vs `Active provider`
- `Fallback reason` (if acceleration is unavailable and YA-WAMF fell back)

See [AI Models & Performance](../features/ai-models.md) for provider behavior and [Diagnostics & Logs](../troubleshooting/diagnostics.md) for troubleshooting steps.

**Portainer Stacks (common deployment):**
- Create a new Stack from the `docker-compose.yml` (and your `.env`).
- To update later: use "Pull and redeploy" (or redeploy the stack) after bumping image tags (`:latest`, `:dev`, or a pinned `:vX.Y.Z` tag).

### 4. Verify
Open your browser to `http://<your-ip>:9852`. You should see the dashboard! Once detections start flowing, they will appear in the Events list:

![Events List](../images/frontend_events.png)

### 5. (Optional) Enable Guest Mode
If you want to share a read‑only public view:

1. Go to **Settings > Security** and set a password.
2. Enable **Public Access**.
3. Configure rate limits and whether camera names are visible.

See [Authentication & Access](../features/authentication.md) for the full guest mode checklist and proxy guidance.

## 🌍 The Importance of Timezone (`TZ`)
Setting your correct local timezone is **critical** for YA-WAMF to function correctly. Ensure `TZ` is set in your `.env` (e.g., `TZ=Europe/London`).

If the timezone is incorrect:
- **Audio correlation will fail:** Visual events from Frigate and Audio events from BirdNET won't align, and birds won't be "Verified".
- **Histogram will be wrong:** The dashboard Activity Pulse will show birds at the wrong hours.
- **Cleanup issues:** The system may prematurely delete recent audio detections.

> 💡 **Tip:** Ensure the same `TZ` value is used for **all** containers in your stack (Frigate, MQTT, BirdNET, and YA-WAMF).

## Data Persistence
YA-WAMF uses two volumes for data:
- `/config`: Stores `config.json` (your settings).
- `/data`: Stores the SQLite database and downloaded ML models.

Ensure these are mapped to persistent storage in your `docker-compose.yml` to avoid data loss during updates.

> 🔒 **Permissions Note:** From v2.5.0+, containers run as non-root. Always set `PUID`/`PGID` and fix host ownership before first boot. See [MIGRATION.md](../../MIGRATION.md) for background context.
