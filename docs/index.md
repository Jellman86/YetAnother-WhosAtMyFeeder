# YA-WAMF Documentation

Welcome to the documentation for **Yet Another WhosAtMyFeeder (YA-WAMF)**. This guide covers everything from basic setup to advanced AI tuning.

> 🦜 **New to YA-WAMF?** Start with the [Getting Started](setup/getting-started.md) guide to have your feeder online in minutes.
> 🔓 **Sharing your dashboard?** See [Authentication & Access](features/authentication.md) for guest mode, rate limits, and privacy controls.

---

## 🚀 Setup & Installation
Everything you need to get the containers running and configured correctly.
- **[🚀 Getting Started](setup/getting-started.md)** - Fast-track installation using Docker Compose.
- **[📦 Full Docker Stack](setup/docker-stack.md)** - A complete example including Frigate and MQTT.
- **[🔄 Split-to-Monolith Migration](setup/migrate-split-to-monolith.md)** - Transition guidance for existing two-container installs.
- **[📷 Recommended Frigate Config](setup/frigate-config.md)** - Optimized settings for bird snapshots.
- **[🌐 Reverse Proxy Guide](setup/reverse-proxy.md)** - Configs for Cloudflare Tunnel, Nginx, Caddy.
- **[⚙️ Configuration Guide](setup/configuration.md)** - Deep dive into all web UI settings.
- **[⚡ GPU Acceleration Setup & Diagnostics](troubleshooting/diagnostics.md)** - CUDA/OpenVINO requirements, provider badges, and troubleshooting.

## 🔌 API & Development
Build integrations and custom tools with YA-WAMF.
- **[🔌 API Reference](api.md)** - Complete REST API documentation with examples
- **OpenAPI/Swagger** - Interactive API docs. Accessible at `http://localhost:8000/docs` when running the backend directly. In the monolithic container the FastAPI process is internal — see the [API Reference](api.md) for access options. In the legacy split deployment the backend is exposed at `http://localhost:8946/docs`.

### Mobile Ready
YA-WAMF is fully responsive and works great on phones and tablets.

<div align="center">
  <img src="images/dashboard-mobile.png" width="300" alt="Mobile Dashboard" />
</div>

## 🔗 Integrations
Connect YA-WAMF to the rest of your smart home and community projects.
- **[📹 Frigate NVR](integrations/frigate.md)** - Connecting to your camera system.
- **[🎵 BirdNET-Go](integrations/birdnet-go.md)** - Multi-sensor audio correlation.
- **[🌦️ BirdWeather](integrations/birdweather.md)** - Uploading to community science stations.
- **[🦉 eBird](integrations/ebird.md)** - Nearby sightings, notable reports, and CSV export.
- **[🌿 iNaturalist](integrations/inaturalist.md)** - Owner-reviewed submissions to iNaturalist.
- **[🏠 Home Assistant](integrations/home-assistant.md)** - Sensors, cards, and automations.

## Feature Deep Dives

- [🔐 Authentication & Access](features/authentication.md) - Admin passwords, guest mode, and security
- [🛡️ Security Policy](../SECURITY.md) - Supported versions, reporting, and security overview
- [🧠 AI Models & Performance](features/ai-models.md) - Understanding the model tiers, plus CPU/CUDA/OpenVINO provider behavior
- [📊 Model Accuracy & Benchmarks](features/model-accuracy.md) - Benchmark results, GPU support matrix, and how to run accuracy tests
- [🎞 Deep Video Analysis](features/video-analysis.md) - Multi-frame clip analysis, sampling behavior, and UI feedback
- [🗂 Taxonomy & Naming](features/taxonomy.md) - How scientific naming works
- [🔔 Notifications](features/notifications.md) - Discord, Pushover, Telegram, Email + Notification Center
- [📊 Telemetry](features/telemetry.md) - Transparency on anonymous usage metrics

## Troubleshooting
Solving common issues and using diagnostic tools.
- **[🛠 Diagnostics & Logs](troubleshooting/diagnostics.md)** - Using MQTT tests and Backfill reports.
