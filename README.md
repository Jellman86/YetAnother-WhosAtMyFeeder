# Yet Another WhosAtMyFeeder (YA-WAMF)

A bird classification system that integrates with [Frigate NVR](https://frigate.video/) to automatically identify birds visiting your feeder using advanced AI models.

![YA-WAMF Dashboard](dashboard-preview.png)

> If you share your guest dashboard publicly, I would love to see it. Please open an issue or discussion and drop a link so I can take a look.

## Features at a Glance

- **Advanced AI Classification** - MobileNetV2, ConvNeXt, or EVA-02 models (up to 91% accuracy)
- **Multi-Sensor Verification** - Correlates visual detections with BirdNET-Go audio
- **Smart Notifications** - Discord, Telegram, Pushover, Email with customizable filters + Notification Center
- **Video Analysis** - Automatic scanning of 15+ frames (temporal ensemble) for improved accuracy
- **LLM Insights** - AI-powered behavioral analysis (Gemini/OpenAI/Claude)
- **Leaderboard AI Insights** - Analyze detection charts for trends and weather correlations
- **Home Assistant Integration** - Sensors, automation, and dashboard cards
- **BirdWeather Reporting** - Contribute to community science
- **Real-time Dashboard** - Live updates, video playback, species statistics
- **Notification Center** - Pinned progress for long-running jobs and a full notifications view
- **Public View (Guest Mode)** - Share a read-only dashboard with rate limits and optional camera name hiding

## About This Project

A personal project built with AI-assisted coding, inspired by the original [WhosAtMyFeeder](https://github.com/mmcc-xx/WhosAtMyFeeder). When I noticed the original project wasn't being maintained, I saw an opportunity to learn and build something better.

Built with help from AI coding assistants as an experiment in what's possible with modern development tools. Feedback and contributions are welcome!

## Security

Please see the [Security Policy](SECURITY.md) for supported versions, reporting guidelines, and a summary of security features.

## Live Instance

A public instance of YA-WAMF is available here (*always on dev branch, may be broken!*):

- **https://yetanotherwhosatmyfeeder.pownet.uk**

## What It Does

When Frigate detects a bird at your feeder, YA-WAMF:
1. Captures the snapshot and classifies it with local AI (or trusted Frigate sublabels).
2. Optionally correlates with BirdNET-Go audio detections.
3. Stores the detection, pushes notifications, and updates the live UI.
4. Optionally performs deeper clip analysis (15+ frames) for better accuracy.
5. Adds optional enrichments like weather, BirdWeather reporting, and AI naturalist insights.

Detailed feature behavior, edge cases, and integration notes are documented in the links below.

## Documentation

Use the full docs hub for setup, integrations, and troubleshooting:
- [📚 Full Documentation Suite](docs/index.md)
- [🚀 Getting Started](docs/setup/getting-started.md)
- [📦 Full Docker Stack Example](docs/setup/docker-stack.md)
- [📷 Recommended Frigate Config](docs/setup/frigate-config.md)
- [🌐 Reverse Proxy Guide](docs/setup/reverse-proxy.md)
- [🔌 API Reference](docs/api.md)
- [🔗 BirdNET-Go Integration](docs/integrations/birdnet-go.md)
- [🏠 Home Assistant Setup](docs/integrations/home-assistant.md)
- [🧠 AI Models & Performance](docs/features/ai-models.md)
- [🛠 Troubleshooting Guide](docs/troubleshooting/diagnostics.md)
- [🧪 Known Issues / Testing Gaps](ISSUES.md)
- [✅ Integration Testing Requests](INTEGRATION_TESTING.md)

## How It Works

Here's the flow from bird to identification:

```
┌─────────────┐     MQTT Event      ┌─────────────┐
│   Frigate   │ ─────────────────>  │  YA-WAMF    │
│   (NVR)     │   "bird detected"   │  Backend    │
└─────────────┘                     └──────┬──────┘
                                           │
                                           v
                                    ┌──────────────┐
                                    │ Fast Path:   │
                                    │ Use Frigate  │
                                    │ Sublabels?   │
                                    └──────┬───────┘
                                           │
                                     (No)  v  (Yes)
                                    ┌──────────────┐
                                    │  AI Engine   │
                                    │ (TFLite/ONNX)│
                                    └──────┬───────┘
                                           │
                                           v
                                    ┌──────────────┐
                                    │ Save to DB & │
                                    │ Notify User  │
                                    └──────┬───────┘
                                           │
                                           v
                                    ┌──────────────┐
                                    │ Auto Video   │
                                    │ Analysis     │
                                    │ (Background) │
                                    └──────────────┘
```

For the full event lifecycle and architecture details, see the documentation links above.

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Frigate NVR running with MQTT enabled
- MQTT broker accessible (typically Mosquitto running alongside Frigate)
- Basic knowledge of Docker networking

### Installation

**1. Download configuration files:**

```bash
mkdir ya-wamf && cd ya-wamf
curl -O https://raw.githubusercontent.com/Jellman86/YetAnother-WhosAtMyFeeder/main/docker-compose.yml
curl -O https://raw.githubusercontent.com/Jellman86/YetAnother-WhosAtMyFeeder/main/.env.example
cp .env.example .env
```

**2. Configure your environment:**

Edit `.env` with your settings:

```env
# Docker network (check with: docker network ls)
DOCKER_NETWORK=frigate

# Frigate instance
FRIGATE_URL=http://frigate:5000

# MQTT broker (usually 'mosquitto' if running in Docker)
MQTT_SERVER=mosquitto
MQTT_PORT=1883

# MQTT authentication (if required)
MQTT_AUTH=true
MQTT_USERNAME=mqtt_user
MQTT_PASSWORD=secret_password

# Timezone
TZ=Europe/London
```

**3. Verify Docker network:**

Ensure the network specified in `.env` exists and matches your Frigate setup:

```bash
docker network ls
```

**4. Set permissions, create directories, and start:**

```bash
PUID=$(id -u)
PGID=$(id -g)
echo "PUID=$PUID" >> .env
echo "PGID=$PGID" >> .env
mkdir -p config data/models
sudo chown -R "$PUID:$PGID" config data
sudo chmod -R u+rwX,g+rwX config data
docker compose up -d
```

If you use Portainer stacks, set the same `PUID`/`PGID` values in stack environment variables.

> If you deploy via Portainer: create a Stack from `docker-compose.yml` and use "Pull and redeploy" for updates (after changing image tags or pulling the latest `:latest`/`:dev`).

**5. Access the dashboard:**

Open `http://localhost:9852` (or `http://YOUR_SERVER_IP:9852`)

**6. Download the AI model:**

In the web UI, go to **Settings** and click the model download button. The model is saved to `data/models/` and persists across updates.

### Public View (Guest Mode) at a Glance

Guest mode is read-only and rate-limited. Guests can view detections and any existing AI Naturalist analysis, but cannot change settings, delete items, or run new AI analysis. You can hide camera names and limit the public history window in **Settings > Security**.

### Verification

Check logs to confirm everything is working:

```bash
docker compose ps                    # Check container status
docker compose logs yawamf-backend -f  # Follow backend logs

# You should see:
# MQTT config: auth=True port=1883 server=mosquitto
# Connected to MQTT topic=frigate/events
```

### Troubleshooting

| Issue | Solution |
|-------|----------|
| **MQTT connection failed** | Verify `DOCKER_NETWORK` matches Frigate's network<br>Check MQTT hostname and credentials |
| **Frontend not loading** | Run `docker compose ps` to check health<br>View logs: `docker compose logs yawamf-frontend` |
| **No detections** | Confirm Frigate is detecting birds<br>Check backend logs for events<br>Verify model was downloaded in Settings |

For detailed troubleshooting, see the [**Troubleshooting Guide**](docs/troubleshooting/diagnostics.md).

## Configuration

All settings are managed through the web UI under **Settings**. Configuration is persisted to `config/config.json`.

### Key Settings

| Setting | Description | Default |
|---------|-------------|---------|
| **Frigate URL** | Frigate instance for fetching media | `http://frigate:5000` |
| **MQTT Server** | MQTT broker hostname | `mqtt` |
| **Classification Threshold** | Minimum confidence for detections (0-1) | `0.7` |
| **Min Confidence Floor** | Reject detections below this score | `0.4` |
| **Trust Frigate Sublabels** | Use Frigate's labels instead of local AI | `Enabled` |
| **Auto Video Analysis** | Analyze full video clips for accuracy | `Disabled` |
| **AI Model** | MobileNet (Fast), ConvNeXt (High), EVA-02 (Elite) | `MobileNet` |
| **BirdWeather Token** | Upload detections to BirdWeather | _(none)_ |
| **BirdNET-Go Topic** | MQTT topic for audio detections | `birdnet/text` |

## Security & Authentication

### 🔐 Built-in Authentication
- **Setup Wizard:** On first run, you'll be prompted to set an admin username and password.
- **Guest Mode:** Optionally enable a "Public View" to share your bird detections with friends (read-only) while keeping settings and admin tools secure.
- **Security:** Includes login rate limiting, session management, and security headers.

👉 **[Read the Full Authentication & Access Control Guide](docs/features/authentication.md)**

### 🔑 Legacy API Key (Deprecated)
If you are upgrading from an older version using `YA_WAMF_API_KEY`, your setup will continue to work, but this method is deprecated and will be removed in a future release.

For detailed upgrade instructions, see the [Migration Guide](MIGRATION.md).

## Tech Stack

- **Backend:** Python 3.12, FastAPI, SQLite
- **Frontend:** Svelte 5, Tailwind CSS
- **ML Engine:** ONNX Runtime & TensorFlow Lite
- **Messaging:** MQTT for Frigate events, SSE for live UI updates

## Video Playback & Bandwidth

YA-WAMF includes a robust video proxy that streams clips directly from Frigate. This supports:
- **Instant Playback:** Starts playing immediately without waiting for the whole file.
- **Seeking:** You can jump to any part of the video (scrubbing) thanks to HTTP Range support.
- **Bandwidth Control:** If you are on a metered connection or want to reduce load, you can disable "Fetch Video Clips" in the Settings. This prevents the backend from fetching heavy video files.

## Home Assistant Integration

YA-WAMF includes a custom component for Home Assistant to bring your bird sightings into your smart home.

**Features:**
- **Last Bird Detected Sensor:** Shows the name of the most recent visitor with all metadata (score, camera, weather) as attributes.
- **Daily Count Sensor:** Keeps track of how many birds have visited today.
- **Camera Entity:** (Optional) Proxy for the latest bird snapshot.

**Setup:**
1. Copy the `custom_components/yawamf` folder to your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. If the integration icon doesn't appear right away, hard-refresh Home Assistant or clear the browser cache (icons are cached).
4. Add the integration via **Settings > Devices & Services > Add Integration**.
5. Enter your YA-WAMF backend URL (e.g., `http://192.168.1.50:9852`).

## Help Improve YA-WAMF

This project is actively developed and your feedback is valuable!

**How to contribute:**
- **Report bugs** - [Open an issue](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/issues) for bugs or feature requests
- **Share feedback** - Let me know what works and what doesn't
- **Enable telemetry** - Turn on anonymous usage stats in **Settings > Connections** (see [Telemetry Spec](docs/TELEMETRY_SPEC.md))
- **Test features** - Try video analysis, notifications, and integrations in your environment

## Contributing

Feel free to open PRs if you have improvements to share. Just keep in mind this is a hobby project maintained in spare time.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Thanks To

- The original [WhosAtMyFeeder](https://github.com/mmcc-xx/WhosAtMyFeeder) project for the idea
- [Frigate](https://frigate.video/) for being such a great NVR
- [BirdNET-Go](https://github.com/tbeceele/birdnet-go) for the excellent audio classification integration
- **Ben Jordan** on YouTube for his inspiring [bird detection video](https://youtu.be/hCQCP-5g5bo?si=r__2KjXi6KPGM5FF)
- The AI assistants that helped build this thing
