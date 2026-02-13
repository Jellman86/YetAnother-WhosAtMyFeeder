# Full Docker Stack Example

This is a complete, "batteries-included" Docker Compose example. It includes everything you need to run a professional-grade bird identification station.

## Example `docker-compose.yml`

```yaml
version: '3.9'

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
      - ./config:/config        # Stores config.json
      - ./data:/data            # Stores database and AI models
    environment:
      - TZ=Europe/London
      - PUID=${PUID:-1000}
      - PGID=${PGID:-1000}
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
    privileged: true # Required for hardware acceleration
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
      - TZ=Europe/London # Ensure this matches YA-WAMF
      - FRIGATE_MQTT_PASSWORD=password

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

  # --- The Ears: BirdNET-Go (Optional) ---
  birdnet-go:
    image: ghcr.io/tphacyj/birdnet-go:latest
    container_name: birdnet-go
    restart: unless-stopped
    networks:
      - bird_network
    environment:
      - TZ=Europe/London
      - MQTT_SERVER=mosquitto
      - MQTT_PORT=1883
      - RTSP_URL=rtsp://frigate:8554/birdcam # Point this to your camera feed

networks:
  bird_network:
    name: bird_network
```

## Key Configuration Steps

### 1. Networking
Notice that all containers share the same `bird_network`. This allows `yawamf-backend` to talk to `frigate` using just the name `http://frigate:5000` instead of complex IP addresses.

### 2. MQTT Setup
YA-WAMF listens to the events that Frigate publishes. Ensure your `frigate/config.yml` has the following:
```yaml
mqtt:
  host: mosquitto # Matches the service name in docker-compose
  topic_prefix: frigate
```

### 3. Storage
Ensure your host machine has enough space. 
- **YA-WAMF data:** ~2GB (mostly for large AI models).
- **Frigate storage:** Depends on your recording settings (usually 100GB+ recommended).

## 🖥 Hardware Requirements

YA-WAMF currently has the most validation on x86_64 environments.  
Raspberry Pi compatibility is being implemented as a **best-effort ARM64 target** and is not yet validated on physical Pi hardware in this project environment.

Model choice still strongly affects RAM/CPU requirements:

| Model Tier | CPU | RAM (Recommended) |
|------------|-----|-------------------|
| **Fast (MobileNet)** | Low | 512MB (baseline, may be higher in real deployments) |
| **High (ConvNeXt)** | Medium | 2GB |
| **Elite (EVA-02)** | High | 4GB+ |

> 💡 **Pro Tip:** For low-power or ARM devices (including trial Pi deployments), start with **MobileNet V2** and only enable heavier features after stability checks.

## 🔄 Updating YA-WAMF

To update to the latest version, run the following commands in your `ya-wamf` directory:

```bash
docker compose pull
docker compose up -d
```
Your settings and history will be preserved because they are stored in the persistent volumes (`/config` and `/data`).
