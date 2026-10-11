# Telemetry Service Specification

## Overview
YA-WAMF includes an optional telemetry service to collect anonymous usage statistics. **Telemetry is disabled by default** and requires explicit opt-in.

## Why Telemetry?
As a solo developer working on this project, telemetry helps me understand if YA-WAMF is solving real problems for the broader bird enthusiast community, or if I'm primarily building for my own use case. Knowing that others find value in this work helps validate the time investment and guides development priorities - it's encouraging to know you're not building in isolation.

Additionally, the data helps to:
- Identify popular hardware platforms to prioritize optimization
- Understand which AI models are most commonly used
- Monitor version adoption rates to ensure users are on stable builds

## Data Collection Policy

### What is Collected?
The heartbeat payload is strictly limited to metadata about the installation and environment:
- **Installation ID**: A random UUID generated once per installation. It is not linked to any personal identity.
- **Application Version**: The current version/build of YA-WAMF.
- **Platform Metadata**: Operating system type, release version, and machine architecture (e.g., Linux x86_64).
- **Configuration Flags**: Enabled LLM and integration features, event-clip retention, and automatic video classification. Photograph retention is always enabled.
- **Runtime and Hardware**: Configured versus active inference provider, backend, worker mode, coarse device availability, compile result, and degraded recovery state.
- **Deployment**: Packaged image family, architecture, branch and Git identity. These do not include local hostnames or paths.
- **Feature Usage**: Which integrations (eBird, iNaturalist), notification channels (Discord, Email, etc.), and enrichment modes are active.
- **Access Settings**: Whether authentication or public access is enabled (boolean flags only).
- **Geography**: The approximate country derived from the Cloudflare request header (the IP address itself is **not** stored in the database).

### What is NOT Collected?
- **No Private Data**: No audio recordings, video clips, or snapshots are ever sent.
- **No User Content**: No bird detection transcripts, species names, or scientific data are collected.
- **No PII**: No names, email addresses, IP addresses, usernames, tokens, or precise locations are stored.

## Technical Details

### Endpoint
- **URL**: `https://yawamf-telemetry.ya-wamf.workers.dev/heartbeat`
- **Frequency**: Once every 24 hours while the application is running.

### Heartbeat contract

The canonical builder is `build_runtime_telemetry_payload` in
[`telemetry_service.py`](../backend/app/services/telemetry_service.py). Settings shows a preview
of that payload rather than a separately maintained approximation.

| Group | Content |
|---|---|
| `installation_id`, `timestamp`, `version` | Random installation identity, heartbeat time, running application version. |
| `platform` | Operating system, release and machine architecture. |
| `configuration` | Model ID, LLM enable/provider, always-true photograph-retention flag, event-clip copies and automatic video setting. |
| `runtime` | Model runtime, configured/active provider, active backend, execution mode, crop tier, inference-health counts and latest recovery status/reason. |
| `hardware` | CUDA/OpenVINO availability, coarse NVIDIA/Intel GPU/NPU availability, OpenVINO compile result/device and fallback state. |
| `deployment` | Deployment mode, image family, architecture, branch and Git hash. |
| `integrations`, `notifications`, `enrichment`, `access` | Enabled features and configured source/mode flags, without credentials. |

These are coarse application facts. An active-provider value is not a species-accuracy result,
and an unavailable field must not be interpreted as proof of a failed device.

`configuration.media_cache_enabled` is always `true` from #622 on, when photographs and visit media
stopped being optional. It is still sent because earlier reports carry it, and a missing value would
count as off. A jump to every install reporting it is that change, not installs turning it on.

## User Control (Opt-In)
Telemetry is **disabled by default** and completely optional. Users who wish to help improve YA-WAMF can opt in at any time via the **Settings → Connection → Telemetry** toggle in the UI. You can also disable it at any time if you change your mind.

The opt-in banner can be dismissed. **Anonymous health diagnostics** is a separate, also opt-in report of sanitized warning/error groups. It does not upload raw support bundles, owner notes or media. See [Telemetry & Usage Metrics](features/telemetry.md) for the boundaries and public aggregate dashboard.

## Source Code & Transparency
I believe in full transparency regarding the data I collect. You can inspect exactly how the heartbeat is constructed and transmitted in the backend source code:

- **[Telemetry Service (Backend)](../backend/app/services/telemetry_service.py)**: This module handles the generation of the anonymous Installation ID, gathers the metadata defined above, and transmits the payload via HTTPS.
- **[Telemetry Worker (Receiver)](../apps/telemetry-worker/)**: The source code for the Cloudflare Worker that receives and stores the data is available in the repository.
