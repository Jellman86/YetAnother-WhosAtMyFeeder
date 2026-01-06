# Getting Started

This guide will walk you through the basic installation of YA-WAMF using Docker Compose.

## Prerequisites
- **Docker & Docker Compose** installed on your host.
- **Frigate NVR** already running and accessible.
- **MQTT Broker** (e.g., Mosquitto) configured and connected to Frigate.

## Quick Install

### 1. Download the core files
Create a directory for YA-WAMF and download the latest compose and example environment files:

```bash
mkdir ya-wamf && cd ya-wamf
curl -O https://raw.githubusercontent.com/Jellman86/YetAnother-WhatAtMyFeeder/dev/docker-compose.yml
curl -O https://raw.githubusercontent.com/Jellman86/YetAnother-WhatAtMyFeeder/dev/.env.example
```

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

### 3. Launch
Start the containers in detached mode:

```bash
docker compose up -d
```

> 💡 **Need a full example?** If you haven't set up Frigate or an MQTT broker yet, check out our [Full Docker Stack Example](docker-stack.md).

### 4. Initial Setup
Once the dashboard is open, follow this checklist to get your first detection:

1.  **Select Cameras:** Go to **Settings > Connection** and select the Frigate cameras you want to monitor.
2.  **Download Model:** Go to **Settings > Detection** and click "Download" on the **MobileNet V2** model.
3.  **Set Timezone:** Ensure your `TZ` environment variable in `.env` matches your location for accurate sighting timestamps.
4.  **Wait for a bird!** Once a bird visits, check the dashboard. If nothing appears after a few minutes, check the [Diagnostics](..//troubleshooting/diagnostics.md) guide.

## Data Persistence
YA-WAMF uses two volumes for data:
- `/config`: Stores `config.json` (your settings).
- `/data`: Stores the SQLite database and downloaded ML models.

Ensure these are mapped to persistent storage in your `docker-compose.yml` to avoid data loss during updates.
