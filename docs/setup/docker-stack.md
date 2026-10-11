# Full Docker Stack Example

This page shows the **monolithic deployment** (recommended) followed by the **legacy split deployment** for reference. For the monolithic image, use [`docker-compose.monolith.yml`](../../docker-compose.monolith.yml) and point your reverse proxy at `yawamf-monalithic:8080`.

## Monolithic quick example

```yaml
services:
  yawamf:
    image: ghcr.io/jellman86/yawamf-monalithic:latest
    container_name: yawamf-monalithic
    restart: unless-stopped
    user: "${PUID:-1000}:${PGID:-1000}"
    networks:
      - bird_network
    volumes:
      - ./config:/config
      - ./data:/data
    ports:
      - "9852:8080"
    environment:
      - TZ=Europe/London
      - FRIGATE__FRIGATE_URL=http://frigate:5000
      - FRIGATE__MQTT_SERVER=mosquitto
      - FRIGATE__MQTT_PORT=1883

networks:
  bird_network:
    name: bird_network
    external: true
```

This example joins an existing `bird_network`; use the actual network shared by
your Frigate and broker, or use their reachable LAN addresses instead. Configure
MQTT credentials in YA-WAMF when your broker requires them.

The unsuffixed `latest` tag is the full compatibility image. To avoid pulling
unused accelerator runtimes, change only the suffix: `latest-cpu` for CPU-only,
`latest-intel` for OpenVINO CPU/GPU/NPU, or `latest-cuda` for NVIDIA CUDA. Every
variant keeps ONNX CPU fallback and the same `/config` and `/data` volumes. See
[Hardware Acceleration](hardware-acceleration.md) before selecting a variant.

## Legacy Split Example

> [!WARNING]
> The split deployment (`wamf-backend` + `wamf-frontend`) is a **legacy path** kept for existing installs. New installs should use the monolithic example above. See the [Split-to-Monolith Migration](migrate-split-to-monolith.md) guide.

The example below shows the legacy two-container layout for reference.

## Example `docker-compose.yml` (legacy split)

```yaml
services:
  # --- The Core: Bird Identification ---
  yawamf-backend:
    image: ghcr.io/jellman86/wamf-backend:latest
    container_name: yawamf-backend
    restart: unless-stopped
    user: "${PUID:-1000}:${PGID:-1000}"
    networks:
      - bird_network
    volumes:
      - ./config:/config        # Settings, credentials and default retained media
      - ./data:/data            # Stores database and AI models
    # Optional Intel iGPU (OpenVINO) pass-through for ONNX models:
    # devices:
    #   - /dev/dri:/dev/dri
    # group_add:
    #   # Use host /dev/dri numeric group IDs (check with: ls -ln /dev/dri)
    #   - "44"   # example: card0 / video
    #   - "107"  # example: renderD128 / render
    environment:
      - TZ=Europe/London
      - FRIGATE__FRIGATE_URL=http://frigate:5000
      - FRIGATE__MQTT_SERVER=mosquitto
      - FRIGATE__MQTT_PORT=1883
    depends_on:
      - mosquitto
      - frigate

  yawamf-frontend:
    image: ghcr.io/jellman86/wamf-frontend:latest
    container_name: yawamf-frontend
    restart: unless-stopped
    user: "${PUID:-1000}:${PGID:-1000}"
    networks:
      - bird_network
    ports:
      - "9852:80"
    depends_on:
      - yawamf-backend

  # --- The Eyes: Frigate NVR ---
  frigate:
    image: ghcr.io/blakeblackshear/frigate:stable
    container_name: frigate
    # Add only the device access your Frigate detector/decoder requires.
    restart: unless-stopped
    networks:
      - bird_network
    volumes:
      - /etc/localtime:/etc/localtime:ro
      - ./frigate/config:/config
      - ./frigate/storage:/media/frigate
      - type: tmpfs # Optional: improves performance
        target: /tmp/cache
        tmpfs:
          size: 1000000000
    ports:
      - "5000:5000"
      - "8554:8554" # RTSP feeds
    environment:
      - TZ=Europe/London

  # --- The Voice: MQTT Broker ---
  mosquitto:
    image: eclipse-mosquitto:latest
    container_name: mosquitto
    restart: unless-stopped
    networks:
      - bird_network
    environment:
      - TZ=Europe/London
    volumes:
      - ./mosquitto/config:/mosquitto/config
      - ./mosquitto/data:/mosquitto/data
      - ./mosquitto/log:/mosquitto/log
    ports:
      - "1883:1883"

networks:
  bird_network:
    name: bird_network
```

