# YA-WAMF documentation

Start with [Getting Started](setup/getting-started.md). These guides follow current `dev`;
use the [stable release notes](https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/releases/latest)
for behavior shipped in a tagged image.

## Setup and maintenance

- [Getting Started](setup/getting-started.md) — install, connect and verify a first visit.
- [Raspberry Pi](setup/raspberry-pi.md) · [Unraid](setup/unraid.md) · [Full Docker stack](setup/docker-stack.md).
- [Frigate configuration](setup/frigate-config.md) · [MQTT broker](setup/mqtt-broker.md) · [Reverse proxy](setup/reverse-proxy.md).
- [Settings reference](setup/configuration.md) · [Environment variables](setup/environment-variables.md).
- [Hardware Acceleration](setup/hardware-acceleration.md) — image families, device passthrough and active providers.
- [Upgrade and rollback](../MIGRATION.md) · [Split-to-monolith migration](setup/migrate-split-to-monolith.md).

## Use your history

- [Explorer and review](features/explorer.md) — seen visits, heard calls, individual captures and corrections.
- [Add observation](features/manual-observations.md) — classify and save your own photograph or clip.
- [Video and photo analysis](features/video-analysis.md) — frame evidence and counted birds.
- [Favourites](features/favourites.md) — archives, retention and storage limits.
- [Notifications](features/notifications.md) — channels, filters and background jobs.
- [Taxonomy and naming](features/taxonomy.md) — species identity, names and leaderboard rankings.
- [Authentication and public access](features/authentication.md) — owner permissions and guest sharing.
- [Telemetry](features/telemetry.md) · [Privacy](../PRIVACY.md) — what stays local and what optional services receive.

## Choose and test models

- [AI Models & Performance](features/ai-models.md) — select and validate a classifier.
- [October model catalogue](features/model-catalogue-2026-10.md) — coverage, sizes and hardware limits.
- [Accuracy and benchmarks](features/model-accuracy.md) — measured results and their limits.
- [Model Evaluation](features/model-evaluation.md) — compatibility checks, results and temporary model changes.

## 🔗 Integrations

- [Frigate NVR](integrations/frigate.md) — camera events and media.
- [BirdNET-Go](integrations/birdnet-go.md) — audio history, source mapping and visual correlation.
- [BirdWeather](integrations/birdweather.md) — station reporting.
- [eBird](integrations/ebird.md) — nearby sightings and reviewed CSV export.
- [iNaturalist](integrations/inaturalist.md) — owner-reviewed submissions.
- [Home Assistant](integrations/home-assistant.md) — sensors, automations and sidebar access.

## Troubleshooting

- [Diagnostics & Logs](troubleshooting/diagnostics.md) — Health outcomes and fresh support bundles.
- [Frigate Event Not Found](troubleshooting/frigate-event-not-found.md) — missing or expired upstream media.
- [Slow interface](troubleshooting/slow-interface.md) — request and database pressure.
- [Safari playback](troubleshooting/safari-video-playback.md) — inspect clip compatibility.
- [Support](../SUPPORT.md) · [Known gaps](../ISSUES.md) · [Integration testing](../INTEGRATION_TESTING.md).

## Contribute and release

- [Contributing](../CONTRIBUTING.md) · [Development workflow](../DEVELOPMENT.md) · [Architecture](../DEVELOPER.md).
- [API reference](api.md) · [Regression testing](development/testing.md) · [Model conversion](conversions/birder-model-conversion.md).
- [Engineering contract](../CLAUDE.md) · [Code quality](standards/code-quality.md) · [UI/UX](standards/ui-ux.md).
- [Documentation standard](documentation-standard.md) · [Screenshot capture](images/README.md).
- [Writing a release](development/releasing.md) · [v2.22.0 notes](releases/v2.22.0.md) · [Contributors](../CONTRIBUTORS.md).
- [Release archive](releases/) · [Dated reviews](reviews/) · [Roadmap](../ROADMAP.md).