BirdNET-Go is optional and has its own deployment, audio-source and MQTT
configuration. Install it using its maintained upstream instructions, then follow
[the YA-WAMF integration guide](../integrations/birdnet-go.md). Do not assume
YA-WAMF's environment-variable names configure another application's container.

## Key Configuration Steps

### 1. Networking
Notice that all containers share the same `bird_network`. This allows the monolithic `yawamf-monalithic` service (or `yawamf-backend` in the legacy split example) to talk to `frigate` using just the name `http://frigate:5000` instead of complex IP addresses.

### 2. MQTT Setup
YA-WAMF listens to the events that Frigate publishes. Ensure your `frigate/config.yml` has the following:
```yaml
mqtt:
  host: mosquitto # Matches the service name in docker-compose
  topic_prefix: frigate
```

### 3. Storage
Ensure your host machine has enough space. 
- **YA-WAMF data:** allow for model downloads, staging/compile caches and retained media.
  The experimental BioCLIP model alone downloads about 2.4 GiB; installing every
  October addition needs about 4.9 GiB before staging and other storage.
  Set explicit [media limits](configuration.md#data) for a busy feeder.
- **Frigate storage:** Depends on your recording settings (usually 100GB+ recommended).

### 4. Optional GPU Acceleration (YA-WAMF ONNX models)

YA-WAMF can accelerate its ONNX classifier models with:

- **NVIDIA CUDA** (ONNX Runtime CUDA)
- **Intel OpenVINO** (Intel CPU, GPU, or NPU)

Recommended flow:

1. Start with `Auto` under **Settings → Detection → Inference Provider**.
2. Check **Image**, **Packaged**, **Selected**, and **Active** under
   **Runtime diagnostics**.
3. If fallback occurs, use the diagnostics shown in the UI and backend logs before forcing a provider.

For Intel iGPU specifically:

- `/dev/dri` must be mounted into the backend container
- `group_add` must match your host's actual `/dev/dri` device GIDs
- If OpenVINO imports but only shows `CPU`, the UI diagnostics now show the GPU plugin error (for example missing OpenCL runtime or driver/userspace mismatch)

## 🖥 Hardware Requirements

YA-WAMF currently has the most validation on x86_64 environments.  
A dedicated Raspberry Pi ARM64 CPU image is published as a best-effort target. CI runs
MobileNet inference under emulation; the maintainer has not validated physical Pi hardware.
See [Raspberry Pi setup](raspberry-pi.md).

Model memory estimates are working sets, not whole-container limits. In the default
subprocess mode one live and one background worker can each hold a model copy.
Leave room for the app, operating system, Frigate and concurrent media jobs.
Choose one classifier to start; you do not need every model installed. See
[AI Models & Performance](../features/ai-models.md) and the
[October catalogue](../features/model-catalogue-2026-10.md) for model-specific limits.

## 🔄 Updating YA-WAMF

To update to the latest version, run the following commands in your `ya-wamf` directory:

```bash
# Monolithic deployment (recommended):
docker compose -f docker-compose.monolith.yml pull
docker compose -f docker-compose.monolith.yml up -d

# Legacy split deployment:
# docker compose pull
# docker compose up -d
```

Back up `/config` and `/data` consistently before updating. Settings and history are stored in the
persistent volumes rather than the image. Keep those mount paths unchanged if
you also switch image flavor while updating.
